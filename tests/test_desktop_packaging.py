import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from desktop import build, smoke

PROJECT = Path(__file__).resolve().parents[1]


class DesktopPackagingTests(unittest.TestCase):
    def test_native_payload_paths_match_launcher_contract(self):
        payload = Path('/payload')
        backend, godot, data, monitor = smoke.runtime_paths(payload, 'darwin')
        self.assertEqual(backend, payload / 'backend/lowsky-server')
        self.assertEqual(godot, payload / 'godot/LOW SKY 3D.app/Contents/MacOS/LOW SKY 3D')
        self.assertEqual(data, payload / 'backend/_internal/data')
        self.assertEqual(monitor, payload / 'backend/_internal/monitor')
        backend, godot, _, _ = smoke.runtime_paths(payload, 'win32')
        self.assertEqual(backend.name, 'lowsky-server.exe')
        self.assertEqual(godot.name, 'LOW SKY 3D.exe')
        with self.assertRaises(smoke.SmokeError):
            smoke.runtime_paths(payload, 'linux')

    def test_godot_manifest_resolves_actual_export_name_and_rejects_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            payload = Path(directory)
            manifest = payload / 'godot-executable.txt'
            relative = 'godot/LOW SKY 3D.app/Contents/MacOS/LOW SKY — 3D Simulation'
            manifest.write_text(relative, encoding='utf-8')
            self.assertEqual(smoke.runtime_paths(payload, 'darwin')[1], payload / relative)
            for invalid in ('../outside', '/outside', 'backend/lowsky-server', ''):
                manifest.write_text(invalid, encoding='utf-8')
                with self.assertRaises(smoke.SmokeError):
                    smoke.runtime_paths(payload, 'darwin')

    def test_smoke_and_build_reject_private_payload_files(self):
        for relative in ('.env', 'backend/.env.production', 'backend/.local/reviews.json',
                         'source.docx', 'event-decisions.jsonl'):
            with self.subTest(relative=relative), tempfile.TemporaryDirectory() as directory:
                payload = Path(directory)
                path = payload / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('synthetic test fixture', encoding='utf-8')
                with self.assertRaises(smoke.SmokeError):
                    smoke.check_public_payload(payload)
                with self.assertRaises(RuntimeError):
                    build.assert_public_payload(payload)

    def test_smoke_rejects_empty_private_directories(self):
        with tempfile.TemporaryDirectory() as directory:
            payload = Path(directory)
            (payload / '.local').mkdir()
            with self.assertRaises(smoke.SmokeError):
                smoke.check_public_payload(payload)

    def test_public_data_and_license_payload_are_allowed(self):
        with tempfile.TemporaryDirectory() as directory:
            payload = Path(directory)
            (payload / 'licenses').mkdir()
            (payload / 'licenses/LICENSE.txt').write_text('test public license')
            (payload / 'data.json').write_text('{"synthetic":true}')
            smoke.check_public_payload(payload)
            build.assert_public_payload(payload)

    def test_child_environment_disables_models_and_external_tracing(self):
        with patch.dict(os.environ, dict(OPENAI_API_KEY='test-secret', ANTHROPIC_API_KEY='test-secret',
                                        LANGSMITH_API_KEY='test-secret', LOW_SKY_AGENT_MODEL='openai:anything',
                                        LANGSMITH_TRACING='true')):
            environment = smoke.isolated_environment()
        self.assertNotIn('OPENAI_API_KEY', environment)
        self.assertNotIn('ANTHROPIC_API_KEY', environment)
        self.assertNotIn('LANGSMITH_API_KEY', environment)
        self.assertEqual(environment['LOW_SKY_AGENT_MODEL'], '')
        self.assertEqual(environment['LANGSMITH_TRACING'], 'false')
        self.assertEqual(environment['LANGCHAIN_TRACING_V2'], 'false')

    def test_readiness_protocol_rejects_bad_shapes_and_ports(self):
        class Process:
            pass
        for ready in ({'event': 'ready', 'port': True}, {'event': 'ready', 'port': 0},
                      {'event': 'ready', 'port': 65536}, {'event': 'other', 'port': 8765},
                      {'event': 'ready', 'port': 8765, 'secret': 'unexpected'}, []):
            with self.subTest(ready=ready):
                process = Process()
                process.stdout = io.StringIO(json.dumps(ready) + '\n')
                with self.assertRaises(smoke.SmokeError):
                    smoke.read_ready(process, timeout=1)
        process = Process()
        process.stdout = io.StringIO(json.dumps(dict(event="ready", port=12345, desktop_token="x" * 43)) + "\n")
        self.assertEqual(smoke.read_ready(process, timeout=1), 12345)

    def test_missing_packaged_data_fails_before_process_start(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(smoke.SmokeError):
                smoke.check_data(Path(directory) / 'data', Path(directory) / 'monitor')

    def test_shared_smoke_runner_checks_source_sidecar_without_api_calls(self):
        result = smoke.run_checks([sys.executable, str(PROJECT / 'tools/desktop_runtime.py')],
                                  PROJECT / 'data', PROJECT / 'monitor')
        self.assertTrue(result['ok'])
        self.assertTrue(result['shared_clock'])
        self.assertTrue(result['port_closed'])
        self.assertEqual(result['shutdown'], 'stdin_eof')
        self.assertEqual(result['godot'], 'skipped')
        self.assertFalse(result['external_api_calls'])
        self.assertEqual(result['assets'], len(smoke.ASSETS))


if __name__ == '__main__':
    unittest.main()
