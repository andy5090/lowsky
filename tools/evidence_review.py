"""Received-evidence explanations and append-only local human review audit."""
import copy
import hashlib
import json
import os
from pathlib import Path


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def evidence_snapshot(object_id, observations, health, quality, last_known):
    """Only pass allowlisted, received public evidence; never authored world data."""
    return copy.deepcopy(dict(object_id=object_id, observations=observations, sources=health,
                              quality=quality, observation_status='last_known' if last_known else 'current'))


def explain(records, health, at_ms, freshness_ms, quality, last_known, evidence_version):
    evidence = [dict(id=row['id'], source_id=row['source_id'], kind='observation',
                     observed_at_ms=row['observed_at_ms'], available_at_ms=row['available_at_ms'])
                for row in records]
    evidence += [dict(id=channel['evidence']['id'], source_id=channel['source_id'], kind='source_health',
                      observed_at_ms=channel['evidence']['observed_at_ms'],
                      available_at_ms=channel['evidence']['available_at_ms'])
                 for channel in health if channel['evidence']]
    ids = [row['id'] for row in records]
    missing = []
    for channel in health:
        source = channel['source_id']
        row = next((record for record in records if record['source_id'] == source), None)
        if channel['status'] != 'online':
            missing.append(dict(code='source_' + channel['status'], source_id=source,
                                evidence_ids=[channel['evidence']['id']] if channel['evidence'] else []))
        if row is None:
            missing.append(dict(code='no_received_observation', source_id=source, evidence_ids=[]))
        elif at_ms - row['observed_at_ms'] > freshness_ms:
            missing.append(dict(code='observation_stale', source_id=source, evidence_ids=[row['id']]))
    uncertain = [dict(code='object_type_unknown', evidence_ids=ids),
                 dict(code='intent_unknown', evidence_ids=ids)]
    if quality == 'not_comparable':
        uncertain.append(dict(code='observation_times_differ', evidence_ids=ids))
    if quality == 'contradictory':
        uncertain.append(dict(code='marker_conflict', evidence_ids=ids))
    if last_known:
        uncertain.append(dict(code='current_position_unknown', evidence_ids=ids))
    known = [dict(code='received_observation', evidence_ids=ids)]
    if quality == 'consistent':
        known.append(dict(code='same_time_marker_agreement', evidence_ids=ids))
    return dict(observation_status='last_known' if last_known else 'current',
                object_type_assessment='unknown', intent_assessment='unknown',
                evidence_status={'consistent': 'corroborated', 'contradictory': 'conflicting'}.get(quality, 'incomplete'),
                known=known, uncertain=uncertain, missing=missing, evidence=evidence,
                evidence_version=evidence_version)


class AuditLog:
    """Local durability, not authentication or tamper-proof remote storage."""
    def __init__(self, path=None):
        self.path = Path(path) if path is not None else None
        self.records = []
        if self.path is not None and self.path.exists():
            contents = self.path.read_text(encoding='utf-8')
            if contents and not contents.endswith('\n'):
                raise ValueError(f'Incomplete final audit record: {self.path}')
            for number, line in enumerate(contents.splitlines(), 1):
                try:
                    record = json.loads(line)
                    if (not isinstance(record, dict) or record.get('schema_version') != 1
                            or not all(key in record for key in ('id', 'run_id', 'case_id', 'object_id',
                                                                  'reviewer', 'decision', 'reason', 'at_ms',
                                                                  'reviewed_at_unix_ms', 'evidence_snapshot'))
                            or digest(record['evidence_snapshot']) != record.get('evidence_version')):
                        raise ValueError('Invalid record')
                except (ValueError, TypeError) as error:
                    raise ValueError(f'Invalid audit record at line {number}: {self.path}') from error
                self.records.append(record)

    def append(self, record):
        saved = copy.deepcopy(record)
        encoded = json.dumps(saved, ensure_ascii=False, allow_nan=False, separators=(',', ':')) + '\n'
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            # Persist before exposing success to the operator.
            with self.path.open('a', encoding='utf-8') as stream:
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
        self.records.append(saved)

    def export(self):
        return dict(schema_version=1, records=copy.deepcopy(self.records))

    def current(self, run_id):
        return [{key: copy.deepcopy(value) for key, value in record.items() if key != 'evidence_snapshot'}
                for record in self.records if record['run_id'] == run_id]


def make_track_review(command, state, basis, review_id, reviewed_at_unix_ms):
    if command.get('run_id') != state['run_id']:
        raise ValueError('Stale run')
    track = next((item for item in state['tracks'] if item['object_id'] == command.get('object_id')), None)
    if track is None:
        raise ValueError('Unknown received track')
    if command.get('evidence_version') != track['evidence_version'] or digest(basis) != track['evidence_version']:
        raise ValueError('Evidence changed; refresh the track before review')
    reviewer, reason = command.get('reviewer'), command.get('reason')
    if not isinstance(reviewer, str) or not 1 <= len(reviewer.strip()) <= 80:
        raise ValueError('Reviewer alias is required (1-80 characters)')
    if not isinstance(reason, str) or not 1 <= len(reason.strip()) <= 1000:
        raise ValueError('Review reason is required (1-1000 characters)')
    if command.get('decision') not in ('noted', 'needs_review', 'dismissed'):
        raise ValueError('Invalid review decision')
    return dict(schema_version=1, id=review_id, run_id=state['run_id'], case_id=state['case_id'],
                test_run=copy.deepcopy(state.get('test_run')),
                object_id=track['object_id'], at_ms=state['at_ms'], reviewed_at_unix_ms=reviewed_at_unix_ms,
                reviewer=reviewer.strip(), decision=command['decision'], reason=reason.strip(),
                evidence_version=track['evidence_version'], evidence_snapshot=copy.deepcopy(basis))
