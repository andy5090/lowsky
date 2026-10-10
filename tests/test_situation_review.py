import copy
import json
import unittest
from pathlib import Path

from tools.monitor_server import Simulation
from tools.situation_review import snapshot

PROJECT = Path(__file__).resolve().parents[1]


class SituationReviewTests(unittest.TestCase):
    def setUp(self):
        self.sim = Simulation(clock=lambda: 0)

    def advance(self, at_ms):
        self.sim.anchor_ms = at_ms
        return self.sim.state()

    def review(self, event='context_first', **changes):
        command = dict(action='review_event', run_id=self.sim.run_id, event_id=event,
                       decision='needs_review', reason='Compare the received source records.')
        command.update(changes)
        return self.sim.control(command)

    def test_public_context_creates_neither_track_nor_alert(self):
        state = self.sim.state()
        self.assertEqual(state['tracks'], [])
        self.assertEqual(state['alerts'], [])
        self.assertEqual([e['id'] for e in state['situation']['events']], ['context_public'])
        self.assertEqual(state['situation']['summary']['recorded_reviews'], 0)
        self.assertIsNone(state['situation']['summary']['accuracy'])

    def test_future_and_unknown_object_context_remain_hidden(self):
        feed = copy.deepcopy(self.sim.situation_feed)
        first = next(e for e in feed['events'] if e['id'] == 'context_first')
        first['available_at_ms'] = 20000
        first['private_field'] = 'private-canary'
        for time, known in [(19999, ['object_11']), (20000, [])]:
            result = snapshot(feed, 'case_001', time, known, [])
            self.assertNotIn('context_first', [e['id'] for e in result['events']])
        result = snapshot(feed, 'case_001', 20000, ['object_11'], [])
        self.assertIn('context_first', [e['id'] for e in result['events']])
        self.assertNotIn('private-canary', json.dumps(result))
        self.assertNotIn('context_close', json.dumps(result))

    def test_case_specific_outage_and_conflict_context(self):
        for case, expected, absent in [('case_002', 'context_ambiguity', 'context_outage'),
                                      ('case_003', 'context_outage', 'context_ambiguity')]:
            self.sim.control(dict(action='case', case_id=case))
            self.assertNotIn(expected, [e['id'] for e in self.advance(59999)['situation']['events']])
            ids = [e['id'] for e in self.advance(60000)['situation']['events']]
            self.assertIn(expected, ids)
            self.assertNotIn(absent, ids)

    def test_only_actual_human_reviews_link_to_later_prompt(self):
        self.advance(10000)
        state = self.review()
        record = state['situation']['review_log'][0]
        self.assertEqual(set(record) - {'id','run_id','case_id'},
                         {'event_id','evidence_ids','assessment','uncertainty','decision','reason','reviewed_at_ms'})
        self.assertEqual(record['reviewed_at_ms'], 10000)
        self.assertEqual(record['decision'], 'needs_review')
        later = self.advance(150000)['situation']
        prompt = next(e for e in later['events'] if e['id'] == 'context_revisit')
        self.assertEqual(prompt['related_reviews'], [record])
        self.assertEqual(later['summary']['recorded_reviews'], 1)
        self.assertEqual(later['summary']['decisions']['needs_review'], 1)
        self.assertIsNone(later['summary']['accuracy'])
        clean = Simulation(clock=lambda: 0)
        clean.anchor_ms = 150000
        self.assertEqual(next(e for e in clean.state()['situation']['events']
                              if e['id'] == 'context_revisit')['related_reviews'], [])

    def test_review_validation_does_not_change_state(self):
        self.advance(10000)
        invalid = [{'event_id':'context_close'}, {'run_id':'stale'}, {'decision':'approve_weapon'},
                   {'reason':'a'*1001}, {'reason':None}]
        for change in invalid:
            before = self.sim.state()
            with self.assertRaises(ValueError): self.review(**change)
            self.assertEqual(self.sim.state(), before)

    def test_optional_comment_accepts_decision_without_typing(self):
        self.advance(10000)
        self.review(reason='')
        self.assertEqual(self.sim.state()['situation']['review_log'][-1]['reason'],'')

    def test_rewind_and_case_reset_isolate_review_history(self):
        self.advance(10000)
        self.review()
        old_run = self.sim.run_id
        state = self.sim.control(dict(action='seek', at_ms=5000))
        self.assertEqual(state['situation']['review_log'], [])
        with self.assertRaises(ValueError): self.review(run_id=old_run)
        self.advance(150000)
        self.assertEqual(self.sim.state()['situation']['summary']['recorded_reviews'], 0)

    def test_all_context_sources_resolve_and_three_cases_remain(self):
        catalog = json.loads((PROJECT/'data/references/ukraine_observation_lessons.json').read_text())
        ids = {s['id'] for s in catalog['sources']}
        self.assertEqual(len(self.sim.cases), 3)
        briefs = json.loads((PROJECT/'data/scenarios/v1/briefings.json').read_text())['cases']
        self.assertEqual(sum(b['scenario_type'] == 'load_test' for b in briefs), 1)
        for row in self.sim.situation_feed['events']:
            self.assertTrue(set(row['source_ids']) <= ids)
            self.assertLessEqual(row['available_at_ms'], 180000)
            for key in ['title','summary','uncertainty','story_time']:
                self.assertEqual(set(row[key]), {'en','ko'})


if __name__ == '__main__':
    unittest.main()
