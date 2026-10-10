"""Local shared replay clock and observation-only monitoring API (stdlib only)."""
import argparse
import copy
import json
import secrets
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

try:
    from .scenario_dataset import ROOT, read_json, snapshot, information_state
    from .evidence_review import AuditLog, digest, evidence_snapshot, explain, make_track_review
    from .sensor_fleet import snapshot as fleet_snapshot
    from .situation_agent import configuration_status, evaluate as evaluate_situation
    from .env_config import load_agent_env
    from .decision_engine import DecisionEngine, DecisionBusy
    from .early_warning import snapshot as early_snapshot
    from .situation_review import snapshot as situation_snapshot, make_review
    from .simulation_test import generate as generate_test, fixture_metadata, validate_seed, MAX_SEED
    from .test_operator import TestOperator
    from . import exercise
    from .decision_dashboard import DecisionDashboard
    from .desktop_controls import DesktopControls, DesktopBusy
    from .rehearsal_review import summarize as summarize_rehearsals, export_run as export_rehearsal
except ImportError:
    from scenario_dataset import ROOT, read_json, snapshot, information_state
    from evidence_review import AuditLog, digest, evidence_snapshot, explain, make_track_review
    from sensor_fleet import snapshot as fleet_snapshot
    from situation_agent import configuration_status, evaluate as evaluate_situation
    from env_config import load_agent_env
    from decision_engine import DecisionEngine, DecisionBusy
    from early_warning import snapshot as early_snapshot
    from situation_review import snapshot as situation_snapshot, make_review
    from simulation_test import generate as generate_test, fixture_metadata, validate_seed, MAX_SEED
    from test_operator import TestOperator
    import exercise
    from decision_dashboard import DecisionDashboard
    from desktop_controls import DesktopControls, DesktopBusy
    from rehearsal_review import summarize as summarize_rehearsals, export_run as export_rehearsal

PROJECT = Path(__file__).resolve().parents[1]


class AssessmentBusy(ValueError):
    pass


