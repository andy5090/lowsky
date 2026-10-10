import copy
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.decision_engine import DecisionAudit, DecisionBusy, OPTIONS, semantic_state, transitions
from tools.monitor_server import Simulation
from tools.situation_agent import build_bundle


class FakeClock:
    def __init__(self):
        self.value = 100.0

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += seconds


def report(state, event, language):
    evidence = [build_bundle(state)['observations']['id']]
    return dict(summary='Received evidence review', mode='rules', known=[], uncertain=[], review_items=[],
                decision_options=[dict(id=o['id'], reason='Local review choice', evidence_ids=evidence) for o in OPTIONS],
                recommended_option_id='hold_review')


class DecisionEngineTests(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.calls = []
        def evaluator(state, event, language):
            self.calls.append((copy.deepcopy(state), copy.deepcopy(event)))
            return report(state, event, language)
        self.sim = Simulation(clock=self.clock, decision_evaluator=evaluator,
                              assessment_configuration=lambda: {'mode': 'rules', 'configured': False})
        self.engine = self.sim.decisions

    def wait(self):
        if self.engine.worker:
            self.engine.worker.join(3)
            self.assertFalse(self.engine.worker.is_alive())

    def assess(self):
        self.engine.command(dict(action='assess_current', run_id=self.sim.run_id, language='en'))
        self.wait()
        return self.engine.snapshot()['events'][0]

    def confirmation(self, event, option='hold_review'):
        return dict(action='confirm', run_id=self.sim.run_id, event_id=event['id'],
                    evidence_version=event['evidence_version'], option_id=option,
                    reviewer='reviewer', reason='Evidence needs human attention', confirm=True)

    def test_first_received_outage_triggers_but_initial_online_does_not(self):
        from tools.decision_engine import transitions
        for kind, before, after in [('source_health', 'unknown', 'offline'), ('fleet_health', 'waiting', 'lost')]:
            previous = {(kind, 'sensor'): (before, [])}
            current = {(kind, 'sensor'): (after, ['received_loss'])}
            self.assertEqual(len(transitions(previous, current)), 1)
            self.assertEqual(transitions(previous, {(kind, 'sensor'): ('online', ['healthy'])}), [])

    def test_paused_gets_and_ack_do_not_start_provider(self):
        self.engine.snapshot()
        self.engine.tick()
        self.sim.state()
        self.assertEqual(self.calls, [])
        self.assertIsNone(self.engine.worker)

    def test_first_observation_pauses_exact_clock_and_no_automatic_effect(self):
        self.sim.control({'action': 'play'})
        self.clock.advance(10)
        self.engine.tick()
        self.wait()
        event = self.engine.snapshot()['events'][0]
        self.assertEqual(event['status'], 'ready')
        self.assertEqual(event['at_ms'], 10000)
        self.assertIn('first_tracks', [t['kind'] for t in event['triggers']])
        self.assertFalse(self.sim.playing)
        self.clock.advance(10)
        self.assertEqual(self.sim.clock_state()['at_ms'], 10000)
        self.assertEqual(self.engine.audit.records, [])
        self.assertNotIn('simulation_positions', self.calls[0][0])
        self.assertEqual(self.calls[0][0]['at_ms'], 10000)

    def test_confirmation_required_and_options_have_only_local_effects(self):
        event = self.assess()
        command = self.confirmation(event, 'continue_monitoring')
        for invalid in ({'confirm': False}, {'reason': None}, {'reviewer': None}, {'reason': 'x' * 1001}, {'reviewer': 'x' * 81}, {'option_id': 'send_alert'},
                        {'evidence_version': 'wrong'}, {'run_id': 'other'}):
            with self.assertRaises(ValueError):
                self.engine.command({**command, **invalid})
            self.assertFalse(self.sim.playing)
            self.assertEqual(self.engine.audit.records, [])
        self.engine.command(command)
        self.assertTrue(self.sim.playing)
        with self.assertRaises(ValueError):
            self.engine.command(command)
        self.assertEqual(len(self.engine.audit.records), 1)

    def test_hold_and_defer_decisions_persist_different_outcomes(self):
        held = self.assess()
        self.engine.command(self.confirmation(held))
        self.assertFalse(self.sim.playing)
        deferred = self.assess()
        self.engine.command(self.confirmation(deferred, 'defer'))
        self.assertTrue(self.sim.playing)
        self.assertEqual(self.engine.audit.records[-1]['outcome'], 'deferred')

    def test_confirmed_continue_at_end_uses_normal_play_new_run_behavior(self):
        self.sim.control({'action': 'seek', 'at_ms': 180000})
        old_run = self.sim.run_id
        event = self.assess()
        self.engine.command(self.confirmation(event, 'continue_monitoring'))
        self.assertTrue(self.sim.playing)
        self.assertEqual(self.sim.clock_state()['at_ms'], 0)
        self.assertNotEqual(self.sim.run_id, old_run)
        self.assertEqual(self.engine.audit.records[-1]['run_id'], old_run)

    def test_heartbeat_and_ack_dedupe_semantic_events(self):
        self.sim.control({'action': 'play'})
        self.clock.advance(10)
        self.engine.tick()
        self.wait()
        event = self.engine.snapshot()['events'][0]
        self.engine.command(self.confirmation(event, 'continue_monitoring'))
        self.clock.advance(1)
        self.engine.tick()
        self.assertEqual(len(self.calls), 1)
        alert = self.sim.state()['alerts']
        if alert:
            self.sim.control(dict(action='ack', run_id=self.sim.run_id, alert_id=alert[0]['id']))
        self.engine.tick()
        self.assertEqual(len(self.calls), 1)

    def test_seek_supersedes_and_old_confirmation_rejected(self):
        event = self.assess()
        old_command = self.confirmation(event)
        self.sim.control({'action': 'seek', 'at_ms': 5000})
        self.assertEqual(self.engine.snapshot()['events'][0]['status'], 'superseded')
        with self.assertRaises(ValueError):
            self.engine.command(old_command)
        newer = self.assess()
        self.assertEqual(newer['at_ms'], 5000)
        self.assertNotEqual(newer['id'], event['id'])

    def test_option_only_confirmation_records_human_without_inventing_a_comment(self):
        event = self.assess()
        command = self.confirmation(event)
        command.pop('reviewer')
        command.pop('reason')
        command['actor'] = {'type': 'automated_test'}
        self.engine.command(command)
        row = self.engine.audit.records[-1]
        self.assertEqual(row['reason'], '')
        self.assertEqual(row['reviewer'], '')
        self.assertEqual(row['actor'], {'type': 'human'})

    def test_play_drift_invalidates_old_card_even_without_new_observation(self):
        event = self.assess()
        self.sim.control({'action': 'play'})
        self.clock.advance(.001)
        with self.assertRaises(ValueError):
            self.engine.command(self.confirmation(event))
        self.assertEqual(self.engine.snapshot()['events'][0]['status'], 'superseded')

    def test_failure_pauses_and_retry_captures_current_input(self):
        def fail(*args):
            raise RuntimeError('secret credential provider detail')
        self.engine.evaluator = fail
        event = self.assess()
        self.assertEqual(event['status'], 'failed')
        self.assertNotIn('secret', event['error'])
        self.assertFalse(self.sim.playing)
        self.engine.evaluator = report
        self.engine.command(dict(action='retry', run_id=self.sim.run_id, event_id=event['id'], language='ko'))
        self.wait()
        retried = self.engine.snapshot()['events'][0]
        self.assertEqual(retried['status'], 'ready')
        self.assertEqual(retried['report']['language'], 'ko')
        self.assertEqual(self.engine.snapshot()['events'][1]['status'], 'superseded')

    def test_late_thread_result_discarded_after_reset_and_stop(self):
        entered, release = threading.Event(), threading.Event()
        def delayed(*args):
            entered.set()
            release.wait(3)
            return report(*args)
        self.engine.evaluator = delayed
        self.engine.command(dict(action='assess_current', run_id=self.sim.run_id, language='en'))
        self.assertTrue(entered.wait(1))
        with self.assertRaises(DecisionBusy):
            self.engine.command(dict(action='assess_current', run_id=self.sim.run_id, language='en'))
        self.sim.control({'action': 'reset'})
        release.set()
        self.wait()
        event = self.engine.snapshot()['events'][0]
        self.assertEqual(event['status'], 'superseded')
        self.assertIsNone(event['report'])

    def test_new_run_event_pauses_while_old_provider_finishes_then_evaluates(self):
        entered, release = threading.Event(), threading.Event()
        received = []
        def delayed(state, event, language):
            received.append((state['run_id'], state['at_ms']))
            if len(received) == 1:
                entered.set()
                release.wait(3)
            return report(state, event, language)
        self.engine.evaluator = delayed
        self.engine.command(dict(action='assess_current', run_id=self.sim.run_id, language='en'))
        self.assertTrue(entered.wait(1))
        old_worker = self.engine.worker
        self.sim.control({'action': 'reset'})
        self.sim.control({'action': 'play'})
        self.clock.advance(10)
        self.engine.tick()
        pending = self.engine.snapshot()['events'][0]
        self.assertEqual(pending['status'], 'pending')
        self.assertEqual(pending['at_ms'], 10000)
        self.assertFalse(self.sim.playing)
        self.clock.advance(5)
        self.assertEqual(self.sim.clock_state()['at_ms'], 10000)
        self.assertEqual(len(received), 1)
        release.set()
        old_worker.join(3)
        self.wait()
        latest = self.engine.snapshot()['events'][0]
        self.assertEqual(latest['status'], 'ready')
        self.assertEqual(latest['run_id'], self.sim.run_id)
        self.assertEqual(received[-1], (self.sim.run_id, 10000))
        self.assertEqual(self.engine.snapshot()['events'][1]['status'], 'superseded')
        self.assertIsNone(self.engine.snapshot()['events'][1]['report'])

    def test_history_is_current_run_but_export_retains_all_runs(self):
        event = self.assess()
        self.engine.command(self.confirmation(event))
        self.assertEqual(len(self.engine.snapshot()['history']), 1)
        self.sim.control({'action': 'reset'})
        self.assertEqual(self.engine.snapshot()['history'], [])
        self.assertEqual(len(self.engine.audit.export()['records']), 1)

    def test_persistence_failure_never_applies_replay_effect(self):
        event = self.assess()
        with patch.object(self.engine.audit, 'append', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                self.engine.command(self.confirmation(event, 'continue_monitoring'))
        self.assertFalse(self.sim.playing)
        self.assertEqual(self.engine.snapshot()['events'][0]['status'], 'ready')

    def test_audit_round_trip_contains_frozen_report_and_allowlisted_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'decisions.jsonl'
            self.engine.audit = DecisionAudit(path)
            event = self.assess()
            self.engine.command(self.confirmation(event))
            loaded = DecisionAudit(path).export()['records'][0]
            self.assertEqual(loaded['snapshot']['report']['summary'], 'Received evidence review')
            self.assertEqual(loaded['snapshot']['evidence']['input_version'], event['evidence_version'])
            self.assertNotIn('tracks', loaded['snapshot']['evidence'])
            self.assertNotIn('simulation_positions', str(loaded))
            path.write_text(path.read_text()[:-1])
            with self.assertRaises(ValueError):
                DecisionAudit(path)

    def test_disabled_mode_does_not_interrupt_and_config_validates(self):
        self.engine.command(dict(action='configure', run_id=self.sim.run_id, enabled=False, language='ko'))
        self.sim.control({'action': 'play'})
        self.clock.advance(10)
        self.engine.tick()
        self.assertTrue(self.sim.playing)
        self.assertEqual(self.calls, [])
        with self.assertRaises(ValueError):
            self.engine.command(dict(action='configure', run_id=self.sim.run_id, enabled=1, language='xx'))

    def test_semantic_transitions_ignore_initial_waiting_and_detect_recovery(self):
        previous = {('source_health', 'A'): ('unknown', []), ('fleet_health', 'g'): ('waiting', [])}
        online = {('source_health', 'A'): ('online', ['a']), ('fleet_health', 'g'): ('online', ['f'])}
        self.assertEqual(transitions(previous, online), [])
        lost = {('source_health', 'A'): ('offline', ['a2']), ('fleet_health', 'g'): ('lost', ['f2'])}
        self.assertEqual(len(transitions(online, lost)), 2)
        self.assertEqual(len(transitions(lost, online)), 2)
        self.assertEqual(transitions(online, online), [])

    def test_early_signal_escalation_clear_and_conflict_stale_are_batched(self):
        before = {('early_signal', 'z'): ('single', []), ('track_conflict', 'received_tracks'): (False, []),
                  ('track_stale', 'received_tracks'): (False, [])}
        after = {('early_signal', 'z'): ('conflicting', ['e']), ('track_conflict', 'received_tracks'): (True, ['t']),
                 ('track_stale', 'received_tracks'): (True, ['t'])}
        self.assertEqual(len(transitions(before, after)), 3)
        self.assertEqual(transitions(after, {('early_signal', 'z'): ('no_current_positive', ['e'])})[0]['previous'], 'conflicting')


if __name__ == '__main__':
    unittest.main()
