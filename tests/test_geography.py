import json
import math
import tempfile
import unittest
from pathlib import Path

from tools import tactics
from tools.build_mdl import build as build_mdl, to_local
from tools.infiltration_routes import CORRIDORS, launch_areas, line_z_at, plan_objects
from tools.monitor_server import Simulation

PROJECT = Path(__file__).resolve().parents[1]
MDL = json.loads((PROJECT / 'data/geography/korean_mdl.json').read_text())
CORRIDORS_DATA = json.loads((PROJECT / 'data/geography/approach_corridors.json').read_text())
LAYOUT = json.loads((PROJECT / 'data/site_layout.json').read_text())
CATALOG = tactics.load_catalog()


def parts(name):
    return [part['local'] for part in MDL['lines'][name]['parts']]


class BoundaryTests(unittest.TestCase):
    def test_pinned_source_and_line_order_at_the_site_longitude(self):
        self.assertEqual(MDL['source']['sha256'], '74d9c16229c095fde65943a9919e337682f044bcebccb120764f38edf3b70f4a')
        self.assertIn('Public domain', MDL['source']['license'])
        north, mdl, south = (line_z_at(parts(name), 0) for name in ('dmz_north', 'mdl', 'dmz_south'))
        # Z grows southward: northern limit, then MDL, then southern limit; nominal 2 km offsets, 40-52 km north.
        self.assertLess(north, mdl)
        self.assertLess(mdl, south)
        self.assertAlmostEqual(mdl - north, 2000, delta=60)
        self.assertAlmostEqual(south - mdl, 2000, delta=60)
        self.assertTrue(-52000 < mdl < -42000)
        self.assertEqual({len(MDL['lines'][key]['parts']) for key in ('mdl', 'dmz_north', 'dmz_south')}, {1})
        self.assertEqual(set(MDL['reference_lines']), {'natural_earth_dmz_south', 'natural_earth_dmz_north'})

    def test_builder_converts_with_the_monitor_projection(self):
        lat, lon = 38.3, 127.2
        x, z = to_local(lat, lon)
        self.assertAlmostEqual(x, 0, places=1)
        self.assertAlmostEqual(z, -(0.4 * math.pi / 180) * 6378137, delta=1)
        source = dict(features=[dict(properties=dict(NAME=name, ADM0_LEFT=left), geometry=dict(type='LineString', coordinates=[[127.0, lat], [127.4, lat]]))
                                for name, left, lat in (('Military Demarcation Line 1953', 'North Korea', 38.3),
                                                        ('Korean Demilitarized Zone', 'South Korea', 38.28),
                                                        ('Korean Demilitarized Zone', 'North Korea', 38.32))])
        built = build_mdl(source)
        self.assertEqual(set(built['lines']), {'mdl', 'dmz_south', 'dmz_north'})
        north = built['lines']['dmz_north']['parts'][0]['local'][0]
        mdl = built['lines']['mdl']['parts'][0]['local'][0]
        self.assertAlmostEqual(mdl[1] - north[1], 2000, delta=1)
        with self.assertRaises(ValueError):
            build_mdl(dict(features=source['features'][:1]))


