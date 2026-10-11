"""Synthetic infiltration routes from launch areas north of the DMZ to the virtual airfield.

Launch areas sit 5 km north of the MDL (3 km beyond the nominal 2 km DMZ half-width, North Korean side).
Offsets are measured from the Natural Earth MDL because its generalized DMZ limit lines lie 4-6 km from it here.
Five approach corridors follow curved, valley-like paths south; each aircraft adds its own
lateral offset and weave, then ends by role: decoys overfly, strike aircraft dogleg and
descend onto a facility, reconnaissance aircraft loiter, multirotors hover near a facility.

The 4½-minute indirect phase compresses the 40-50 km transit; after the first direct
observation, speeds follow class assumptions. Corridors are scenario-design assumptions
about avenues of approach, not observed or predicted enemy routes.
"""
import json
import math
import random
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
MDL_PATH = PROJECT / 'data/geography/korean_mdl.json'
VERSION = 'infiltration-routes-v1'
DMZ_HALF_WIDTH_M = 2000  # Armistice nominal; Natural Earth's DMZ limit lines are generalized
LAUNCH_NORTH_OF_MDL_M = DMZ_HALF_WIDTH_M + 3000
GATE_RADIUS_M = 7500
# Godot's finale starts at facility + 35 m anchor + 100 m (godot/preview.gd update_mission_vignettes).
VIGNETTE_HEIGHT_M = 135
PULL_OUT_FLOOR_M = 30

# Corridor control points in local metres (X east, Z south). Launch Z is derived from the DMZ line.
CORRIDORS = [
    dict(id='west_valley', label=dict(en='Western valley corridor', ko='서측 계곡 회랑'), launch_x=-20000,
         controls=[(-21500, -37000), (-16500, -27500), (-12500, -17500), (-9000, -9500)], gate_bearing=300),
    dict(id='central_west', label=dict(en='Central-west corridor', ko='중서부 회랑'), launch_x=-9000,
         controls=[(-10500, -37500), (-5500, -28500), (-8000, -18500), (-4500, -11000)], gate_bearing=335),
    dict(id='central', label=dict(en='Central corridor', ko='중앙 회랑'), launch_x=2000,
         controls=[(3500, -38000), (-1500, -29500), (2500, -20500), (-500, -12500)], gate_bearing=0),
    dict(id='central_east', label=dict(en='Central-east corridor', ko='중동부 회랑'), launch_x=14000,
         controls=[(12500, -38500), (9500, -28500), (7000, -19000), (4500, -11500)], gate_bearing=25),
    dict(id='eastern_arc', label=dict(en='Eastern arc corridor', ko='동측 우회 회랑'), launch_x=25000,
         controls=[(24000, -37000), (20000, -24000), (14500, -12000), (10000, -5500)], gate_bearing=65),
]

ROLE_BY_AIRFRAME = {
    'gerbera': 'decoy', 'parodiya': 'decoy', 'molniya': 'decoy',
    'geran_2': 'strike', 'geran_3': 'strike_jet', 'lancet': 'strike', 'garpiya': 'strike',
    'orlan_10': 'recon', 'orlan_30': 'recon', 'zala': 'recon', 'supercam': 'recon',
    'quadcopter': 'multirotor', 'fpv': 'multirotor', 'hexacopter': 'multirotor',
}
# Final-phase ground speed (m/s) after the first direct observation; transit is compressed separately.
SPEED = dict(decoy=(17, 21), strike=(17, 22), strike_jet=(30, 38), recon=(15, 19), multirotor=(10, 14))
ALTITUDE = dict(decoy=(70, 130), strike=(60, 120), strike_jet=(140, 220), recon=(240, 340), multirotor=(40, 90))
LAUNCH_WINDOW_MS = dict(decoy=(0, 20_000), recon=(0, 30_000), multirotor=(0, 30_000), strike=(30_000, 70_000), strike_jet=(80_000, 110_000))


def _load_lines(path=MDL_PATH):
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    return {key: [part['local'] for part in value['parts']] for key, value in data['lines'].items()}


