import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import tactics
from tools.build_identification_feed import build as build_feed
from tools.evidence_review import AuditLog
from tools.monitor_server import Simulation
from tools.scenario_dataset import read_json
from tools.situation_agent import build_bundle

LAYOUT = read_json(tactics.PROJECT / 'data/site_layout.json')
CATALOG = tactics.load_catalog()


def track(object_id, points, first_ms=None, sources=('channel_a', 'channel_b'), last_known=False):
    """points: list of (at_ms, x, y, z) received from one position source."""
    history = [dict(id=f'{object_id}_{at}', object_id=object_id, source_id='channel_a', observed_at_ms=at,
                    available_at_ms=at, position=[x, y, z], marker_label='circle') for at, x, y, z in points]
    records = [dict(history[-1], source_id=source, id=f'{object_id}_{source}') for source in sources]
    return dict(object_id=object_id, position=history[-1]['position'], history=history, records=records,
                first_received_at_ms=first_ms if first_ms is not None else points[0][0], last_known=last_known,
                quality='consistent')


def straight(object_id, x, z0=-6000, speed_mps=58.0, altitude=100, first_ms=0, samples=4):
    return track(object_id, [(first_ms + i * 10000, x, altitude, z0 + i * speed_mps * 10) for i in range(samples)], first_ms)


class IdentificationTests(unittest.TestCase):
    def identify(self, tracks, reports=(), at_ms=100000):
        return {row['object_id']: row for row in tactics.identify(tracks, list(reports), LAYOUT, at_ms, CATALOG)}

    def test_group_structure_and_first_wave_lean_decoy_with_received_evidence_only(self):
        swarm = [straight(f'o{i}', -300 + 120 * i) for i in range(6)]
        result = self.identify(swarm)
        for row in result.values():
            self.assertEqual(row['lean'], 'decoy_leaning')
            self.assertEqual({cue['id'] for cue in row['cues']}, {'group_structure', 'first_wave'})
            self.assertGreaterEqual(row['group_size'], 5)
            self.assertIn('group_from_received_positions_only', row['uncertainty'])
            self.assertIn('no_eo_report', row['uncertainty'])
            self.assertEqual(row['verification'], 'suspected')
            self.assertTrue(all(isinstance(cue['evidence_ids'], list) and cue['evidence_ids'] for cue in row['cues']))

    def test_terminal_descent_outweighs_first_wave_for_a_lone_aircraft(self):
        lone = track('lone', [(0, 400, 120, -3000), (10000, 400, 120, -2400), (20000, 400, 100, -1800), (30000, 400, 60, -1200)])
        row = self.identify([lone])['lone']
        self.assertEqual(row['lean'], 'attack_leaning')
        self.assertIn('terminal_maneuver', {cue['id'] for cue in row['cues']})
        self.assertEqual(row['kinematics']['descent_m'], 40.0)

    def test_jet_speed_and_acoustic_jet_set_profile_and_keep_decoy_uncertainty(self):
        fast = straight('fast', 0, speed_mps=120.0)
        rows = self.identify([fast], [dict(id='r1', object_id='fast', sensor_type='acoustic', available_at_ms=5000,
                                            observed_at_ms=4000, fields=dict(signature='jet'))])
        row = rows['fast']
        self.assertEqual(row['profile'], 'jet')
        self.assertIn('jet_speed', {cue['id'] for cue in row['cues']})
        self.assertIn('acoustic_jet', {cue['id'] for cue in row['cues']})
        self.assertIn('jet_decoy_possible', row['uncertainty'])
        self.assertIn('r1', row['evidence_ids'])

    def test_rf_emission_leans_reconnaissance_and_eo_conflict_is_flagged(self):
        recon = straight('recon', 0)
        reports = [dict(id='rf1', object_id='recon', sensor_type='rf', available_at_ms=5000, observed_at_ms=4000, fields=dict(rf_emission=True)),
                   dict(id='eo1', object_id='recon', sensor_type='eo', available_at_ms=6000, observed_at_ms=5000, fields=dict(airframe_class='fixed_wing', payload_visible=False)),
                   dict(id='eo2', object_id='recon', sensor_type='eo', available_at_ms=7000, observed_at_ms=6000, fields=dict(airframe_class='multirotor', payload_visible=False))]
        row = self.identify([recon], reports)['recon']
        self.assertEqual(row['lean'], 'reconnaissance_leaning')
        self.assertEqual(row['verification'], 'observed_class')
        for item in ('eo_conflict', 'payload_not_visible'):
            self.assertIn(item, row['uncertainty'])
        self.assertNotIn('no_eo_report', row['uncertainty'])

    def test_light_airframe_report_adds_decoy_and_single_sample_is_insufficient(self):
        decoy = straight('decoy', 0)
        report = dict(id='eo', object_id='decoy', sensor_type='eo', available_at_ms=5000, observed_at_ms=4000, fields=dict(airframe_class='light_airframe', payload_visible=False))
        self.assertIn('eo_light_airframe', {cue['id'] for cue in self.identify([decoy], [report])['decoy']['cues']})
        single = track('single', [(0, 0, 100, -3000)])
        row = self.identify([single])['single']
        self.assertEqual(row['lean'], 'insufficient_data')
        self.assertIsNone(row['kinematics']['speed_kmh'])

    def test_reports_are_time_gated_and_scoped_to_the_case(self):
        feed = dict(cases=dict(case_x=dict(reports=[
            dict(id='late', object_id='a', sensor_type='eo', available_at_ms=50000, observed_at_ms=45000, fields={}),
            dict(id='early', object_id='a', sensor_type='eo', available_at_ms=10000, observed_at_ms=9000, fields={})])))
        self.assertEqual([row['id'] for row in tactics.arrived_reports(feed, 'case_x', 20000)], ['early'])
        self.assertEqual(tactics.arrived_reports(feed, 'other', 20000), [])

    def test_feed_builder_is_deterministic_and_only_reports_after_first_receipt(self):
        first, second = build_feed(), build_feed()
        self.assertEqual(json.dumps(first, sort_keys=True), json.dumps(second, sort_keys=True))
        for case_id, case in first['cases'].items():
            public = read_json(tactics.PROJECT / f'data/scenarios/v1/cases/{case_id}/public.json')
            earliest = {}
            for row in public['observations']:
                earliest[row['object_id']] = min(earliest.get(row['object_id'], row['available_at_ms']), row['available_at_ms'])
            self.assertTrue(case['reports'])
            for report in case['reports']:
                self.assertGreater(report['available_at_ms'], earliest[report['object_id']])
                self.assertLess(report['observed_at_ms'], report['available_at_ms'])
                self.assertIn(report['sensor_type'], first['sensor_types'])


