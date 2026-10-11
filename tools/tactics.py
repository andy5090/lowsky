"""Rule-based training recommendation layer: identification, response options, formation, placement.

Everything here is advice over received evidence and the virtual site layout. Nothing changes
aircraft motion, facility status or observations, and no interception, damage or propagation model
is implemented. Scores are uncalibrated rubric points from the local scenario documents.
"""
import copy
import hashlib
import json
import math
import uuid
from pathlib import Path

try:
    from .evidence_review import digest as audit_digest
except ImportError:
    from evidence_review import digest as audit_digest

PROJECT = Path(__file__).resolve().parents[1]
CATALOG_PATH = PROJECT / 'data/tactics/catalog.json'
FEED_PATH = PROJECT / 'data/tactics/identification_demo.json'
TERRAIN_PATH = PROJECT / 'data/terrain/korea_site.json'
CONTEXT_PATH = PROJECT / 'data/terrain/korea_context.json'
CORRIDORS_PATH = PROJECT / 'data/geography/approach_corridors.json'

SCOPE = 'rule_based_training_advice'
SECTORS = ('N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW')
LEANS = ('decoy_leaning', 'attack_leaning', 'reconnaissance_leaning', 'indeterminate', 'insufficient_data')
STATUSES = ('recommended', 'penalized', 'rejected')
POSTURES = ('observe_preserve', 'hold', 'engage_candidate')
SUB_SECTORS = 24
BOUNDS_M = 5000
MAX_TASKING = 12


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def load_catalog(path=CATALOG_PATH):
    return read_json(path)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()[:16]


# ----------------------------------------------------------------------------- geometry

def bearing_deg(x, z, origin=(0.0, 0.0)):
    """Compass bearing from the site origin; local X points east and Z south."""
    return math.degrees(math.atan2(x - origin[0], -(z - origin[1]))) % 360


