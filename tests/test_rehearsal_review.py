import copy
import tempfile
import unittest
from pathlib import Path

from tools.decision_engine import DecisionAudit
from tools.evidence_review import digest
from tools.rehearsal_review import export_run, summarize


def record(run='old', actor='human', option='hold_review'):
    snapshot = dict(event=dict(id='event', triggers=[dict(kind='manual_review')]),
        evidence=dict(observations={'total': 2}, test_run=dict(mode='seeded', seed=42, input_digest='same-inputs')),
        report=dict(summary='Received reports disagree', known=[], uncertain=[dict(text='Identity unknown')],
                    decision_options=[], recommended_option_id='hold_review', mode='rules', language='en'))
    return dict(schema_version=1, kind='event_decision', id=run+actor, run_id=run, case_id='case_001',
        event_id='event', actor={'type':actor}, option_id=option, outcome='confirmed',
        reviewer='', reason='', at_ms=10000, decided_at_unix_ms=1234,
        evidence_version='received-only-version', snapshot=snapshot, snapshot_hash=digest(snapshot))


class RehearsalReviewTests(unittest.TestCase):
    def setUp(self):
        self.clock = dict(run_id='current', case_id='case_002', test_run=dict(mode='seeded',seed=99))

    def test_current_empty_run_and_separate_actor_counts(self):
        result = summarize([record(),record(actor='automated_test',option='defer')],self.clock)
        self.assertEqual(result['runs'][0]['run_id'],'current')
        self.assertEqual(result['runs'][0]['decisions'],0)
        old = result['runs'][1]
        self.assertEqual(old['actors'],dict(human=1,automated_test=1,unknown=0))
        self.assertEqual(old['choices'],dict(continue_monitoring=0,hold_review=1,defer=1))
        self.assertNotIn('score',old)
        self.assertNotIn('reason',old)

    def test_same_seed_does_not_merge_distinct_runs(self):
        result = summarize([record('a'),record('b')],self.clock)
        self.assertEqual(result['total_runs'],3)
        self.assertEqual([r['decisions'] for r in result['runs']],[0,1,1])

    def test_export_seven_fields_preserves_original_uncertainty_blank_comment_and_provenance(self):
        source=record()
        source['snapshot']['unused_private_author_data']='must not copy'
        result=export_run([source,record('other')],'old',self.clock)
        self.assertEqual(len(result['records']),1)
        entry=result['records'][0]
        self.assertEqual(set(entry['fields']),{'event','evidence','assessment','uncertainty','decision','reason','time'})
        self.assertEqual(entry['fields']['reason'],'')
        self.assertEqual(entry['fields']['uncertainty'][0]['text'],'Identity unknown')
        self.assertEqual(entry['fields']['evidence']['test_run']['seed'],42)
        self.assertEqual(entry['snapshot_hash'],source['snapshot_hash'])
        self.assertNotIn('unused_private_author_data',str(result))
        entry['fields']['evidence']['test_run']['seed']=1
        self.assertEqual(source['snapshot']['evidence']['test_run']['seed'],42)

    def test_unknown_run_rejected_and_empty_current_export_allowed(self):
        with self.assertRaises(ValueError): export_run([], 'missing',self.clock)
        self.assertEqual(export_run([], 'current',self.clock)['records'],[])

    def test_legacy_human_records_reload_from_durable_journal(self):
        row=record();row.pop('actor')
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'journal.jsonl'
            DecisionAudit(path).append(row)
            records=DecisionAudit(path).records
        self.assertEqual(summarize(records,self.clock)['runs'][1]['actors']['human'],1)
        self.assertEqual(export_run(records,'old',self.clock)['records'][0]['fields']['decision']['actor']['type'],'human')

    def test_summary_limit_is_explicit_and_retains_current_run(self):
        result=summarize([record(str(i)) for i in range(55)],self.clock)
        self.assertTrue(result['truncated'])
        self.assertEqual(result['total_runs'],56)
        self.assertEqual(len(result['runs']),50)
        self.assertEqual(result['runs'][0]['run_id'],'current')
        self.assertEqual(export_run([record('0')],'0',self.clock)['run_id'],'0')


if __name__=='__main__': unittest.main()
