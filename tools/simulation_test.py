"""Seeded variations of synthetic received inputs, not a physical sensor model.

Generate once per test. Polls and seeks read the same immutable input schedule.
World paths and observation times/positions remain the authored fixtures.
"""
import copy
import hashlib
import json
import random


VERSION = 'observation-variation-v1'
MAX_SEED = 2_147_483_647


def validate_seed(seed):
    if type(seed) is not int or not 0 <= seed <= MAX_SEED:
        raise ValueError('Seed must be an integer from 0 to 2147483647')
    return seed


def generate(case_id, seed, public, early_feed, fleet_feed):
    """Small delivery variation; rates are demo assumptions, never measured specs."""
    validate_seed(seed)
    rng = random.Random(f'{VERSION}:{case_id}:{seed}')
    public, early, fleet = copy.deepcopy((public, early_feed, fleet_feed))
    # Modest run-level packet loss, plus independent jitter per received record.
    loss = rng.uniform(0.02, 0.06)
    public['observations'] = [row for row in public['observations'] if rng.random() >= loss]
    for row in public['observations']:
        row['available_at_ms'] += rng.randint(0, 3000)
    for row in public['source_health']:
        row['available_at_ms'] += rng.randint(0, 2500)
    early['observations'] = [row for row in early['observations'] if rng.random() >= 0.03]
    for row in early['observations']:
        row['available_at_ms'] += rng.randint(0, 4000)
    fleet['receipt_delay_ms'] = rng.randint(500, 2500)
    for event in fleet['interruptions']:
        if event['case_id'] == case_id:
            # Ten-second health sampling can move a visible outage by one sample.
            event['from_ms'] += rng.randint(-5000, 5000)
            event['until_ms'] += rng.randint(-5000, 5000)
    payload = dict(public=public, early=early, fleet=fleet)
    fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False,
                                             separators=(',', ':'), allow_nan=False).encode()).hexdigest()
    metadata = dict(mode='seeded', seed=seed, generator_version=VERSION, input_digest=fingerprint)
    return public, early, fleet, metadata


def fixture_metadata():
    return dict(mode='fixture', seed=None, generator_version=None, input_digest=None)
