import copy
import json
import unittest
from unittest.mock import patch

from tools.monitor_server import Simulation, PROJECT
from tools.scenario_dataset import read_json, ROOT
from tools.simulation_test import generate, MAX_SEED, VERSION
from tools.situation_agent import build_bundle
from tools.decision_engine import OPTIONS


class SeededTestTests(unittest.TestCase):
    def setUp(self):
        self.now = 100.0
        self.sim = Simulation(clock=lambda: self.now)

    def start(self, seed=42, case='case_003'):
        return self.sim.control(dict(action='start_test', seed=seed, case_id=case))

    def received(self, at_ms):
        self.sim.control(dict(action='pause'))
        return self.sim.control(dict(action='seek', at_ms=at_ms))

    def test_same_seed_reproduces_all_received_inputs_across_instances(self):
        self.start()
        first = self.received(75000)
        fresh = Simulation(clock=lambda: self.now)
        fresh.control(dict(action='start_test', seed=42, case_id='case_003'))
        fresh.control(dict(action='pause'))
        second = fresh.control(dict(action='seek', at_ms=75000))
        self.assertNotEqual(first['run_id'], second['run_id'])
        for field in ('test_run', 'tracks', 'sources', 'alerts', 'early_warning', 'sensor_fleet'):
            self.assertEqual(first[field], second[field], field)

    def test_different_seeds_change_results_and_never_modify_fixtures(self):
        original = copy.deepcopy(self.sim.public)
        early = copy.deepcopy(self.sim.early_feed)
        self.start(42)
        first = self.received(60000)
        self.start(43)
        second = self.received(60000)
        self.assertNotEqual(first['test_run']['input_digest'], second['test_run']['input_digest'])
        self.assertNotEqual(first['tracks'], second['tracks'])
        self.assertNotEqual(first['sources'], second['sources'])
        self.assertEqual(original, self.sim.public)
        self.assertEqual(early, self.sim.early_feed)
        self.assertEqual(original['case_003'], read_json(ROOT / 'cases/case_003/public.json'))

    def test_generation_preserves_observation_truth_times_and_bounded_delivery(self):
        self.start()
        baseline = {row['id']: row for row in self.sim.public['case_003']['observations']}
        self.assertLess(len(self.sim.test_public['observations']), len(baseline))
        for row in self.sim.test_public['observations']:
            original = baseline[row['id']]
            self.assertEqual(row['observed_at_ms'], original['observed_at_ms'])
            self.assertEqual(row['position'], original['position'])
            self.assertLessEqual(original['available_at_ms'], row['available_at_ms'])
            self.assertLessEqual(row['available_at_ms'], original['available_at_ms'] + 3000)

    def test_polling_pause_seek_reset_and_completed_resume_preserve_input(self):
        started = self.start(0)
        self.assertTrue(started['playing'])
        metadata = started['test_run']
        self.assertEqual(metadata['generator_version'], VERSION)
        self.assertEqual(self.sim.clock_state()['test_run'], metadata)
        first = self.received(60000)
        self.assertEqual(first, self.sim.state())
        for command in (dict(action='speed', speed=4), dict(action='reset'),
                        dict(action='seek', at_ms=180000), dict(action='play')):
            self.assertEqual(self.sim.control(command)['test_run'], metadata)
        self.assertEqual(self.received(60000)['tracks'], first['tracks'])
        fixture = self.sim.control(dict(action='case', case_id='case_002'))
        self.assertEqual(fixture['test_run']['mode'], 'fixture')
        self.assertIsNone(self.sim.test_public)

    def test_invalid_seed_or_case_is_atomic(self):
        self.start()
        self.sim.control(dict(action='pause'))
        before = self.sim.state()
        for seed in (True, False, -1, MAX_SEED + 1, 0.5, '42', None):
            with self.assertRaises(ValueError):
                self.start(seed)
            self.assertEqual(self.sim.state(), before)
        for case in ('unknown', [], None):
            with self.assertRaises(ValueError):
                self.start(case=case)
            self.assertEqual(self.sim.state(), before)

    def test_random_start_gets_new_seed_and_run_not_on_poll(self):
        with patch('tools.monitor_server.secrets.randbelow', return_value=42):
            first = self.sim.control(dict(action='start_test'))
            second = self.sim.control(dict(action='start_test'))
        self.assertEqual(first['test_run']['seed'], 42)
        self.assertEqual(second['test_run']['seed'], 43)
        self.assertNotEqual(first['run_id'], second['run_id'])
        self.assertEqual(second['test_run'], self.sim.state()['test_run'])

    def test_received_gate_truth_toggle_and_agent_provenance(self):
        self.start()
        state = self.received(0)
        self.assertEqual(state['tracks'], [])
        self.assertNotIn('simulation_positions', state)
        self.assertNotIn('observations', state['test_run'])
        state = self.received(60000)
        for track in state['tracks']:
            for row in track['records'] + track['history']:
                self.assertLessEqual(row['available_at_ms'], state['at_ms'])
        for source in state['sources']:
            if source['evidence']:
                self.assertLessEqual(source['evidence']['available_at_ms'], state['at_ms'])
        bundle = build_bundle(state)
        self.assertEqual(bundle['test_run'], state['test_run'])
        self.assertNotIn('position', json.dumps(bundle))
        truth = self.sim.state(show_positions=True)['simulation_positions']
        self.start(123)
        self.received(60000)
        self.assertEqual(self.sim.state(show_positions=True)['simulation_positions'], truth)

    def test_evidence_review_uses_generated_inputs_and_records_seed(self):
        self.start()
        state = self.received(60000)
        track = state['tracks'][0]
        self.sim.control(dict(action='review_track', run_id=state['run_id'], object_id=track['object_id'],
                              evidence_version=track['evidence_version'], reviewer='test', reason='Review received input', decision='noted'))
        row = self.sim.audit.export()['records'][-1]
        self.assertEqual(row['test_run'], state['test_run'])

    def test_new_test_invalidates_old_decision_and_event_captures_seed(self):
        calls = []
        def evaluator(state, event, language):
            calls.append(state)
            return dict(summary='Review', decision_options=[dict(id=o['id']) for o in OPTIONS],
                        recommended_option_id='hold_review')
        self.sim.decisions.evaluator = evaluator
        self.start()
        self.now += 15
        self.sim.decisions.tick()
        self.sim.decisions.worker.join(3)
        event = self.sim.decisions.snapshot()['events'][0]
        self.assertEqual(event['status'], 'ready')
        self.assertTrue(self.sim.playing)
        self.assertEqual(calls[0]['test_run']['seed'], 42)
        self.start(43)
        with self.assertRaises(ValueError):
            self.sim.decisions.command(dict(action='confirm', run_id=event['run_id'], event_id=event['id'],
                evidence_version=event['evidence_version'], option_id='hold_review', confirm=True, reviewer='test', reason='Stale'))
        self.assertEqual(self.sim.decisions.snapshot()['events'][0]['status'], 'superseded')


if __name__ == '__main__':
    unittest.main()