def line_z_at(parts, x):
    """Z of a polyline at local X; the northernmost crossing if the line folds."""
    hits = []
    for part in parts:
        for (x1, z1), (x2, z2) in zip(part, part[1:]):
            if min(x1, x2) <= x <= max(x1, x2) and x1 != x2:
                hits.append(z1 + (z2 - z1) * (x - x1) / (x2 - x1))
    if not hits:
        raise ValueError(f'Line does not cover x={x}')
    return min(hits)


def launch_areas(path=MDL_PATH):
    lines = _load_lines(path)
    areas = []
    for corridor in CORRIDORS:
        x = corridor['launch_x']
        areas.append(dict(id=corridor['id'], label=corridor['label'],
                          position=[x, 0, round(line_z_at(lines['mdl'], x) - LAUNCH_NORTH_OF_MDL_M, 1)],
                          mdl_crossing=[x, 0, round(line_z_at(lines['mdl'], x), 1)]))
    return areas


def _catmull(points, samples=18):
    """Centripetal-free uniform Catmull-Rom through points; returns a dense 2D polyline."""
    padded = [points[0], *points, points[-1]]
    result = []
    for i in range(1, len(padded) - 2):
        p0, p1, p2, p3 = padded[i - 1:i + 3]
        for step in range(samples):
            t = step / samples
            t2, t3 = t * t, t * t * t
            result.append(tuple(0.5 * ((2 * p1[k]) + (-p0[k] + p2[k]) * t + (2 * p0[k] - 5 * p1[k] + 4 * p2[k] - p3[k]) * t2
                                       + (-p0[k] + 3 * p1[k] - 3 * p2[k] + p3[k]) * t3) for k in (0, 1)))
    result.append(tuple(points[-1]))
    return result


def _cumulative(path):
    total = [0.0]
    for a, b in zip(path, path[1:]):
        total.append(total[-1] + math.dist(a, b))
    return total


def _at(path, cumulative, s):
    s = max(0.0, min(s, cumulative[-1]))
    index = 0
    while index < len(cumulative) - 2 and cumulative[index + 1] < s:
        index += 1
    span = cumulative[index + 1] - cumulative[index] or 1.0
    t = (s - cumulative[index]) / span
    a, b = path[index], path[index + 1]
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def _weave(path, rng, offset, amplitude, wavelength):
    """Shift a path sideways: constant offset plus a slow sinusoidal weave, tapering near the end."""
    cumulative = _cumulative(path)
    total = cumulative[-1] or 1.0
    phase = rng.uniform(0, 2 * math.pi)
    result = []
    for index, (x, z) in enumerate(path):
        before, after = path[max(0, index - 1)], path[min(len(path) - 1, index + 1)]
        dx, dz = after[0] - before[0], after[1] - before[1]
        norm = math.hypot(dx, dz) or 1.0
        nx, nz = -dz / norm, dx / norm
        # Keep a residual spread at the gate so aircraft sharing a corridor never stack on one point.
        taper = 0.4 + 0.6 * min(1.0, (total - cumulative[index]) / 2500)
        lateral = taper * (offset + amplitude * math.sin(phase + 2 * math.pi * cumulative[index] / wavelength))
        result.append((x + nx * lateral, z + nz * lateral))
    return result


def _gate(corridor):
    angle = math.radians(corridor['gate_bearing'])
    return (GATE_RADIUS_M * math.sin(angle), -GATE_RADIUS_M * math.cos(angle))


def _terminal(role, gate, target, rng):
    """Role-specific end of route after the entry gate."""
    gx, gz = gate
    tx, tz = target
    dx, dz = tx - gx, tz - gz
    norm = math.hypot(dx, dz) or 1.0
    ux, uz = dx / norm, dz / norm
    side = rng.choice((-1, 1))
    if role == 'decoy':
        # Straight-ish overflight that continues 3 km past the airfield.
        return [(gx + dx * 0.5 + side * uz * 300, gz + dz * 0.5 - side * ux * 300), (tx, tz), (tx + ux * 3000, tz + uz * 3000)], None
    if role == 'recon':
        # Loiter orbit centred 2.5-4 km short of the airfield.
        distance = rng.uniform(2500, 4000)
        centre = (tx - ux * distance, tz - uz * distance)
        radius = rng.uniform(700, 1300)
        mid = ((gx + centre[0]) / 2, (gz + centre[1]) / 2)
        # End the approach on the orbit circle so loiter entry is continuous.
        mx, mz = mid[0] - centre[0], mid[1] - centre[1]
        norm_m = math.hypot(mx, mz) or 1.0
        entry = (centre[0] + mx / norm_m * radius, centre[1] + mz / norm_m * radius)
        return [mid, entry], dict(centre=centre, radius=radius, clockwise=side > 0)
    if role == 'multirotor':
        return [(gx + dx * 0.55 + side * uz * 600, gz + dz * 0.55 - side * ux * 600), (tx + side * 60, tz - 80)], 'hover'
    # Strike: dogleg 1-1.6 km to the side, then a direct run onto the facility.
    dogleg = rng.uniform(1000, 1600)
    return [(gx + dx * 0.55 + side * uz * dogleg, gz + dz * 0.55 - side * ux * dogleg),
            (tx - ux * 900 + side * uz * 200, tz - uz * 900 - side * ux * 200), (tx, tz)], 'descend'


