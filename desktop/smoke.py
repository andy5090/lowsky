"""Exercise a native desktop payload from outside the checkout, without paid APIs."""
import argparse
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import queue
import re
import socket
import subprocess
import sys
import tempfile
import threading
import time


class SmokeError(RuntimeError):
    pass


ASSETS = ('index.html', 'app.js', 'styles.css', 'logo.svg', 'logo-metal.png', 'geo.mjs',
          'decisions.mjs', 'test_runs.mjs', 'review.mjs', 'exercise.mjs', 'dashboard.mjs',
          'radar.mjs', 'i18n.mjs', 'notifications.mjs', 'sw.js', 'manifest.webmanifest', 'pwa-icon.svg')
DATA_FILES = ('site_layout.json', 'early_warning_demo.json', 'sensor_fleet_demo.json',
              'situation_review.json', 'radar_display.json', 'terrain/korea_site.json',
              'references/ukraine_observation_lessons.json', 'scenarios/v1/manifest.json',
              'scenarios/v1/scene.json', 'scenarios/v1/briefings.json')


def ensure(condition, message):
    if not condition:
        raise SmokeError(message)


def check_public_payload(payload):
    for path in payload.rglob('*'):
        parts = path.relative_to(payload).parts
        ensure(not any(part == '.local' or part.startswith('.env') for part in parts)
               and path.suffix.lower() not in ('.docx', '.jsonl'),
               'Payload contains a private configuration, source document, or journal')


def runtime_paths(payload, platform=None):
    platform = platform or sys.platform
    ensure(platform in ('darwin', 'win32'), 'Run native payload smoke tests on macOS or Windows')
    backend = payload / 'backend' / ('lowsky-server.exe' if platform == 'win32' else 'lowsky-server')
    godot = payload / 'godot' / ('LOW SKY 3D.exe' if platform == 'win32'
                               else 'LOW SKY 3D.app/Contents/MacOS/LOW SKY 3D')
    manifest = payload / 'godot-executable.txt'
    if manifest.is_file():
        relative = Path(manifest.read_text(encoding='utf-8').strip())
        ensure(not relative.is_absolute() and '..' not in relative.parts and relative.parts
               and relative.parts[0] == 'godot', 'Invalid Godot executable manifest path')
        godot = payload / relative
    internal = payload / 'backend' / '_internal'
    return backend, godot, internal / 'data', internal / 'monitor'


def check_data(data, monitor):
    ensure(data.is_dir() and monitor.is_dir(), 'Frozen runtime data/monitor directories are missing')
    for filename in DATA_FILES:
        path = data / filename
        ensure(path.is_file(), 'Required bundled JSON data is missing: ' + filename)
        try:
            json.loads(path.read_text(encoding='utf-8'))
        except (ValueError, OSError):
            raise SmokeError('Invalid bundled JSON data: ' + filename) from None
    manifest = json.loads((data / 'scenarios/v1/manifest.json').read_text(encoding='utf-8'))
    cases = [row['case_id'] for row in manifest['cases']]
    ensure(len(cases) >= 2, 'Scenario manifest must contain multiple cases')
    for case_id in cases:
        ensure(isinstance(case_id, str) and re.fullmatch(r'case_[0-9]+', case_id), 'Invalid packaged case ID')
        for filename in ('public.json', 'world.json'):
            path = data / 'scenarios/v1/cases' / case_id / filename
            ensure(path.is_file(), 'Bundled scenario file missing: ' + case_id + '/' + filename)
            try:
                json.loads(path.read_text(encoding='utf-8'))
            except (ValueError, OSError):
                raise SmokeError('Invalid packaged scenario JSON') from None
    for filename in ASSETS:
        ensure((monitor / filename).is_file(), 'Bundled monitor asset missing: ' + filename)
    return cases


