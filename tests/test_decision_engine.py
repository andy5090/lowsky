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
        self.sim.control({'action': 'case', 'case_id': 'case_003'})
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

    def paced_early_fixture(self):
        template = self.sim.state()
        template.update(tracks=[], sources=[], sensor_fleet={'sensors': []}, dashboard={'cards': []},
                        training_timing={'paced': True, 'early_review_ms': 120000, 'received_review_ms': 90000})
        template['early_warning'] = dict(freshness_ms=180000, zones=[dict(id='early_zone', evidence=[dict(
            id='indirect_1', sensor_id='phone_a', observed_at_ms=10000, available_at_ms=10000,
            assessment='current', object_present=True)])])
        self.sim.public[self.sim.case_id]['duration_ms'] = 600000
        self.sim.public[self.sim.case_id]['training_timing'] = template['training_timing']
        def current():
            return {**copy.deepcopy(template), **self.sim._clock_state()}
        override = patch.object(self.sim, 'state', side_effect=current)
        override.start()
        self.addCleanup(override.stop)
        return template

    def test_early_choices_exist_without_tracks_with_two_minute_window_and_no_pause(self):
        self.paced_early_fixture()
        self.sim.control({'action': 'play'})
        self.clock.advance(10)
        self.engine.tick(); self.wait()
        event = self.engine.snapshot()['events'][0]
        self.assertEqual(event['stage'], 'early_indication')
        self.assertEqual(event['review_window_ms'], 120000)
        self.assertEqual(event['expires_at_ms'], 130000)
        self.assertEqual(len(event['choice_report']['decision_options']), 3)
        self.assertEqual(self.calls[0][0]['tracks'], [])
        self.assertIn('independent', event['choice_report']['uncertain'][-1]['text'])
        self.clock.advance(60)
        self.assertEqual(self.engine.snapshot()['events'][0]['status'], 'ready')
        self.assertFalse(self.engine.snapshot()['events'][0]['new_evidence_available'])
        self.engine.command(self.confirmation(event, 'hold_review'))
        self.assertTrue(self.sim.playing)
        self.assertEqual(self.sim._time(), 70000)
        self.assertEqual(self.engine.audit.records[-1]['snapshot']['evidence']['observations']['total'], 0)

    def test_new_indirect_receipt_stays_discoverable_without_invalidating_choice(self):
        template = self.paced_early_fixture()
        self.sim.control({'action': 'play'})
        self.clock.advance(10)
        self.engine.tick(); self.wait()
        event = self.engine.snapshot()['events'][0]
        self.clock.advance(40)
        template['early_warning']['zones'][0]['evidence'][0].update(
            id='indirect_renewed', observed_at_ms=50000, available_at_ms=50000)
        self.engine.tick()
        current = self.engine.snapshot()['events'][0]
        self.assertEqual(current['id'], event['id'])
        self.assertEqual(current['status'], 'ready')
        self.assertTrue(current['new_evidence_available'])
        self.assertEqual(current['latest_evidence_at_ms'], 50000)
        self.assertEqual(len(self.calls), 1)
        self.engine.command(self.confirmation(event))
        saved = self.engine.audit.records[-1]['snapshot']
        self.assertEqual(saved['evidence']['early_signals'][0]['reports'][0]['id'], 'indirect_1')
        self.assertEqual(saved['current_evidence']['early_signals'][0]['reports'][0]['id'], 'indirect_renewed')

    def test_first_direct_observation_closes_pretrack_choices_and_opens_90_second_window(self):
        template = self.paced_early_fixture()
        self.sim.control({'action': 'play'})
        self.clock.advance(10)
        self.engine.tick(); self.wait()
        early = self.engine.snapshot()['events'][0]
        self.clock.advance(70)
        template['sources'] = [dict(source_id='A', evidence=dict(
            id='health_direct', status='online', observed_at_ms=80000, available_at_ms=80000))]
        template['tracks'] = [dict(object_id='received_object', evidence_version='test', records=[dict(
            id='direct_receipt', source_id='A', observed_at_ms=80000, available_at_ms=80000, marker_label='unknown')])]
        self.engine.tick(); self.wait()
        events = self.engine.snapshot()['events']
        self.assertEqual(events[0]['stage'], 'received_observation')
        self.assertEqual(events[0]['review_window_ms'], 90000)
        self.assertEqual(events[0]['expires_at_ms'], 170000)
        old = next(event for event in events if event['id'] == early['id'])
        self.assertEqual(old['status'], 'expired')
        self.assertEqual(old['expiration_reason'], 'situation_changed')
        with self.assertRaises(ValueError):
            self.engine.command(self.confirmation(early))
        self.assertTrue(self.sim.playing)

    def test_paced_early_deadline_expires_at_120_seconds_without_clock_control(self):
        self.paced_early_fixture()
        self.sim.control({'action': 'play'})
        self.clock.advance(10)
        self.engine.tick(); self.wait()
        event = self.engine.snapshot()['events'][0]
        self.clock.advance(119)
        self.assertEqual(self.engine.snapshot()['events'][0]['status'], 'ready')
        self.clock.advance(1)
        with self.assertRaises(ValueError):
            self.engine.command(self.confirmation(event))
        self.assertEqual(self.engine.snapshot()['events'][0]['expiration_reason'], 'deadline')
        self.assertTrue(self.sim.playing)

    def test_paced_scenario_opens_early_review_and_keeps_renewed_question_open(self):
        self.sim.control({'action': 'case', 'case_id': 'case_001'})
        self.sim.control({'action': 'play'})
        self.clock.advance(30)
        self.engine.tick(); self.wait()
        early = self.engine.snapshot()['events'][0]
        self.assertEqual(self.sim.state()['tracks'], [])
        self.assertEqual(early['stage'], 'early_indication')
        self.assertEqual(early['expires_at_ms'], 150000)
        for seconds in (50, 50):
            self.clock.advance(seconds)
            self.engine.tick(); self.wait()
            renewed = next(event for event in self.engine.snapshot()['events'] if event['id'] == early['id'])
            self.assertEqual(renewed['status'], 'ready')
            self.assertTrue(renewed['new_evidence_available'])
            self.assertEqual(self.sim.state()['tracks'], [])
        self.engine.command(self.confirmation(early, 'continue_monitoring'))
        self.assertEqual(self.sim._time(), 130000)
        self.assertTrue(self.sim.playing)
        self.clock.advance(95)
        self.engine.tick(); self.wait()
        pretrack = self.engine.snapshot()['events'][0]
        self.assertEqual(pretrack['stage'], 'early_indication')
        self.assertEqual(self.sim.state()['tracks'], [])
        self.clock.advance(45)
        self.engine.tick(); self.wait()
        direct = self.engine.snapshot()['events'][0]
        self.assertEqual(direct['stage'], 'received_observation')
        self.assertEqual(direct['review_window_ms'], 90000)
        self.assertTrue(self.sim.state()['tracks'])
        previous = next(event for event in self.engine.snapshot()['events'] if event['id'] == pretrack['id'])
        self.assertEqual(previous['status'], 'expired')
        self.assertTrue(self.sim.playing)

    def test_first_received_outage_triggers_but_initial_online_does_not(self):
        from tools.decision_engine import transitions
        for kind, before, after in [('source_health', 'unknown', 'offline'), ('fleet_health', 'waiting', 'lost')]:
            previous = {(kind, 'sensor'): (before, [])}
            current = {(kind, 'sensor'): (after, ['received_loss'])}
            self.assertEqual(len(transitions(previous, current)), 1)
            self.assertEqual(transitions(previous, {(kind, 'sensor'): ('online', ['healthy'])}), [])

    def test_standard_choices_are_immediate_and_late_model_result_cannot_replace_confirmation(self):
        entered, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)
        def slow(*args):
            entered.set();release.wait(3)
            return report(*args)
        self.engine.evaluator=slow
        self.engine.command(dict(action='assess_current',run_id=self.sim.run_id))
        self.assertTrue(entered.wait(1))
        event=self.engine.snapshot()['events'][0]
        self.assertEqual(event['status'],'evaluating')
        self.assertEqual(len(event['choice_report']['decision_options']),3)
        self.assertIsNone(event['choice_report']['recommended_option_id'])
        self.engine.command(self.confirmation(event))
        self.assertEqual(self.engine.audit.records[-1]['snapshot']['report']['mode'],'standard')
        release.set();self.wait()
        self.assertEqual(self.engine.snapshot()['events'][0]['status'],'decided')
        self.assertIsNone(self.engine.snapshot()['events'][0]['report'])

    def test_failed_agent_still_allows_explicit_standard_review(self):
        def fail(*args): raise RuntimeError('provider unavailable')
        self.engine.evaluator=fail
        event=self.assess()
        self.assertEqual(event['status'],'failed')
        self.engine.command(self.confirmation(event,'defer'))
        saved=self.engine.audit.records[-1]
        self.assertEqual(saved['snapshot']['report']['mode'],'standard')
        self.assertEqual(saved['outcome'],'deferred')

    def test_unrelated_new_signal_does_not_expire_first_track_choice(self):
        self.sim.control({'action':'play'})
        self.clock.advance(10);self.engine.tick();self.wait()
        event=self.engine.snapshot()['events'][0]
        self.clock.advance(5);self.engine.tick();self.wait()
        old=next(e for e in self.engine.snapshot()['events'] if e['id']==event['id'])
        self.assertEqual(old['status'],'ready')
        self.engine.command(self.confirmation(old))
        self.assertTrue(self.sim.playing)

    def test_paused_gets_and_ack_do_not_start_provider(self):
        self.engine.snapshot()
        self.engine.tick()
        self.sim.state()
        self.assertEqual(self.calls, [])
        self.assertIsNone(self.engine.worker)

    def test_first_observation_keeps_clock_running_and_no_automatic_decision(self):
        self.sim.control({'action': 'play'})
        self.clock.advance(10)
        self.engine.tick()
        self.wait()
        event = self.engine.snapshot()['events'][0]
        self.assertEqual(event['status'], 'ready')
        self.assertEqual(event['at_ms'], 10000)
        self.assertIn('first_tracks', [t['kind'] for t in event['triggers']])
        self.assertTrue(self.sim.playing)
        self.clock.advance(10)
        self.assertEqual(self.sim.clock_state()['at_ms'], 20000)
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
        self.assertFalse(self.sim.playing)
        with self.assertRaises(ValueError):
            self.engine.command(command)
        self.assertEqual(len(self.engine.audit.records), 1)

    def test_hold_and_defer_decisions_persist_different_outcomes(self):
        held = self.assess()
        self.engine.command(self.confirmation(held))
        self.assertFalse(self.sim.playing)
        deferred = self.assess()
        self.engine.command(self.confirmation(deferred, 'defer'))
        self.assertFalse(self.sim.playing)
        self.assertEqual(self.engine.audit.records[-1]['outcome'], 'deferred')

    def test_expired_end_card_cannot_restart_run(self):
        self.sim.control({'action': 'seek', 'at_ms': 180000})
        old_run = self.sim.run_id
        event = self.assess()
        with self.assertRaises(ValueError):
            self.engine.command(self.confirmation(event, 'continue_monitoring'))
        self.assertFalse(self.sim.clock_state()['playing'])
        self.assertEqual(self.sim.clock_state()['at_ms'], 180000)
        self.assertEqual(self.sim.run_id, old_run)
        self.assertEqual(self.engine.audit.records, [])

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

    def test_clock_drift_keeps_card_valid_and_confirmation_never_rewinds(self):
        self.sim.control({'action': 'play'})
        self.clock.advance(10)
        event = self.assess()
        self.clock.advance(1)
        self.engine.command(self.confirmation(event))
        self.assertTrue(self.sim.playing)
        self.assertEqual(self.sim.clock_state()['at_ms'], 11000)
        row = self.engine.audit.records[-1]
        self.assertEqual(row['at_ms'], 10000)
        self.assertEqual(row['decided_at_simulation_ms'], 11000)
        self.assertEqual(row['snapshot']['evidence']['at_ms'], 10000)

    def test_all_choices_preserve_running_clock_and_manual_pause(self):
        for option in ('continue_monitoring','hold_review','defer'):
            with self.subTest(option=option):
                self.sim.control({'action':'reset'})
                self.sim.control({'action':'play'})
                self.clock.advance(10)
                event=self.assess()
                self.clock.advance(1)
                self.engine.command(self.confirmation(event, option))
                self.assertTrue(self.sim.clock_state()['playing'])
                self.assertEqual(self.sim.clock_state()['at_ms'],11000)
                self.sim.control({'action':'pause'})
                event=self.assess()
                self.clock.advance(1)
                self.engine.command(self.confirmation(event, option))
                self.assertFalse(self.sim.clock_state()['playing'])
                self.assertEqual(self.sim.clock_state()['at_ms'],11000)

    def test_deadline_rejects_late_confirmation_without_pausing(self):
        self.sim.control({'action': 'play'})
        event = self.assess()
        self.clock.advance(30)
        with self.assertRaises(ValueError):
            self.engine.command(self.confirmation(event))
        expired = self.engine.snapshot()['events'][0]
        self.assertEqual(expired['status'], 'expired')
        self.assertEqual(expired['expiration_reason'], 'deadline')
        self.assertTrue(self.sim.playing)
        self.assertEqual(self.engine.audit.records, [])

    def test_material_situation_change_expires_card_and_captures_new_event(self):
        self.sim.control({'action': 'play'})
        event = self.assess()
        self.clock.advance(10)
        self.engine.tick()
        self.wait()
        old = next(e for e in self.engine.snapshot()['events'] if e['id']==event['id'])
        self.assertEqual(old['status'], 'expired')
        self.assertEqual(old['expiration_reason'], 'situation_changed')
        self.assertEqual(self.engine.snapshot()['events'][0]['status'], 'ready')
        with self.assertRaises(ValueError):
            self.engine.command(self.confirmation(event))
        self.assertTrue(self.sim.playing)

    def test_slow_assessment_does_not_stop_clock_and_late_result_is_discarded(self):
        entered, release = threading.Event(), threading.Event()
        def slow(*args):
            entered.set(); release.wait(3)
            return report(*args)
        self.engine.evaluator = slow
        self.sim.control({'action':'play'})
        self.engine.command(dict(action='assess_current',run_id=self.sim.run_id))
        self.assertTrue(entered.wait(1))
        self.clock.advance(31)
        self.assertEqual(self.sim.clock_state()['at_ms'],31000)
        release.set(); self.wait()
        event = self.engine.snapshot()['events'][0]
        self.assertEqual(event['status'],'expired')
        self.assertIsNone(event['report'])
        self.assertTrue(self.sim.playing)

    def test_failure_preserves_playback_and_retry_captures_current_input(self):
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

    def test_new_run_event_advances_while_old_provider_finishes_then_evaluates(self):
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
        self.assertTrue(self.sim.playing)
        self.clock.advance(1)
        self.assertEqual(self.sim.clock_state()['at_ms'], 11000)
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
