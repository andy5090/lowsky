"""Build data/geography/korean_mdl.json from a pinned Natural Earth revision (stdlib only).

Natural Earth 1:10m "Admin 0 boundary lines (land)" carries the Military Demarcation
Line 1953 and the southern/northern DMZ limits. The file is public domain. Lines are
generalized at 1:10m, so offsets of hundreds of metres are expected; the result is a
simulation reference, not a survey or a legal boundary.
"""
import argparse
import hashlib
import json
import math
import urllib.request
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
OUTPUT = PROJECT / 'data/geography/korean_mdl.json'
COMMIT = 'ca96624a56bd078437bca8184e78163e5039ad19'
URL = f'https://raw.githubusercontent.com/nvkelso/natural-earth-vector/{COMMIT}/geojson/ne_10m_admin_0_boundary_lines_land.geojson'
SHA256 = '74d9c16229c095fde65943a9919e337682f044bcebccb120764f38edf3b70f4a'
# Same small-area projection and radius as monitor/geo.mjs (localToGeo / geoToLocal).
EARTH_RADIUS = 6378137
ORIGIN = dict(lat=37.9, lon=127.2)
LON_RANGE = (126.6, 127.9)
FEATURES = {
    'mdl': dict(match=('Military Demarcation Line 1953', None),
                label=dict(en='Military Demarcation Line (MDL)', ko='군사분계선 (MDL)')),
    'dmz_south': dict(match=('Korean Demilitarized Zone', 'South Korea'),
                      label=dict(en='DMZ southern limit', ko='비무장지대 남방한계선')),
    'dmz_north': dict(match=('Korean Demilitarized Zone', 'North Korea'),
                      label=dict(en='DMZ northern limit', ko='비무장지대 북방한계선')),
}


DMZ_HALF_WIDTH_M = 2000  # Korean Armistice Agreement: 2 km on each side of the MDL


def to_geo(x, z):
    radians = math.pi / 180
    return [round(ORIGIN['lat'] - z / EARTH_RADIUS / radians, 5),
            round(ORIGIN['lon'] + x / (EARTH_RADIUS * math.cos(ORIGIN['lat'] * radians)) / radians, 5)]


def offset_part(points, distance):
    """Offset a local polyline sideways; positive distance moves toward smaller Z (north)."""
    result = []
    for index, (x, z) in enumerate(points):
        ax, az = points[max(0, index - 1)]
        bx, bz = points[min(len(points) - 1, index + 1)]
        dx, dz = bx - ax, bz - az
        length = math.hypot(dx, dz) or 1.0
        nx, nz = -dz / length, dx / length
        if nz > 0:  # choose the normal that points north (negative Z)
            nx, nz = -nx, -nz
        result.append([round(x + nx * distance, 1), round(z + nz * distance, 1)])
    return result


def chain(runs, tolerance=1e-6):
    """Join line fragments that share endpoints into continuous runs (reversing fragments as needed)."""
    pending = [list(run) for run in runs]
    chains = []
    while pending:
        current = pending.pop(0)
        extended = True
        while extended:
            extended = False
            for index, run in enumerate(pending):
                close = lambda a, b: abs(a[0] - b[0]) < tolerance and abs(a[1] - b[1]) < tolerance
                if close(current[-1], run[0]):
                    current += run[1:]
                elif close(current[-1], run[-1]):
                    current += run[::-1][1:]
                elif close(current[0], run[-1]):
                    current = run[:-1] + current
                elif close(current[0], run[0]):
                    current = run[::-1][:-1] + current
                else:
                    continue
                pending.pop(index)
                extended = True
                break
        chains.append(current)
    return chains


def to_local(lat, lon):
    radians = math.pi / 180
    return [round((lon - ORIGIN['lon']) * radians * EARTH_RADIUS * math.cos(ORIGIN['lat'] * radians), 1),
            round((ORIGIN['lat'] - lat) * radians * EARTH_RADIUS, 1)]


def download(cache=None):
    if cache and Path(cache).is_file():
        content = Path(cache).read_bytes()
    else:
        request = urllib.request.Request(URL, headers={'User-Agent': 'LowSkySimulation/1.0'})
        with urllib.request.urlopen(request, timeout=120) as response:
            content = response.read()
    if hashlib.sha256(content).hexdigest() != SHA256:
        raise ValueError('Natural Earth source changed; review before updating the pinned hash')
    return json.loads(content)


def build(source):
    lines = {}
    for feature in source['features']:
        properties = feature['properties']
        key = next((key for key, spec in FEATURES.items()
                    if properties.get('NAME') == spec['match'][0]
                    and (spec['match'][1] is None or properties.get('ADM0_LEFT') == spec['match'][1])), None)
        if key is None:
            continue
        geometry = feature['geometry']
        parts = [geometry['coordinates']] if geometry['type'] == 'LineString' else geometry['coordinates']
        clipped = []
        for run in chain([[(lat, lon) for lon, lat in part] for part in parts]):
            run = [(lat, lon) for lat, lon in run if LON_RANGE[0] <= lon <= LON_RANGE[1]]
            if len(run) >= 2:
                clipped.append(run)
        lines[key] = dict(label=FEATURES[key]['label'],
                          parts=[dict(lat_lon=[[round(lat, 5), round(lon, 5)] for lat, lon in run],
                                      local=[to_local(lat, lon) for lat, lon in run]) for run in clipped])
    missing = set(FEATURES) - set(lines)
    if missing:
        raise ValueError(f'Natural Earth file lacks {sorted(missing)}')
    # Natural Earth's generalized DMZ limit lines lie 4-6 km from its MDL near the site. Draw the limits at the
    # nominal 2 km offset from the MDL instead, and keep Natural Earth's own lines as reference data only.
    reference = {f'natural_earth_{key}': lines.pop(key) for key in ('dmz_south', 'dmz_north')}
    for key, sign in (('dmz_north', 1), ('dmz_south', -1)):
        parts = []
        for part in lines['mdl']['parts']:
            local = offset_part(part['local'], sign * DMZ_HALF_WIDTH_M)
            parts.append(dict(lat_lon=[to_geo(x, z) for x, z in local], local=local))
        lines[key] = dict(label=FEATURES[key]['label'], parts=parts,
                          derivation=f'MDL offset {DMZ_HALF_WIDTH_M} m to the {"north" if sign > 0 else "south"}')
    return dict(schema_version='1.0', origin=ORIGIN, earth_radius_m=EARTH_RADIUS,
                axes='local X east, Z south; metres; same projection as monitor/geo.mjs',
                lon_range=list(LON_RANGE), lines=lines, reference_lines=reference,
                source=dict(name='Natural Earth 1:10m Admin 0 boundary lines (land)', url=URL, commit=COMMIT,
                            sha256=SHA256, license='Public domain (Natural Earth)',
                            feature_class_note='Natural Earth labels the MDL "Line of control (please verify)".'),
                limitations=['1:10m generalization: positions can be off by hundreds of metres.',
                             'Simulation reference only; not a survey, legal boundary or navigation source.',
                             'DMZ limits are drawn at the nominal 2 km from the Natural Earth MDL; Natural Earth\'s own generalized DMZ limit lines (4-6 km from its MDL near the site) are kept under reference_lines only.'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache', help='Use a previously downloaded copy (hash still verified)')
    args = parser.parse_args()
    data = build(download(args.cache))
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(data, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print(OUTPUT, {key: sum(len(part['local']) for part in value['parts']) for key, value in data['lines'].items()})


if __name__ == '__main__':
    main()
