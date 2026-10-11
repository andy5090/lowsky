import json
import struct
import unittest
from tools.fetch_korean_terrain import PROJECT, SHA256, URL, local_to_geo, sample


class TerrainTests(unittest.TestCase):
    def test_hgt_row_orientation_and_bilinear_sample(self):
        raw = struct.pack('>hhhh',100,200,300,400)
        self.assertEqual(sample(raw,2,38,127),100)
        self.assertEqual(sample(raw,2,37,128),400)
        self.assertEqual(sample(raw,2,37.5,127.5),250)
        with self.assertRaises(ValueError): sample(struct.pack('>hhhh',-32768,0,0,0),2,37.5,127.5)
        with self.assertRaises(ValueError): sample(raw,2,39,127)

    def test_map_and_terrain_share_origin_and_scale(self):
        terrain=json.loads((PROJECT/'data/terrain/korea_site.json').read_text())
        config=json.loads((PROJECT/'monitor/map_config.json').read_text())
        self.assertEqual(terrain['origin'],config['site_origin'])
        self.assertEqual(terrain['spacing_m']*(terrain['grid_size']-1),terrain['extent_m'])
        self.assertEqual(len(terrain['heights_m']),201)
        self.assertTrue(all(len(row)==201 for row in terrain['heights_m']))
        self.assertEqual(terrain['heights_m'][100][100],terrain['reference_elevation_m'])
        self.assertLess(local_to_geo(0,1000,terrain['origin'])[0],terrain['origin']['lat'])
        self.assertGreater(local_to_geo(1000,0,terrain['origin'])[1],terrain['origin']['lon'])
        self.assertGreater(max(map(max,terrain['heights_m']))-min(map(min,terrain['heights_m'])),100)

    def test_northern_gyeonggi_source_is_pinned_and_departure_uses_the_mdl_reference(self):
        terrain=json.loads((PROJECT/'data/terrain/korea_site.json').read_text())
        config=json.loads((PROJECT/'monitor/map_config.json').read_text())
        placement=json.loads((PROJECT/'data/terrain/site_placement.json').read_text())
        self.assertEqual(terrain['origin'], {'lat':37.9,'lon':127.2})
        self.assertEqual(terrain['source_tile'], 'N37E127')
        self.assertEqual(terrain['source_sha256'], SHA256)
        self.assertEqual(terrain['source_url'], URL)
        self.assertIn('/N37/N37E127.hgt.gz', URL)
        self.assertEqual(len(SHA256), 64)
        self.assertEqual(placement['origin'], terrain['origin'])
        self.assertTrue(config['distant_departure']['georeferenced'])
        self.assertTrue(placement['distant_departure']['georeferenced'])
        self.assertEqual(config['distant_departure']['source'], 'data/geography/korean_mdl.json')
        self.assertNotIn('candidates', placement)
        self.assertEqual(config['terrain_extent_m'], 10000)

    def test_uniform_airspace_lift_clears_relief_without_modifying_dem(self):
        terrain=json.loads((PROJECT/'data/terrain/korea_site.json').read_text())
        peak=max(map(max, terrain['heights_m']))-terrain['reference_elevation_m']
        offset=terrain['display_airspace_offset_m']
        self.assertGreaterEqual(offset, peak)
        self.assertLess(offset-peak, 1)
        # Same global display offset for every aerial marker, not a sampled route.
        self.assertGreater(80+offset, peak)
        self.assertEqual(terrain['reference_elevation_m'],105.0)
        self.assertEqual(min(map(min, terrain['heights_m'])),79.13)
        self.assertEqual(max(map(max, terrain['heights_m'])),746.73)