class RecommendationTests(unittest.TestCase):
    def recommend(self, tracks, reports=(), allocations=(), units=()):
        ident = tactics.identify(tracks, list(reports), LAYOUT, 100000, CATALOG)
        return {row['object_id']: row for row in tactics.recommend(ident, tracks, list(allocations), list(units), LAYOUT, CATALOG)}

    def test_runway_overflight_rejects_every_effector_and_holds(self):
        over = track('over', [(0, -300, 100, -1200), (10000, -300, 100, -600)])
        row = self.recommend([over])['over']
        self.assertEqual(row['posture'], 'hold')
        self.assertIsNone(row['primary'])
        self.assertIn('runway_overflight', row['constraints'])
        for option in row['options']:
            self.assertEqual(option['status'], 'rejected')
            self.assertIn('runway_overflight', option['reasons'])

    def test_penalize_versus_reject_semantics(self):
        team = dict(id='effector_team_1', kind='effector_team', position=[1500, 0, -2600])
        far = track('far', [(0, 1500, 100, -4200), (10000, 1500, 100, -3600)])
        row = self.recommend([far], units=[team])['far']
        options = {option['effector_id']: option for option in row['options']}
        self.assertEqual(options['interceptor_drone']['status'], 'penalized')
        self.assertIn('resource_preservation', options['interceptor_drone']['reasons'])
        self.assertEqual(options['rf_jammer']['status'], 'penalized')
        self.assertIn('rf_emission_unknown', options['rf_jammer']['reasons'])
        self.assertEqual(options['autocannon']['status'], 'recommended')
        self.assertEqual(options['laser']['status'], 'recommended')
        self.assertEqual(row['posture'], 'observe_preserve')
        self.assertIn(row['primary'], ('laser', 'autocannon'))
        self.assertTrue(all(0 <= option['suitability'] <= 1 for option in row['options']))

    def test_own_radar_debris_and_fiber_evidence_reject_specific_effectors(self):
        near_tower = track('tower', [(0, 500, 100, 900), (10000, 500, 100, 600)])
        inside = track('inside', [(0, 300, 100, -1200), (10000, 300, 100, -700)])
        report = dict(id='rf0', object_id='inside', sensor_type='rf', available_at_ms=5000, observed_at_ms=4000, fields=dict(rf_emission=False))
        rows = self.recommend([near_tower, inside], [report])
        tower_options = {option['effector_id']: option for option in rows['tower']['options']}
        self.assertIn('own_radar_interference', tower_options['rf_jammer']['reasons'])
        self.assertEqual(tower_options['rf_jammer']['status'], 'rejected')
        inside_options = {option['effector_id']: option for option in rows['inside']['options']}
        self.assertEqual(inside_options['autocannon']['status'], 'rejected')
        self.assertIn('debris_over_facilities', inside_options['autocannon']['reasons'])
        self.assertIn('no_rf_link_evidence', inside_options['rf_jammer']['reasons'])
        self.assertIn('over_facilities', rows['inside']['constraints'])

    def test_coverage_inventory_and_laser_queue(self):
        target = track('t', [(0, 0, 100, -4800), (10000, 0, 100, -4200)])
        no_team = self.recommend([target])['t']
        self.assertTrue(all('no_effector_team_placed' in option['reasons'] for option in no_team['options']))
        far_team = self.recommend([target], units=[dict(id='e', kind='effector_team', position=[0, 0, 3000])])['t']
        self.assertTrue(all('coverage_gap' in option['reasons'] for option in far_team['options']))
        close_team = self.recommend([target], units=[dict(id='e', kind='effector_team', position=[0, 0, -2500])])['t']
        self.assertFalse(any('coverage_gap' in option['reasons'] for option in close_team['options']))
        used = [dict(id=str(i), object_id=f'x{i}', effector_id='interceptor_drone', at_ms=0, status_at_record='recommended') for i in range(12)]
        used.append(dict(id='l', object_id='other', effector_id='laser', at_ms=0, status_at_record='recommended'))
        row = self.recommend([target], allocations=used)['t']
        options = {option['effector_id']: option for option in row['options']}
        self.assertEqual(options['interceptor_drone']['status'], 'rejected')
        self.assertIn('inventory_exhausted', options['interceptor_drone']['reasons'])
        self.assertEqual(options['interceptor_drone']['inventory_remaining'], 0)
        self.assertIn('single_target_queue', options['laser']['reasons'])

    def test_jet_profile_prefers_laser_and_penalizes_interceptor(self):
        fast = track('jet', [(0, 2500, 200, -4800), (10000, 2500, 200, -3600), (20000, 2500, 160, -2400)], first_ms=0)
        slow_first = track('first', [(-200000, -3000, 100, -4800), (-190000, -3000, 100, -4700)], first_ms=-200000)
        row = self.recommend([fast, slow_first], units=[dict(id='e', kind='effector_team', position=[1800, 0, -1800])])['jet']
        options = {option['effector_id']: option for option in row['options']}
        self.assertIn('speed_disadvantage', options['interceptor_drone']['reasons'])
        self.assertIn('preferred_for_jet', options['laser']['reasons'])
        self.assertEqual(row['primary'], 'laser')
        self.assertEqual(row['posture'], 'engage_candidate')
        self.assertEqual(row['authority'], 'human_confirmation_required')


