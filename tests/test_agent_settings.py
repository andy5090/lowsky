import http.client
import importlib.util
import json
import os
import stat
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from tools import monitor_server
from tools.agent_settings import AgentSettings, PRESETS, test_connection
from tools.situation_agent import (_evidence_tools, build_bundle, chat_model_options, configuration_status,
                                   deepagents_report, evaluate, rules_report)

SECRET = 'sk-ant-test-0123456789-SECRET'


class AgentSettingsStoreTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / 'agent-settings.json'

    def test_environment_fallback_matches_legacy_behaviour(self):
        store = AgentSettings(environ={})
        self.assertEqual(store.resolve()['model'], 'openai:gpt-6.1-sol')
        self.assertIsNone(store.resolve()['api_key'])
        self.assertEqual(configuration_status(store.resolve())['configuration_error'], 'missing_api_key')
        env = AgentSettings(environ={'LOW_SKY_AGENT_MODEL': 'anthropic:claude-sonnet-5', 'ANTHROPIC_API_KEY': 'env-key-1234'})
        resolved = env.resolve()
        self.assertEqual((resolved['provider'], resolved['model_id'], resolved['key_source']),
                         ('anthropic', 'claude-sonnet-5', 'environment'))
        self.assertEqual(AgentSettings(environ={'LOW_SKY_AGENT_MODEL': ''}).resolve()['provider'], 'rules')

    def test_saved_settings_win_persist_privately_and_never_leave_through_public(self):
        environ = {'OPENAI_API_KEY': 'env-openai-key-9999', 'LOW_SKY_AGENT_MODEL': 'openai:gpt-6.1-sol'}
        store = AgentSettings(self.path, environ=environ)
        public = store.save(dict(provider='anthropic', model='claude-opus-5', api_key=f'  {SECRET}  '))
        self.assertEqual((public['provider'], public['model'], public['source']), ('anthropic', 'anthropic:claude-opus-5', 'settings'))
        self.assertEqual(public['providers']['anthropic']['key_hint'], '…CRET')
        self.assertEqual(public['providers']['anthropic']['key_source'], 'settings')
        self.assertEqual(public['providers']['openai']['key_source'], 'environment')
        self.assertNotIn(SECRET, json.dumps(public))
        self.assertNotIn('env-openai-key', json.dumps(public))
        if os.name == 'posix':
            self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)
        self.assertEqual(AgentSettings(self.path, environ=environ).resolve()['api_key'], SECRET)
        self.assertNotIn(SECRET, os.environ.values())
        # Switching provider keeps the other provider's saved key and model.
        store.save(dict(provider='openai'))
        self.assertEqual(store.resolve()['api_key'], 'env-openai-key-9999')
        store.save(dict(provider='anthropic'))
        self.assertEqual(store.resolve()['model'], 'anthropic:claude-opus-5')
        # An omitted key keeps the saved one; clear_key removes it and falls back to the environment (none here).
        store.save(dict(provider='anthropic', model='claude-sonnet-5'))
        self.assertEqual(store.resolve()['api_key'], SECRET)
        store.save(dict(provider='anthropic', clear_key=True))
        self.assertIsNone(store.resolve()['api_key'])
        store.save(dict(provider='rules'))
        self.assertEqual(configuration_status(store.resolve())['mode'], 'rules')

    def test_invalid_input_is_rejected_without_changing_saved_state(self):
        store = AgentSettings(self.path, environ={})
        store.save(dict(provider='anthropic', model='claude-opus-5', api_key=SECRET))
        before = self.path.read_text()
        for command in (dict(provider='gemini'), dict(provider='anthropic', model='anthropic:claude-opus-5'),
                        dict(provider='anthropic', model='has space'), dict(provider='anthropic', api_key='bad key'),
                        dict(provider='anthropic', api_key='x' * 401), dict(provider='openai', api_key=['list'])):
            with self.assertRaises(ValueError):
                store.save(command)
        self.assertEqual(self.path.read_text(), before)

    def test_damaged_file_and_leftover_temporaries_never_block_startup(self):
        self.path.write_text('{"schema_version": 99, "keys": {"anthropic": "' + SECRET + '"}}')
        leftover = self.path.parent / '.agent-settings-crash'
        leftover.write_text(SECRET)
        store = AgentSettings(self.path, environ={})
        self.assertEqual(store.public()['load_error'], 'corrupt_settings_file')
        self.assertFalse(self.path.exists())
        self.assertTrue((self.path.parent / 'agent-settings.json.corrupt').exists())
        self.assertFalse(leftover.exists())
        self.assertEqual(store.resolve()['provider'], 'openai')
        store.save(dict(provider='rules'))
        self.assertIsNone(store.public()['load_error'])

    def test_remove_key_keeps_the_active_provider_and_models(self):
        store = AgentSettings(self.path, environ={'ANTHROPIC_API_KEY': 'env-anthropic-5678'})
        store.save(dict(provider='anthropic', model='claude-sonnet-5', api_key=SECRET))
        store.save(dict(provider='rules'))
        public = store.remove_key(dict(provider='anthropic'))
        self.assertEqual(public['saved_provider'], 'rules')
        self.assertEqual(public['providers']['anthropic']['saved_model'], 'claude-sonnet-5')
        self.assertEqual(public['providers']['anthropic']['key_source'], 'environment')
        self.assertNotIn(SECRET, self.path.read_text())
        with self.assertRaises(ValueError):
            store.remove_key(dict(provider='rules'))

    def test_candidate_and_connection_test_use_typed_sdk_errors_without_generation(self):
        store = AgentSettings(environ={})
        self.assertEqual(test_connection(store.candidate(dict(provider='anthropic')))['code'], 'missing_api_key')
        with self.assertRaises(ValueError):
            store.candidate(dict(provider='rules'))
        if not importlib.util.find_spec('anthropic'):
            self.skipTest('anthropic SDK not installed')
        import anthropic
        candidate = store.candidate(dict(provider='anthropic', model='claude-opus-5', api_key=SECRET))
        self.assertEqual(candidate['key_source'], 'unsaved')
        cases = [(anthropic.AuthenticationError, 401, 'invalid_key'), (anthropic.NotFoundError, 404, 'model_not_found'),
                 (anthropic.PermissionDeniedError, 403, 'permission_denied'), (anthropic.RateLimitError, 429, 'rate_limited')]
        import httpx
        for error, status, code in cases:
            response = httpx.Response(status, request=httpx.Request('GET', 'https://api.anthropic.com/v1/models/x'))
            with patch('anthropic.resources.models.Models.retrieve', side_effect=error('x', response=response, body=None)):
                self.assertEqual(test_connection(candidate)['code'], code)
        with patch('anthropic.resources.models.Models.retrieve', side_effect=RuntimeError(f'unexpected {SECRET}')):
            result = test_connection(candidate)
        self.assertEqual(result['code'], 'provider_error')
        self.assertNotIn(SECRET, json.dumps(result))
        with patch('anthropic.resources.models.Models.retrieve', return_value=type('M', (), {'id': 'claude-opus-5'})()):
            self.assertEqual(test_connection(candidate), dict(ok=True, code='ok', model='claude-opus-5'))


