"""Verify pinned context assets, or restore missing WMS images (stdlib only).

The OSM snapshot is retained in the repository: querying today's OSM cannot
reproduce that snapshot. Upstream WMS changes fail the hash check deliberately.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import urllib.request

PROJECT = Path(__file__).resolve().parents[1]


def validate_image(data, entry):
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"Expected PNG: {entry['path']}")
    if struct.unpack(">II", data[16:24]) != (entry["width"], entry["height"]):
        raise ValueError(f"Unexpected image dimensions: {entry['path']}")
    if hashlib.sha256(data).hexdigest() != entry["sha256"]:
        raise ValueError(f"Source content changed: {entry['path']}; review before updating provenance")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download-missing", action="store_true")
    args = parser.parse_args()
    manifest = json.loads((PROJECT / "data/terrain/context_provenance.json").read_text())
    for entry in manifest["imagery"]:
        path = PROJECT / entry["path"]
        if not path.exists() and args.download_missing:
            request = urllib.request.Request(entry["url"], headers={"User-Agent": "LowSkyVisualContext/1.0"})
            with urllib.request.urlopen(request, timeout=120) as response:
                content = response.read()
            validate_image(content, entry)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        validate_image(path.read_bytes(), entry)
        print(f"Verified {entry['path']}")
    osm = manifest["osm"]
    if hashlib.sha256((PROJECT / osm["path"]).read_bytes()).hexdigest() != osm["sha256"]:
        raise ValueError("Retained OSM snapshot changed")
    print(f"Verified {osm['path']}")


if __name__ == "__main__":
    main()