def build_route(corridor, launch, target, role, rng):
    gate = _gate(corridor)
    head = [(launch[0], launch[2]), *corridor['controls'], gate]
    smooth = _catmull(head)
    weave = _weave(smooth, rng, offset=rng.uniform(-700, 700), amplitude=rng.uniform(150, 450), wavelength=rng.uniform(6000, 11000))
    tail_points, ending = _terminal(role, gate, target, rng)
    tail = _catmull([weave[-1], *tail_points], samples=10)
    return dict(transit=weave, terminal=tail, ending=ending, gate=gate)


def sample_route(route, role, rng, times, gate_ms, launch_ms, end_ms, final_speed, altitude, arrive_ms=None,
                 entry_ms=None):
    """Keyframes for the replay clock. Transit is time-compressed from launch to gate_ms."""
    transit, terminal = route['transit'], route['terminal']
    t_cum, f_cum = _cumulative(transit), _cumulative(terminal)
    if arrive_ms is not None:
        # Vignette aircraft arrive at the end of the terminal path exactly at arrive_ms.
        final_speed = f_cum[-1] / max(1.0, (arrive_ms - gate_ms) / 1000)
    frames = []
    for at in times:
        if at <= launch_ms:
            x, z = transit[0]
            y = 0.0
        elif at <= gate_ms:
            progress = (at - launch_ms) / max(1, gate_ms - launch_ms)
            x, z = _at(transit, t_cum, t_cum[-1] * progress)
            # Climb out over the first 40 s after launch; the compact case starts airborne at the gate.
            y = altitude if launch_ms < 0 else altitude * min(1.0, (at - launch_ms) / 40_000)
        else:
            s = final_speed * (at - gate_ms) / 1000
            if s <= f_cum[-1]:
                x, z = _at(terminal, f_cum, s)
                fraction = s / (f_cum[-1] or 1)
                y = altitude
                if route['ending'] == 'vignette' and fraction > 0.8:
                    # Meet the 3D finale start point (100 m above the facility) exactly on arrival.
                    y = altitude + (VIGNETTE_HEIGHT_M - altitude) * (fraction - 0.8) / 0.2
                elif route['ending'] == 'descend' and fraction > 0.75:
                    y = max(PULL_OUT_FLOOR_M, altitude * max(0.15, 1 - (fraction - 0.75) * 3.4))
                elif route['ending'] == 'hover':
                    y = altitude * (1 - 0.4 * fraction)
            else:
                beyond = s - f_cum[-1]
                ending = route['ending']
                if isinstance(ending, dict):
                    # Loiter orbit, entered tangentially from the last terminal point.
                    cx, cz = ending['centre']
                    ex, ez = terminal[-1]
                    start = math.atan2(ez - cz, ex - cx)
                    # Z points south, so an increasing angle turns clockwise on the map.
                    angle = start + (1 if ending['clockwise'] else -1) * beyond / ending['radius']
                    x, z = cx + ending['radius'] * math.cos(angle), cz + ending['radius'] * math.sin(angle)
                    y = altitude
                elif ending == 'vignette':
                    x, z = terminal[-1]
                    y = VIGNETTE_HEIGHT_M
                elif ending == 'hover':
                    x, z = terminal[-1]
                    y = altitude * 0.6
                elif ending == 'descend':
                    # No damage model outside the scripted vignettes: pull out low past the target and continue.
                    a, b = terminal[-2], terminal[-1]
                    length = math.dist(a, b) or 1.0
                    x, z = b[0] + (b[0] - a[0]) / length * beyond, b[1] + (b[1] - a[1]) / length * beyond
                    y = max(PULL_OUT_FLOOR_M, altitude * min(0.6, 0.15 + beyond / 4000))
                else:
                    a, b = terminal[-2], terminal[-1]
                    length = math.dist(a, b) or 1.0
                    x, z = b[0] + (b[0] - a[0]) / length * beyond, b[1] + (b[1] - a[1]) / length * beyond
                    y = altitude
        frames.append({'at_ms': at, 'position': [round(x, 1), round(y, 1), round(z, 1)]})
    return frames


