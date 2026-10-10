"""Fetch a pinned CC0 building sample for visual comparison, not base reconstruction."""

import argparse
import hashlib
import io
import json
from pathlib import Path
from urllib.request import urlopen
from zipfile import ZipFile


URL = "https://kenney.nl/media/pages/assets/city-kit-industrial/0ec35b139d-1788171848/kenney_city-kit-industrial_2.0.zip"
SHA256 = "5b381164e5760f3830a2dbee43b972deee38b2a695d091b56e238ab2910c96d2"
DEST = Path(__file__).resolve().parents[1] / "godot" / "third_party" / "kenney_industrial"
SELECTED = ("building-k.glb", "building-h.glb", "shipping-container-a.glb", "shipping-container-b.glb", "Textures/colormap.png")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, help="Use an already downloaded archive")
    args = parser.parse_args()
    if args.archive:
        data = args.archive.read_bytes()
    else:
        with urlopen(URL, timeout=60) as response:
            data = response.read(20_000_001)
    if hashlib.sha256(data).hexdigest() != SHA256:
        raise ValueError("Archive checksum mismatch; inspect the upstream change before updating")
    files = []
    with ZipFile(io.BytesIO(data)) as archive:
        for name in (*SELECTED, "License.txt"):
            source = name if name == "License.txt" else "Models/GLB format/" + name
            contents = archive.read(source)
            destination = DEST / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(contents)
            files.append({"path": name, "sha256": hashlib.sha256(contents).hexdigest()})
    provenance = {
        "name": "Kenney City Kit Industrial", "version": "2.0", "author": "Kenney",
        "source_page": "https://kenney.nl/assets/city-kit-industrial",
        "download_url": URL, "archive_sha256": SHA256, "license": "CC0-1.0",
        "license_url": "https://creativecommons.org/publicdomain/zero/1.0/",
        "purpose": "Candidate modular buildings; not models of a specific airbase",
        "modifications": "None to source files; runtime uniform scale and pivot normalization only",
        "files": files,
    }
    (DEST / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
    print(f"Extracted 4 GLB models, palette texture and original license to {DEST}")


if __name__ == "__main__":
    main()
