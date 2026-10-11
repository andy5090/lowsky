"""Author paced, area-only indication feeds while preserving the compact load feed."""
import copy
import json
from pathlib import Path


PATH = Path(__file__).resolve().parents[1] / 'data/early_warning_demo.json'
MDL_PATH = Path(__file__).resolve().parents[1] / 'data/geography/korean_mdl.json'
FORWARD_AREA_X = -2000
# 2.5 km beyond the nominal 2 km DMZ southern half-width, measured from the MDL.
FORWARD_AREA_SOUTH_OF_MDL_M = 2000 + 2500


def forward_area_center():
    """Georeferenced forward reporting area south of the DMZ (MDL + nominal 2 km + 2.5 km), on the central corridors."""
    try:
        from .infiltration_routes import line_z_at
    except ImportError:
        from infiltration_routes import line_z_at
    lines = json.loads(MDL_PATH.read_text(encoding='utf-8'))['lines']
    z = line_z_at([part['local'] for part in lines['mdl']['parts']], FORWARD_AREA_X)
    return [FORWARD_AREA_X, 0, round(z + FORWARD_AREA_SOUTH_OF_MDL_M, 1)]


def paced_profile(case_id):
    """Independent synthetic reports; no object IDs, trajectories or positions."""
    rows = []

    def report(sensor, zone, kind, observed, present, available=None, status='operational', valid='valid'):
        specification = {'acoustic': 'civilian_acoustic_reference', 'citizen_report': 'citizen_report_reference',
                         'fixed_phone_acoustic': 'pole_phone_reference'}[kind]
        row = dict(id=f'{case_id}_indirect_{len(rows) + 1:03d}', zone_id=zone, sensor_id=sensor,
                   sensor_type=kind, sensor_spec_id=specification, observed_at_ms=observed,
                   available_at_ms=observed if available is None else available, sensor_status=status,
                   measurement_status=valid, measurement={'object_present': present},
                   quality={'classifier_score': None}, synthetic=True)
        if kind == 'fixed_phone_acoustic':
            row['device_health'] = dict(power_status='external' if status == 'operational' else 'battery',
                                        network_status='online' if status == 'operational' else 'offline')
        rows.append(row)

    for sensor in ('pole_phone_1', 'pole_phone_2'):
        report(sensor, 'fixed_phone_pilot', 'fixed_phone_acoustic', 0, False)
    # Renewals change evidence IDs but keep the first review question stable for
    # two minutes. They are one source, not independent corroboration.
    for tick in (30_000, 80_000, 130_000, 180_000, 210_000):
        report('acoustic_a', 'remote_reference', 'acoustic', tick, True)
    for observed, received in ((135_000, 150_000), (180_000, 195_000), (210_000, 220_000)):
        report('report_a', 'remote_reference', 'citizen_report', observed, case_id == 'case_001', available=received)
    report('acoustic_a', 'remote_reference', 'acoustic', 225_000, False)
    if case_id == 'case_002':
        report('report_a', 'remote_reference', 'citizen_report', 240_000, True, available=245_000)
    # Other areas develop independently; none implies the location of a hidden
    # world object or an association with a subsequently received direct track.
    report('report_b', 'community_b', 'citizen_report', 70_000, True, available=100_000)
    report('report_b', 'community_b', 'citizen_report', 240_000, None, status='offline', valid='unavailable')
    report('acoustic_c', 'community_c', 'acoustic', 60_000, None, valid='invalid')
    report('acoustic_c', 'community_c', 'acoustic', 120_000, False)
    report('pole_phone_1', 'fixed_phone_pilot', 'fixed_phone_acoustic', 210_000, True)
    report('pole_phone_2', 'fixed_phone_pilot', 'fixed_phone_acoustic', 210_000, True, available=225_000)
    for sensor in ('pole_phone_1', 'pole_phone_2'):
        report(sensor, 'fixed_phone_pilot', 'fixed_phone_acoustic', 300_000, False)
        report(sensor, 'fixed_phone_pilot', 'fixed_phone_acoustic', 420_000, None,
               status='offline', valid='unavailable')
        report(sensor, 'fixed_phone_pilot', 'fixed_phone_acoustic', 630_000, False)
    return dict(freshness_ms=90_000, observations=sorted(rows, key=lambda row: (row['available_at_ms'], row['id'])))


def build(feed):
    result = copy.deepcopy(feed)
    result['description'] = ('Independent simulated area indications on the replay clock. '
                             'Cases 001/002 provide deliberate early-review periods; the root feed remains the compact case 003 fixture. '
                             'Area geometry describes sensor context, never the position of an unobserved object.')
    result['case_overrides'] = {}
    for case_id in ('case_001', 'case_002'):
        profile = paced_profile(case_id)
        profile['zones'] = [dict(id='remote_reference',
            label={'en': 'Forward area south of the DMZ', 'ko': '비무장지대 남측 전방 구역'},
            center=forward_area_center(), radius_m=4000, deployment_type='community',
            schematic=False, georeferenced=True,
            reference='MDL + nominal 2 km DMZ half-width + 2.5 km (Natural Earth MDL); simulated reporting area, not a surveyed sensor site'),
            *copy.deepcopy(feed['zones'])]
        result['case_overrides'][case_id] = profile
    return result


if __name__ == '__main__':
    PATH.write_text(json.dumps(build(json.loads(PATH.read_text(encoding='utf-8'))), ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