class RouteTests(unittest.TestCase):
    def test_launch_areas_are_north_of_the_dmz_and_corridors_reach_the_entry_gates(self):
        areas = launch_areas()
        self.assertEqual(len(areas), len(CORRIDORS))
        for area in areas:
            x, _, z = area['position']
            self.assertAlmostEqual(z, line_z_at(parts('mdl'), x) - 5000, delta=1)
            self.assertAlmostEqual(area['mdl_crossing'][2], line_z_at(parts('mdl'), x), places=0)
        for corridor in CORRIDORS_DATA['corridors']:
            self.assertAlmostEqual(math.hypot(corridor['gate'][0], corridor['gate'][2]), 7500, delta=1)
            self.assertGreater(len(corridor['centreline']), 10)

    def test_routes_are_deterministic_curved_and_role_specific(self):
        airframes = {'o1': 'gerbera', 'o2': 'geran_2', 'o3': 'orlan_10', 'o4': 'quadcopter', 'o5': 'geran_3'}
        times = list(range(0, 780_001, 10_000))
        first, meta = plan_objects('case_x', list(airframes), airframes, LAYOUT, times, paced=True)
        second, _ = plan_objects('case_x', list(airframes), airframes, LAYOUT, times, paced=True)
        self.assertEqual(json.dumps(first), json.dumps(second))
        self.assertEqual({row['role'] for row in meta.values()}, {'decoy', 'strike', 'recon', 'multirotor', 'strike_jet'})
        recon = [frame['position'] for frame in first['o3'] if frame['at_ms'] >= 600_000]
        centre = (sum(p[0] for p in recon) / len(recon), sum(p[2] for p in recon) / len(recon))
        spread = [math.hypot(p[0] - centre[0], p[2] - centre[1]) for p in recon]
        self.assertGreater(min(spread), 300, 'Reconnaissance aircraft loiter on an orbit, not a straight line')
        strike = {frame['at_ms']: frame['position'] for frame in first['o2']}
        self.assertLess(min(p[1] for p in strike.values() if p[1] > 0), max(p[1] for p in strike.values()) * 0.5,
                        'Strike aircraft descend on the terminal run')
        for frames in first.values():
            self.assertEqual(frames[0]['position'][1], 0, 'Every aircraft starts on the ground in its launch area')

    def test_no_teleports_after_first_receipt_in_generated_cases(self):
        from tools.exercise import sample
        for case in ('case_001', 'case_002', 'case_003'):
            world = json.loads((PROJECT / f'data/scenarios/v1/cases/{case}/world.json').read_text())
            start = 0 if case == 'case_003' else 270_000
            for obj in world['objects']:
                frames = obj['keyframes']
                for at in range(start, world['duration_ms'] - 1000, 1000):
                    a, b = sample(frames, at), sample(frames, at + 1000)
                    self.assertLess(math.dist((a[0], a[2]), (b[0], b[2])), 75, (case, obj['object_id'], at))
                    self.assertGreaterEqual(b[1], 0)

    def test_compact_case_uses_terminal_segments_inside_the_gate(self):
        airframes = {f'o{i}': 'gerbera' for i in range(6)}
        frames, meta = plan_objects('case_y', list(airframes), airframes, LAYOUT, list(range(0, 180_001, 10_000)), paced=False)
        for rows in frames.values():
            self.assertLessEqual(math.hypot(rows[0]['position'][0], rows[0]['position'][2]), 8200)
            self.assertGreater(rows[0]['position'][1], 0)
        self.assertTrue(all(row['launch_ms'] is None for row in meta.values()))