def targets(layout):
    facilities = {f['id']: f['position'] for f in layout['facilities']}
    return facilities


def corridor_summary(path=MDL_PATH):
    """Planning view of corridors (no per-aircraft offsets): launch area, MDL crossing, gate and centreline."""
    areas = {area['id']: area for area in launch_areas(path)}
    rows = []
    for corridor in CORRIDORS:
        area = areas[corridor['id']]
        line = _catmull([(area['position'][0], area['position'][2]), *corridor['controls'], _gate(corridor)], samples=6)
        rows.append(dict(id=corridor['id'], label=corridor['label'], launch=area['position'], mdl_crossing=area['mdl_crossing'],
                         gate=[round(_gate(corridor)[0], 1), 0, round(_gate(corridor)[1], 1)], gate_bearing_deg=corridor['gate_bearing'],
                         centreline=[[round(x, 1), 0, round(z, 1)] for x, z in line]))
    return rows


def plan_objects(case_id, object_ids, airframes, layout, times, paced, path=MDL_PATH, vignettes=None):
    """Deterministic keyframes and route metadata for every object in one case."""
    vignettes = vignettes or {}
    areas = {area['id']: area for area in launch_areas(path)}
    facility_positions = targets(layout)
    strike_targets = ['hangar_1', 'hangar_2', 'hangar_3', 'tower', 'maintenance_hangar', 'support_1', 'admin_1', 'station_a', 'station_b']
    end_ms = times[-1]
    worlds, meta = {}, {}
    for index, object_id in enumerate(object_ids):
        rng = random.Random(f'{VERSION}:{case_id}:{object_id}')
        airframe = airframes[object_id]
        role = ROLE_BY_AIRFRAME.get(airframe, 'decoy')
        # Spread aircraft across corridors in small groups so decoy waves travel together.
        corridor = CORRIDORS[(index // 3) % len(CORRIDORS)]
        target_id = vignettes.get(object_id, {}).get('asset_id') or strike_targets[(index * 7 + len(object_id)) % len(strike_targets)]
        tx, _, tz = facility_positions[target_id]
        if role == 'decoy':
            tx, tz = tx + rng.uniform(-400, 400), tz + rng.uniform(-600, 600)
        route = build_route(corridor, areas[corridor['id']]['position'], (tx, tz), role, rng)
        altitude = rng.uniform(*ALTITUDE[role])
        speed = rng.uniform(*SPEED[role])
        if paced:
            launch_ms = rng.randint(*LAUNCH_WINDOW_MS[role])
            gate_ms = rng.randint(255_000, 270_000)
        else:
            # Compact load test: aircraft are already inbound at the gate at replay start.
            launch_ms, gate_ms = -1, 0
            speed *= 1.8
        arrive_ms = vignettes.get(object_id, {}).get('arrive_ms')
        if arrive_ms is not None:
            # Strike-style run onto the authored facility; the 3D finale takes over on arrival.
            tail_points, _ = _terminal('strike', route['gate'], (tx, tz), rng)
            route['terminal'] = _catmull([route['transit'][-1], *tail_points], samples=10)
            route['ending'] = 'vignette'
        frames = sample_route(route, role, rng, times, gate_ms, launch_ms, end_ms, speed, altitude, arrive_ms=arrive_ms)
        worlds[object_id] = frames
        meta[object_id] = dict(corridor_id=corridor['id'], role=role, target_id=target_id,
                               launch_ms=launch_ms if paced else None, gate_ms=gate_ms if paced else None,
                               launch_area=areas[corridor['id']]['position'] if paced else None)
    return worlds, meta
