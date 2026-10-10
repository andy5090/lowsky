"""Build the synthetic, time-gated identification report feed for the tactics layer.

Reports imitate classifier outputs from separate EO, acoustic and RF sources. They are
derived offline from the fixture world so that appearance and report agree most of the
time, with deliberate omissions, delays and a few conflicting reports. The runtime server
reads only this feed; it never reads world truth for identification.
"""
import hashlib
import json
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
OUTPUT = PROJECT / 'data/tactics/identification_demo.json'
VERSION = 'identification-feed-v1'

CLASS_BY_PROFILE = {
    'small_multirotor': 'multirotor', 'medium_multirotor': 'multirotor',
    'delta_large': 'fixed_wing', 'tandem_wing': 'fixed_wing', 'fixed_wing_medium': 'fixed_wing',
    'delta_compact': 'light_airframe', 'fixed_wing_compact': 'light_airframe',
}
JET_AIRFRAMES = {'geran_3'}
RECON_AIRFRAMES = {'orlan_10', 'orlan_30', 'zala', 'supercam'}
FIBER_AIRFRAMES = {'fpv'}


def _ratio(*parts):
    digest = hashlib.sha256(':'.join(str(p) for p in parts).encode()).digest()
    return int.from_bytes(digest[:4], 'big') / 2 ** 32


def load_profiles(profiles_path=PROJECT / 'godot/assets/display_profiles.json'):
    return json.loads(profiles_path.read_text(encoding='utf-8'))['airframes']


def case_reports(case_id, variant, airframes, public, profiles, duration_ms, cast_signature=''):
    """Reports for one case: airframes maps object_id → airframe id (fixture or seeded cast)."""
    first = {}
    for row in public['observations']:
        if row.get('detected', True) is True:
            first[row['object_id']] = min(first.get(row['object_id'], row['available_at_ms']), row['available_at_ms'])
    reports = []
    salt = f'{VERSION}:{cast_signature}'

    def add(obj, sensor_type, fields, offset_s, note):
        base = first.get(obj)
        if base is None:
            return
        available = base + offset_s * 1000
        if available >= duration_ms:
            return
        observed = available - int(2000 + 4000 * _ratio(salt, case_id, obj, sensor_type, 'obs'))
        reports.append(dict(id=f'ident_{case_id}_{obj}_{sensor_type}_{len(reports):03d}', object_id=obj,
                            sensor_type=sensor_type, observed_at_ms=observed, available_at_ms=available,
                            fields=fields, synthetic=True, note=note))

    for oid, airframe in airframes.items():
        klass = CLASS_BY_PROFILE[profiles[airframe]['size_profile']]
        eo_roll = _ratio(salt, case_id, oid, 'eo')
        if eo_roll < 0.35:
            offset = 15 + int(30 * _ratio(salt, case_id, oid, 'eo_delay'))
            add(oid, 'eo', dict(airframe_class=klass, payload_visible=False),
                offset, 'Synthetic EO classifier output; payload is not visible at night.')
            if variant == 'contradictory' and _ratio(salt, case_id, oid, 'eo_conflict') < 0.25:
                other = 'multirotor' if klass != 'multirotor' else 'fixed_wing'
                add(oid, 'eo', dict(airframe_class=other, payload_visible=False), offset + 12,
                    'Deliberately conflicting second EO report for the contradictory case.')
        if airframe in JET_AIRFRAMES and _ratio(salt, case_id, oid, 'acoustic') < 0.7:
            add(oid, 'acoustic', dict(signature='jet'), 10 + int(20 * _ratio(salt, case_id, oid, 'ac_delay')),
                'Synthetic acoustic signature classifier output.')
        elif klass == 'fixed_wing' and _ratio(salt, case_id, oid, 'acoustic') < 0.3:
            add(oid, 'acoustic', dict(signature='propeller'), 10 + int(20 * _ratio(salt, case_id, oid, 'ac_delay')),
                'Synthetic acoustic signature classifier output.')
        if airframe in RECON_AIRFRAMES and _ratio(salt, case_id, oid, 'rf') < 0.6:
            add(oid, 'rf', dict(rf_emission=True, band='control_link'), 12 + int(25 * _ratio(salt, case_id, oid, 'rf_delay')),
                'Synthetic RF receiver output; emission suggests a link, not identity or intent.')
        elif airframe in FIBER_AIRFRAMES and _ratio(salt, case_id, oid, 'rf') < 0.4:
            add(oid, 'rf', dict(rf_emission=False, band=None), 12 + int(25 * _ratio(salt, case_id, oid, 'rf_delay')),
                'Synthetic negative RF report; absence of RF does not prove a fiber link.')
    reports.sort(key=lambda row: (row['available_at_ms'], row['id']))
    return dict(report_count=len(reports), reports=reports, cast_signature=cast_signature or None)


def build(root=PROJECT / 'data/scenarios/v1', profiles_path=PROJECT / 'godot/assets/display_profiles.json'):
    profiles = load_profiles(profiles_path)
    manifest = json.loads((root / 'manifest.json').read_text(encoding='utf-8'))
    cases = {}
    for entry in manifest['cases']:
        case_id = entry['case_id']
        world = json.loads((root / 'cases' / case_id / 'world.json').read_text(encoding='utf-8'))
        public = json.loads((root / 'cases' / case_id / 'public.json').read_text(encoding='utf-8'))
        airframes = {obj['object_id']: obj['visual']['airframe_id'] for obj in world['objects']}
        cases[case_id] = case_reports(case_id, entry['variant'], airframes, public, profiles, world['duration_ms'])
    return dict(schema_version='1.0', synthetic=True, generator=VERSION,
                # Seeded runs regenerate reports from this table, so installed builds need no Godot asset files.
                airframes={airframe_id: dict(size_profile=row['size_profile']) for airframe_id, row in sorted(profiles.items())},
                purpose='Synthetic classifier reports for the training identification layer. Derived offline from fixture appearance with omissions, delays and a few conflicts; not sensor performance.',
                sensor_types=['eo', 'acoustic', 'rf'], cases=cases)


def main():
    feed = build()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(feed, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(OUTPUT, {case: value['report_count'] for case, value in feed['cases'].items()})


if __name__ == '__main__':
    main()
