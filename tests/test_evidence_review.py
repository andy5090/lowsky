import json
import tempfile
import unittest
from pathlib import Path

from tools.evidence_review import AuditLog, digest
from tools.monitor_server import Simulation


class EvidenceReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'audit.jsonl'
        self.sim = Simulation(clock=lambda: 0, audit_path=self.path)

    def state(self, at_ms=60000, case_id='case_001'):
        self.sim.control(dict(action='case', case_id=case_id))
        return self.sim.control(dict(action='seek', at_ms=at_ms))

    def command(self, state):
        track = state['tracks'][0]
        return dict(action='review_track', run_id=state['run_id'], object_id=track['object_id'],
                    evidence_version=track['evidence_version'], reviewer='Operator One',
                    decision='needs_review', reason='Compare the received sources.')

    def test_explanation_changes_when_received_marker_changes(self):
        state = self.state()
        track = state['tracks'][0]
        self.assertEqual(track['explanation']['evidence_status'], 'corroborated')
        selected_id = track['records'][0]['id']
        selected = next(row for row in self.sim.public[self.sim.case_id]['observations'] if row['id'] == selected_id)
        selected['marker_label'] = 'changed'
        changed = self.sim.state()['tracks'][0]
        self.assertEqual(changed['explanation']['evidence_status'], 'conflicting')
        self.assertNotEqual(changed['evidence_version'], track['evidence_version'])
        self.assertIn('marker_conflict', [item['code'] for item in changed['explanation']['uncertain']])
        self.assertEqual(changed['explanation']['object_type_assessment'], 'unknown')
        self.assertEqual(changed['explanation']['intent_assessment'], 'unknown')

    def test_offline_stale_missing_are_not_absence_or_classification(self):
        state = self.state(90000, 'case_003')
        explanation = state['tracks'][0]['explanation']
        self.assertEqual(explanation['evidence_status'], 'incomplete')
        self.assertIn('source_offline', [item['code'] for item in explanation['missing']])
        public = self.sim.public[self.sim.case_id]
        public['observations'] = [row for row in public['observations'] if row['observed_at_ms'] <= 10000]
        public['source_health'] = [row for row in public['source_health'] if row['observed_at_ms'] <= 10000]
        explanation = self.sim.state()['tracks'][0]['explanation']
        self.assertEqual(explanation['observation_status'], 'last_known')
        self.assertIn('source_stale', [item['code'] for item in explanation['missing']])
        self.assertIn('observation_stale', [item['code'] for item in explanation['missing']])
        self.assertIn('current_position_unknown', [item['code'] for item in explanation['uncertain']])
        self.assertNotIn('absent', json.dumps(explanation))

    def test_evidence_hash_stable_between_receipts_and_changes_on_freshness(self):
        public = self.sim.public[self.sim.case_id]
        public['observations'] = [row for row in public['observations'] if row['observed_at_ms'] == 10000]
        public['source_health'] = [row for row in public['source_health'] if row['observed_at_ms'] == 10000]
        first = self.state(55000)['tracks'][0]['evidence_version']
        self.sim.anchor_ms = 55001
        stale = self.sim.state()['tracks'][0]['evidence_version']
        self.assertNotEqual(first, stale)
        self.sim.anchor_ms = 55002
        self.assertEqual(stale, self.sim.state()['tracks'][0]['evidence_version'])

    def test_review_persists_full_received_basis_and_survives_restart(self):
        state = self.state(60000)
        command = self.command(state)
        reviewed = self.sim.control(command)
        self.assertEqual(reviewed['review_summary']['total_saved'], 1)
        self.assertEqual(reviewed['review_summary']['by_decision']['needs_review'], 1)
        self.assertNotIn('evidence_snapshot', reviewed['track_reviews'][0])
        record = self.sim.audit.export()['records'][0]
        self.assertEqual(record['evidence_version'], digest(record['evidence_snapshot']))
        self.assertGreater(record['reviewed_at_unix_ms'], 0)
        self.assertEqual(record['reviewer'], 'Operator One')
        self.assertGreater(len(record['evidence_snapshot']['observations']), 2)
        restored = Simulation(clock=lambda: 0, audit_path=self.path)
        self.assertEqual(restored.audit.export()['records'], [record])
        self.assertEqual(restored.state()['track_reviews'], [])
        self.assertEqual(restored.state()['review_summary']['total_saved'], 1)
        exported = self.sim.audit.export()
        exported['records'][0]['reason'] = 'mutated'
        self.assertEqual(self.sim.audit.export()['records'][0], record)
        self.sim.public['case_001']['observations'][0]['marker_label'] = 'modified later'
        self.assertEqual(self.sim.audit.export()['records'][0], record)

    def test_stale_run_changed_evidence_and_invalid_review_rejected(self):
        state = self.state()
        command = self.command(state)
        for patch in ({'run_id': 'old'}, {'evidence_version': 'old'}, {'object_id': 'unreceived'},
                      {'reviewer': None}, {'reviewer': 'x' * 81},
                      {'reason': 'x' * 1001}, {'decision': 'attack'}, {'reason': None}):
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                self.sim.control({**command, **patch})
        self.assertFalse(self.path.exists())
        public = self.sim.public[self.sim.case_id]
        row_id = state['tracks'][0]['records'][0]['id']
        next(row for row in public['observations'] if row['id'] == row_id)['position'] = [1, 2, 3]
        with self.assertRaisesRegex(ValueError, 'Evidence changed'):
            self.sim.control(command)
        self.assertEqual(self.sim.audit.export()['records'], [])

    def test_optional_reviewer_and_comment_do_not_require_typing(self):
        state=self.state()
        command=self.command(state)
        command.pop('reviewer'); command.pop('reason')
        self.sim.control(command)
        saved=self.sim.audit.records[-1]
        self.assertEqual(saved['reviewer'],'')
        self.assertEqual(saved['reason'],'')
        self.assertEqual(saved['decision'],command['decision'])

    def test_future_and_world_annotations_never_enter_explanation_or_audit(self):
        public = self.sim.public[self.sim.case_id]
        for row in public['observations']:
            row['ground_truth'] = 'private-canary'
            if row['observed_at_ms'] > 10000:
                row['marker_label'] = 'future-canary'
        public['source_health'][0]['answer'] = 'private-canary'
        self.assertEqual(self.sim.state()['tracks'], [])
        state = self.state(15000)
        self.sim.control(self.command(state))
        encoded = json.dumps(self.sim.audit.export())
        for token in ('private-canary', 'future-canary', 'ground_truth', 'world_truth', 'simulation_positions'):
            self.assertNotIn(token, encoded)
        record = self.sim.audit.export()['records'][0]
        for row in record['evidence_snapshot']['observations']:
            self.assertLessEqual(row['available_at_ms'], 15000)
        for ref in state['tracks'][0]['explanation']['evidence']:
            self.assertLessEqual(ref['available_at_ms'], 15000)

    def test_corrupt_audit_fails_closed_without_overwriting(self):
        self.path.write_text('{broken\n', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'Invalid audit record at line 1'):
            AuditLog(self.path)
        self.assertEqual(self.path.read_text(), '{broken\n')

    def test_incomplete_final_line_is_not_joined_to_a_new_review(self):
        state = self.state()
        self.sim.control(self.command(state))
        contents = self.path.read_text().rstrip('\n')
        self.path.write_text(contents, encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'Incomplete final audit record'):
            AuditLog(self.path)
        self.assertEqual(self.path.read_text(), contents)

    def test_review_snapshots_append_instead_of_replacing(self):
        state = self.state()
        command = self.command(state)
        self.sim.control(command)
        self.sim.control({**command, 'decision': 'noted', 'reason': 'Second independent review'})
        self.assertEqual(len(self.path.read_text().splitlines()), 2)
        restored = AuditLog(self.path)
        self.assertEqual([item['decision'] for item in restored.records], ['needs_review', 'noted'])


if __name__ == '__main__':
    unittest.main()