class ClaudeOptionsTests(unittest.TestCase):
    def test_claude_options_enable_adaptive_thinking_only_where_supported(self):
        base = dict(provider='anthropic', api_key=SECRET, base_url=None)
        for model_id in ('claude-opus-5', 'claude-opus-5-5', 'claude-sonnet-5', 'claude-fable-5-1'):
            options = chat_model_options(dict(base, model_id=model_id))
            self.assertEqual(options['thinking'], {'type': 'adaptive'}, model_id)
            self.assertEqual((options['api_key'], options['max_tokens'], options['max_retries']), (SECRET, 16000, 0))
        self.assertNotIn('thinking', chat_model_options(dict(base, model_id='claude-haiku-4-5')))
        openai = chat_model_options(dict(provider='openai', model_id='gpt-6.1-sol', api_key='k', base_url='http://127.0.0.1:1'))
        self.assertEqual(openai, dict(timeout=60, max_retries=0, api_key='k', base_url='http://127.0.0.1:1'))
        self.assertTrue(all(preset['id'].startswith('claude-') for preset in PRESETS['anthropic']))


class FakeAnthropic(BaseHTTPRequestHandler):
    """Loopback stand-in for POST /v1/messages; records request bodies and headers."""
    def log_message(self, *args):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        server = self.server
        server.requests.append(dict(path=self.path, key=self.headers.get('x-api-key'), body=body))
        content = server.respond(body, len(server.requests))
        message = dict(id=f'msg_{len(server.requests)}', type='message', role='assistant', model=body['model'],
                       content=content, stop_reason='tool_use', stop_sequence=None,
                       usage=dict(input_tokens=10, output_tokens=10))
        if body.get('stream'):
            events = [('message_start', dict(type='message_start', message={**message, 'content': [], 'stop_reason': None}))]
            for index, block in enumerate(content):
                if block['type'] == 'tool_use':
                    events += [('content_block_start', dict(type='content_block_start', index=index, content_block={**block, 'input': {}})),
                               ('content_block_delta', dict(type='content_block_delta', index=index,
                                                            delta=dict(type='input_json_delta', partial_json=json.dumps(block['input']))))]
                else:
                    events += [('content_block_start', dict(type='content_block_start', index=index, content_block={**block, 'thinking': ''})),
                               ('content_block_delta', dict(type='content_block_delta', index=index, delta=dict(type='thinking_delta', thinking=block['thinking']))),
                               ('content_block_delta', dict(type='content_block_delta', index=index, delta=dict(type='signature_delta', signature=block['signature'])))]
                events.append(('content_block_stop', dict(type='content_block_stop', index=index)))
            events += [('message_delta', dict(type='message_delta', delta=dict(stop_reason='tool_use', stop_sequence=None), usage=dict(output_tokens=10))),
                       ('message_stop', dict(type='message_stop'))]
            payload = ''.join(f'event: {name}\ndata: {json.dumps(data)}\n\n' for name, data in events).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream')
        else:
            payload = json.dumps(message).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


