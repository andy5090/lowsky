import hashlib
import http.client
import json
import os
from pathlib import Path
import queue
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from tools import desktop_runtime
from tools.env_config import AGENT_SETTINGS
from tools.monitor_server import make_server

PROJECT = Path(__file__).resolve().parents[1]


class DesktopRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.data_dir = self.directory / 'user data'
        self.data_dir.mkdir()
        (self.data_dir / '.env').write_text('LOW_SKY_AGENT_MODEL=\n', encoding='utf-8')

    def start(self, package_root=PROJECT, data_dir=None, direct=False):
        environment = {key: value for key, value in os.environ.items() if key not in AGENT_SETTINGS}
        environment['PYTHONPATH'] = str(package_root)
        environment['PYTHONDONTWRITEBYTECODE'] = '1'
        entry = [str(package_root / 'tools' / 'desktop_runtime.py')] if direct else ['-m', 'tools.desktop_runtime']
        process = subprocess.Popen(
            [sys.executable, *entry, '--data-dir', str(data_dir or self.data_dir), '--port', '0'],
            cwd=self.directory, env=environment, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True,
        )
        self.addCleanup(self.cleanup_process, process)
        lines = queue.Queue(maxsize=1)
        def read_line():
            try:
                lines.put(process.stdout.readline())
            except (OSError, ValueError):
                lines.put('')
        threading.Thread(target=read_line, daemon=True).start()
        try:
            line = lines.get(timeout=30)
        except queue.Empty:
            self.fail('Desktop backend readiness timed out')
        self.assertTrue(line, 'Desktop backend exited before readiness')
        ready = json.loads(line)
        self.assertEqual(set(ready), {'event', 'port', 'desktop_token'})
        self.assertGreaterEqual(len(ready['desktop_token']), 32)
        self.desktop_token = ready['desktop_token']
        self.assertEqual(ready['event'], 'ready')
        self.assertIs(type(ready['port']), int)
        self.assertGreater(ready['port'], 0)
        return process, ready['port']

    @staticmethod
    def cleanup_process(process):
        if process.poll() is None:
            if process.stdin and not process.stdin.closed:
                process.stdin.close()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)
        for stream in (process.stdin, process.stdout, process.stderr):
            if stream and not stream.closed:
                stream.close()

    def request(self, port, method, path, command=None, extra_headers=None):
        connection = http.client.HTTPConnection('127.0.0.1', port, timeout=5)
        try:
            body = json.dumps(command) if command is not None else None
            headers = {'Content-Type': 'application/json'} if body else {}
            headers.update(extra_headers or {})
            connection.request(method, path, body=body, headers=headers)
            response = connection.getresponse()
            raw = response.read()
            value = json.loads(raw) if response.getheader('Content-Type', '').startswith('application/json') else raw
            return response.status, value
        finally:
            connection.close()

    def stop_and_check(self, process, port, terminate=False):
        if terminate:
            process.send_signal(signal.SIGTERM)
        else:
            process.stdin.close()
        # Windows SIGTERM maps to TerminateProcess(exit_code=1), not a POSIX handler.
        expected_code = 1 if terminate and os.name == 'nt' else 0
        self.assertEqual(process.wait(timeout=5), expected_code)
        self.assertEqual(process.stdout.read(), '')
        stderr = process.stderr.read()
        self.assertNotIn('Traceback', stderr)
        self.assertNotIn('test-only-not-a-real-key', stderr)
        with self.assertRaises(OSError):
            self.request(port, 'GET', '/health')

    def test_ephemeral_loopback_readiness_and_stdin_eof_shutdown(self):
        process, port = self.start()
        self.assertEqual(self.request(port, 'GET', '/health'), (200, {'ok': True}))
        status, configuration = self.request(port, 'GET', '/api/assessment')
        self.assertEqual(status, 200)
        self.assertEqual(configuration['mode'], 'rules')
        self.assertIsNone(configuration['model'])
        status, state = self.request(port, 'GET', '/api/state')
        self.assertEqual(status, 200)
        self.assertFalse(state['playing'])
        self.stop_and_check(process, port)

    def test_direct_entry_and_sigterm_shutdown(self):
        process, port = self.start(direct=True)
        self.assertEqual(self.request(port, 'GET', '/health')[0], 200)
        self.stop_and_check(process, port, terminate=True)

    def test_native_command_pipe_and_authenticated_ack(self):
        process, port = self.start()
        status, state = self.request(port, 'GET', '/api/desktop')
        self.assertEqual(status, 200)
        self.assertEqual((state['available'], state['view'], state['three_d_open']), (True, '3d', True))
        self.assertNotIn(self.desktop_token, json.dumps(state))
        status, pending = self.request(port, 'POST', '/api/desktop', {'action': 'show_monitor'})
        self.assertEqual(status, 202)
        self.assertTrue(pending['pending'])
        self.assertEqual(pending['view'], '3d')
        command = json.loads(process.stdout.readline())
        self.assertEqual(command['event'], 'desktop_command')
        self.assertEqual(command['state']['view'], 'monitor')
        self.assertNotIn(self.desktop_token, json.dumps(command))
        self.assertEqual(self.request(port, 'POST', '/api/desktop', {'action': 'close_3d'})[0], 409)
        ack = {'id': command['id'], 'ok': True}
        self.assertEqual(self.request(port, 'POST', '/api/desktop/runtime', ack)[0], 403)
        self.assertEqual(self.request(port, 'POST', '/api/desktop/runtime', ack,
                                     {'X-Low-Sky-Desktop-Token': 'wrong'})[0], 403)
        headers = {'X-Low-Sky-Desktop-Token': self.desktop_token}
        self.assertEqual(self.request(port, 'POST', '/api/desktop/runtime', ack,
                                     {**headers, 'Origin': 'https://untrusted.test'})[0], 403)
        status, done = self.request(port, 'POST', '/api/desktop/runtime', ack, headers)
        self.assertEqual(status, 200)
        self.assertEqual((done['view'], done['pending'], done['revision']), ('monitor', False, 1))
        self.assertEqual(self.request(port, 'POST', '/api/desktop/runtime', ack, headers)[0], 409)
        status, closed = self.request(port, 'POST', '/api/desktop/runtime', {'event': 'godot_closed'}, headers)
        self.assertEqual(status, 200)
        self.assertFalse(closed['three_d_open'])
        self.assertEqual(closed['revision'], 2)
        self.assertNotIn(self.desktop_token, json.dumps(self.request(port, 'GET', '/api/state')[1]))
        self.stop_and_check(process, port)

    def test_standalone_server_has_no_native_controls_or_credential(self):
        server = make_server(0)
        worker = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .01}, daemon=True)
        worker.start()
        try:
            port = server.server_port
            status, state = self.request(port, 'GET', '/api/desktop')
            self.assertEqual(status, 200)
            self.assertEqual(state, dict(available=False, view='monitor', fullscreen=False,
                                         three_d_open=False, pending=False, error=None, revision=0))
            self.assertIsNone(server.desktop.runtime_token)
            self.assertEqual(self.request(port, 'POST', '/api/desktop', {'action': 'open_3d'})[0], 409)
            self.assertEqual(self.request(port, 'POST', '/api/desktop', {'action': 'exec'})[0], 400)
            self.assertEqual(self.request(port, 'POST', '/api/desktop/runtime', {'event': 'godot_closed'})[0], 403)
        finally:
            server.shutdown()
            worker.join(timeout=2)
            server.server_close()

    def test_user_settings_override_absent_environment_without_secret_output(self):
        marker = 'test-only-not-a-real-key'
        (self.data_dir / '.env').write_text(
            f'OPENAI_API_KEY={marker}\nLOW_SKY_AGENT_MODEL=openai:desktop-config-test\n', encoding='utf-8')
        process, port = self.start()
        status, configuration = self.request(port, 'GET', '/api/assessment')
        self.assertEqual(status, 200)
        self.assertEqual(configuration['model'], 'openai:desktop-config-test')
        self.assertNotEqual(configuration['configuration_error'], 'missing_api_key')
        self.assertNotIn(marker, json.dumps(configuration))
        # Merely starting or reading status never calls the configured provider.
        self.assertFalse(configuration['running'])
        self.stop_and_check(process, port)

    def test_readonly_packaged_assets_and_all_journals_live_outside_bundle(self):
        bundle = self.directory / 'bundle'
        bundle.mkdir()
        for name in ('tools', 'data', 'monitor'):
            shutil.copytree(PROJECT / name, bundle / name, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        (bundle / '.env').write_text('LOW_SKY_AGENT_MODEL=openai:DO_NOT_LOAD_BUNDLED_ENV\n', encoding='utf-8')
        files = [path for path in bundle.rglob('*') if path.is_file()]
        before = {str(path.relative_to(bundle)): hashlib.sha256(path.read_bytes()).hexdigest() for path in files}
        directories = [bundle, *[path for path in bundle.rglob('*') if path.is_dir()]]
        for path in files:
            path.chmod(0o444)
        for path in directories:
            path.chmod(0o555)
        def restore_modes():
            for path in directories:
                path.chmod(0o755)
            for path in files:
                path.chmod(0o644)
        self.addCleanup(restore_modes)
        process, port = self.start(package_root=bundle)
        self.assertEqual(self.request(port, 'GET', '/api/assessment')[1]['mode'], 'rules')
        self.assertEqual(self.request(port, 'GET', '/')[1], (bundle / 'monitor' / 'index.html').read_bytes())
        self.request(port, 'POST', '/api/control', {'action': 'case', 'case_id': 'case_003'})
        state = self.request(port, 'POST', '/api/control', {'action': 'seek', 'at_ms': 10000})[1]
        track = state['tracks'][0]
        status, _ = self.request(port, 'POST', '/api/control', dict(
            action='review_track', run_id=state['run_id'], object_id=track['object_id'],
            evidence_version=track['evidence_version'], reviewer='desktop-tester',
            decision='noted', reason='Verified packaged audit storage'))
        self.assertEqual(status, 200)
        card = state['dashboard']['cards'][0]
        status, _ = self.request(port, 'POST', '/api/control', dict(
            action='dashboard_action', run_id=state['run_id'], object_id=card['object_id'],
            card_version=card['version'], choice='continue_observe', confirm=True,
            reviewer='desktop-tester', comment='Local test'))
        self.assertEqual(status, 200)
        self.assertEqual(self.request(port, 'POST', '/api/decisions', dict(
            action='assess_current', run_id=state['run_id'], language='en'))[0], 202)
        event = None
        for _ in range(100):
            event = self.request(port, 'GET', '/api/decisions')[1]['events'][0]
            if event['status'] in ('ready', 'failed'):
                break
            time.sleep(.02)
        self.assertEqual(event['status'], 'ready')
        self.assertEqual(self.request(port, 'POST', '/api/decisions', dict(
            action='confirm', run_id=state['run_id'], event_id=event['id'],
            evidence_version=event['evidence_version'], option_id='hold_review', confirm=True,
            reviewer='desktop-tester', reason='Keep received evidence paused'))[0], 200)
        for name in ('track-reviews.jsonl', 'event-decisions.jsonl', 'dashboard-decisions.jsonl'):
            rows = (self.data_dir / name).read_text(encoding='utf-8').splitlines()
            self.assertEqual(len(rows), 1)
            self.assertEqual(json.loads(rows[0])['reviewer'], 'desktop-tester')
        self.stop_and_check(process, port)
        after = {str(path.relative_to(bundle)): hashlib.sha256(path.read_bytes()).hexdigest()
                 for path in bundle.rglob('*') if path.is_file()}
        self.assertEqual(before, after)
        self.assertFalse((bundle / '.local').exists())

    def test_startup_failure_is_sanitized_and_never_ready(self):
        private = 'private-malformed-key-marker'
        (self.data_dir / '.env').write_text(f'OPENAI_API_KEY="{private}\n', encoding='utf-8')
        result = subprocess.run([sys.executable, '-m', 'tools.desktop_runtime', '--data-dir', str(self.data_dir)],
                                cwd=PROJECT, text=True, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, '')
        self.assertIn('could not start', result.stderr)
        self.assertNotIn(private, result.stderr)
        self.assertNotIn('Traceback', result.stderr)

    def test_data_directory_is_required_and_port_validated(self):
        for args in ([], ['--data-dir', str(self.data_dir), '--port', '-1']):
            result = subprocess.run([sys.executable, '-m', 'tools.desktop_runtime', *args],
                                    cwd=PROJECT, text=True, capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stdout, '')

    def test_create_server_uses_only_explicit_appdata_env_and_journal_paths(self):
        with patch.object(desktop_runtime, 'load_agent_env') as loader:
            server = desktop_runtime.create_server(self.data_dir)
        self.addCleanup(server.server_close)
        loader.assert_called_once_with(self.data_dir.resolve() / '.env')
        self.assertEqual(server.server_address[0], '127.0.0.1')
        simulation = server.simulation
        self.assertEqual(simulation.audit.path, self.data_dir.resolve() / 'track-reviews.jsonl')
        self.assertEqual(simulation.decisions.audit.path, self.data_dir.resolve() / 'event-decisions.jsonl')
        self.assertEqual(simulation.dashboard.audit.path, self.data_dir.resolve() / 'dashboard-decisions.jsonl')


if __name__ == '__main__':
    unittest.main()
