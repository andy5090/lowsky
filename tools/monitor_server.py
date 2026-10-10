"""Local shared replay clock and observation-only monitoring API (stdlib only)."""
import argparse
import json
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

try:
    from .scenario_dataset import ROOT, read_json, snapshot, information_state
except ImportError:
    from scenario_dataset import ROOT, read_json, snapshot, information_state

PROJECT = Path(__file__).resolve().parents[1]


class Simulation:
    def __init__(self, root=ROOT, clock=time.monotonic):
        self.root, self.clock = root, clock
        self.lock = threading.RLock()
        self.cases = read_json(root / 'manifest.json')['cases']
        self.public = {entry['case_id']: read_json(root / 'cases' / entry['case_id'] / 'public.json') for entry in self.cases}
        self.case_id = self.cases[0]['case_id']
        self.anchor_ms, self.anchor_wall = 0, clock()
        self.playing, self.speed = False, 1
        self.run_id = uuid.uuid4().hex
        self.revision = 0
        self.acknowledged = set()

    def _time(self):
        elapsed = (self.clock() - self.anchor_wall) * 1000 * self.speed if self.playing else 0
        return min(self.public[self.case_id]['duration_ms'], int(self.anchor_ms + elapsed))

    def _clock_state(self):
        at_ms = self._time()
        duration = self.public[self.case_id]['duration_ms']
        return dict(case_id=self.case_id, run_id=self.run_id, revision=self.revision,
                    at_ms=at_ms, duration_ms=duration, playing=self.playing and at_ms < duration, speed=self.speed)

    def clock_state(self):
        with self.lock:
            return self._clock_state()

    def state(self):
        with self.lock:
            clock = self._clock_state()
            payload = snapshot(self.public[self.case_id], clock['at_ms'])
            health = []
            latest_health = {}
            for source in payload['source_ids']:
                rows = [r for r in payload['source_health'] if r['source_id'] == source]
                row = max(rows, key=lambda r: (r['observed_at_ms'], r['available_at_ms']), default=None)
                status = 'unknown' if row is None else row['status']
                if row and payload['at_ms'] - row['observed_at_ms'] > payload['freshness_ms']:
                    status = 'stale'
                latest_health[source] = status
                health.append(dict(source_id=source, status=status, evidence=row))
            tracks, alerts = [], []
            for obj in payload['object_ids']:
                records = []
                for source in payload['source_ids']:
                    rows = [r for r in payload['observations'] if r['source_id'] == source and r['object_id'] == obj]
                    row = max(rows, key=lambda r: (r['observed_at_ms'], r['available_at_ms']), default=None)
                    if row:
                        records.append(row)
                fresh = [r for r in records if latest_health[r['source_id']] == 'online'
                         and payload['at_ms'] - r['observed_at_ms'] <= payload['freshness_ms']]
                position_record = max(fresh or records, key=lambda r: (r['observed_at_ms'], r['available_at_ms']), default=None)
                quality = information_state(payload, obj)
                track = dict(object_id=obj, quality=quality, records=records,
                             position=position_record['position'] if position_record else None,
                             observed_at_ms=position_record['observed_at_ms'] if position_record else None,
                             position_source=position_record['source_id'] if position_record else None,
                             last_known=not bool(fresh),
                             history=[r for r in payload['observations'] if r['object_id'] == obj
                                      and position_record and r['source_id'] == position_record['source_id']])
                tracks.append(track)
                if quality in ('contradictory', 'not_comparable'):
                    alerts.append(dict(id=f'{obj}:{quality}', kind=quality, object_id=obj,
                                       title='관측 정보 충돌' if quality == 'contradictory' else '관측 시각 불일치',
                                       evidence_ids=[r['id'] for r in records]))
                if track['last_known']:
                    alerts.append(dict(id=f'{obj}:stale', kind='stale', object_id=obj,
                                       title='최신 위치 관측 없음', evidence_ids=[r['id'] for r in records]))
            for channel in health:
                if channel['status'] != 'online':
                    row = channel['evidence']
                    alerts.append(dict(id=f"{channel['source_id']}:{channel['status']}", kind='channel',
                                       source_id=channel['source_id'], title='관측 채널 갱신 중단',
                                       evidence_ids=[row['id']] if row else []))
            for alert in alerts:
                alert['acknowledged'] = alert['id'] in self.acknowledged
            return dict(**clock, synthetic=True, tracks=tracks, sources=health, alerts=alerts,
                        contexts=payload['contexts'], coordinate_system='fictional_local_meters')

    def control(self, command):
        with self.lock:
            action = command.get('action')
            now_ms = self._time()
            if action == 'play':
                self.playing = True
                if now_ms >= self.public[self.case_id]['duration_ms']:
                    now_ms = 0
                    self.run_id = uuid.uuid4().hex
                    self.acknowledged.clear()
            elif action == 'pause':
                self.playing = False
            elif action in ('reset', 'case'):
                case_id = command.get('case_id', self.case_id)
                if case_id not in self.public:
                    raise ValueError('Unknown case')
                self.case_id, now_ms, self.playing = case_id, 0, False
                self.run_id = uuid.uuid4().hex
                self.acknowledged.clear()
            elif action == 'seek':
                value = command.get('at_ms')
                if type(value) is not int or not 0 <= value <= self.public[self.case_id]['duration_ms']:
                    raise ValueError('Invalid replay time')
                now_ms = value
                self.run_id = uuid.uuid4().hex
                self.acknowledged.clear()
            elif action == 'speed':
                speed = command.get('speed')
                if type(speed) not in (int, float) or speed not in (1, 2, 4):
                    raise ValueError('Invalid speed')
                self.speed = speed
            elif action == 'ack':
                if command.get('run_id') != self.run_id:
                    raise ValueError('Stale run')
                alert_id = command.get('alert_id')
                if alert_id not in {a['id'] for a in self.state()['alerts']}:
                    raise ValueError('Unknown current alert')
                self.acknowledged.add(alert_id)
            else:
                raise ValueError('Unknown action')
            self.anchor_ms, self.anchor_wall = now_ms, self.clock()
            self.revision += 1
            return self.state()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        if str(args[1] if len(args) > 1 else '') not in ('200', '304'):
            super().log_message(format, *args)

    def respond(self, status, value, mime='application/json; charset=utf-8'):
        body = json.dumps(value, ensure_ascii=False).encode() if isinstance(value, (dict, list)) else value
        self.send_response(status)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'strict-origin-when-cross-origin')
        self.end_headers()
        self.wfile.write(body)

    def valid_host(self):
        port = self.server.server_port
        return self.headers.get('Host') in (f'127.0.0.1:{port}', f'localhost:{port}')

    def do_GET(self):
        if not self.valid_host():
            self.respond(403, {'error': 'Local host only'})
            return
        path = urlsplit(self.path).path
        if path == '/api/state':
            self.respond(200, self.server.simulation.state())
        elif path == '/api/clock':
            self.respond(200, self.server.simulation.clock_state())
        elif path == '/api/config':
            self.respond(200, dict(site=read_json(PROJECT / 'data' / 'site_layout.json'),
                                   cases=[{'case_id': c['case_id'], 'variant': c['variant']} for c in self.server.simulation.cases],
                                   regional_map=read_json(PROJECT / 'monitor' / 'map_config.json')))
        elif path == '/health':
            self.respond(200, {'ok': True})
        else:
            assets = {'/': ('index.html', 'text/html; charset=utf-8'),
                      '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
                      '/geo.mjs': ('geo.mjs', 'text/javascript; charset=utf-8'),
                      '/i18n.mjs': ('i18n.mjs', 'text/javascript; charset=utf-8'),
                      '/styles.css': ('styles.css', 'text/css; charset=utf-8')}
            if path not in assets:
                self.respond(404, {'error': 'Not found'})
                return
            filename, mime = assets[path]
            self.respond(200, (PROJECT / 'monitor' / filename).read_bytes(), mime)

    def do_POST(self):
        port = self.server.server_port
        origin = self.headers.get('Origin')
        if (not self.valid_host() or (origin and origin not in (f'http://127.0.0.1:{port}', f'http://localhost:{port}'))
                or self.headers.get('Sec-Fetch-Site') == 'cross-site'):
            self.respond(403, {'error': 'Same-origin requests only'})
            return
        if urlsplit(self.path).path != '/api/control':
            self.respond(404, {'error': 'Not found'})
            return
        if self.headers.get_content_type() != 'application/json':
            self.respond(415, {'error': 'JSON required'})
            return
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 4096:
                raise ValueError('Invalid request size')
            body = json.loads(self.rfile.read(length))
            if not isinstance(body, dict):
                raise ValueError('Expected an object')
            self.respond(200, self.server.simulation.control(body))
        except (ValueError, TypeError) as error:
            self.respond(400, {'error': str(error)})


def make_server(port=8765, simulation=None):
    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    server.simulation = simulation or Simulation()
    return server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    server = make_server(args.port)
    print(f'LOW SKY monitor: http://127.0.0.1:{server.server_port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