def sector_of(x, z):
    return SECTORS[int(((bearing_deg(x, z) + 22.5) % 360) // 45)]


def sub_sector_of(x, z):
    return int(((bearing_deg(x, z) + 180 / SUB_SECTORS) % 360) // (360 / SUB_SECTORS))


def point_in_polygon(x, z, polygon):
    inside = False
    for index in range(len(polygon)):
        (x1, z1), (x2, z2) = polygon[index - 1], polygon[index]
        if (z1 > z) != (z2 > z):
            cross = (x2 - x1) * (z - z1) / (z2 - z1) + x1
            if x < cross:
                inside = not inside
    return inside


def horizontal_distance(a, b):
    return math.hypot(a[0] - b[0], a[2] - b[2])


def in_runway_corridor(position, layout, margin_m):
    runway = layout['runway']
    cx, _, cz = runway['center']
    return (abs(position[0] - cx) <= runway['width_m'] / 2 + margin_m
            and abs(position[2] - cz) <= runway['length_m'] / 2 + margin_m)


def _grading_distance(x, z, layout):
    """Mirror of godot/geographic_environment.gd grading_distance: negative inside the graded site."""
    polygon = layout['perimeter']['polygon']
    margin = layout['terrain_grading']['margin_m']
    if point_in_polygon(x, z, polygon):
        return -margin
    best = float('inf')
    for index in range(len(polygon)):
        (x1, z1), (x2, z2) = polygon[index - 1], polygon[index]
        dx, dz = x2 - x1, z2 - z1
        t = max(0.0, min(1.0, ((x - x1) * dx + (z - z1) * dz) / ((dx * dx + dz * dz) or 1.0)))
        best = min(best, math.hypot(x - (x1 + dx * t), z - (z1 + dz * t)))
    return best - margin


def graded_elevation(terrain, layout, x, z):
    """Elevation as rendered: flattened airfield blended into the DEM (smoothstep over blend_m)."""
    outside = _grading_distance(x, z, layout)
    if outside <= 0:
        return -0.02
    raw = elevation(terrain, x, z)
    t = max(0.0, min(1.0, outside / layout['terrain_grading']['blend_m']))
    return -0.02 + (raw + 0.02) * t * t * (3 - 2 * t)


def elevation(terrain, x, z):
    """Bilinear DEM sample relative to the reference elevation; no site grading."""
    if not terrain:
        return 0.0
    size, spacing, half = terrain['grid_size'], terrain['spacing_m'], terrain['extent_m'] / 2
    column = min(max((x + half) / spacing, 0.0), size - 1.0)
    row = min(max((z + half) / spacing, 0.0), size - 1.0)
    x0, z0 = int(column), int(row)
    x1, z1 = min(x0 + 1, size - 1), min(z0 + 1, size - 1)
    heights = terrain['heights_m']
    north = heights[z0][x0] + (heights[z0][x1] - heights[z0][x0]) * (column - x0)
    south = heights[z1][x0] + (heights[z1][x1] - heights[z1][x0]) * (column - x0)
    return north + (south - north) * (row - z0) - terrain['reference_elevation_m']


def ring_points(radius, count=16):
    return [[round(radius * math.sin(math.radians(360 * index / count)), 1), 0,
             round(-radius * math.cos(math.radians(360 * index / count)), 1)] for index in range(count)]


def valid_position(position, bounds=BOUNDS_M):
    return (isinstance(position, list) and len(position) == 3
            and all(type(v) in (int, float) and math.isfinite(v) for v in position)
            and position[1] == 0 and abs(position[0]) <= bounds and abs(position[2]) <= bounds)


# ----------------------------------------------------------------------------- identification

def arrived_reports(feed, case_id, at_ms):
    rows = feed.get('cases', {}).get(case_id, {}).get('reports', [])
    return [copy.deepcopy(row) for row in rows
            if type(row.get('available_at_ms')) is int and row['available_at_ms'] <= at_ms
            and type(row.get('observed_at_ms')) is int and row['observed_at_ms'] <= at_ms]


def kinematics(track, layout):
    history = sorted((row for row in track.get('history', []) if row.get('position') is not None),
                     key=lambda row: (row['observed_at_ms'], row['available_at_ms']))
    distinct = []
    for row in history:
        if not distinct or row['observed_at_ms'] != distinct[-1]['observed_at_ms']:
            distinct.append(row)
    result = dict(samples=len(distinct), speed_kmh=None, heading_deg=None, heading_persistence=None,
                  altitude_m=None, descent_m=None, nearest_facility=None, facility_distance_m=None, closing=None)
    if not distinct:
        return result
    last = distinct[-1]
    result['altitude_m'] = round(last['position'][1], 1)
    facilities = [dict(id='runway', position=layout['runway']['center'])] + layout['facilities']
    nearest = min(facilities, key=lambda item: horizontal_distance(item['position'], last['position']))
    result['nearest_facility'] = nearest['id']
    result['facility_distance_m'] = round(horizontal_distance(nearest['position'], last['position']))
    if len(distinct) < 2:
        return result
    previous = distinct[-2]
    dt = (last['observed_at_ms'] - previous['observed_at_ms']) / 1000
    result['speed_kmh'] = round(horizontal_distance(previous['position'], last['position']) / dt * 3.6, 1)
    headings = [bearing_deg(b['position'][0] - a['position'][0], b['position'][2] - a['position'][2])
                for a, b in zip(distinct, distinct[1:])
                if horizontal_distance(a['position'], b['position']) > 1]
    if headings:
        result['heading_deg'] = round(headings[-1], 1)
        deviations = [abs((h - headings[-1] + 180) % 360 - 180) for h in headings[-6:]]
        result['heading_persistence'] = round(max(0.0, 1 - max(deviations) / 90), 2)
    result['descent_m'] = round(previous['position'][1] - last['position'][1], 1)
    result['closing'] = horizontal_distance(nearest['position'], last['position']) < horizontal_distance(nearest['position'], previous['position'])
    return result


GROUP_RADIUS_M = 600


def _grid(tracks):
    cells = {}
    for track in tracks:
        if track.get('position') is None or track.get('last_known'):
            continue
        key = (int(track['position'][0] // GROUP_RADIUS_M), int(track['position'][2] // GROUP_RADIUS_M))
        cells.setdefault(key, []).append(track)
    return cells


def group_of(track, cells):
    position, heading = track.get('position'), track['_kinematics'].get('heading_deg')
    cx, cz = int(position[0] // GROUP_RADIUS_M), int(position[2] // GROUP_RADIUS_M)
    members = []
    for dx in (-1, 0, 1):
        for dz in (-1, 0, 1):
            for other in cells.get((cx + dx, cz + dz), ()):
                if other is track or horizontal_distance(position, other['position']) > GROUP_RADIUS_M:
                    continue
                other_heading = other['_kinematics'].get('heading_deg')
                if heading is None or other_heading is None or abs((heading - other_heading + 180) % 360 - 180) <= 20:
                    members.append(other['object_id'])
    return sorted(members)


def identify(tracks, reports, layout, at_ms, catalog):
    """Received kinematics and arrived classifier reports → lean, cues and uncertainty."""
    rubric = catalog['rubric']
    tracks = [dict(track) for track in tracks if track.get('position') is not None]
    for track in tracks:
        track['_kinematics'] = kinematics(track, layout)
    by_object = {}
    for row in reports:
        by_object.setdefault(row['object_id'], []).append(row)
    first_receipt = min((track['first_received_at_ms'] for track in tracks), default=None)
    cells = _grid(tracks)
    results = []
    for track in sorted(tracks, key=lambda item: item['object_id']):
        kin = track['_kinematics']
        own_reports = [{key: row[key] for key in ('id', 'sensor_type', 'observed_at_ms', 'available_at_ms', 'fields')}
                       for row in sorted(by_object.get(track['object_id'], []), key=lambda row: (row['available_at_ms'], row['id']))]
        scores = dict(decoy=0.0, attack=0.0, reconnaissance=0.0)
        cues, uncertainty = [], []
        evidence_ids = [row['id'] for row in track.get('records', [])] + [row['id'] for row in own_reports]

        sample_ids = [row['id'] for row in sorted(track.get('history', []), key=lambda row: (row['observed_at_ms'], row['available_at_ms']))[-2:]]

        def cue(cue_id, ids=None, **effects):
            for key, value in effects.items():
                scores[key] += value
            cues.append(dict(id=cue_id, effect=effects, evidence_ids=ids if ids is not None else sample_ids or [row['id'] for row in track.get('records', [])]))

        group = group_of(track, cells) if kin['heading_deg'] is not None else []
        if len(group) + 1 >= rubric['group_size_decoy']['min_group']:
            cue('group_structure', decoy=rubric['group_size_decoy']['decoy'])
            uncertainty.append('group_from_received_positions_only')
        if first_receipt is not None and track['first_received_at_ms'] - first_receipt <= rubric['first_wave']['window_ms']:
            cue('first_wave', decoy=rubric['first_wave']['decoy'])
        terminal = (kin['descent_m'] is not None and kin['descent_m'] >= 15) or (
            kin['heading_persistence'] is not None and kin['heading_persistence'] < 0.7
            and kin['facility_distance_m'] is not None and kin['facility_distance_m'] <= 2500 and kin['closing'])
        if terminal:
            cue('terminal_maneuver', attack=rubric['terminal_maneuver']['attack'], decoy=rubric['terminal_maneuver']['decoy'])
        if kin['speed_kmh'] is not None and kin['speed_kmh'] >= rubric['jet_speed']['min_kmh']:
            cue('jet_speed', attack=rubric['jet_speed']['attack'], decoy=rubric['jet_speed']['decoy'])
            uncertainty.append('jet_decoy_possible')
        rf_reports = [row for row in own_reports if row['sensor_type'] == 'rf']
        eo_reports = [row for row in own_reports if row['sensor_type'] == 'eo']
        acoustic = [row for row in own_reports if row['sensor_type'] == 'acoustic']
        if any(row['fields'].get('rf_emission') is True for row in rf_reports):
            cue('rf_emission', [row['id'] for row in rf_reports], reconnaissance=rubric['rf_emission']['reconnaissance'])
        if (kin['speed_kmh'] is not None and kin['speed_kmh'] <= rubric['loiter']['max_kmh']
                and kin['heading_persistence'] is not None and kin['heading_persistence'] < 0.7):
            cue('loiter', reconnaissance=rubric['loiter']['reconnaissance'])
        if any(row['fields'].get('signature') == 'jet' for row in acoustic):
            cue('acoustic_jet', [row['id'] for row in acoustic], attack=rubric['jet_speed']['attack'], decoy=rubric['jet_speed']['decoy'])
            if 'jet_decoy_possible' not in uncertainty:
                uncertainty.append('jet_decoy_possible')
        classes = {row['fields'].get('airframe_class') for row in eo_reports}
        if 'fixed_wing' in classes:
            cue('eo_fixed_wing', [row['id'] for row in eo_reports], attack=rubric['eo_fixed_wing']['attack'], decoy=rubric['eo_fixed_wing']['decoy'])
        if 'light_airframe' in classes:
            cue('eo_light_airframe', [row['id'] for row in eo_reports], decoy=rubric['eo_light_airframe']['decoy'])
        if eo_reports:
            if not any(row['fields'].get('payload_visible') for row in eo_reports):
                uncertainty.append('payload_not_visible')
            if len(classes) > 1:
                uncertainty.append('eo_conflict')
        else:
            uncertainty.append('no_eo_report')
        if any(row['fields'].get('rf_emission') is False for row in rf_reports):
            uncertainty.append('rf_absent_not_fiber_proof')
        if len(track.get('records', [])) < 2:
            uncertainty.append('single_source_position')
        if kin['samples'] < 2:
            lean = 'insufficient_data'
        elif scores['reconnaissance'] >= 0.3 and scores['reconnaissance'] > max(scores['decoy'], scores['attack']):
            lean = 'reconnaissance_leaning'
        elif abs(scores['attack'] - scores['decoy']) < rubric['indeterminate_margin']:
            lean = 'indeterminate'
        else:
            lean = 'attack_leaning' if scores['attack'] > scores['decoy'] else 'decoy_leaning'
        if lean == 'indeterminate':
            uncertainty.append('attack_decoy_not_separable')
        profile = ('jet' if (kin['speed_kmh'] or 0) >= rubric['jet_speed']['min_kmh'] or any(r['fields'].get('signature') == 'jet' for r in acoustic)
                   else 'multirotor' if 'multirotor' in classes and len(classes) == 1
                   else 'light_airframe' if classes == {'light_airframe'}
                   else 'fixed_wing' if 'fixed_wing' in classes
                   else 'unclassified')
        item = dict(object_id=track['object_id'], lean=lean, profile=profile, stale=bool(track.get('last_known')),
                    verification='observed_class' if eo_reports else 'suspected',
                    scores={key: round(value, 2) for key, value in scores.items()},
                    kinematics={key: value for key, value in kin.items()}, group_size=len(group) + 1,
                    sector=sector_of(track['position'][0], track['position'][2]),
                    cues=cues, uncertainty=uncertainty, reports=own_reports, quality=track.get('quality'),
                    evidence_ids=sorted(set(evidence_ids)), synthetic=True)
        item['version'] = digest(dict(lean=lean, profile=profile, cues=[c['id'] for c in cues],
                                      uncertainty=uncertainty, reports=[r['id'] for r in own_reports]))
        results.append(item)
    return results


# ----------------------------------------------------------------------------- recommendation

def recommend(identifications, tracks, allocations, units, layout, catalog):
    """Effector options with penalize-vs-reject reasons; never an order."""
    rules = catalog['constraints']
    positions = {track['object_id']: track['position'] for track in tracks if track.get('position') is not None}
    polygon = layout['perimeter']['polygon']
    radar_sites = [f['position'] for f in layout['facilities'] if f['id'] in rules['radar_facility_ids']]
    fuel_sites = [f['position'] for f in layout['facilities'] if f['id'] in rules['fuel_like_facility_ids']]
    teams = [unit for unit in units if unit['kind'] == 'effector_team']
    used = {}
    for record in allocations:
        used[record['effector_id']] = used.get(record['effector_id'], 0) + 1
    allocated_objects = {record['object_id']: record for record in allocations}
    results = []
    for ident in identifications:
        position = positions[ident['object_id']]
        kin = ident['kinematics']
        constraints = []
        if ident.get('stale'):
            constraints.append('stale_track')
        if in_runway_corridor(position, layout, rules['runway_corridor_margin_m']):
            constraints.append('runway_overflight')
        if point_in_polygon(position[0], position[2], polygon):
            constraints.append('over_facilities')
        jammer = next(e for e in catalog['effectors'] if e['id'] == 'rf_jammer')
        if any(horizontal_distance(site, position) <= jammer['radar_interference_radius_m'] for site in radar_sites):
            constraints.append('own_radar_nearby')
        if any(horizontal_distance(site, position) <= 400 for site in fuel_sites):
            constraints.append('fuel_like_facility_nearby')
        nearest_team = min((horizontal_distance(team['position'], position) for team in teams), default=None)
        options = []
        for effector in catalog['effectors']:
            reasons, status, suitability = [], 'recommended', 1.0

            def penalize(reason, amount=0.25):
                nonlocal status, suitability
                reasons.append(reason)
                if status != 'rejected':
                    status = 'penalized'
                    suitability = max(0.0, suitability - amount)

            def reject(reason):
                nonlocal status, suitability
                reasons.append(reason)
                status, suitability = 'rejected', 0.0

            if 'stale_track' in constraints:
                reject('stale_track')
            if 'runway_overflight' in constraints:
                reject('runway_overflight')
            if effector['id'] == 'autocannon' and ('over_facilities' in constraints or 'fuel_like_facility_nearby' in constraints):
                reject('debris_over_facilities')
            if effector['id'] == 'rf_jammer':
                if 'own_radar_nearby' in constraints:
                    reject('own_radar_interference')
                rf = [row for row in ident['reports'] if row['sensor_type'] == 'rf']
                if any(row['fields'].get('rf_emission') is False for row in rf):
                    reject('no_rf_link_evidence')
                elif not any(row['fields'].get('rf_emission') is True for row in rf):
                    penalize('rf_emission_unknown')
            if effector['id'] == 'interceptor_drone':
                remaining = effector['inventory_per_run'] - used.get('interceptor_drone', 0)
                if remaining <= 0:
                    reject('inventory_exhausted')
                if (kin.get('speed_kmh') or 0) >= 300 or ident['profile'] == 'jet':
                    penalize('speed_disadvantage')
                if ident['lean'] in ('decoy_leaning', 'indeterminate'):
                    penalize('resource_preservation')
            if effector['id'] == 'laser':
                if any(record['effector_id'] == 'laser' and record['object_id'] != ident['object_id'] for record in allocations):
                    penalize('single_target_queue', 0.15)
                if ident['profile'] == 'jet':
                    reasons.append('preferred_for_jet')
            if not teams:
                penalize('no_effector_team_placed', 0.2)
            elif nearest_team is not None and nearest_team > effector['nominal_range_m']:
                penalize('coverage_gap', 0.3)
            options.append(dict(effector_id=effector['id'], status=status, suitability=round(suitability, 2),
                                reasons=reasons, cost_tier=effector['cost_tier'],
                                inventory_remaining=(effector['inventory_per_run'] - used.get(effector['id'], 0))
                                if effector['inventory_per_run'] is not None else None))
        usable = [option for option in options if option['status'] != 'rejected']
        if 'stale_track' in constraints or 'runway_overflight' in constraints or not usable:
            posture = 'hold'
        elif ident['lean'] in ('decoy_leaning', 'reconnaissance_leaning', 'indeterminate', 'insufficient_data'):
            posture = 'observe_preserve'
        else:
            posture = 'engage_candidate'
        primary = max(usable, key=lambda option: (option['suitability'], option['effector_id'] == 'laser'))['effector_id'] if usable else None
        allocation = allocated_objects.get(ident['object_id'])
        response = dict(object_id=ident['object_id'], posture=posture, primary=primary, options=options,
                        constraints=constraints, authority='human_confirmation_required',
                        allocation={key: allocation[key] for key in ('id', 'effector_id', 'at_ms', 'status_at_record')} if allocation else None)
        response['version'] = digest(dict(posture=posture, primary=primary, constraints=constraints,
                                          options=[(o['effector_id'], o['status'], o['reasons']) for o in options],
                                          identification=ident['version'], allocated=bool(allocation)))
        results.append(response)
    return results


def select_allocation(command, state, catalog):
    """Validate a human allocation record against the current recommendation card."""
    if command.get('confirm') is not True or command.get('run_id') != state['run_id']:
        raise ValueError('Confirm an allocation for the current run')
    targets = {target['object_id']: target for target in state['tactics']['targets']}
    target = targets.get(command.get('object_id'))
    if not target:
        raise ValueError('Choose a currently received aircraft')
    if target['response']['version'] != command.get('version'):
        raise ValueError('The recommendation changed; review the current card')
    if target['response'].get('allocation'):
        raise ValueError('An allocation is already recorded for this aircraft in this run')
    option = next((row for row in target['response']['options'] if row['effector_id'] == command.get('effector_id')), None)
    if option is None or option['status'] == 'rejected':
        raise ValueError('Rejected or unknown effector option')
    reviewer = command.get('reviewer', '')
    comment = command.get('comment', '')
    if not isinstance(reviewer, str) or not isinstance(comment, str):
        raise ValueError('Invalid reviewer or comment')
    reviewer, comment = reviewer.strip(), comment.strip()
    if len(reviewer) > 80 or len(comment) > 1000:
        raise ValueError('Reviewer alias or comment is too long')
    snapshot = dict(identification={key: target['identification'][key] for key in ('lean', 'profile', 'verification', 'cues', 'uncertainty', 'evidence_ids')},
                    response={key: target['response'][key] for key in ('posture', 'primary', 'constraints', 'options')})
    return dict(schema_version=1, id=uuid.uuid4().hex, run_id=state['run_id'], case_id=state['case_id'],
                object_id=target['object_id'], effector_id=option['effector_id'], status_at_record=option['status'],
                reasons=option['reasons'], decision='allocate', reason=comment, reviewer=reviewer,
                at_ms=state['at_ms'], reviewed_at_unix_ms=None, evidence_snapshot=snapshot,
                evidence_version=audit_digest(snapshot), scope=SCOPE, actor=dict(type='human'),
                test_run={key: copy.deepcopy(state.get('test_run', {}).get(key)) for key in ('mode', 'seed', 'generator_version', 'input_digest')},
                note='Training record of a confirmed recommendation; no engagement, interception or damage is simulated.')


# ----------------------------------------------------------------------------- placement

def threat_weights(tracks, early_warning, catalog):
    """Sector weights from received tracks and positive area signals, else the scenario prior."""
    weights = dict.fromkeys(SECTORS, 0.0)
    for track in tracks:
        if track.get('position') is not None and not track.get('last_known'):
            weights[sector_of(track['position'][0], track['position'][2])] += 1.0
    for zone in (early_warning or {}).get('zones', []):
        if zone.get('positive_sources', 0) > 0 and zone.get('center'):
            weights[sector_of(zone['center'][0], zone['center'][2])] += 2.0
    if sum(weights.values()) == 0:
        return dict(catalog['sector_prior']['weights']), 'scenario_prior'
    peak = max(weights.values())
    prior = catalog['sector_prior']['weights']
    return {key: round(0.15 * prior[key] + 0.85 * weights[key] / peak, 3) for key in SECTORS}, 'received_picture'


def _sub_weights(weights):
    return [weights[SECTORS[int(((index * 360 / SUB_SECTORS) + 22.5) % 360 // 45)]] for index in range(SUB_SECTORS)]


def _rep_point(index, radius):
    angle = math.radians(index * 360 / SUB_SECTORS)
    return [radius * math.sin(angle), 0, -radius * math.cos(angle)]


def _coverage_gain(position, range_m, covered, sub_weights, radius):
    return sum(sub_weights[index] for index in range(SUB_SECTORS)
               if index not in covered and horizontal_distance(position, _rep_point(index, radius)) <= range_m)


def _covered(position, range_m, radius):
    return {index for index in range(SUB_SECTORS) if horizontal_distance(position, _rep_point(index, radius)) <= range_m}


def _blocked(position, layout, margin):
    return (in_runway_corridor(position, layout, margin)
            or any(horizontal_distance(f['position'], position) < 70 for f in layout['facilities']))


def road_candidates(context, layout, settings):
    polygon = layout['perimeter']['polygon']
    seen, result = set(), []
    for road in (context or {}).get('roads', []):
        for x, z in road.get('points', [])[::3]:
            key = (round(x / 200), round(z / 200))
            distance = math.hypot(x, z)
            if key in seen or not settings['phone_min_distance_m'] <= distance <= settings['phone_max_distance_m']:
                continue
            if abs(x) > settings['bounds_m'] or abs(z) > settings['bounds_m'] or point_in_polygon(x, z, polygon):
                continue
            seen.add(key)
            result.append([round(x, 1), 0, round(z, 1)])
    return sorted(result)


class RadarModel:
    """Terrain line-of-sight visibility from candidate radar sites to assumed approach samples.

    Samples lie on the axis from each corridor's entry gate toward the airfield (and +-700 m to each side),
    inside the local DEM, at two assumed heights above local terrain (low 50 m, higher 120 m); radars sit on
    a 6 m mast. Visibility is geometric only: no clutter, propagation, Doppler or detection probability.
    """

    def __init__(self, layout, terrain, catalog, corridors):
        settings = catalog['placement']
        kinds = {kind['id']: kind for kind in catalog['unit_kinds']}
        self.range_m = kinds['radar']['display_range_m']
        self.mast_m = settings.get('radar_mast_m', 6)
        self.target_agl_m = settings.get('assumed_target_agl_m', [50, 120])
        self.separation_m = settings.get('radar_separation_m', 1200)
        self.terrain = terrain
        self.layout = layout
        # Line-of-sight steps at the DEM spacing so ridges between grid posts are not skipped.
        self.step_m = (terrain or {}).get('spacing_m', 50)
        self._position_cache = {}
        self._graded = self._graded_grid()
        extent = (terrain or {}).get('extent_m', 10000) / 2 - 100
        step = settings.get('radar_grid_m', 600)
        self.candidates = [[x, 0, z] for x in range(-int(extent // step) * step, int(extent) + 1, step)
                           for z in range(-int(extent // step) * step, int(extent) + 1, step)
                           if not _blocked([x, 0, z], layout, 150) and math.hypot(x, z) <= extent]
        self.samples, self.sample_corridor, self.sample_agl = [], [], []
        for corridor in corridors:
            gx, _, gz = corridor['gate']
            length = math.hypot(gx, gz)
            ux, uz = -gx / length, -gz / length
            for distance in range(int(length) - 200, 400, -settings.get('approach_sample_m', 400)):
                for lateral in (-700, 0, 700):
                    x = ux * -distance - uz * lateral
                    z = uz * -distance + ux * lateral
                    if abs(x) <= extent and abs(z) <= extent:
                        for agl in self.target_agl_m:
                            self.samples.append([round(x, 1), 0, round(z, 1)])
                            self.sample_corridor.append(corridor['id'])
                            self.sample_agl.append(agl)
        self.heights = [self.ground(p[0], p[2]) for p in self.samples]
        self.visible = [self._visible_from(c) for c in self.candidates]

    def ground(self, x, z):
        """Bilinear sample of the graded (as-rendered) height grid built once in _graded_grid."""
        grid = self._graded
        if grid is None:
            return elevation(self.terrain, x, z)
        size, spacing, half = self.terrain['grid_size'], self.terrain['spacing_m'], self.terrain['extent_m'] / 2
        column = min(max((x + half) / spacing, 0.0), size - 1.0)
        row = min(max((z + half) / spacing, 0.0), size - 1.0)
        x0, z0 = int(column), int(row)
        x1, z1 = min(x0 + 1, size - 1), min(z0 + 1, size - 1)
        north = grid[z0][x0] + (grid[z0][x1] - grid[z0][x0]) * (column - x0)
        south = grid[z1][x0] + (grid[z1][x1] - grid[z1][x0]) * (column - x0)
        return north + (south - north) * (row - z0)

    def _graded_grid(self):
        if not self.terrain or not (self.layout.get('terrain_grading') and self.layout.get('perimeter')):
            return None
        size, spacing, half = self.terrain['grid_size'], self.terrain['spacing_m'], self.terrain['extent_m'] / 2
        return [[graded_elevation(self.terrain, self.layout, -half + col * spacing, -half + row * spacing)
                 for col in range(size)] for row in range(size)]

    def visible_at(self, position):
        """Visibility from an arbitrary placed position (memoized to the metre)."""
        key = (round(position[0]), round(position[2]))
        if key not in self._position_cache:
            self._position_cache[key] = self._visible_from([key[0], 0, key[1]])
        return self._position_cache[key]

    def coverage_at(self, positions, weights):
        seen = set().union(*(self.visible_at(p) for p in positions)) if positions else set()
        return sum(weights[i] for i in seen) / (sum(weights) or 1.0)

    def _visible_from(self, candidate):
        rx, rz = candidate[0], candidate[2]
        ry = self.ground(rx, rz) + self.mast_m
        result = set()
        for index, sample in enumerate(self.samples):
            distance = math.hypot(sample[0] - rx, sample[2] - rz)
            if distance > self.range_m:
                continue
            ty = self.heights[index] + self.sample_agl[index]
            steps = max(1, int(distance // self.step_m))
            clear = True
            for step in range(1, steps):
                t = step / steps
                ground = self.ground(rx + (sample[0] - rx) * t, rz + (sample[2] - rz) * t)
                if ground > ry + (ty - ry) * t - 5:
                    clear = False
                    break
            if clear:
                result.add(index)
        return result

    def weights(self, sector_weights):
        # Farther samples matter more (earlier warning); sector weights follow the received picture or prior.
        # Low-level samples weigh more: terrain masking matters most for low-flying aircraft.
        return [(0.5 + math.hypot(p[0], p[2]) / 5000) * (0.2 + sector_weights.get(sector_of(p[0], p[2]), 0))
                * (1.5 if agl < 100 else 1.0) for p, agl in zip(self.samples, self.sample_agl)]

    def coverage(self, indices, weights):
        seen = set().union(*(self.visible[i] for i in indices)) if indices else set()
        total = sum(weights) or 1.0
        return sum(weights[i] for i in seen) / total

    def nearest(self, position):
        return min(range(len(self.candidates)), key=lambda i: horizontal_distance(self.candidates[i], position))

    def greedy(self, fixed, count, weights):
        """Add `count` sites to `fixed` candidate indices, maximizing newly visible weighted samples."""
        chosen = list(fixed)
        seen = set().union(*(self.visible[i] for i in chosen)) if chosen else set()
        added = []
        for _ in range(count):
            best = None
            for index, candidate in enumerate(self.candidates):
                if index in chosen or any(horizontal_distance(candidate, self.candidates[j]) < self.separation_m for j in chosen):
                    continue
                gain = sum(weights[i] for i in self.visible[index] - seen)
                if gain <= 0:
                    continue
                score = gain + 0.001 * self.ground(candidate[0], candidate[2])
                if best is None or score > best[0]:
                    best = (score, index)
            if best is None:
                break
            chosen.append(best[1])
            added.append(best[1])
            seen |= self.visible[best[1]]
        return added


_RADAR_MODELS = {}


def LAYOUT_KEY(layout):
    return dict(runway=layout.get('runway'), facilities=[f.get('position') for f in layout.get('facilities', [])])


def radar_model(layout, terrain, catalog, corridors_path=CORRIDORS_PATH):
    """Cached per terrain/catalog/corridor set: the visibility matrix is static for a run."""
    if not terrain or not Path(corridors_path).exists():
        return None
    corridors = read_json(corridors_path)['corridors']
    # Terrain content identity (pinned source hash + grid), not object identity, so every simulation shares it.
    terrain_key = (terrain.get('source_sha256'), terrain.get('grid_size'), terrain.get('spacing_m'), terrain.get('reference_elevation_m'))
    key = (terrain_key, digest(LAYOUT_KEY(layout)), digest(catalog['placement']), digest([c['gate'] for c in corridors]),
           next(k['display_range_m'] for k in catalog['unit_kinds'] if k['id'] == 'radar'))
    if key not in _RADAR_MODELS:
        _RADAR_MODELS[key] = RadarModel(layout, terrain, catalog, corridors)
    return _RADAR_MODELS[key]


def propose_radar_adjustment(units, layout, terrain, tracks, early_warning, catalog, at_ms=0):
    """Move existing radars and add new ones up to budget to maximize line-of-sight approach coverage."""
    model = radar_model(layout, terrain, catalog)
    if model is None:
        raise ValueError('Radar coverage model needs terrain and approach corridor data')
    budget = next(kind['budget'] for kind in catalog['unit_kinds'] if kind['id'] == 'radar')
    weights_by_sector, basis = threat_weights(tracks, early_warning, catalog)
    weights = model.weights(weights_by_sector)
    radars = [unit for unit in units if unit['kind'] == 'radar']
    # Coverage of the current placement, evaluated at the radars' exact positions.
    before = model.coverage_at([unit['position'] for unit in radars], weights)
    target = model.greedy([], budget, weights)
    # Pair radars with target sites shortest-distance first, so radars already in place stay put.
    pairs = sorted((horizontal_distance(model.candidates[i], unit['position']), unit['id'], i) for unit in radars for i in target)
    assigned, used = {}, set()
    for distance, unit_id, index in pairs:
        if unit_id in assigned or index in used:
            continue
        assigned[unit_id], used = index, used | {index}
    remaining = [i for i in target if i not in used]
    moves = []
    for unit in sorted(radars, key=lambda u: u['id']):
        if unit['id'] not in assigned:
            continue
        destination = model.candidates[assigned[unit['id']]]
        distance = horizontal_distance(destination, unit['position'])
        if distance >= 300:
            moves.append(dict(unit_id=unit['id'], label=copy.deepcopy(unit['label']), from_position=list(unit['position']),
                              to_position=list(destination), distance_m=round(distance)))
    added = remaining[:max(0, budget - len(radars))]
    # Label additions exactly as place_unit will name them (catalog label + first free number).
    kind = next(kind for kind in catalog['unit_kinds'] if kind['id'] == 'radar')
    used = {int(unit['id'].rsplit('_', 1)[1]) for unit in radars if unit['id'].rsplit('_', 1)[1].isdigit()}
    free = [n for n in range(1, budget + 1) if n not in used]
    additions = [dict(position=list(model.candidates[i]),
                      label=dict(en=f"{kind['label']['en']} {free[n]}", ko=f"{kind['label']['ko']} {free[n]}"))
                 for n, i in enumerate(added)]
    moved = {move['unit_id']: move['to_position'] for move in moves}
    final = [moved.get(unit['id'], unit['position']) for unit in radars] + [model.candidates[i] for i in added]
    after = model.coverage_at(final, weights)
    proposal = dict(id=uuid.uuid4().hex, status='pending', moves=moves, additions=additions,
                    coverage_before=round(before, 2), coverage_after=round(after, 2), threat_basis=basis,
                    computed_at_ms=at_ms, budget=budget, scope=SCOPE,
                    basis=dict(en=('Terrain line-of-sight from a 6 m mast to aircraft assumed 50 m and 120 m above local terrain, along the approach axes '
                                   'inside the local DEM, weighted toward ' + ('the scenario prior.' if basis == 'scenario_prior' else 'currently received tracks and area signals.')
                                   + ' Geometry only: no clutter, propagation or detection probability.'),
                               ko=('6 m 마스트에서 지형 위 50 m·120 m로 가정한 비행체까지의 가시선을 접근 축(로컬 DEM 범위)에서 계산했으며, '
                                   + ('시나리오 사전 가정' if basis == 'scenario_prior' else '현재 수신 항적과 지역 신호') + '에 가중치를 두었습니다. '
                                   '기하 계산일 뿐 클러터·전파·탐지 확률은 반영하지 않습니다.')))
    proposal['signature'] = digest(dict(moves=moves, additions=additions))
    return proposal


def apply_radar_adjustment(units, adjustment, catalog):
    budget = next(kind['budget'] for kind in catalog['unit_kinds'] if kind['id'] == 'radar')
    by_id = {unit['id']: unit for unit in units}
    for move in adjustment['moves']:
        unit = by_id.get(move['unit_id'])
        if unit is None or unit['kind'] != 'radar':
            raise ValueError('A radar in this adjustment is no longer placed')
        if horizontal_distance(unit['position'], move['from_position']) > 1:
            raise ValueError('A radar moved since this adjustment was proposed')
    if sum(unit['kind'] == 'radar' for unit in units) + len(adjustment['additions']) > budget:
        raise ValueError('Radar budget would be exceeded')
    for move in adjustment['moves']:
        by_id[move['unit_id']]['position'] = list(move['to_position'])
        by_id[move['unit_id']]['source'] = 'adjusted'
    for addition in adjustment['additions']:
        unit = place_unit(dict(position=addition['position'], kind='radar', role='surveillance'), units, catalog)
        unit['source'] = 'adjusted'
    return units


def propose_placement(layout, terrain, context, tracks, early_warning, catalog, at_ms=0):
    """Deterministic greedy coverage over sectors; display assumptions, not propagation modeling."""
    settings = catalog['placement']
    kinds = {kind['id']: kind for kind in catalog['unit_kinds']}
    weights, basis = threat_weights(tracks, early_warning, catalog)
    sub_weights = _sub_weights(weights)
    positions = []

    # Radar: terrain line-of-sight coverage along the assumed approach axes (see RadarModel).
    model = radar_model(layout, terrain, catalog)
    sample_weights = model.weights(weights) if model else []
    chosen = model.greedy([], kinds['radar']['budget'], sample_weights) if model else []
    if model is None:
        # Without terrain or corridor data, fall back to sector coverage from a fence-side ring.
        covered = set()
        for number in range(kinds['radar']['budget']):
            options = [c for c in ring_points(1200, 16) if not _blocked(c, layout, 150)
                       and all(horizontal_distance(c, row['position']) >= 900 for row in positions)]
            if not options:
                break
            candidate = max(options, key=lambda c: _coverage_gain(c, kinds['radar']['display_range_m'], covered, sub_weights, 4500))
            covered |= _covered(candidate, kinds['radar']['display_range_m'], 4500)
            positions.append(dict(kind='radar', role='surveillance', position=list(candidate),
                                  label=dict(en=f'Radar {number + 1}', ko=f'레이더 {number + 1}'),
                                  basis=dict(en=f'Sector coverage toward {sector_of(candidate[0], candidate[2])} (no terrain data).',
                                             ko=f'{sector_of(candidate[0], candidate[2])} 방향 구역 커버리지 (지형 자료 없음).')))
        radar_fallback = round(sum(sub_weights[i] for i in covered) / (sum(sub_weights) or 1), 2)
    for number, index in enumerate(chosen):
        candidate = model.candidates[index]
        height = model.ground(candidate[0], candidate[2])
        seen = model.coverage([index], sample_weights)
        forward = math.hypot(candidate[0], candidate[2]) > 2000
        positions.append(dict(kind='radar', role='surveillance', position=list(candidate),
                              label=dict(en=f'Radar {number + 1}', ko=f'레이더 {number + 1}'),
                              basis=dict(en=f"{'Forward' if forward else 'Base'} radar on terrain {height:+.0f} m; line of sight to {round(seen * 100)}% of weighted approach samples ({sector_of(candidate[0], candidate[2])}).",
                                         ko=f"{'전방' if forward else '기지'} 레이더, 지형 {height:+.0f} m · 가중 접근 표본의 {round(seen * 100)}%를 가시선으로 관측 ({sector_of(candidate[0], candidate[2])}).")))

    # Acoustic listening posts: road-side posts outside the fence (existing power and access as a proxy).
    phone_covered = set()
    candidates = road_candidates(context, layout, settings) or [p for p in ring_points(2500, 24)]
    phone_positions = []
    for number in range(kinds['detection_phone']['budget']):
        best = None
        for candidate in candidates:
            if any(horizontal_distance(candidate, p) < settings['phone_spacing_m'] for p in phone_positions):
                continue
            gain = _coverage_gain(candidate, kinds['detection_phone']['display_range_m'], phone_covered, sub_weights, 2500)
            score = gain + 0.05 * weights[sector_of(candidate[0], candidate[2])] - math.hypot(candidate[0], candidate[2]) / 100000
            if best is None or score > best[0]:
                best = (score, candidate)
        if best is None:
            break
        candidate = best[1]
        phone_positions.append(candidate)
        phone_covered |= _covered(candidate, kinds['detection_phone']['display_range_m'], 2500)
        positions.append(dict(kind='detection_phone', role='picket', position=list(candidate),
                              label=dict(en=f'P{number + 1} acoustic post', ko=f'P{number + 1} 드론 청음 초소'),
                              basis=dict(en=f'Road-side drone acoustic listening post covering the {sector_of(candidate[0], candidate[2])} sector.',
                                         ko=f'{sector_of(candidate[0], candidate[2])} 방향을 담당하는 도로변 드론 청음 초소.')))

    # Effector teams: fence ring facing the heaviest sectors, away from the runway corridor.
    team_covered = set()
    team_positions = []
    team_candidates = [p for p in ring_points(settings['effector_ring_m'], 16) if not _blocked(p, layout, 150)]
    for number in range(kinds['effector_team']['budget']):
        best = None
        for candidate in team_candidates:
            if any(horizontal_distance(candidate, p) < 500 for p in team_positions):
                continue
            gain = _coverage_gain(candidate, kinds['effector_team']['display_range_m'], team_covered, sub_weights, 1500)
            if best is None or gain > best[0]:
                best = (gain, candidate)
        if best is None:
            break
        candidate = best[1]
        team_positions.append(candidate)
        team_covered |= _covered(candidate, kinds['effector_team']['display_range_m'], 1500)
        sector = sector_of(candidate[0], candidate[2])
        positions.append(dict(kind='effector_team', role='response', position=list(candidate),
                              label=dict(en=f'Team {sector}', ko=f'{sector} 대응 팀'),
                              basis=dict(en=f'Faces the {sector} approach outside the runway corridor.',
                                         ko=f'활주로 회랑 밖에서 {sector} 접근 방향을 담당.')))

    # Infantry: observation posts at remaining gaps, a quick-reaction group, and an eastern road patrol.
    op_covered = set(team_covered)
    op_positions = []
    op_candidates = [p for p in ring_points(settings['observation_ring_m'], 24) if not _blocked(p, layout, 150)]
    budget = kinds['infantry']['budget']
    for number in range(budget // 2):
        best = None
        for candidate in op_candidates:
            if any(horizontal_distance(candidate, p) < 350 for p in op_positions):
                continue
            gain = _coverage_gain(candidate, 900, op_covered, sub_weights, 1500) + 0.01 * weights[sector_of(candidate[0], candidate[2])]
            if best is None or gain > best[0]:
                best = (gain, candidate)
        if best is None:
            break
        candidate = best[1]
        op_positions.append(candidate)
        op_covered |= _covered(candidate, 900, 1500)
        positions.append(dict(kind='infantry', role='observation_post', position=list(candidate),
                              label=dict(en=f'OP {number + 1}', ko=f'관측초소 {number + 1}'),
                              basis=dict(en=f'Eyes and ears on the {sector_of(candidate[0], candidate[2])} gap.',
                                         ko=f'{sector_of(candidate[0], candidate[2])} 방향 공백을 사람이 감시.')))
    apron = next((zone['position'] for zone in layout.get('display_zones', []) if zone['id'] == 'apron'), [100, 0, -100])
    for number in range(3):
        position = [apron[0] + 60 * number, 0, apron[2] + 160]
        positions.append(dict(kind='infantry', role='quick_reaction', position=position,
                              label=dict(en=f'QRF {number + 1}', ko=f'기동타격 {number + 1}'),
                              basis=dict(en='Quick-reaction group near the apron and flight line.', ko='계류장·비행선 인근 기동 대응 인원.')))
    east_road = sorted((p for p in candidates if p[0] > 600 and abs(p[2]) < 1200 and math.hypot(p[0], p[2]) <= 1900),
                       key=lambda p: (math.hypot(p[0], p[2]), p[2])) or [[1300, 0, -400], [1300, 0, 0], [1300, 0, 400]]
    patrol_positions = []
    for candidate in east_road:
        if len(patrol_positions) == 3:
            break
        if all(horizontal_distance(candidate, p) >= 250 for p in patrol_positions):
            patrol_positions.append(candidate)
    while len(patrol_positions) < 3:
        patrol_positions.append([1300, 0, -400 + 400 * len(patrol_positions)])
    for number, position in enumerate(patrol_positions):
        positions.append(dict(kind='infantry', role='patrol', position=list(position),
                              label=dict(en=f'Patrol E {number + 1}', ko=f'동측 순찰 {number + 1}'),
                              basis=dict(en='Exterior east road patrol for vehicle-launch indications.', ko='차량 발진 징후 대비 외곽 동측 도로 순찰.')))
    capped, counts = [], {}
    for row in positions:
        counts[row['kind']] = counts.get(row['kind'], 0) + 1
        if counts[row['kind']] <= kinds[row['kind']]['budget']:
            capped.append(row)
    positions = capped
    total = sum(sub_weights) or 1
    coverage = dict(radar=round(model.coverage(chosen, sample_weights), 2) if model else radar_fallback,
                    detection_phone=round(sum(sub_weights[i] for i in phone_covered) / total, 2),
                    effector_team=round(sum(sub_weights[i] for i in team_covered) / total, 2),
                    infantry=round(sum(sub_weights[i] for i in op_covered) / total, 2))
    proposal = dict(id=uuid.uuid4().hex, status='pending', positions=positions, coverage=coverage,
                    threat_basis=basis, sector_weights=weights, computed_at_ms=at_ms, scope=SCOPE,
                    basis=dict(en=('Greedy sector coverage over the site layout, DEM and mapped roads using '
                                   + ('the scenario prior (north-biased approaches).' if basis == 'scenario_prior' else 'currently received tracks and area signals.')
                                   + ' Ranges are display assumptions, not propagation or detection modeling.'),
                               ko=('기지 배치·지형·도로를 바탕으로 구역 커버리지를 탐욕적으로 계산했습니다. '
                                   + ('기준은 시나리오 사전 가정(북측 접근 편중)입니다.' if basis == 'scenario_prior' else '기준은 현재 수신된 항적과 지역 신호입니다.')
                                   + ' 범위는 표시용 가정이며 전파·탐지 모델이 아닙니다.')))
    proposal['signature'] = digest(dict(positions=positions, coverage=coverage))
    return proposal


def units_from_proposal(proposal):
    counters = {}
    units = []
    for row in proposal['positions']:
        counters[row['kind']] = counters.get(row['kind'], 0) + 1
        units.append(dict(id=f"{row['kind']}_{counters[row['kind']]}", kind=row['kind'], role=row['role'],
                          label=copy.deepcopy(row['label']), position=list(row['position']),
                          status='positioned', source='proposal'))
    return units


def place_unit(command, units, catalog):
    """Manual placement or move within per-kind budgets and the local bounds."""
    kinds = {kind['id']: kind for kind in catalog['unit_kinds']}
    position = command.get('position')
    if not valid_position(position):
        raise ValueError('Position must be finite local metres within 5 km of the site origin with Y = 0')
    unit_id = command.get('unit_id')
    if unit_id is not None:
        unit = next((row for row in units if row['id'] == unit_id), None)
        if unit is None:
            raise ValueError('Unknown unit')
        unit['position'] = [float(position[0]), 0, float(position[2])]
        unit['source'] = 'manual'
        return unit
    kind = command.get('kind', 'infantry')
    if kind not in kinds:
        raise ValueError('Unknown unit kind')
    if sum(row['kind'] == kind for row in units) >= kinds[kind]['budget']:
        raise ValueError('Unit budget for this kind is exhausted')
    numbers = {int(row['id'].rsplit('_', 1)[1]) for row in units if row['kind'] == kind and row['id'].rsplit('_', 1)[1].isdigit()}
    number = next(n for n in range(1, kinds[kind]['budget'] + 1) if n not in numbers)
    label = kinds[kind]['label']
    unit = dict(id=f'{kind}_{number}', kind=kind, role=command.get('role') if command.get('role') in ('observation_post', 'patrol', 'quick_reaction', 'surveillance', 'picket', 'response') else None,
                label=dict(en=f"{label['en']} {number}", ko=f"{label['ko']} {number}"),
                position=[float(position[0]), 0, float(position[2])], status='positioned', source='manual')
    units.append(unit)
    return unit


# ----------------------------------------------------------------------------- formation

def formation(units, targets, catalog):
    """Task organization by sector from placed units and current identification."""
    teams = []
    by_sector = {}
    for target in targets:
        by_sector.setdefault(target['identification']['sector'], []).append(target)
    for unit in units:
        sector = sector_of(unit['position'][0], unit['position'][2])
        role = unit.get('role') or {'infantry': 'observation_post', 'radar': 'surveillance',
                                    'detection_phone': 'picket', 'effector_team': 'response'}[unit['kind']]
        key = (unit['kind'], role, sector if role in ('response', 'observation_post', 'picket', 'surveillance', 'patrol') else 'site')
        team = next((row for row in teams if row['key'] == key), None)
        if team is None:
            team = dict(key=key, id=f"{unit['kind']}:{role}:{key[2]}", kind=unit['kind'], role=role, sector=key[2], unit_ids=[], tasking=[])
            teams.append(team)
        team['unit_ids'].append(unit['id'])
    for team in teams:
        tracked = by_sector.get(team['sector'], [])
        if team['role'] == 'response':
            tasking = [dict(object_id=t['object_id'], posture=t['response']['posture'], primary=t['response']['primary']) for t in tracked]
        elif team['role'] in ('observation_post', 'picket', 'surveillance'):
            tasking = [dict(object_id=t['object_id'], lean=t['identification']['lean']) for t in tracked]
        else:
            tasking = []
        team['tasking'], team['tasking_count'] = tasking[:MAX_TASKING], len(tasking)
        del team['key']
    current = [t for t in targets if not t['identification'].get('stale')]
    if any('runway_overflight' in t['response']['constraints'] for t in current):
        posture = 'hold'
    elif any(t['response']['posture'] == 'engage_candidate' for t in current):
        posture = 'respond'
    elif current:
        posture = 'observe'
    else:
        posture = 'ready'
    return dict(posture=posture, teams=teams, unit_count=len(units),
                by_kind={kind['id']: sum(u['kind'] == kind['id'] for u in units) for kind in catalog['unit_kinds']})


# ----------------------------------------------------------------------------- state view

def view(tracks, reports, allocations, units, layout, catalog, at_ms, early_warning=None):
    received = {track['object_id'] for track in tracks}
    reports = [row for row in reports if row['object_id'] in received]
    identifications = identify(tracks, reports, layout, at_ms, catalog)
    responses = {row['object_id']: row for row in recommend(identifications, tracks, allocations, units, layout, catalog)}
    targets = [dict(object_id=ident['object_id'], identification=ident, response=responses[ident['object_id']])
               for ident in identifications]
    effectors = []
    for effector in catalog['effectors']:
        used = sum(record['effector_id'] == effector['id'] for record in allocations)
        effectors.append(dict(id=effector['id'], label=copy.deepcopy(effector['label']), cost_tier=effector['cost_tier'],
                              cost_note=copy.deepcopy(effector['cost_note']), nominal_range_m=effector['nominal_range_m'],
                              inventory=effector['inventory_per_run'], used=used,
                              remaining=effector['inventory_per_run'] - used if effector['inventory_per_run'] is not None else None))
    counts = {lean: sum(t['identification']['lean'] == lean for t in targets) for lean in LEANS}
    return dict(scope=SCOPE, synthetic=True, targets=targets, effectors=effectors,
                formation=formation(units, targets, catalog),
                allocations=[{key: copy.deepcopy(value) for key, value in record.items() if key != 'evidence_snapshot'} for record in allocations],
                summary=dict(received=len(targets), by_lean=counts,
                             postures={posture: sum(t['response']['posture'] == posture for t in targets) for posture in POSTURES},
                             reports_received=len(reports)),
                limitations=['Rule-based rubric from the scenario documents; uncalibrated and not a classifier benchmark.',
                             'Identification reports are synthetic fixtures, not sensor performance.',
                             'Options are training recommendations; confirmation records a decision and changes nothing in the scene.'])
