"""Restore the pinned CesiumDrone source; verify its recorded SHA-256 before writing."""

import json

from fetch_realistic_assets import ROOT, download


def main():
    manifest = json.loads((ROOT / "cesium_drone/provenance.json").read_text())
    download({**manifest, "path": "cesium_drone/CesiumDrone.glb"})


if __name__ == "__main__":
    main()
