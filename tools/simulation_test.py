"""Seeded variations of synthetic received inputs, not a physical sensor model.

Generate once per test. Polls and seeks read the same immutable input schedule.
World paths and observation times/positions remain the authored fixtures.
"""
import copy
import hashlib
import json
import random


VERSION = 'observation-variation-v1'
VISUAL_VERSION = 'visual-cast-v1'
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


def visual_cast(case_id, seed, objects):
    """Seeded scenery casting only: no roles, strategy, routes or performance.

    Reuse a small palette in repeated groups instead of cycling the full catalog.
    A separate random stream leaves all received-input generation unchanged.
    """
    validate_seed(seed)
    rng = random.Random(f'{VISUAL_VERSION}:{case_id}:{seed}')
    palette = sorted({item['visual']['airframe_id'] for item in objects})
    chosen = rng.sample(palette, min(len(palette), rng.randint(2, 3)))
    rows = []
    while len(rows) < len(objects):
        airframe = chosen[len(rows) // 6] if len(rows) < len(chosen) * 6 else rng.choice(chosen)
        for item in objects[len(rows):len(rows) + 6]:
            rows.append(dict(object_id=item['object_id'], airframe_id=airframe))
    signature = hashlib.sha256(json.dumps(rows, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return dict(version=VISUAL_VERSION, signature=signature, objects=rows)