class PlacementTests(unittest.TestCase):
    def setUp(self):
        self.terrain = read_json(tactics.TERRAIN_PATH)
        self.context = read_json(tactics.CONTEXT_PATH)

    def test_prior_proposal_is_deterministic_bounded_and_respects_budgets(self):
        first = tactics.propose_placement(LAYOUT, self.terrain, self.context, [], None, CATALOG)
        second = tactics.propose_placement(LAYOUT, self.terrain, self.context, [], None, CATALOG)
        self.assertEqual(first['signature'], second['signature'])
        self.assertNotEqual(first['id'], second['id'])
        self.assertEqual(first['threat_basis'], 'scenario_prior')
        counts = {}
        polygon = LAYOUT['perimeter']['polygon']
        for row in first['positions']:
            counts[row['kind']] = counts.get(row['kind'], 0) + 1
            self.assertTrue(tactics.valid_position(row['position']))
            self.assertTrue(row['label']['en'] and row['label']['ko'] and row['basis']['en'] and row['basis']['ko'])
            if row['kind'] in ('radar', 'effector_team'):
                self.assertFalse(tactics.in_runway_corridor(row['position'], LAYOUT, 150))
            if row['kind'] == 'detection_phone':
                self.assertFalse(tactics.point_in_polygon(row['position'][0], row['position'][2], polygon))
        self.assertEqual(counts, {kind['id']: kind['budget'] for kind in CATALOG['unit_kinds']})
        self.assertEqual({row['role'] for row in first['positions'] if row['kind'] == 'infantry'}, {'observation_post', 'quick_reaction', 'patrol'})
        phones = [row['position'] for row in first['positions'] if row['kind'] == 'detection_phone']
        for index, phone in enumerate(phones):
            for other in phones[index + 1:]:
                self.assertGreaterEqual(tactics.horizontal_distance(phone, other), CATALOG['placement']['phone_spacing_m'])
        self.assertTrue(all(0 <= value <= 1 for value in first['coverage'].values()))

    def test_received_picture_shifts_weights_and_works_without_roads(self):
        east = [straight(f'e{i}', 4000 + 100 * i, z0=-200) for i in range(4)]
        for row in east:
            row['history'] = [dict(h, position=[h['position'][0], 100, -200 + 10 * j]) for j, h in enumerate(row['history'])]
        weights, basis = tactics.threat_weights(east, dict(zones=[dict(center=[3000, 0, 0], positive_sources=2)]), CATALOG)
        self.assertEqual(basis, 'received_picture')
        self.assertEqual(max(weights, key=weights.get), 'E')
        proposal = tactics.propose_placement(LAYOUT, None, {}, east, None, CATALOG, at_ms=5000)
        self.assertEqual(proposal['threat_basis'], 'received_picture')
        self.assertEqual(proposal['computed_at_ms'], 5000)
        self.assertEqual(len(proposal['positions']), sum(kind['budget'] for kind in CATALOG['unit_kinds']))

    def test_manual_placement_enforces_kind_budget_bounds_and_identity(self):
        units = []
        radar_budget = next(kind['budget'] for kind in CATALOG['unit_kinds'] if kind['id'] == 'radar')
        for number in range(radar_budget):
            tactics.place_unit(dict(position=[100 + number, 0, -2000], kind='radar'), units, CATALOG)
        with self.assertRaises(ValueError):
            tactics.place_unit(dict(position=[300, 0, -2000], kind='radar'), units, CATALOG)
        for bad in ([5001, 0, 0], [0, 1, 0], [0, 0], [float('nan'), 0, 0], 'x'):
            with self.assertRaises(ValueError):
                tactics.place_unit(dict(position=bad), units, CATALOG)
        with self.assertRaises(ValueError):
            tactics.place_unit(dict(position=[0, 0, 0], kind='tank'), units, CATALOG)
        with self.assertRaises(ValueError):
            tactics.place_unit(dict(position=[0, 0, 0], unit_id='missing'), units, CATALOG)
        moved = tactics.place_unit(dict(position=[-1000, 0, 500], unit_id='radar_1'), units, CATALOG)
        self.assertEqual(moved['position'], [-1000.0, 0, 500.0])
        self.assertEqual([unit['id'] for unit in units], [f'radar_{n}' for n in range(1, radar_budget + 1)])
        placed = tactics.place_unit(dict(position=[10, 0, 10]), units, CATALOG)
        self.assertEqual((placed['kind'], placed['id'], placed['label']['ko']), ('infantry', 'infantry_1', '보병 1'))


class ServerIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.audit_path = Path(self.temp.name) / 'tactics.jsonl'
        self.now = 0.0
        self.sim = Simulation(clock=lambda: self.now, decision_evaluator=lambda *_: {}, tactics_audit_path=self.audit_path)
        self.sim.control(dict(action='case', case_id='case_003'))
        self.sim.control(dict(action='seek', at_ms=100000))

    def proposal(self):
        return self.sim.state()['exercise']['unit_proposal']

    def unit_command(self, action, **extra):
        return self.sim.control(dict(action=action, run_id=self.sim.run_id, confirm=True, **extra))

    def test_state_exposes_proposal_units_kinds_and_targets_without_world_reads(self):
        with patch('tools.monitor_server.read_json', side_effect=AssertionError('no world reads')):
            state = self.sim.state()
        exercise = state['exercise']
        self.assertEqual(exercise['units'], [])
        self.assertEqual(exercise['unit_proposal']['status'], 'pending')
        self.assertEqual(len(exercise['unit_proposal']['positions']), sum(kind['budget'] for kind in CATALOG['unit_kinds']))
        self.assertEqual([kind['id'] for kind in exercise['unit_kinds']], ['infantry', 'radar', 'detection_phone', 'effector_team'])
        tactics_state = state['tactics']
        self.assertEqual(tactics_state['scope'], 'rule_based_training_advice')
        self.assertEqual({t['object_id'] for t in tactics_state['targets']}, {t['object_id'] for t in state['tracks']})
        self.assertEqual(tactics_state['summary']['received'], len(state['tracks']))
        self.assertGreater(tactics_state['summary']['reports_received'], 0)
        self.assertEqual(tactics_state['formation']['posture'], 'hold')
        encoded = json.dumps(tactics_state)
        for field in ('keyframes', 'simulation_positions', 'airframe_id'):
            self.assertNotIn(field, encoded)
        self.assertEqual(json.dumps(tactics_state['targets'], sort_keys=True),
                         json.dumps(self.sim.state()['tactics']['targets'], sort_keys=True))

    def test_accept_manual_place_move_remove_and_run_reset(self):
        proposal = self.proposal()
        with self.assertRaises(ValueError):
            self.unit_command('exercise_place_unit', position=[0, 0, 0])
        with self.assertRaises(ValueError):
            self.unit_command('exercise_accept_units', proposal_id='stale')
        with self.assertRaises(ValueError):
            self.sim.control(dict(action='exercise_accept_units', run_id='old', proposal_id=proposal['id'], confirm=True))
        state = self.unit_command('exercise_accept_units', proposal_id=proposal['id'])
        self.assertEqual(len(state['exercise']['units']), sum(kind['budget'] for kind in CATALOG['unit_kinds']))
        self.assertEqual(state['exercise']['unit_proposal']['status'], 'accepted')
        self.assertEqual(state['tactics']['formation']['by_kind'], {kind['id']: kind['budget'] for kind in CATALOG['unit_kinds']})
        self.assertTrue(state['tactics']['formation']['teams'])
        self.assertTrue(all(not any('no_effector_team_placed' in option['reasons'] for option in target['response']['options'])
                            for target in state['tactics']['targets']))
        with self.assertRaises(ValueError):
            self.unit_command('exercise_accept_units', proposal_id=proposal['id'])
        state = self.unit_command('exercise_manual_units', proposal_id=proposal['id'])
        self.assertEqual(state['exercise']['unit_proposal']['status'], 'manual')
        with self.assertRaises(ValueError):
            self.unit_command('exercise_place_unit', position=[0, 0, 0], kind='radar')  # radar budget already used
        state = self.unit_command('exercise_remove_unit', unit_id='radar_2')
        self.assertEqual(sum(unit['kind'] == 'radar' for unit in state['exercise']['units']), 3)
        state = self.unit_command('exercise_place_unit', position=[1200, 0, -1800], kind='radar')
        radar = next(unit for unit in state['exercise']['units'] if unit['id'] == 'radar_2')
        self.assertEqual((radar['position'], radar['source']), ([1200.0, 0, -1800.0], 'manual'))
        state = self.unit_command('exercise_place_unit', position=[1300, 0, -1700], unit_id='radar_2')
        self.assertEqual(next(unit for unit in state['exercise']['units'] if unit['id'] == 'radar_2')['position'], [1300.0, 0, -1700.0])
        with self.assertRaises(ValueError):
            self.unit_command('exercise_remove_unit', unit_id='missing')
        run_before = self.sim.run_id
        state = self.sim.control(dict(action='seek', at_ms=120000))
        self.assertNotEqual(state['run_id'], run_before)
        self.assertEqual(state['exercise']['units'], [])
        self.assertEqual(state['exercise']['unit_proposal']['status'], 'pending')
        self.assertNotEqual(state['exercise']['unit_proposal']['id'], proposal['id'])
        self.assertEqual(state['exercise']['unit_proposal']['signature'], proposal['signature'])

    def test_reoptimize_uses_received_picture_and_keeps_placed_units(self):
        proposal = self.proposal()
        self.unit_command('exercise_accept_units', proposal_id=proposal['id'])
        state = self.unit_command('exercise_reoptimize_units')
        new = state['exercise']['unit_proposal']
        self.assertEqual(new['status'], 'pending')
        self.assertNotEqual(new['id'], proposal['id'])
        self.assertEqual(new['threat_basis'], 'received_picture')
        self.assertEqual(new['computed_at_ms'], 100000)
        self.assertEqual(len(state['exercise']['units']), sum(kind['budget'] for kind in CATALOG['unit_kinds']))
        with self.assertRaises(ValueError):
            self.sim.control(dict(action='exercise_reoptimize_units', run_id=self.sim.run_id))

    def test_allocation_requires_current_card_rejects_rejected_options_and_persists(self):
        proposal = self.proposal()
        self.unit_command('exercise_accept_units', proposal_id=proposal['id'])
        state = self.sim.state()
        target = next(t for t in state['tactics']['targets'] if t['response']['posture'] != 'hold')
        option = next(o for o in target['response']['options'] if o['status'] != 'rejected')
        rejected = next(o for o in next(t for t in state['tactics']['targets'] if t['response']['posture'] == 'hold')['response']['options'])
        command = dict(action='tactics_allocate', run_id=self.sim.run_id, object_id=target['object_id'],
                       effector_id=option['effector_id'], version=target['response']['version'], confirm=True,
                       reviewer=' Duty officer ', comment='Training record only')
        for override in ({'confirm': False}, {'run_id': 'old'}, {'version': 'stale'}, {'object_id': 'hidden'},
                         {'effector_id': 'phaser'}, {'reviewer': 'x' * 81}):
            with self.assertRaises(ValueError):
                self.sim.control({**command, **override})
        hold_target = next(t for t in state['tactics']['targets'] if t['response']['posture'] == 'hold')
        with self.assertRaises(ValueError):
            self.sim.control(dict(command, object_id=hold_target['object_id'], effector_id=rejected['effector_id'],
                                  version=hold_target['response']['version']))
        state = self.sim.control(command)
        recorded = next(t for t in state['tactics']['targets'] if t['object_id'] == target['object_id'])
        self.assertEqual(recorded['response']['allocation']['effector_id'], option['effector_id'])
        self.assertNotEqual(recorded['response']['version'], target['response']['version'])
        self.assertEqual(len(state['tactics']['allocations']), 1)
        record = state['tactics']['allocations'][0]
        self.assertEqual((record['reviewer'], record['reason'], record['actor']['type']), ('Duty officer', 'Training record only', 'human'))
        self.assertNotIn('evidence_snapshot', record)
        effector = next(e for e in state['tactics']['effectors'] if e['id'] == option['effector_id'])
        self.assertEqual(effector['used'], 1)
        with self.assertRaises(ValueError):
            self.sim.control(dict(command, version=recorded['response']['version']))
        self.assertEqual(len(self.audit_path.read_text().splitlines()), 1)
        reloaded = AuditLog(self.audit_path)
        self.assertEqual(reloaded.records[0]['effector_id'], option['effector_id'])
        self.assertEqual(reloaded.records[0]['scope'], 'rule_based_training_advice')
        self.assertEqual(self.sim.tactics_audit.export()['records'][0]['id'], record['id'])
        bundle = build_bundle(state)
        self.assertEqual(bundle['tactics']['allocations'], 1)
        self.assertEqual(bundle['tactics']['placed_units']['effector_team'], 4)
        self.assertNotIn('position', json.dumps(bundle['tactics']))
        self.assertIn(bundle['tactics']['id'], bundle['evidence_ids'])
        state = self.sim.control(dict(action='reset'))
        self.assertEqual(state['tactics']['allocations'], [])
        self.assertNotIn('tactics', build_bundle(state))
        self.assertEqual(len(self.sim.tactics_audit.records), 1)

    def test_identification_in_paced_case_waits_for_received_tracks(self):
        self.sim.control(dict(action='case', case_id='case_001'))
        self.sim.control(dict(action='seek', at_ms=100000))
        state = self.sim.state()
        self.assertEqual(state['tactics']['targets'], [])
        self.assertEqual(state['tactics']['formation']['posture'], 'ready')
        self.sim.control(dict(action='seek', at_ms=330000))
        state = self.sim.state()
        self.assertTrue(state['tactics']['targets'])
        profiles = {t['identification']['profile'] for t in state['tactics']['targets']}
        self.assertTrue(profiles & {'jet', 'multirotor', 'fixed_wing', 'light_airframe'})
        self.assertTrue(all(report['available_at_ms'] <= 330000 for t in state['tactics']['targets'] for report in t['identification']['reports']))


