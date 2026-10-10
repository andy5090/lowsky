import json
import struct
import unittest
from tools.fetch_korean_terrain import PROJECT, local_to_geo, sample


class TerrainTests(unittest.TestCase):
    def test_hgt_row_orientation_and_bilinear_sample(self):
        raw = struct.pack('>hhhh',100,200,300,400)
        self.assertEqual(sample(raw,2,37,127),100)
        self.assertEqual(sample(raw,2,36,128),400)
        self.assertEqual(sample(raw,2,36.5,127.5),250)
        with self.assertRaises(ValueError): sample(struct.pack('>hhhh',-32768,0,0,0),2,36.5,127.5)
        with self.assertRaises(ValueError): sample(raw,2,38,127)

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