class Simulation:
    def __init__(self, root=ROOT, clock=time.monotonic, early_feed=None, audit_path=None,
                 assessment_evaluator=None, assessment_configuration=None,
                 decision_evaluator=None, decision_audit_path=None, operator_runner=None, operator_configuration=None,
                 dashboard_audit_path=None):
        self.root, self.clock = root, clock
        self.early_feed = early_feed if early_feed is not None else read_json(PROJECT / 'data' / 'early_warning_demo.json')
        self.fleet_feed = read_json(PROJECT / 'data' / 'sensor_fleet_demo.json')
        self.test_public = self.test_early = self.test_fleet = None
        self.test_run = fixture_metadata()
        self.audit = AuditLog(audit_path)
        self.dashboard = DecisionDashboard(dashboard_audit_path)
        self.reviews = []
        self.context_reviews = []
        self.situation_feed = read_json(PROJECT / "data/situation_review.json")
        self.lock = threading.RLock()
        self.cases = read_json(root / 'manifest.json')['cases']
        self.public = {entry['case_id']: read_json(root / 'cases' / entry['case_id'] / 'public.json') for entry in self.cases}
        self.exercise_selection = None
        self.site_layout = read_json(PROJECT / 'data/site_layout.json')
        self.world_frames = {}
        self.case_id = self.cases[0]['case_id']
        self.anchor_ms, self.anchor_wall = 0, clock()
        self.playing, self.speed = False, 1
        self.run_id = uuid.uuid4().hex
        self.revision = 0
        self.acknowledged = set()
        self.assessment_evaluator = assessment_evaluator or evaluate_situation
        self.assessment_configuration = assessment_configuration or configuration_status
        self.assessment_job = None
        self.assessment_latest = None
        self.assessment_error = None
        self.assessment_thread = None
        self.decisions = DecisionEngine(self, decision_evaluator, decision_audit_path)
        self.test_operator = TestOperator(self, operator_runner, operator_configuration)

    def _time(self):
        elapsed = (self.clock() - self.anchor_wall) * 1000 * self.speed if self.playing else 0
        return min(self.public[self.case_id]['duration_ms'], int(self.anchor_ms + elapsed))

    def _clock_state(self):
        at_ms = self._time()
        duration = self.public[self.case_id]['duration_ms']
        return dict(case_id=self.case_id, run_id=self.run_id, revision=self.revision,
                    at_ms=at_ms, duration_ms=duration, playing=self.playing and at_ms < duration, speed=self.speed,
                    test_run=copy.deepcopy(self.test_run),
                    training_timing=copy.deepcopy(self._public_input().get('training_timing', {})))

    def _public_input(self):
        return self.test_public if self.test_public is not None else self.public[self.case_id]

    def _early_input(self, case_id=None):
        # Case-specific authored receipt schedules share the same zone definitions.
        # Select before seeded jitter; never mix another case's evidence into a run.
        case_id = case_id or self.case_id
        feed = {key: value for key, value in self.early_feed.items() if key != 'case_overrides'}
        return {**feed, **self.early_feed.get('case_overrides', {}).get(case_id, {})}

    def _exercise_frames(self):
        if self.case_id not in self.world_frames:
            self.world_frames[self.case_id] = {obj['object_id']:obj['keyframes'] for obj in read_json(self.root / 'cases' / self.case_id / 'world.json')['objects']}
        return self.world_frames[self.case_id]

    def clock_state(self):
        with self.lock:
            return self._clock_state()

    def state(self, show_positions=False):
        with self.lock:
            clock = self._clock_state()
            payload = exercise.apply_observations(snapshot(self._public_input(), clock['at_ms']), self.exercise_selection, self._exercise_frames() if self.exercise_selection else {})
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
            observations_by_object = {}
            for row in payload['observations']:
                observations_by_object.setdefault(row['object_id'], []).append(row)
            tracks, alerts = [], []
            for obj in payload['object_ids']:
                object_rows = observations_by_object.get(obj, [])
                records = []
                for source in payload['source_ids']:
                    rows = [r for r in object_rows if r['source_id'] == source]
                    row = max(rows, key=lambda r: (r['observed_at_ms'], r['available_at_ms']), default=None)
                    if row:
                        records.append(row)
                if not records:
                    continue  # No received evidence: do not reveal author-known objects.
                fresh = [r for r in records if latest_health[r['source_id']] == 'online'
                         and payload['at_ms'] - r['observed_at_ms'] <= payload['freshness_ms']]
                position_record = max(fresh or records, key=lambda r: (r['observed_at_ms'], r['available_at_ms']), default=None)
                quality = information_state({**payload, 'observations': object_rows}, obj)
                track = dict(object_id=obj, quality=quality, records=records,
                             first_received_at_ms=min(r['available_at_ms'] for r in object_rows),
                             position=position_record['position'] if position_record else None,
                             observed_at_ms=position_record['observed_at_ms'] if position_record else None,
                             position_source=position_record['source_id'] if position_record else None,
                             last_known=not bool(fresh),
                             history=[r for r in object_rows if position_record
                                      and r['source_id'] == position_record['source_id']])
                basis = evidence_snapshot(obj, object_rows, health, quality, track['last_known'])
                track['evidence_version'] = digest(basis)
                track['explanation'] = explain(records, health, payload['at_ms'], payload['freshness_ms'],
                                               quality, track['last_known'], track['evidence_version'])
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
            early_warning, early_alerts = early_snapshot(self.test_early if self.test_early is not None else self._early_input(), clock['at_ms'])
            alerts = early_alerts + alerts
            for alert in alerts:
                alert['acknowledged'] = alert['id'] in self.acknowledged
            situation = situation_snapshot(self.situation_feed, self.case_id, clock['at_ms'], payload['object_ids'],
                                           [r for r in self.context_reviews if r['run_id'] == self.run_id])
            track_reviews = self.audit.current(self.run_id)
            result = dict(**clock, situation=situation, synthetic=True, tracks=tracks, sources=health, alerts=alerts,
                        contexts=payload['contexts'], early_warning=early_warning,
                        sensor_fleet=fleet_snapshot(self.case_id, clock['at_ms'], self.test_fleet if self.test_fleet is not None else self.fleet_feed),
                        track_reviews=track_reviews,
                        review_summary=dict(total_saved=len(self.audit.records), current_run=len(track_reviews),
                            by_decision={decision: sum(r['decision'] == decision for r in track_reviews)
                                         for decision in ('noted', 'needs_review', 'dismissed')}),
                        reviews=[r for r in self.reviews if r['run_id'] == self.run_id],
                        coordinate_system='fictional_local_meters')
            result['exercise'] = exercise.view(self.site_layout, tracks, self.exercise_selection, clock['at_ms'],
                                               clock['duration_ms'], bool(clock.get('training_timing', {}).get('paced')))
            result['dashboard'] = self.dashboard.view(result)
            if show_positions:
                # Explicit author view: only positions at this response's replay time.
                # Never merge truth into observed tracks, alerts, or evidence.
                world = read_json(self.root / 'cases' / self.case_id / 'world.json')
                positions = []
                for obj in world['objects']:
                    positions.append(dict(object_id=obj['object_id'],position=exercise.sample(obj['keyframes'],
                        exercise.motion_time(self.exercise_selection,obj['object_id'],clock['at_ms']))))
                result['simulation_positions'] = positions
                result['simulation_missions'] = exercise.missions(None, self.exercise_selection, clock['at_ms'],
                    clock['duration_ms'], bool(clock.get('training_timing', {}).get('paced')))
            return result

    def assessment_state(self):
        with self.lock:
            current = self._clock_state()
            latest = self.assessment_latest
            if latest and latest['run_id'] != current['run_id']:
                latest = None
            error = self.assessment_error
            if error and error['run_id'] != current['run_id']:
                error = None
            return copy.deepcopy(dict(**self.assessment_configuration(),
                running=self.assessment_job is not None, job=self.assessment_job,
                latest=latest, error=error['message'] if error else None,
                stale=bool(latest and latest['at_ms'] != current['at_ms'])))

    def start_assessment(self, command):
        with self.lock:
            if command.get('run_id') != self.run_id:
                raise ValueError('Stale run')
            language = command.get('language')
            if language not in ('en', 'ko'):
                raise ValueError('Invalid assessment language')
            if self.assessment_configuration().get('configuration_error'):
                raise ValueError('Assessment configuration is incomplete; check the configuration status')
            if self.assessment_job is not None:
                raise AssessmentBusy('An assessment is already running')
            # Freeze the observation-only state once; provider work runs outside this lock.
            frozen = copy.deepcopy(self.state())
            frozen.pop('simulation_positions', None)
            job = dict(run_id=frozen['run_id'], case_id=frozen['case_id'],
                       at_ms=frozen['at_ms'], language=language)
            self.assessment_job = job
            self.assessment_error = None
            worker = threading.Thread(target=self._evaluate_assessment, args=(frozen, job), daemon=True)
            self.assessment_thread = worker
            try:
                worker.start()
            except RuntimeError:
                self.assessment_job = None
                raise
            return self.assessment_state()

    def _evaluate_assessment(self, frozen, job):
        result, error = None, None
        try:
            result = self.assessment_evaluator(frozen, job['language'])
            if not isinstance(result, dict):
                raise ValueError('Invalid assessment response')
            # Clock/run provenance belongs to the frozen input, never model-generated text.
            result = {**result, **job}
        except Exception:
            # Provider exceptions may include credentials or raw remote responses.
            error = 'Assessment failed; provider configuration, connection, or response could not be validated.'
        with self.lock:
            if self.run_id == job['run_id']:
                if error:
                    self.assessment_error = dict(run_id=job['run_id'], message=error)
                else:
                    self.assessment_latest = copy.deepcopy(result)
                    self.assessment_error = None
            self.assessment_job = None

    def control(self, command):
        with self.lock:
            action = command.get('action')
            now_ms = self._time()
            previous_run = self.run_id
            if action == 'start_test':
                case_id = command.get('case_id', self.case_id)
                if not isinstance(case_id, str) or case_id not in self.public:
                    raise ValueError('Unknown case')
                if 'seed' in command:
                    seed = validate_seed(command['seed'])
                else:
                    previous_seed = self.test_run['seed']
                    seed = secrets.randbelow(MAX_SEED if previous_seed is not None else MAX_SEED + 1)
                    if previous_seed is not None and seed >= previous_seed:
                        seed += 1  # A fresh random test never repeats the active seed.
                inputs = generate_test(case_id, seed, self.public[case_id], self._early_input(case_id), self.fleet_feed)
                self.test_public, self.test_early, self.test_fleet, self.test_run = inputs
                self.case_id, now_ms, self.playing = case_id, 0, True
                self.run_id = uuid.uuid4().hex
                self.acknowledged.clear()
            elif action == 'play':
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
                if action == 'case' or case_id != self.case_id:
                    self.test_public = self.test_early = self.test_fleet = None
                    self.test_run = fixture_metadata()
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
                if type(speed) not in (int, float) or speed not in (0.5, 1, 2, 4):
                    raise ValueError('Invalid speed')
                self.speed = speed
            elif action == 'exercise_branch':
                self.exercise_selection = exercise.select(command, self.state())
            elif action == 'dashboard_action':
                self.dashboard.confirm(command, self.state())
            elif action == 'review_track':
                state = self.state()
                track = next((item for item in state['tracks'] if item['object_id'] == command.get('object_id')), None)
                payload = exercise.apply_observations(snapshot(self._public_input(), state['at_ms']), self.exercise_selection, self._exercise_frames() if self.exercise_selection else {})
                rows = [row for row in payload['observations'] if row['object_id'] == command.get('object_id')]
                basis = evidence_snapshot(command.get('object_id'), rows, state['sources'],
                                          track['quality'] if track else None,
                                          track['last_known'] if track else True)
                record = make_track_review(command, state, basis, uuid.uuid4().hex, int(time.time() * 1000))
                self.audit.append(record)
            elif action == 'review_event':
                situation = self.state()['situation']
                record = make_review(command, situation, self.run_id, self.case_id, now_ms, uuid.uuid4().hex)
                self.context_reviews.append(record)
                self.context_reviews = self.context_reviews[-1000:]
            elif action == 'ack':
                if command.get('run_id') != self.run_id:
                    raise ValueError('Stale run')
                alert_id = command.get('alert_id')
                if alert_id not in {a['id'] for a in self.state()['alerts']}:
                    raise ValueError('Unknown current alert')
                if alert_id not in self.acknowledged:
                    self.reviews.append(dict(run_id=self.run_id, case_id=self.case_id, alert_id=alert_id,
                                             at_ms=now_ms, reviewed_at_unix_ms=int(time.time() * 1000), action='acknowledged'))
                    self.reviews = self.reviews[-1000:]
                self.acknowledged.add(alert_id)
            else:
                raise ValueError('Unknown action')
            if self.run_id != previous_run:
                self.exercise_selection = None
            self.anchor_ms, self.anchor_wall = now_ms, self.clock()
            self.revision += 1
            if not self.test_operator.applying and action in ('start_test', 'case', 'reset', 'seek', 'pause', 'play'):
                self.test_operator.cancel('manual_override')
            self.decisions.observe_control()
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
        if path == '/api/desktop':
            self.respond(200, self.server.desktop.snapshot())
        elif path == '/api/state':
            self.respond(200, self.server.simulation.state(
                show_positions=parse_qs(urlsplit(self.path).query).get('show_positions') == ['1']))
        elif path == '/api/assessment':
            self.respond(200, self.server.simulation.assessment_state())
        elif path == '/api/decisions':
            self.respond(200, self.server.simulation.decisions.snapshot())
        elif path == '/api/test-operator':
            self.respond(200, self.server.simulation.test_operator.snapshot())
        elif path == '/api/rehearsals':
            with self.server.simulation.lock:
                sim = self.server.simulation
                run_id = parse_qs(urlsplit(self.path).query).get('run_id', [None])[0]
                try:
                    result = (export_rehearsal(sim.decisions.audit.records, run_id, sim.clock_state()) if run_id
                              else summarize_rehearsals(sim.decisions.audit.records, sim.clock_state()))
                    self.respond(200, result)
                except ValueError:
                    self.respond(404, {'error': 'Unknown recorded run'})
        elif path == '/api/decisions/audit':
            with self.server.simulation.lock:
                self.respond(200, self.server.simulation.decisions.audit.export())
        elif path == '/api/dashboard/audit':
            with self.server.simulation.lock:
                self.respond(200, self.server.simulation.dashboard.export())
        elif path == '/api/audit':
            with self.server.simulation.lock:
                self.respond(200, self.server.simulation.audit.export())
        elif path == '/api/briefings':
            # Deliberate operator preview; kept out of observation-only state and clock.
            self.respond(200, read_json(self.server.simulation.root / 'briefings.json'))
        elif path == '/api/clock':
            self.respond(200, self.server.simulation.clock_state())
        elif path == '/api/config':
            self.respond(200, dict(site=read_json(PROJECT / 'data' / 'site_layout.json'),
                                   cases=[{'case_id': c['case_id'], 'variant': c['variant']} for c in self.server.simulation.cases],
                                   regional_map=read_json(PROJECT / 'monitor' / 'map_config.json'),
                                   radar_display=read_json(PROJECT / 'data' / 'radar_display.json'),
                                   research_sources=read_json(PROJECT / 'data/references/ukraine_observation_lessons.json')['sources']))
        elif path == '/health':
            self.respond(200, {'ok': True})
        else:
            assets = {'/': ('index.html', 'text/html; charset=utf-8'),
                      '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
                      '/logo.svg': ('logo.svg', 'image/svg+xml'),
                      '/logo-metal.png': ('logo-metal.png', 'image/png'),
                      '/geo.mjs': ('geo.mjs', 'text/javascript; charset=utf-8'),
                      '/decisions.mjs': ('decisions.mjs', 'text/javascript; charset=utf-8'),
                      '/test_runs.mjs': ('test_runs.mjs', 'text/javascript; charset=utf-8'),
                      '/review.mjs': ('review.mjs', 'text/javascript; charset=utf-8'),
                      '/exercise.mjs': ('exercise.mjs', 'text/javascript; charset=utf-8'),
                      '/dashboard.mjs': ('dashboard.mjs', 'text/javascript; charset=utf-8'),
                      '/desktop.mjs': ('desktop.mjs', 'text/javascript; charset=utf-8'),
                      '/custom_selects.mjs': ('custom_selects.mjs', 'text/javascript; charset=utf-8'),
                      '/radar.mjs': ('radar.mjs', 'text/javascript; charset=utf-8'),
                      '/i18n.mjs': ('i18n.mjs', 'text/javascript; charset=utf-8'),
                      '/notifications.mjs': ('notifications.mjs', 'text/javascript; charset=utf-8'),
                      '/sw.js': ('sw.js', 'text/javascript; charset=utf-8'),
                      '/manifest.webmanifest': ('manifest.webmanifest', 'application/manifest+json'),
                      '/pwa-icon.svg': ('pwa-icon.svg', 'image/svg+xml'),
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
        path = urlsplit(self.path).path
        if path not in ('/api/control', '/api/assessment', '/api/decisions', '/api/test-operator', '/api/desktop', '/api/desktop/runtime'):
            self.respond(404, {'error': 'Not found'})
            return
        if path == '/api/desktop/runtime' and not self.server.desktop.authenticated(
                self.headers.get('X-Low-Sky-Desktop-Token')):
            self.respond(403, {'error': 'Native authentication required'})
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
            if path == '/api/desktop':
                self.respond(202, self.server.desktop.command(body))
            elif path == '/api/desktop/runtime':
                self.respond(200, self.server.desktop.acknowledge(body))
            elif path == '/api/test-operator':
                self.respond(200, self.server.simulation.test_operator.command(body))
            elif path == '/api/decisions':
                self.respond(202 if body.get('action') in ('assess_current', 'retry') else 200,
                             self.server.simulation.decisions.command(body))
            elif path == '/api/assessment':
                self.respond(202, self.server.simulation.start_assessment(body))
            else:
                self.respond(200, self.server.simulation.control(body))
        except (AssessmentBusy, DecisionBusy, DesktopBusy) as error:
            self.respond(409, {'error': str(error)})
        except (ValueError, TypeError) as error:
            self.respond(400, {'error': str(error)})
        except OSError:
            self.respond(503, {'error': 'Review could not be saved; local audit storage is unavailable'})


class MonitorServer(ThreadingHTTPServer):
    def serve_forever(self, poll_interval=.5):
        self.simulation.decisions.start()
        try:
            super().serve_forever(poll_interval)
        finally:
            self.simulation.decisions.stop()

    def server_close(self):
        self.simulation.decisions.stop()
        super().server_close()


def make_server(port=8765, simulation=None, desktop=None):
    server = MonitorServer(('127.0.0.1', port), Handler)
    server.simulation = simulation or Simulation()
    server.desktop = desktop or DesktopControls()
    return server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--audit-path', type=Path, default=PROJECT / '.local' / 'track-reviews.jsonl')
    parser.add_argument('--decision-audit-path', type=Path, default=PROJECT / '.local' / 'event-decisions.jsonl')
    parser.add_argument('--dashboard-audit-path', type=Path, default=PROJECT / '.local' / 'dashboard-decisions.jsonl')
    args = parser.parse_args()
    load_agent_env(PROJECT / '.env')
    server = make_server(args.port, Simulation(audit_path=args.audit_path, decision_audit_path=args.decision_audit_path,
                                             dashboard_audit_path=args.dashboard_audit_path))
    print(f'LOW SKY monitor: http://127.0.0.1:{server.server_port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
