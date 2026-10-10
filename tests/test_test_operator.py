import threading
import unittest
from unittest.mock import patch

from tools.monitor_server import Simulation
from tools.decision_engine import OPTIONS


def assessment(state, event, language):
    return dict(summary='Synthetic received evidence', known=[], uncertain=[], review_items=[],
                decision_options=[dict(id=o['id'], reason='Local review', evidence_ids=['aggregate_test']) for o in OPTIONS],
                recommended_option_id='hold_review')


class TestOperatorTests(unittest.TestCase):
    def setUp(self):
        self.now = 100.0
        self.calls = []
        def runner(context, cancel):
            self.calls.append(context)
            return dict(option_id='continue_monitoring', reason='Continue the synthetic workflow test.')
        self.sim = Simulation(clock=lambda: self.now, decision_evaluator=assessment, operator_runner=runner,
                              operator_configuration=lambda: dict(available=True, model='test', provider='codex_cli'))
        self.sim.control(dict(action='case', case_id='case_003'))
        self.operator = self.sim.test_operator
        self.addCleanup(self.operator.cancel)

    def start_test(self):
        self.sim.control(dict(action='start_test', seed=42))

    def enable(self, limit=3):
        return self.operator.command(dict(action='start', run_id=self.sim.run_id, max_decisions=limit, confirm=True))

    def event(self):
        self.now += 15
        self.sim.decisions.tick()
        self.sim.decisions.worker.join(2)
        return self.sim.decisions.snapshot()['events'][0]

    def select(self):
        self.operator.tick()
        self.operator.worker.join(2)
        self.assertFalse(self.operator.worker.is_alive())

    def test_default_off_and_explicit_seeded_start_required(self):
        self.assertFalse(self.operator.snapshot()['active'])
        with self.assertRaises(ValueError):
            self.enable()
        self.start_test()
        for body in ({'action':'start','confirm':False}, {'action':'start','confirm':True,'max_decisions':11},
                     {'action':'start','confirm':True,'max_decisions':True}):
            with self.assertRaises(ValueError):
                self.operator.command(dict(run_id=self.sim.run_id, **body))
        self.event()
        self.operator.tick()
        self.assertEqual(self.calls, [])
        self.assertEqual(self.sim.decisions.audit.records, [])

    def test_automatic_choice_is_distinguished_and_journaled_before_resume(self):
        self.start_test()
        event = self.event()
        self.enable()
        self.select()
        row = self.sim.decisions.audit.records[-1]
        self.assertEqual(row['actor']['type'], 'automated_test')
        self.assertEqual(row['actor']['provider'], 'codex_cli')
        self.assertEqual(row['event_id'], event['id'])
        self.assertEqual(row['snapshot']['evidence']['test_run']['seed'], 42)
        self.assertTrue(self.sim.playing)
        self.assertEqual(self.operator.snapshot()['completed'], 1)
        self.assertNotIn('simulation_positions', self.calls[0])
        self.assertNotIn('evidence_bundle', self.calls[0]['report'])

    def test_limit_stops_only_automation(self):
        self.start_test(); self.event(); self.enable(1); self.select()
        self.assertEqual(self.operator.status, 'decision_limit')
        self.assertTrue(self.sim.playing)
        self.assertFalse(self.operator.active)

    def test_hold_ends_automation_instead_of_silently_resuming(self):
        self.operator.runner = lambda *_: dict(option_id='hold_review', reason='Hold this test for review.')
        self.start_test(); self.event(); self.enable(); self.select()
        self.assertEqual(self.operator.status, 'held')
        self.assertTrue(self.sim.playing)

    def test_stop_discards_inflight_choice(self):
        entered, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)
        def slow(context, cancel):
            entered.set(); release.wait(2)
            return dict(option_id='continue_monitoring', reason='Late answer')
        self.operator.runner = slow
        self.start_test(); self.event(); self.enable(); self.operator.tick()
        self.assertTrue(entered.wait(2))
        self.operator.command(dict(action='stop',run_id=self.sim.run_id))
        release.set(); self.operator.worker.join(2)
        self.assertEqual(self.sim.decisions.audit.records, [])
        self.assertTrue(self.sim.playing)
        self.assertEqual(self.operator.status, 'stopped')

    def test_expired_inflight_automatic_choice_is_rejected_without_pausing(self):
        entered, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)
        def slow(context, cancel):
            entered.set(); release.wait(2)
            return dict(option_id='continue_monitoring',reason='Late answer')
        self.operator.runner=slow
        self.start_test(); self.event(); self.enable(); self.operator.tick()
        self.assertTrue(entered.wait(1))
        self.now += 31
        release.set(); self.operator.worker.join(2)
        self.assertEqual(self.sim.decisions.audit.records,[])
        self.assertEqual(self.operator.status,'evidence_changed')
        self.assertTrue(self.sim.clock_state()['playing'])

    def test_new_test_cancels_old_operator(self):
        self.start_test(); self.enable()
        self.sim.control(dict(action='start_test', seed=43))
        self.assertFalse(self.operator.active)
        self.assertTrue(self.sim.playing)
        self.assertEqual(self.sim.decisions.audit.records, [])

    def test_manual_pause_and_checkpoint_disable_cancel(self):
        self.start_test(); self.enable()
        self.sim.control(dict(action='pause'))
        self.assertFalse(self.sim.playing)
        self.assertFalse(self.operator.active)
        self.enable()
        self.sim.decisions.command(dict(action='configure', run_id=self.sim.run_id, enabled=False, language='en'))
        self.assertFalse(self.operator.active)
        self.assertTrue(self.sim.playing)

    def test_failures_never_confirm_and_leave_simulation_running(self):
        self.operator.runner = lambda *_: dict(option_id='invented', reason='No')
        self.start_test(); self.event(); self.enable(); self.select()
        self.assertEqual(self.operator.status, 'failed')
        self.assertEqual(self.sim.decisions.audit.records, [])
        self.assertTrue(self.sim.playing)

    def test_journal_failure_never_applies_automatic_choice(self):
        self.start_test(); self.event(); self.enable()
        with patch.object(self.sim.decisions.audit, 'append', side_effect=OSError('disk failure')):
            self.select()
        self.assertEqual(self.operator.status, 'failed')
        self.assertTrue(self.sim.playing)
        self.assertEqual(self.operator.decisions, [])
        self.assertEqual(self.sim.decisions.snapshot()['events'][0]['status'], 'ready')

    def test_unavailable_cli_is_not_silently_replaced(self):
        self.operator.configuration = lambda: dict(available=False, model='test')
        self.start_test()
        with self.assertRaisesRegex(ValueError, 'not available'):
            self.enable()

    def test_time_and_completion_stop_without_more_decisions(self):
        self.start_test(); self.enable()
        self.operator.started -= 601
        self.operator.tick()
        self.assertEqual(self.operator.status, 'time_limit')
        self.start_test(); self.enable()
        self.now += 181
        self.operator.tick()
        self.assertEqual(self.operator.status, 'completed')
        self.assertEqual(self.calls, [])


if __name__ == '__main__':
    unittest.main()
