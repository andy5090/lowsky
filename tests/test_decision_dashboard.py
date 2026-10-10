import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.monitor_server import Simulation
from tools.decision_dashboard import DecisionDashboard
from tools.situation_agent import build_bundle, _evidence_tools
from tools.decision_engine import semantic_state, transitions


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.now = 0.0
        self.sim = Simulation(clock=lambda: self.now, decision_evaluator=lambda *_: {})
        self.sim.control(dict(action='seek', at_ms=10000))

    def card(self):
        return self.sim.state()['dashboard']['cards'][0]

    def command(self, choice='continue_observe', **extra):
        card = self.card()
        return dict(action='dashboard_action', run_id=self.sim.run_id, object_id=card['object_id'],
                    card_version=card['version'], choice=choice, confirm=True, **extra)

    def test_no_unreceived_objects_and_no_world_dependency(self):
        self.sim.control(dict(action='reset'))
        self.assertEqual(self.sim.state()['dashboard']['cards'], [])
        self.sim.control(dict(action='seek', at_ms=10000))
        with patch('tools.monitor_server.read_json', side_effect=AssertionError('no world reads')):
            state = self.sim.state()
        self.assertEqual({c['object_id'] for c in state['dashboard']['cards']},
                         {t['object_id'] for t in state['tracks']})
        encoded = json.dumps(state['dashboard'])
        for field in ('position', 'keyframes', 'hypotheses', 'engage_now'):
            self.assertNotIn(field, encoded)

    def test_wait_uses_shared_clock_and_arrives_only_after_30_seconds(self):
        before = copy.deepcopy(self.sim._public_input())
        self.sim.control(dict(action='play'))
        state = self.sim.control(self.command())
        pending = state['dashboard']['cards'][0]
        self.assertTrue(state['playing'])
        self.assertEqual(pending['next_review_at_ms'], 40000)
        self.assertIsNone(pending['followup']['result'])
        baseline = semantic_state(build_bundle(state))
        self.now += 29
        self.assertEqual(self.card()['followup']['status'], 'pending')
        self.now += 1
        state = self.sim.state()
        card = state['dashboard']['cards'][0]
        self.assertEqual(card['followup']['result'], 'scripted_visual_review')
        self.assertEqual(card['remaining_ms'], pending['remaining_ms']-30000)
        self.assertTrue(state['playing'])
        self.assertEqual(self.sim._public_input(), before)
        bundle = build_bundle(state)
        self.assertEqual(bundle['dashboard_review']['received'], 1)
        self.assertIn('dashboard_review', _evidence_tools(bundle)[3]())
        self.assertTrue(any(t['kind']=='dashboard_followup' for t in transitions(baseline, semantic_state(bundle))))
        self.assertNotIn('reviewer', json.dumps(bundle['dashboard_review']))

    def test_paused_clock_does_not_deliver_and_speed_scales_wait(self):
        self.sim.control(self.command())
        self.now += 60
        self.assertEqual(self.card()['followup']['status'], 'pending')
        self.sim.control(dict(action='speed', speed=4))
        self.sim.control(dict(action='play'))
        self.now += 7.5
        self.assertEqual(self.card()['followup']['status'], 'received')

    def test_guards_stale_versions_duplicate_hidden_and_expiry(self):
        good = self.command('raise_alert')
        for override in ({'confirm':False}, {'run_id':'old'}, {'object_id':'hidden'},
                         {'card_version':'old'}, {'choice':'fire'}):
            with self.assertRaises(ValueError):
                self.sim.control({**good, **override})
        self.assertFalse(self.sim.dashboard.audit.records)
        self.sim.control(good)
        with self.assertRaises(ValueError):
            self.sim.control(good)
        self.assertTrue(self.card()['priority'])
        self.sim.control(dict(action='play'))
        pending = self.command('dismiss', reason_code='bird')
        self.now += 90
        self.assertEqual(self.card()['status'], 'closed')
        with self.assertRaises(ValueError):
            self.sim.control(pending)

    def test_dismissal_is_opinion_not_track_deletion(self):
        with self.assertRaises(ValueError):
            self.sim.control(self.command('dismiss'))
        initial = len(self.sim.state()['tracks'])
        state = self.sim.control(self.command('dismiss', reason_code='bird'))
        self.assertEqual(len(state['tracks']), initial)
        self.assertEqual(self.card()['status'], 'closed')
        self.assertFalse(self.sim.dashboard.export()['records'][0]['fields']['reason']['classification_verified'])

    def test_material_change_invalidates_draft_but_routine_time_does_not(self):
        card = self.card()
        self.sim.control(dict(action='play'))
        self.now += 1
        self.assertEqual(self.card()['version'], card['version'])
        self.now += 1
        self.assertEqual(self.card()['version'], card['version'])
        self.sim.control(self.command())
        pending_version = self.card()['version']
        self.now += 30
        self.assertNotEqual(self.card()['version'], pending_version)

    def test_journal_is_durable_seven_fields_and_mock_notice_never_sends(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'dashboard.jsonl'
            self.sim.dashboard = DecisionDashboard(path)
            self.sim.control(dict(action='case', case_id='case_002'))
            self.sim.control(dict(action='seek', at_ms=60000))
            card = next(c for c in self.sim.state()['dashboard']['cards'] if c['status']=='needs_review')
            self.sim.control(dict(action='dashboard_action', run_id=self.sim.run_id, object_id=card['object_id'],
                card_version=card['version'], choice='notify_mock', confirm=True, comment='private-note', reviewer='private-alias'))
            export = DecisionDashboard(path).export()
            fields = export['records'][0]['fields']
            self.assertEqual(set(fields), {'event','evidence','assessment','uncertainty','decision','reason','time'})
            self.assertFalse(fields['decision']['outcome']['transmitted'])
            self.assertEqual(fields['decision']['outcome']['kind'], 'local_mock_notice')
            self.assertNotIn('private-', json.dumps(build_bundle(self.sim.state())))

    def test_reset_discards_active_followup_but_retains_audit(self):
        self.sim.control(self.command())
        self.sim.control(dict(action='reset'))
        self.assertEqual(self.sim.state()['dashboard']['recent'], [])
        self.assertEqual(len(self.sim.dashboard.export()['records']), 1)

    def test_write_failure_does_not_apply_or_schedule(self):
        with patch.object(self.sim.dashboard.audit, 'append', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                self.sim.control(self.command())
        self.assertIsNone(self.card()['followup'])

    def test_too_late_to_wait_is_disabled(self):
        self.sim.control(dict(action='seek', at_ms=80000))
        action = next(a for a in self.card()['actions'] if a['id']=='continue_observe')
        self.assertFalse(action['enabled'])
        self.assertEqual(action['reason'], 'too_late')


if __name__ == '__main__':
    unittest.main()