if __name__ == '__main__':
    unittest.main()


class ReviewFollowUpTests(unittest.TestCase):
    def setUp(self):
        self.now = 0.0
        self.sim = Simulation(clock=lambda: self.now, decision_evaluator=lambda *_: {})

    def test_stale_tracks_hold_their_own_card_but_not_the_formation(self):
        fresh = track('fresh', [(0, 2500, 100, -4800), (10000, 2500, 100, -4200)])
        stale = track('stale', [(0, -300, 100, -1200), (10000, -300, 100, -600)], last_known=True)
        ident = tactics.identify([fresh, stale], [], LAYOUT, 100000, CATALOG)
        rows = {row['object_id']: row for row in tactics.recommend(ident, [fresh, stale], [], [], LAYOUT, CATALOG)}
        self.assertIn('stale_track', rows['stale']['constraints'])
        self.assertEqual(rows['stale']['posture'], 'hold')
        self.assertTrue(all(option['status'] == 'rejected' for option in rows['stale']['options']))
        self.assertNotIn('stale_track', rows['fresh']['constraints'])
        targets = [dict(object_id=i['object_id'], identification=i, response=rows[i['object_id']]) for i in ident]
        self.assertEqual(tactics.formation([], targets, CATALOG)['posture'], 'observe')

    def test_seeded_runs_align_reports_with_the_visual_cast(self):
        state = self.sim.control(dict(action='start_test', case_id='case_003', seed=7))
        cast = {row['object_id']: row['airframe_id'] for row in self.sim.test_visuals['objects']}
        reports = self.sim.test_identification['cases']['case_003']['reports']
        self.assertTrue(reports)
        self.assertEqual(self.sim.test_identification['cases']['case_003']['cast_signature'], self.sim.test_visuals['signature'])
        from tools.build_identification_feed import CLASS_BY_PROFILE, load_profiles, JET_AIRFRAMES
        profiles = load_profiles()
        for report in reports:
            if report['sensor_type'] == 'eo' and 'conflict' not in report['note']:
                self.assertEqual(report['fields']['airframe_class'], CLASS_BY_PROFILE[profiles[cast[report['object_id']]]['size_profile']])
            if report['sensor_type'] == 'acoustic' and report['fields']['signature'] == 'jet':
                self.assertIn(cast[report['object_id']], JET_AIRFRAMES)
        again = Simulation(clock=lambda: 0, decision_evaluator=lambda *_: {})
        again.control(dict(action='start_test', case_id='case_003', seed=7))
        self.assertEqual(json.dumps(again.test_identification, sort_keys=True), json.dumps(self.sim.test_identification, sort_keys=True))
        self.assertNotIn('simulation_visuals', state)
        self.sim.control(dict(action='case', case_id='case_003'))
        self.assertIsNone(self.sim.test_identification)

    def test_proposal_never_exceeds_a_reduced_kind_budget(self):
        catalog = json.loads(json.dumps(CATALOG))
        for kind in catalog['unit_kinds']:
            kind['budget'] = 1
        proposal = tactics.propose_placement(LAYOUT, None, {}, [], None, catalog)
        counts = {}
        for row in proposal['positions']:
            counts[row['kind']] = counts.get(row['kind'], 0) + 1
        self.assertEqual(counts, {'infantry': 1, 'radar': 1, 'detection_phone': 1, 'effector_team': 1})

    def test_agent_bundle_labels_rubric_counts_and_never_carries_positions(self):
        self.sim.control(dict(action='case', case_id='case_003'))
        self.sim.control(dict(action='seek', at_ms=100000))
        bundle = build_bundle(self.sim.state())
        self.assertEqual(bundle['tactics']['allocations'], 0)
        self.assertIn('rubric_lean_counts', bundle['tactics'])
        self.assertIn('not identity or intent', bundle['tactics']['note'])
        self.assertNotIn('position', json.dumps(bundle['tactics']))