def isolated_environment():
    blocked = {'OPENAI_API_KEY', 'OPENAI_BASE_URL', 'ANTHROPIC_API_KEY', 'LANGSMITH_API_KEY',
               'LANGCHAIN_API_KEY', 'LOW_SKY_AGENT_MODEL', 'LANGCHAIN_TRACING_V2', 'LANGSMITH_TRACING'}
    environment = {key: value for key, value in os.environ.items() if key not in blocked}
    environment['LOW_SKY_AGENT_MODEL'] = ''
    environment['LANGSMITH_TRACING'] = 'false'
    environment['LANGCHAIN_TRACING_V2'] = 'false'
    return environment


def request(port, path, command=None, expected_status=200):
    connection = http.client.HTTPConnection('127.0.0.1', port, timeout=15)
    try:
        body = json.dumps(command) if command is not None else None
        connection.request('POST' if command is not None else 'GET', path, body=body,
                           headers={'Content-Type': 'application/json'} if body else {})
        response = connection.getresponse()
        raw = response.read()
        ensure(response.status == expected_status, 'Unexpected HTTP status for ' + path)
        content_type = response.getheader('Content-Type', '').split(';')[0]
        if content_type == 'application/json' or content_type.endswith('+json'):
            return json.loads(raw)
        return raw
    finally:
        connection.close()


def read_ready(process, timeout=60):
    # Threads work with Windows pipe handles as well as Unix file descriptors.
    lines = queue.Queue(maxsize=1)
    def read_line():
        try:
            lines.put(process.stdout.readline())
        except (OSError, ValueError):
            lines.put('')
    threading.Thread(target=read_line, name='smoke-readiness', daemon=True).start()
    try:
        line = lines.get(timeout=timeout)
    except queue.Empty:
        raise SmokeError('Backend readiness timed out') from None
    try:
        ready = json.loads(line)
    except (ValueError, TypeError):
        raise SmokeError('Backend did not emit valid readiness JSON') from None
    ensure(isinstance(ready, dict) and set(ready) == {'event', 'port'} and ready['event'] == 'ready'
           and type(ready['port']) is int and 0 < ready['port'] <= 65535,
           'Invalid backend readiness fields')
    return ready['port']


def cleanup(process):
    if process.stdin and not process.stdin.closed:
        process.stdin.close()
    if process.poll() is None:
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
    if process.stdout:
        process.stdout.close()


class LocalResponses:
    """A two-response fixture; no provider credentials or external socket target."""
    def __init__(self, enabled):
        self.enabled = enabled
        self.requests = 0
        self.failure = None
        self.server = self.thread = None
        self.url = None

    def __enter__(self):
        if not self.enabled:
            return self
        owner = self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                status = 200
                try:
                    ensure(self.path == '/v1/responses', 'Unexpected local provider path')
                    ensure(self.headers.get('Authorization') == 'Bearer low-sky-local-smoke', 'Unexpected fixture credential')
                    length = int(self.headers.get('Content-Length', '0'))
                    ensure(0 < length <= 2_000_000, 'Invalid local provider request size')
                    body = json.loads(self.rfile.read(length))
                    ensure(body.get('model') == 'gpt-6.1-sol', 'Unexpected fixture model')
                    required = {'observation_summary', 'source_and_fleet_health', 'early_signals', 'pending_reviews'}
                    names = {tool['name'] for tool in body['tools']}
                    ensure(required <= names and 'SituationReport' in names, 'Evidence tool bindings missing')
                    owner.requests += 1
                    if owner.requests == 1:
                        calls = [dict(id=f'fc_{index}', call_id=f'evidence_{index}', type='function_call',
                                      name=name, arguments='{}', status='completed')
                                 for index, name in enumerate(sorted(required))]
                    else:
                        ensure(owner.requests == 2 and sum(item.get('type') == 'function_call_output'
                               for item in body['input']) == 4, 'Evidence tool results missing')
                        schema = next(tool['parameters'] for tool in body['tools'] if tool['name'] == 'SituationReport')
                        evidence = schema['properties']['known']['items']['properties']['evidence_ids']['items']['enum'][0]
                        report = dict(summary='Local frozen SDK smoke fixture.',
                                      known=[dict(text='Local synthetic fixture evidence.', evidence_ids=[evidence])],
                                      uncertain=[], review_items=[])
                        calls = [dict(id='fc_report', call_id='report', type='function_call', status='completed',
                                      name='SituationReport', arguments=json.dumps(report))]
                    response = dict(id=f'resp_fixture_{owner.requests}', object='response', created_at=0,
                                    model='gpt-6.1-sol', status='completed', output=calls, error=None, incomplete_details=None)
                except Exception:
                    owner.failure = 'Local provider fixture validation failed'
                    status, response = 400, {'error': {'message': owner.failure}}
                raw = json.dumps(response).encode()
                self.send_response(status)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.url = f'http://127.0.0.1:{self.server.server_port}/v1'
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={'poll_interval': .1}, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *_):
        if self.server is not None:
            self.server.shutdown()
            self.server.server_close()
            self.thread.join(timeout=3)