@unittest.skipUnless(importlib.util.find_spec('langchain_anthropic') and importlib.util.find_spec('deepagents'),
                     'Optional Claude adapter is not installed')
class ClaudeAdapterTests(unittest.TestCase):
    def test_actual_langchain_anthropic_tool_loop_without_forced_tool_choice(self):
        from tools.monitor_server import Simulation
        sim = Simulation(clock=lambda: 0, decision_evaluator=lambda *_: {})
        sim.control(dict(action='case', case_id='case_003'))
        sim.control(dict(action='seek', at_ms=100000))
        bundle = build_bundle(sim.state())
        expected = rules_report(bundle)
        server = ThreadingHTTPServer(('127.0.0.1', 0), FakeAnthropic)
        server.requests = []

        def respond(body, number):
            if number == 1:
                return [dict(type='thinking', thinking='Read the evidence tools first.', signature='sig-fixture'),
                        *[dict(type='tool_use', id=f'toolu_{index}', name=tool.__name__, input={})
                          for index, tool in enumerate(_evidence_tools(bundle))]]
            return [dict(type='tool_use', id='toolu_report', name='SituationReport', input=expected)]
        server.respond = respond
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        settings = dict(provider='anthropic', model_id='claude-opus-5', model='anthropic:claude-opus-5',
                        api_key=SECRET, base_url=f'http://127.0.0.1:{server.server_port}', key_source='settings',
                        source='settings')
        environ_before = dict(os.environ)
        self.assertEqual(deepagents_report(bundle, 'en', 'anthropic:claude-opus-5', settings=settings), expected)
        self.assertEqual(dict(os.environ), environ_before, 'API key is passed to the client, not the environment')
        self.assertEqual(len(server.requests), 2)
        for request in server.requests:
            self.assertEqual(request['path'], '/v1/messages')
            self.assertEqual(request['key'], SECRET)
            body = request['body']
            self.assertEqual((body['model'], body['max_tokens']), ('claude-opus-5', 16000))
            self.assertEqual(body['thinking'], {'type': 'adaptive'})
            self.assertNotIn(body.get('tool_choice', {}).get('type'), ('any', 'tool'), 'Claude rejects forced tool use with thinking')
            self.assertTrue({tool.__name__ for tool in _evidence_tools(bundle)} | {'SituationReport'}
                            <= {tool['name'] for tool in body['tools']})
        second = server.requests[1]['body']['messages']
        assistant = next(message for message in second if message['role'] == 'assistant')
        self.assertEqual(assistant['content'][0]['type'], 'thinking', 'Thinking block is replayed unchanged')
        self.assertEqual(assistant['content'][0]['signature'], 'sig-fixture')
        results = [block for message in second if message['role'] == 'user' and isinstance(message['content'], list)
                   for block in message['content'] if block.get('type') == 'tool_result']
        self.assertEqual(len(results), len(_evidence_tools(bundle)))
        # evaluate() threads the same settings through and reports the Claude model.
        server.requests.clear()
        report = evaluate(sim.state(), settings=settings)
        self.assertEqual((report['mode'], report['model']), ('llm', 'anthropic:claude-opus-5'))


class SettingsEndpointTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        settings = AgentSettings(Path(self.folder.name) / 'agent-settings.json', environ={})
        self.server = monitor_server.make_server(0, monitor_server.Simulation(
            clock=lambda: 0, decision_evaluator=lambda *_: {}, agent_settings=settings))
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.port = self.server.server_port

    def call(self, method, path, body=None, origin=True):
        connection = http.client.HTTPConnection('127.0.0.1', self.port, timeout=10)
        headers = {'Content-Type': 'application/json', 'Host': f'127.0.0.1:{self.port}'}
        if origin:
            headers['Origin'] = f'http://127.0.0.1:{self.port}'
        else:
            headers['Origin'] = 'http://evil.example'
        connection.request(method, path, json.dumps(body) if body is not None else None, headers)
        response = connection.getresponse()
        data = json.loads(response.read())
        connection.close()
        return response.status, data

    def test_save_and_status_never_return_the_key(self):
        status, data = self.call('GET', '/api/agent-settings')
        self.assertEqual((status, data['status']['configuration_error'], data['persistent']), (200, 'missing_api_key', True))
        status, data = self.call('POST', '/api/agent-settings', dict(action='save', provider='anthropic',
                                                                     model='claude-sonnet-5', api_key=SECRET))
        self.assertEqual(status, 200)
        self.assertEqual((data['model'], data['status']['provider'], data['status']['key_source']),
                         ('anthropic:claude-sonnet-5', 'anthropic', 'settings'))
        self.assertNotIn(SECRET, json.dumps(data))
        for path in ('/api/agent-settings', '/api/assessment', '/api/decisions', '/api/state'):
            self.assertNotIn(SECRET, json.dumps(self.call('GET', path)[1]), path)
        status, data = self.call('POST', '/api/agent-settings', dict(action='save', provider='anthropic', api_key='has space'))
        self.assertEqual(status, 400)
        status, _ = self.call('POST', '/api/agent-settings', dict(action='save', provider='rules'), origin=False)
        self.assertEqual(status, 403)
        with patch('tools.monitor_server.test_agent_connection', return_value=dict(ok=True, code='ok', model='claude-sonnet-5')) as probe:
            status, data = self.call('POST', '/api/agent-settings', dict(action='test', provider='anthropic'))
        self.assertEqual((status, data['code']), (200, 'ok'))
        self.assertEqual(probe.call_args[0][0]['api_key'], SECRET)
        self.assertEqual(self.call('POST', '/api/agent-settings', dict(action='delete'))[0], 400)
        status, data = self.call('POST', '/api/agent-settings', dict(action='remove_key', provider='anthropic'))
        self.assertEqual((status, data['provider'], data['providers']['anthropic']['key_set']), (200, 'anthropic', False))
        self.assertEqual(data['status']['configuration_error'], 'missing_api_key')


if __name__ == '__main__':
    unittest.main()
