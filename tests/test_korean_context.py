import gzip
import hashlib
import json
import unittest
from tools.build_korean_context import PROJECT, build, building_height, geo_to_local, number
from tools.fetch_korean_context import validate_image
from tools.fetch_korean_terrain import local_to_geo


class KoreanContextTests(unittest.TestCase):
    def test_coordinate_round_trip_and_north_orientation(self):
        origin = {"lat": 36.23, "lon": 127.08}
        for x, z in [(0, 0), (5000, -5000), (-1250, 3145)]:
            lat, lon = local_to_geo(x, z, origin)
            self.assertEqual(geo_to_local(lat, lon, origin), [x, z])

    def test_height_provenance_and_units(self):
        self.assertEqual(building_height({"height": "10 m", "building:levels": "4"}), (10, "osm_height"))
        self.assertEqual(building_height({"building:levels": "4"}), (12, "osm_levels_assumed_3m"))
        self.assertEqual(building_height({"building": "house"}), (7.5, "visual_assumption"))
        self.assertAlmostEqual(number("10 ft"), 3.048)
        self.assertIsNone(number("unknown"))

    def test_data_matches_retained_snapshot_and_shared_origin(self):
        terrain = PROJECT / "data/terrain"
        document = json.loads((terrain / "korea_context.json").read_text())
        origin = json.loads((PROJECT / "monitor/map_config.json").read_text())["site_origin"]
        dem = json.loads((terrain / "korea_site.json").read_text())
        self.assertEqual(document["origin"], origin)
        self.assertEqual(document["origin"], dem["origin"])
        self.assertEqual(document["extent_m"], dem["extent_m"])
        source = (terrain / document.pop("source_snapshot")).read_bytes()
        self.assertEqual(document.pop("source_sha256"), hashlib.sha256(source).hexdigest())
        self.assertEqual(document, build(json.loads(gzip.decompress(source)), origin))
        self.assertGreater(len(document["roads"]), 2000)
        self.assertGreater(len(document["buildings"]), 200)
        self.assertEqual(len({b["id"] for b in document["buildings"]}), len(document["buildings"]))

    def test_pinned_rasters_are_aligned_and_licensed(self):
        manifest = json.loads((PROJECT / "data/terrain/context_provenance.json").read_text())
        origin = manifest["origin"]
        south, west, north, east = manifest["bbox_south_west_north_east"]
        self.assertEqual(geo_to_local(north, west, origin), [-5000, -5000])
        self.assertEqual(geo_to_local(south, east, origin), [5000, 5000])
        for entry in manifest["imagery"]:
            validate_image((PROJECT / entry["path"]).read_bytes(), entry)
            self.assertEqual(entry["license"], "CC-BY-4.0")
            self.assertEqual(entry["time"], "2021-01-01")
        entry = manifest["imagery"][0]
        with self.assertRaises(ValueError):
            validate_image(b"<xml>WMS error</xml>", entry)

    def test_unclosed_footprints_and_tunnels_are_not_rendered(self):
        origin = {"lat": 36.23, "lon": 127.08}
        points = [{"lat": 36.23, "lon": 127.08}, {"lat": 36.231, "lon": 127.081}]
        data = {"elements": [
            {"type": "way", "id": 1, "tags": {"building": "yes"}, "geometry": points},
            {"type": "way", "id": 2, "tags": {"highway": "primary", "tunnel": "yes"}, "geometry": points},
            {"type": "way", "id": 3, "tags": {"highway": "service"}, "geometry": points},
        ]}
        result = build(data, origin)
        self.assertEqual(result["buildings"], [])
        self.assertEqual([r["id"] for r in result["roads"]], [3])
