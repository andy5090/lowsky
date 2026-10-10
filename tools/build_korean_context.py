"""Build display geometry from the retained OSM snapshot; no live requests or dependencies."""

import gzip
import hashlib
import json
import math
from pathlib import Path
import re

PROJECT = Path(__file__).resolve().parents[1]
EXTENT = 10_000
RADIUS = 6_378_137
WIDTHS = {"motorway": 13, "trunk": 11, "primary": 9, "secondary": 8,
          "tertiary": 6, "residential": 5, "unclassified": 5, "service": 3.5,
          "living_street": 4, "track": 3, "cycleway": 2, "footway": 1.5, "path": 1.2}


def geo_to_local(lat, lon, origin):
    return [round(math.radians(lon - origin["lon"]) * RADIUS * math.cos(math.radians(origin["lat"])), 2),
            round(math.radians(origin["lat"] - lat) * RADIUS, 2)]


def number(value):
    match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*(m|ft)?\s*", str(value))
    if not match:
        return None
    return float(match[1]) * (0.3048 if match[2] == "ft" else 1)


def building_height(tags):
    height = number(tags.get("height"))
    if height is not None:
        return min(120, max(2.5, height)), "osm_height"
    levels = number(tags.get("building:levels"))
    if levels is not None:
        return min(120, max(3, levels * 3)), "osm_levels_assumed_3m"
    return (18 if tags.get("building") == "apartments" else 7.5), "visual_assumption"


def build(raw, origin):
    """Keep OSM way IDs/geometry; mapped coordinates never come from visual randomness."""
    roads, buildings = [], []
    for element in sorted(raw["elements"], key=lambda item: item["id"]):
        if element["type"] != "way":
            continue
        tags = element.get("tags", {})
        points = [geo_to_local(p["lat"], p["lon"], origin) for p in element.get("geometry", [])]
        if len(points) < 2:
            continue
        if not any(abs(x) <= EXTENT / 2 and abs(z) <= EXTENT / 2 for x, z in points):
            continue
        if "building" in tags and tags["building"] not in ("no", "construction", "ruins"):
            if len(points) < 4 or points[0] != points[-1]:
                continue
            if any(abs(x) > EXTENT / 2 or abs(z) > EXTENT / 2 for x, z in points):
                continue
            height, source = building_height(tags)
            buildings.append({"id": element["id"], "polygon": points[:-1], "height_m": height,
                              "height_source": source, "kind": tags["building"],
                              "roof_shape": tags.get("roof:shape", "flat")})
        kind = tags.get("highway", "")
        road_type = kind.removesuffix("_link")
        if road_type not in WIDTHS or tags.get("tunnel") in ("yes", "building_passage"):
            continue
        width = number(tags.get("width"))
        roads.append({"id": element["id"], "kind": kind,
                      "width_m": min(30, max(1, width)) if width is not None else WIDTHS[road_type],
                      "width_source": "osm_width" if width is not None else "visual_class_assumption",
                      "bridge": tags.get("bridge", "no") != "no", "points": points})
    return {"schema_version": "1.0", "origin": origin, "extent_m": EXTENT,
            "axes": "X east, Z south; meters", "roads": roads, "buildings": buildings,
            "osm_timestamp": raw.get("osm3s", {}).get("timestamp_osm_base"),
            "license": "ODbL-1.0", "attribution": "© OpenStreetMap contributors",
            "limitations": "Mapped footprints and centerlines only; absent objects are not invented. Untagged heights/widths and all materials are visual assumptions. Fictional site excluded by renderer."}


def main():
    root = PROJECT / "data/terrain"
    path = root / "sources/osm_context.json.gz"
    compressed = path.read_bytes()
    source = json.loads(gzip.decompress(compressed))
    origin = json.loads((PROJECT / "monitor/map_config.json").read_text())["site_origin"]
    terrain_origin = json.loads((root / "korea_site.json").read_text())["origin"]
    if origin != terrain_origin:
        raise ValueError("Map/DEM origin mismatch: regenerate all context together")
    document = build(source, origin)
    document["source_snapshot"] = "sources/osm_context.json.gz"
    document["source_sha256"] = hashlib.sha256(compressed).hexdigest()
    (root / "korea_context.json").write_text(json.dumps(document, ensure_ascii=False, separators=(",", ":")) + "\n")
    print(f"Context: {len(document['roads'])} roads, {len(document['buildings'])} mapped buildings")


if __name__ == "__main__":
    main()
