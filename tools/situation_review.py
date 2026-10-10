"""Received context and human evidence review; no threat or response decisions."""
from copy import deepcopy

EVENT_KEYS = ('id', 'observed_at_ms', 'available_at_ms', 'story_time', 'kind', 'title',
              'summary', 'uncertainty', 'source_ids', 'object_ids', 'related_event_id', 'evidence_ids')
DECISIONS = ('noted', 'needs_review', 'dismissed')


def snapshot(feed, case_id, at_ms, known_objects, review_log):
    known = set(known_objects)
    received = [row for row in feed['events'] if case_id in row['case_ids']
                and 0 <= row['observed_at_ms'] <= at_ms and row['available_at_ms'] <= at_ms
                and set(row['object_ids']) <= known]
    received_ids = {row['id'] for row in received}
    events = []
    for row in received:
        item = deepcopy({key: row[key] for key in EVENT_KEYS})
        related = item['related_event_id']
        if related not in received_ids:
            item['related_event_id'] = None
        item['related_reviews'] = [deepcopy(r) for r in review_log
                                   if related in received_ids and r['event_id'] == related]
        events.append(item)
    return dict(synthetic=True, time_compression_note=deepcopy(feed['time_compression_note']),
                events=events, review_log=deepcopy(review_log),
                summary=dict(received_events=len(events), recorded_reviews=len(review_log),
                             decisions={d: sum(r['decision'] == d for r in review_log) for d in DECISIONS},
                             accuracy=None))


def make_review(command, situation, run_id, case_id, at_ms, record_id):
    if command.get('run_id') != run_id:
        raise ValueError('Stale run')
    event = next((e for e in situation['events'] if e['id'] == command.get('event_id')), None)
    if event is None:
        raise ValueError('Unknown received event')
    decision, reason = command.get('decision'), command.get('reason')
    if decision not in DECISIONS:
        raise ValueError('Invalid review decision')
    if not isinstance(reason, str) or not 1 <= len(reason.strip()) <= 1000:
        raise ValueError('Review reason must contain 1–1000 characters')
    # Seven content fields are captured from the current received context plus human input.
    # IDs and run/case metadata isolate repeated replays; there is no inferred operator identity.
    return dict(id=record_id, run_id=run_id, case_id=case_id,
                event_id=event['id'], evidence_ids=list(event['evidence_ids']),
                assessment=deepcopy(event['summary']), uncertainty=deepcopy(event['uncertainty']),
                decision=decision, reason=reason.strip(), reviewed_at_ms=at_ms)