def run_checks(backend_command, data, monitor, godot=None, check_sdk=False):
    """Shared runner accepts an executable command list to support source regressions."""
    cases = check_data(data, monitor)
    environment = isolated_environment()
    creationflags = getattr(subprocess, 'CREATE_NO_WINDOW', 0) if os.name == 'nt' else 0
    with tempfile.TemporaryDirectory(prefix='lowsky-desktop-smoke-') as directory, LocalResponses(check_sdk) as provider:
        if check_sdk:
            environment.update(OPENAI_API_KEY='low-sky-local-smoke', OPENAI_BASE_URL=provider.url,
                               LOW_SKY_AGENT_MODEL='openai:gpt-6.1-sol')
        app_data = Path(directory)
        (app_data / '.env').write_text('LOW_SKY_AGENT_MODEL=\n', encoding='utf-8')
        with (app_data / 'backend.log').open('w', encoding='utf-8') as log:
            process = subprocess.Popen([*map(str, backend_command), '--data-dir', str(app_data), '--port', '0'],
                                       cwd=app_data, env=environment, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                       stderr=log, text=True, encoding='utf-8', errors='replace', creationflags=creationflags)
            try:
                port = read_ready(process)
                ensure(request(port, '/health') == {'ok': True}, 'Backend health check failed')
                config = request(port, '/api/config')
                ensure([row['case_id'] for row in config['cases']] == cases, 'HTTP cases differ from bundled data')
                briefing = request(port, '/api/briefings')
                ensure(len(briefing['cases']) == len(cases), 'Bundled scenario briefings are incomplete')
                assessment = request(port, '/api/assessment')
                if check_sdk:
                    ensure(assessment['configured'] and assessment['mode'] == 'llm' and not assessment['running'],
                           'Frozen SDK/provider dependencies are unavailable')
                else:
                    ensure(assessment['mode'] == 'rules' and assessment['model'] is None and not assessment['running'],
                           'Smoke run must not use a configured LLM')
                initial = request(port, '/api/state')
                ensure(not initial['playing'] and 'simulation_positions' not in initial,
                       'Initial state must be paused and observation-only')
                changed = request(port, '/api/control', {'action': 'case', 'case_id': cases[1]})
                ensure(changed['case_id'] == cases[1] and changed['run_id'] != initial['run_id']
                       and changed['at_ms'] == 0 and not changed['playing'], 'Case control did not reset shared replay')
                at_ms = min(12345, changed['duration_ms'])
                sought = request(port, '/api/control', {'action': 'seek', 'at_ms': at_ms})
                clock = request(port, '/api/clock')
                state = request(port, '/api/state')
                for key in ('run_id', 'case_id', 'at_ms', 'playing'):
                    ensure(sought[key] == clock[key] == state[key], 'HTTP views do not share the replay clock')
                ensure(state['at_ms'] == at_ms and not state['playing'], 'Seek did not preserve paused replay')
                for track in state['tracks']:
                    for row in track['records']:
                        ensure(row['observed_at_ms'] <= row['available_at_ms'] <= at_ms,
                               'Observation response includes unavailable evidence')
                for filename in ASSETS:
                    path = '/' if filename == 'index.html' else '/' + filename
                    expected = (monitor / filename).read_bytes()
                    actual = request(port, path)
                    if filename == 'manifest.webmanifest':
                        ensure(actual == json.loads(expected), 'PWA manifest differs from bundled asset')
                    else:
                        ensure(actual == expected, 'HTTP asset differs from frozen runtime: ' + filename)
                if check_sdk:
                    request(port, '/api/assessment', {'run_id': state['run_id'], 'language': 'en'}, expected_status=202)
                    deadline = time.monotonic() + 180
                    while True:
                        assessment = request(port, '/api/assessment')
                        if not assessment['running']:
                            break
                        ensure(time.monotonic() < deadline, 'Frozen SDK loopback assessment timed out')
                        time.sleep(.1)
                    ensure(not assessment.get('error') and (assessment.get('latest') or {}).get('mode') == 'llm',
                           'Frozen Deep Agents loopback assessment failed')
                    ensure(assessment['latest']['summary'] == 'Local frozen SDK smoke fixture.' and provider.requests == 2
                           and provider.failure is None, 'Frozen SDK did not complete evidence tools and structured output')
                if godot is not None:
                    ensure(godot.is_file(), 'Native Godot export is missing')
                    result = subprocess.run([str(godot), '--headless', '--quit-after', '2', '--', '--monitor',
                                             f'--monitor-port={port}', f'--data-root={data.resolve()}'],
                                            cwd=app_data, env=environment, text=True, encoding='utf-8', errors='replace',
                                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120,
                                            creationflags=creationflags)
                    ensure(result.returncode == 0, 'Exported Godot exited unsuccessfully')
                    ensure(not re.search(r'(^|\n)\s*(?:SCRIPT )?ERROR:', result.stdout),
                           'Exported Godot reported script or resource errors')
                process.stdin.close()
                try:
                    code = process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    raise SmokeError('Backend did not stop after parent stdin closed') from None
                ensure(code == 0, 'Backend exited unsuccessfully after stdin EOF')
                ensure(process.stdout.read() == '', 'Backend emitted extra stdout protocol data')
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
                    probe.settimeout(3)
                    ensure(probe.connect_ex(('127.0.0.1', port)) != 0, 'Backend port remained open after shutdown')
            finally:
                cleanup(process)
    return dict(ok=True, cases=len(cases), assets=len(ASSETS), shared_clock=True,
                godot='passed' if godot is not None else 'skipped', shutdown='stdin_eof', port_closed=True,
                external_api_calls=False, sdk='passed' if check_sdk else 'skipped')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--payload', type=Path, required=True, help='Native desktop/src-tauri/payload directory')
    parser.add_argument('--check-sdk', action='store_true',
                        help='Run frozen Deep Agents against a dummy loopback OpenAI endpoint (no external calls)')
    parser.add_argument('--skip-godot', action='store_true', help='Check only the frozen backend and its public assets')
    args = parser.parse_args(argv)
    try:
        payload = args.payload.resolve()
        ensure(payload.is_dir(), 'Payload directory is missing')
        check_public_payload(payload)
        backend, godot, data, monitor = runtime_paths(payload)
        ensure(backend.is_file(), 'Frozen backend executable is missing')
        result = run_checks([backend], data, monitor, None if args.skip_godot else godot, check_sdk=args.check_sdk)
        print(json.dumps(result, separators=(',', ':')), flush=True)
        return 0
    except (SmokeError, OSError, ValueError, TypeError, KeyError, subprocess.SubprocessError) as error:
        # All our failure messages describe public paths/protocol checks, never API settings.
        message = str(error) if isinstance(error, SmokeError) else 'Native smoke process or data validation failed'
        print('LOW SKY desktop smoke failed: ' + message, file=sys.stderr, flush=True)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
