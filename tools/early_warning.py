"""Observation-only early signals from a fictional community sensor feed.

Rules describe review priority, never identity, hostile intent or sensor performance.
No world truth, microphone access, triangulation or trajectory prediction is used.
"""
import math


def assess(row, at_ms, freshness_ms):
    observed = row.get('observed_at_ms')
    if type(observed) is not int or observed < 0:
        return 'invalid_time'
    if observed > at_ms:
        return 'future_time'
    if row.get('sensor_status') != 'operational':
        return 'unavailable'
    if row.get('measurement_status') != 'valid':
        return 'no_measurement'
    if at_ms - observed > freshness_ms:
        return 'stale'
    if type(row.get('measurement', {}).get('object_present')) is not bool:
        return 'no_measurement'
    return 'current'


def snapshot(feed, at_ms):
    """Allowlist arrived evidence and summarize latest observations by source/area."""
    freshness = feed['freshness_ms']
    zones, alerts = [], []
    for zone in feed['zones']:
        latest = {}
        for row in feed['observations']:
            received = row.get('available_at_ms')
            if row.get('zone_id') != zone['id'] or type(received) is not int or not 0 <= received <= at_ms:
                continue
            # Prefer newer observations; a delayed old report must not replace a newer reading.
            observed = row.get('observed_at_ms')
            ordering_time = observed if type(observed) is int and 0 <= observed <= at_ms else received
            key = (ordering_time, received, row['id'])
            if row['sensor_id'] not in latest or key > latest[row['sensor_id']][0]:
                latest[row['sensor_id']] = (key, row)
        evidence = []
        for _, row in latest.values():
            result = assess(row, at_ms, freshness)
            observed = row.get('observed_at_ms')
            score = row.get('quality', {}).get('classifier_score')
            if type(score) not in (int, float) or not math.isfinite(score) or not 0 <= score <= 1:
                score = None
            present = row.get('measurement', {}).get('object_present')
            evidence.append(dict(id=row['id'], sensor_id=row['sensor_id'], sensor_type=row['sensor_type'],
                                 sensor_spec_id=row.get('sensor_spec_id'),
                                 observed_at_ms=observed if type(observed) is int else None,
                                 available_at_ms=row['available_at_ms'], assessment=result,
                                 object_present=present if type(present) is bool else None,
                                 classifier_score=score, synthetic=True))
        current = [e for e in evidence if e['assessment'] == 'current']
        positive = [e for e in current if e['object_present'] is True]
        negative = [e for e in current if e['object_present'] is False]
        if positive and negative:
            status = 'conflicting'
        elif len(positive) >= 2:
            status = 'corroborated'
        elif positive:
            status = 'single'
        elif current:
            status = 'no_signal'
        elif any(e['assessment'] == 'stale' for e in evidence):
            status = 'stale'
        elif evidence:
            status = 'unavailable'
        else:
            status = 'waiting'
        item = dict(id=zone['id'], label=zone['label'], center=zone['center'],
                    radius_m=zone['radius_m'], status=status, evidence=evidence,
                    positive_sources=len(positive), radar_association='unknown', synthetic=True)
        zones.append(item)
        if positive:
            # New evidence gets its own acknowledgement; old acknowledgements cannot hide an escalation.
            ids = sorted(e['id'] for e in current)
            alerts.append(dict(id=f"early:{zone['id']}:{':'.join(ids)}", kind='early_warning',
                               zone_id=zone['id'], signal_status=status,
                               evidence_ids=ids))
    return dict(synthetic=True, freshness_ms=freshness, zones=zones), alerts
