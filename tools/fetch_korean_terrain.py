"""Fetch one pinned public DEM tile and sample a 10km local terrain (stdlib only)."""
import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path
import struct
from urllib.request import urlopen

PROJECT = Path(__file__).resolve().parents[1]
URL = 'https://elevation-tiles-prod.s3.amazonaws.com/skadi/N36/N36E127.hgt.gz'
SHA256 = '2c319768aa062b613d4195655fdbd20b8b61729f4c7a7b1cc0b27e46a6589676'
RADIUS = 6378137


def local_to_geo(x, z, origin):
    return (origin['lat'] - math.degrees(z / RADIUS),
            origin['lon'] + math.degrees(x / (RADIUS * math.cos(math.radians(origin['lat'])))))


def sample(raw, size, lat, lon):
    if not (36 <= lat <= 37 and 127 <= lon <= 128):
        raise ValueError('Point outside pinned N36E127 tile')
    x, y = (lon - 127) * (size - 1), (37 - lat) * (size - 1)
    x0, y0 = min(int(x), size - 2), min(int(y), size - 2)
    dx, dy = x - x0, y - y0
    values = [struct.unpack_from('>h', raw, 2 * (row * size + col))[0]
              for row, col in [(y0,x0),(y0,x0+1),(y0+1,x0),(y0+1,x0+1)]]
    if -32768 in values:
        raise ValueError('DEM void encountered; do not invent elevations')
    return (values[0]*(1-dx)+values[1]*dx)*(1-dy)+(values[2]*(1-dx)+values[3]*dx)*dy


def build(cache):
    if not cache.exists():
        with urlopen(URL, timeout=90) as response:
            cache.write_bytes(response.read())
    compressed = cache.read_bytes()
    if hashlib.sha256(compressed).hexdigest() != SHA256:
        raise ValueError('Terrain source checksum changed')
    raw = gzip.decompress(compressed)
    size = math.isqrt(len(raw) // 2)
    if size != 3601 or size*size*2 != len(raw):
        raise ValueError('Unexpected HGT dimensions')
    config = json.loads((PROJECT / 'monitor/map_config.json').read_text())
    origin = config['site_origin']
    heights = [[round(sample(raw,size,*local_to_geo(x*50-5000,z*50-5000,origin)),2)
                for x in range(201)] for z in range(201)]
    data = dict(schema_version='1.0', origin=origin, axes='X east, Y up, Z south',
                grid_size=201, spacing_m=50, extent_m=10000,
                reference_elevation_m=round(sample(raw,size,origin['lat'],origin['lon']),2),
                source='Mapzen Terrain Tiles / USGS', source_url=URL, source_sha256=SHA256,
                attribution='SRTM and GMTED2010 terrain data courtesy of the U.S. Geological Survey; Mapzen Terrain Tiles.',
                source_grid_arcseconds=1, resampling='bilinear, 50m local grid',
                modifications='Raw sampled elevations stored here; renderer flattens fictional site and blends 700m to surrounding DEM.',
                heights_m=heights)
    output = PROJECT / 'data/terrain/korea_site.json'
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(data,separators=(',',':'))+'\n')
    flat = [v for row in heights for v in row]
    print(json.dumps({'grid':201,'range_m':[min(flat),max(flat)],'reference_elevation_m':data['reference_elevation_m'],'output':str(output)}))


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache',type=Path,default=Path('/tmp/lowsky-N36E127.hgt.gz'))
    build(parser.parse_args().cache)
