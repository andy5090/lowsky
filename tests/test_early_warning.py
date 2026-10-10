import copy
import json
import unittest
from pathlib import Path

from tools.early_warning import assess, snapshot
from tools.monitor_server import Simulation


class EarlyWarningTests(unittest.TestCase):
    def setUp(self):
        self.feed = json.loads((Path(__file__).resolve().parents[1] / 'data/early_warning_demo.json').read_text())

    def area(self, at_ms, index=0):
        return snapshot(self.feed, at_ms)[0]['zones'][index]

    def test_delayed_report_is_invisible_before_arrival(self):
        self.assertEqual(self.area(9999)['evidence'], [])
        self.assertEqual(self.area(21999)['status'], 'single')
        self.assertEqual(self.area(22000)['status'], 'corroborated')
        self.assertEqual(self.area(22000)['positive_sources'], 2)
        self.assertEqual(self.area(22000)['radar_association'], 'unknown')

    def test_conflict_and_expiry_do_not_mean_confirmed_attack_or_all_clear(self):
        self.assertEqual(self.area(28000)['status'], 'conflicting')
        self.assertEqual(self.area(42000)['status'], 'corroborated')
        self.assertEqual(self.area(72000)['status'], 'single')
        self.assertEqual(self.area(72001)['status'], 'stale')
        self.assertFalse(snapshot(self.feed, 72001)[1])

    def test_offline_invalid_and_negative_are_distinct(self):
        self.assertEqual(self.area(80000, 1)['evidence'][0]['assessment'], 'unavailable')
        self.assertEqual(self.area(20000, 2)['evidence'][0]['assessment'], 'no_measurement')
        self.assertEqual(self.area(55000, 2)['status'], 'no_signal')
        self.assertEqual(self.area(55000, 2)['evidence'][0]['object_present'], False)

    def test_invalid_or_future_clock_cannot_trigger_alert(self):
        row = copy.deepcopy(self.feed['observations'][0])
        for bad, expected in [('bad', 'invalid_time'), (True, 'invalid_time'), (-1, 'invalid_time'), (90000, 'future_time')]:
            row['observed_at_ms'] = bad
            self.assertEqual(assess(row, 10000, 30000), expected)
            self.feed['observations'] = [row]
            self.assertFalse(snapshot(self.feed, 10000)[1])

    def test_duplicate_source_does_not_count_as_independent_evidence(self):
        row = copy.deepcopy(self.feed['observations'][0])
        row.update(id='duplicate', available_at_ms=11000)
        self.feed['observations'].append(row)
        self.assertEqual(self.area(12000)['positive_sources'], 1)
        self.assertEqual(self.area(12000)['status'], 'single')

    def test_late_old_observation_does_not_replace_newer_evidence(self):
        row = copy.deepcopy(self.feed['observations'][0])
        row.update(id='late-old-report', available_at_ms=45000)
        row['measurement']['object_present'] = False
        self.feed['observations'].append(row)
        self.assertEqual(self.area(45000)['status'], 'corroborated')
        self.assertNotIn('late-old-report', [e['id'] for e in self.area(45000)['evidence']])

    def test_reference_specs_resolve_without_claiming_detector_performance(self):
        path = Path(__file__).resolve().parents[1] / self.feed['spec_catalog']
        catalog = json.loads(path.read_text())
        profiles = {p['id']: p for p in catalog['profiles']}
        self.assertFalse(catalog['hardware_selected'])
        for row in self.feed['observations']:
            profile = profiles[row['sensor_spec_id']]
            self.assertEqual(profile['input_type'], row['sensor_type'])
            self.assertIsNone(profile['detector_performance']['detection_range_m'])

    def test_private_fields_and_unbounded_confidence_are_not_exported(self):
        row = self.feed['observations'][0]
        row.update(raw_audio='private-canary', phone_number='private-canary', ground_truth='private-canary')
        row['quality']['classifier_score'] = float('nan')
        state = self.area(10000)
        self.assertIsNone(state['evidence'][0]['classifier_score'])
        self.assertNotIn('private-canary', json.dumps(state))

    def test_ack_is_evidence_specific_and_records_a_review(self):
        sim = Simulation(early_feed=self.feed)
        state = sim.control({'action': 'seek', 'at_ms': 10000})
        warning = next(a for a in state['alerts'] if a['kind'] == 'early_warning')
        acknowledged = sim.control({'action': 'ack', 'run_id': state['run_id'], 'alert_id': warning['id']})
        self.assertTrue(next(a for a in acknowledged['alerts'] if a['id'] == warning['id'])['acknowledged'])
        self.assertEqual(acknowledged['reviews'][0]['at_ms'], 10000)
        self.assertGreater(acknowledged['reviews'][0]['reviewed_at_unix_ms'], 0)
        # Advance same run without seeking; new corroborating evidence must alert again.
        sim.anchor_ms = 22000
        state = sim.state()
        warning = next(a for a in state['alerts'] if a['kind'] == 'early_warning')
        self.assertFalse(warning['acknowledged'])
        reset = sim.control({'action': 'reset'})
        self.assertEqual(reset['reviews'], [])
        self.assertEqual(reset['early_warning']['zones'][0]['evidence'], [])


if __name__ == '__main__':
    unittest.main()
