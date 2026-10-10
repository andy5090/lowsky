"""Download the selected visual assets, retaining their provenance and hashes."""

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1] / "godot" / "third_party" / "realistic"
USER_AGENT = "LowSkyAssetPreparation/0.1"
TEXTURES = ("hangar_concrete_floor", "aerial_grass_rock", "asphalt_02", "corrugated_iron")
SKY = "kloofendal_48d_partly_cloudy_puresky"


def get_json(url):
    with urlopen(Request(url, headers={"User-Agent": USER_AGENT}), timeout=45) as response:
        return json.load(response)


def download(entry):
    path = ROOT / entry["path"]
    if path.exists():
        data = path.read_bytes()
    else:
        with urlopen(Request(entry["download_url"], headers={"User-Agent": USER_AGENT}), timeout=60) as response:
            data = response.read(40_000_001)
        if len(data) > 40_000_000:
            raise ValueError("Unexpectedly large asset: " + entry["path"])
    if entry.get("source_md5") and hashlib.md5(data).hexdigest() != entry["source_md5"]:
        raise ValueError("Source checksum mismatch: " + entry["path"])
    digest = hashlib.sha256(data).hexdigest()
    if entry.get("sha256") and entry["sha256"] != digest:
        raise ValueError("Pinned checksum mismatch: " + entry["path"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    print("Ready:", entry["path"], len(data), flush=True)
    return {**entry, "sha256": digest, "bytes": len(data)}


def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    manifest_path = ROOT / "provenance.json"
    if manifest_path.exists():
        entries = json.loads(manifest_path.read_text())["files"]
    else:
        entries = []
        for asset in (*TEXTURES, SKY):
            metadata = get_json("https://api.polyhaven.com/files/" + asset)
            channels = (("hdri", "sky.hdr"),) if asset == SKY else (
                ("Diffuse", "albedo.jpg"), ("nor_gl", "normal.jpg"), ("arm", "arm.jpg"))
            for channel, filename in channels:
                source = metadata[channel]["2k"]["hdr" if channel == "hdri" else "jpg"]
                entries.append({
                    "path": asset + "/" + filename, "asset_id": asset,
                    "source_page": "https://polyhaven.com/a/" + asset,
                    "download_url": source["url"], "source_md5": source.get("md5"),
                    "license": "CC0-1.0", "license_url": "https://polyhaven.com/license",
                    "modifications": "Source file unchanged; runtime material scale and tint only",
                })
        for filename, source in (
            ("Cesium_Air.glb", "Apps/SampleData/models/CesiumAir/Cesium_Air.glb"),
            ("LICENSE.md", "LICENSE.md"),
        ):
            entries.append({
                "path": "cesium_air/" + filename, "asset_id": "cesium_air",
                "source_page": "https://github.com/CesiumGS/cesium/tree/main/Apps/SampleData/models/CesiumAir",
                "download_url": "https://raw.githubusercontent.com/CesiumGS/cesium/main/" + source,
                "license": "Apache-2.0", "license_url": "https://github.com/CesiumGS/cesium/blob/main/LICENSE.md",
                "credit": "Copyright CesiumJS Contributors",
                "modifications": "Source file unchanged; display scale and orientation only",
            })
    with ThreadPoolExecutor(max_workers=3) as pool:
        entries = list(pool.map(download, entries))
    manifest_path.write_text(json.dumps({
        "schema_version": "1.0", "purpose": "Visual samples for a fictional training scene",
        "poly_haven_api_terms": "https://github.com/Poly-Haven/Public-API/blob/master/ToS.md",
        "files": entries,
    }, indent=2) + "\n", encoding="utf-8")
    print("Verified", len(entries), "files; source pages, licenses and checksums recorded")


if __name__ == "__main__":
    main()
