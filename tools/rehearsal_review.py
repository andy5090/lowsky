"""Read-only decision rehearsal summaries derived from the durable journal.

These are review-workflow records, not operational effectiveness scores or
training labels. Only the evidence frozen at confirmation is exported.
"""
import copy

OPTIONS = ('continue_monitoring', 'hold_review', 'defer')


def actor_type(row):
    actor = row.get('actor', {'type': 'human'})
    return actor.get('type') if actor.get('type') in ('human', 'automated_test') else 'unknown'


def summarize(records, clock, limit=50):
    runs = {}
    for row in records:
        run = runs.setdefault(row['run_id'], dict(run_id=row['run_id'], case_id=row['case_id'],
            test_run=copy.deepcopy(row['snapshot']['evidence'].get('test_run')), decisions=0,
            actors=dict(human=0, automated_test=0, unknown=0), choices={key: 0 for key in OPTIONS},
            last_decided_at_unix_ms=0))
        run['decisions'] += 1
        run['actors'][actor_type(row)] += 1
        if row['option_id'] in run['choices']:
            run['choices'][row['option_id']] += 1
        run['last_decided_at_unix_ms'] = max(run['last_decided_at_unix_ms'], row['decided_at_unix_ms'])
    current = runs.setdefault(clock['run_id'], dict(run_id=clock['run_id'], case_id=clock['case_id'],
        decisions=0, actors=dict(human=0, automated_test=0, unknown=0), choices={key: 0 for key in OPTIONS},
        last_decided_at_unix_ms=0))
    current['test_run'] = copy.deepcopy(clock.get('test_run'))
    ordered = sorted(runs.values(), key=lambda run: (run['run_id'] == clock['run_id'], run['last_decided_at_unix_ms']), reverse=True)
    return dict(schema_version=1, current_run_id=clock['run_id'], total_runs=len(ordered),
                truncated=len(ordered) > limit, runs=ordered[:limit])


def export_run(records, run_id, clock):
    selected = [row for row in records if row['run_id'] == run_id]
    if not selected and run_id != clock['run_id']:
        raise ValueError('Unknown recorded run')
    entries = []
    for row in selected:
        frozen = row['snapshot']
        report = frozen['report']
        entries.append(dict(id=row['id'], run_id=run_id, case_id=row['case_id'],
            evidence_version=row['evidence_version'], snapshot_hash=row['snapshot_hash'],
            fields=dict(
                event={key: copy.deepcopy(frozen['event'].get(key)) for key in ('id', 'triggers')},
                evidence=copy.deepcopy(frozen['evidence']),
                assessment={key: copy.deepcopy(report.get(key)) for key in
                            ('summary', 'known', 'decision_options', 'recommended_option_id', 'mode', 'model', 'language')},
                uncertainty=copy.deepcopy(report.get('uncertain', [])),
                decision=dict(option_id=row['option_id'], outcome=row['outcome'],
                              actor=copy.deepcopy(row.get('actor', {'type': 'human'}))),
                reason=row['reason'],
                time=dict(simulation_ms=row['at_ms'], decided_at_simulation_ms=row.get('decided_at_simulation_ms'),
                          recorded_at_unix_ms=row['decided_at_unix_ms']))))
    return dict(schema_version=1, scope='simulation_review', run_id=run_id,
                case_id=selected[0]['case_id'] if selected else clock['case_id'], records=entries)