class RadarTests(unittest.TestCase):
    def setUp(self):
        self.terrain = json.loads(tactics.TERRAIN_PATH.read_text())
        self.model = tactics.radar_model(LAYOUT, self.terrain, CATALOG)
        self.weights = self.model.weights(CATALOG['sector_prior']['weights'])

    def test_line_of_sight_coverage_grows_with_more_radars_and_beats_a_single_central_site(self):
        values = [self.model.coverage(self.model.greedy([], n, self.weights), self.weights) for n in range(1, 5)]
        self.assertEqual(values, sorted(values))
        self.assertGreater(values[-1], values[0] + 0.15)
        self.assertLess(self.model.coverage([self.model.nearest([0, 0, 0])], self.weights), values[0])
        self.assertTrue(all(abs(c[0]) <= 5000 and abs(c[2]) <= 5000 for c in self.model.candidates))
        self.assertFalse(any(tactics.in_runway_corridor(c, LAYOUT, 150) for c in self.model.candidates))

    def test_adjustment_moves_only_displaced_radars_and_adds_up_to_budget(self):
        proposal = tactics.propose_placement(LAYOUT, self.terrain, {}, [], None, CATALOG)
        units = tactics.units_from_proposal(proposal)
        radars = [u for u in units if u['kind'] == 'radar']
        self.assertEqual(len(radars), 4)
        units = [u for u in units if u['id'] != 'radar_4']
        next(u for u in units if u['id'] == 'radar_1')['position'] = [0, 0, 0]
        adjustment = tactics.propose_radar_adjustment(units, LAYOUT, self.terrain, [], None, CATALOG)
        self.assertEqual([move['unit_id'] for move in adjustment['moves']], ['radar_1'])
        self.assertEqual(len(adjustment['additions']), 1)
        self.assertGreater(adjustment['coverage_after'], adjustment['coverage_before'])
        tactics.apply_radar_adjustment(units, adjustment, CATALOG)
        self.assertEqual(sum(u['kind'] == 'radar' for u in units), 4)
        self.assertEqual(next(u for u in units if u['id'] == 'radar_1')['source'], 'adjusted')
        with self.assertRaises(ValueError):
            tactics.apply_radar_adjustment(units, adjustment, CATALOG)  # budget would now be exceeded

    def test_coverage_uses_exact_positions_and_graded_airfield(self):
        corner = self.model.coverage_at([[-4900, 0, -4900]], self.weights)
        nearest = self.model.coverage([self.model.nearest([-4900, 0, -4900])], self.weights)
        self.assertLess(corner, 0.1)
        self.assertLessEqual(corner, nearest + 1e-9)
        self.assertAlmostEqual(self.model.ground(-500, -500), -0.02, places=6)

    def test_manual_change_supersedes_a_pending_adjustment(self):
        sim = Simulation(clock=lambda: 0, decision_evaluator=lambda *_: {})
        sim.control(dict(action='case', case_id='case_001'))
        sim.control(dict(action='seek', at_ms=330_000))
        proposal = sim.state()['exercise']['unit_proposal']
        sim.control(dict(action='exercise_accept_units', run_id=sim.run_id, proposal_id=proposal['id'], confirm=True))
        sim.control(dict(action='exercise_manual_units', run_id=sim.run_id, proposal_id=proposal['id'], confirm=True))
        sim.control(dict(action='exercise_place_unit', run_id=sim.run_id, unit_id='radar_1', position=[0, 0, 0], confirm=True))
        adjustment = sim.control(dict(action='exercise_adjust_radars', run_id=sim.run_id, confirm=True))['exercise']['radar_adjustment']
        self.assertEqual([move['unit_id'] for move in adjustment['moves']], ['radar_1'])
        state = sim.control(dict(action='exercise_place_unit', run_id=sim.run_id, unit_id='radar_2', position=[100, 0, 100], confirm=True))
        self.assertEqual(state['exercise']['radar_adjustment']['status'], 'superseded')
        with self.assertRaises(ValueError):
            sim.control(dict(action='exercise_apply_radar_adjustment', run_id=sim.run_id, adjustment_id=adjustment['id'], confirm=True))

    def test_forward_area_flags_reach_the_client_state(self):
        sim = Simulation(clock=lambda: 0, decision_evaluator=lambda *_: {})
        sim.control(dict(action='case', case_id='case_001'))
        zone = next(z for z in sim.state()['early_warning']['zones'] if z['id'] == 'remote_reference')
        self.assertEqual((zone['georeferenced'], zone['schematic']), (True, False))
        self.assertAlmostEqual(zone['center'][2], line_z_at(parts('mdl'), zone['center'][0]) + 4500, delta=1)

    def test_server_adjustment_lifecycle_requires_confirmation_and_resets_with_the_run(self):
        sim = Simulation(clock=lambda: 0, decision_evaluator=lambda *_: {})
        sim.control(dict(action='case', case_id='case_001'))
        sim.control(dict(action='seek', at_ms=330_000))
        self.assertEqual(sim.state()['exercise']['radar_coverage'], 0.0)
        with self.assertRaises(ValueError):
            sim.control(dict(action='exercise_adjust_radars', run_id=sim.run_id))
        state = sim.control(dict(action='exercise_adjust_radars', run_id=sim.run_id, confirm=True))
        adjustment = state['exercise']['radar_adjustment']
        self.assertEqual((len(adjustment['moves']), len(adjustment['additions'])), (0, 4))
        with self.assertRaises(ValueError):
            sim.control(dict(action='exercise_apply_radar_adjustment', run_id=sim.run_id, adjustment_id='stale', confirm=True))
        state = sim.control(dict(action='exercise_apply_radar_adjustment', run_id=sim.run_id, adjustment_id=adjustment['id'], confirm=True))
        self.assertEqual(state['exercise']['radar_adjustment']['status'], 'applied')
        self.assertGreater(state['exercise']['radar_coverage'], 0.8)
        with self.assertRaises(ValueError):
            sim.control(dict(action='exercise_dismiss_radar_adjustment', run_id=sim.run_id, adjustment_id=adjustment['id'], confirm=True))
        state = sim.control(dict(action='seek', at_ms=340_000))
        self.assertIsNone(state['exercise']['radar_adjustment'])
        self.assertEqual(state['exercise']['units'], [])
        self.assertNotIn('route', json.dumps(state['tactics']))


if __name__ == '__main__':
    unittest.main()
