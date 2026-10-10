import io
import json
import os
from pathlib import Path
import signal
import subprocess
import threading
import unittest
from unittest.mock import patch

from tools import codex_test_operator as operator


class FakeProcess:
    def __init__(self, command, *, output=None, mode='success', cancel=None, **kwargs):
        self.command = command
        self.kwargs = kwargs
        self.output = json.dumps({'option_id': 'hold_review', 'reason': 'Check the received evidence gap.'}).encode() if output is None else output
        self.mode = mode
        self.cancel = cancel
        self.returncode = None
        self.pid = 987654
        self.stdin = io.BytesIO()
        self.inputs = []
        self.answer = Path(command[command.index('--output-last-message') + 1])
        self.schema = json.loads(Path(command[command.index('--output-schema') + 1]).read_text())
        self.waited_before_cleanup = False

    def communicate(self, input=None, timeout=None):
        self.inputs.append(input)
        if self.mode in ('cancel', 'timeout', 'stubborn'):
            if self.mode == 'cancel' and self.cancel:
                self.cancel.set()
            raise subprocess.TimeoutExpired(self.command, timeout)
        if self.mode == 'running_oversize':
            self.answer.write_bytes(b'x' * (operator.MAX_OUTPUT_BYTES + 1))
            raise subprocess.TimeoutExpired(self.command, timeout)
        self.returncode = 7 if self.mode == 'failure' else 0
        if self.mode != 'missing':
            self.answer.write_bytes(self.output)
        if self.mode == 'cancel_after_answer':
            self.cancel.set()
        return None, None

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        self.waited_before_cleanup = Path(self.kwargs['cwd']).exists()
        if self.mode == 'stubborn':
            self.mode = 'terminated'
            raise subprocess.TimeoutExpired(self.command, timeout)
        self.returncode = -15
        return self.returncode


class CodexTestOperatorTests(unittest.TestCase):
    def setUp(self):
        self.cancel = threading.Event()
        self.process = None

    def run_fake(self, *, context=None, **process_options):
        def popen(command, **kwargs):
            self.process = FakeProcess(command, cancel=self.cancel, **kwargs, **process_options)
            return self.process
        with patch.object(operator.shutil, 'which', return_value='/usr/local/bin/codex'), \
                patch.object(operator.subprocess, 'Popen', side_effect=popen), \
                patch.object(operator.os, 'killpg') as killpg:
            self.killpg = killpg
            return operator.choose(context or {'report': {'summary': 'Received evidence only.'}}, self.cancel)

    def test_command_schema_stdin_environment_and_cleanup(self):
        with patch.dict(os.environ, {'PATH': '/usr/local/bin', 'HOME': '/home/test', 'LANG': 'en_US.UTF-8',
                                    'TMPDIR': str(Path.cwd()), 'CODEX_HOME': '/home/test/.codex',
                                    'OPENAI_API_KEY': 'not-for-subprocess', 'UNRELATED': 'not-forwarded'}, clear=True):
            result = self.run_fake()
        self.assertEqual(result['option_id'], 'hold_review')
        command = self.process.command
        for flag in ('--ignore-user-config', '--ephemeral', '--skip-git-repo-check'):
            self.assertIn(flag, command)
        self.assertEqual(command[command.index('--sandbox') + 1], 'read-only')
        self.assertEqual(command[command.index('--model') + 1], operator.MODEL)
        self.assertEqual(command[-1], '-')
        self.assertIn('web_search="disabled"', command)
        self.assertIn('project_doc_max_bytes=0', command)
        self.assertIn('model_reasoning_effort="medium"', command)
        disabled = [command[i + 1] for i, flag in enumerate(command) if flag == '--disable']
        self.assertEqual(disabled, list(operator.DISABLED_FEATURES))
        self.assertEqual(self.process.schema, operator.OUTPUT_SCHEMA)
        self.assertNotIn('OPENAI_API_KEY', self.process.kwargs['env'])
        self.assertNotIn('UNRELATED', self.process.kwargs['env'])
        self.assertEqual(self.process.kwargs['env']['CODEX_HOME'], '/home/test/.codex')
        self.assertEqual(self.process.kwargs['stdout'], subprocess.DEVNULL)
        self.assertEqual(self.process.kwargs['stderr'], subprocess.DEVNULL)
        self.assertTrue(self.process.kwargs['start_new_session'])
        self.assertNotIn('shell', self.process.kwargs)
        self.assertIn(b'Received evidence only.', self.process.inputs[0])
        self.assertNotIn('Received evidence only.', ' '.join(command))
        self.assertNotIn(Path.cwd(), Path(self.process.kwargs['cwd']).parents)
        self.assertFalse(Path(self.process.kwargs['cwd']).exists())
        self.assertTrue(self.process.stdin.closed)

    def test_all_choices_are_model_outputs_without_recommendation_override(self):
        for option in operator.OPTION_IDS:
            result = self.run_fake(output=json.dumps({'option_id': option, 'reason': ' 근거 확인 '} ).encode(),
                                   context={'recommended_option_id': 'hold_review'})
            self.assertEqual(result, {'option_id': option, 'reason': '근거 확인'})

    def test_invalid_output_rejected_without_raw_text(self):
        invalid = [b'private-secret', b'[]', b'null', b'\xff',
                   b'{"option_id":"hold_review","reason":" "}',
                   b'{"option_id":"unknown","reason":"private-secret"}',
                   b'{"option_id":"hold_review","reason":42}',
                   b'{"option_id":"hold_review","reason":"ok","extra":"private-secret"}',
                   b'{"option_id":"defer","option_id":"hold_review","reason":"private-secret"}',
                   json.dumps({'option_id':'defer', 'reason':'x' * 1001}).encode(),
                   b'x' * (operator.MAX_OUTPUT_BYTES + 1)]
        for output in invalid:
            with self.subTest(output=output[:40]), self.assertRaises(operator.CodexOperatorError) as error:
                self.run_fake(output=output)
            self.assertEqual(str(error.exception), 'Codex returned an invalid test choice.')
            self.assertFalse(Path(self.process.kwargs['cwd']).exists())

    def test_cancellation_terminates_process_group_before_temp_cleanup(self):
        with self.assertRaisesRegex(operator.CodexOperatorError, 'cancelled'):
            self.run_fake(mode='cancel')
        self.assertEqual(self.killpg.call_args_list[0].args, (self.process.pid, signal.SIGTERM))
        self.assertEqual(self.killpg.call_args_list[1].args, (self.process.pid, signal.SIGKILL))
        self.assertTrue(self.process.waited_before_cleanup)
        self.assertFalse(Path(self.process.kwargs['cwd']).exists())
        self.assertTrue(self.process.stdin.closed)

    def test_deadline_kills_stubborn_process(self):
        with patch.object(operator.time, 'monotonic', side_effect=[10, 10, 131]), \
                self.assertRaisesRegex(operator.CodexOperatorError, 'timed out'):
            self.run_fake(mode='stubborn')
        self.assertEqual(self.killpg.call_args_list[-1].args, (self.process.pid, signal.SIGKILL))
        self.assertTrue(self.process.waited_before_cleanup)
        self.assertFalse(Path(self.process.kwargs['cwd']).exists())

    def test_output_cap_terminates_still_running_cli(self):
        with self.assertRaisesRegex(operator.CodexOperatorError, 'invalid test choice'):
            self.run_fake(mode='running_oversize')
        self.assertEqual(self.killpg.call_args_list[0].args, (self.process.pid, signal.SIGTERM))

    def test_late_cancellation_cannot_return_choice(self):
        with self.assertRaisesRegex(operator.CodexOperatorError, 'cancelled'):
            self.run_fake(mode='cancel_after_answer')

    def test_configuration_missing_cli_and_cancelled_before_spawn(self):
        with patch.object(operator.shutil, 'which', return_value=None), patch.object(operator.subprocess, 'Popen') as spawn:
            self.assertEqual(operator.configuration_status(), {'available':False, 'provider':'codex_cli', 'model':operator.MODEL})
            with self.assertRaisesRegex(operator.CodexOperatorError, 'unavailable'):
                operator.choose({}, self.cancel)
            self.cancel.set()
            with self.assertRaisesRegex(operator.CodexOperatorError, 'cancelled'):
                operator.choose({}, self.cancel)
            spawn.assert_not_called()

    def test_cli_failure_and_missing_output_are_sanitized(self):
        for mode in ('failure', 'missing'):
            with self.assertRaises(operator.CodexOperatorError) as error:
                self.run_fake(mode=mode, output=b'private-secret')
            self.assertNotIn('private-secret', str(error.exception))
            self.assertFalse(Path(self.process.kwargs['cwd']).exists())
        with patch.object(operator.shutil, 'which', return_value='/private/path/codex'), \
                patch.object(operator.subprocess, 'Popen', side_effect=OSError('private-secret')), \
                self.assertRaises(operator.CodexOperatorError) as error:
            operator.choose({}, self.cancel)
        self.assertEqual(str(error.exception), 'Codex test choice is unavailable.')

    def test_invalid_or_oversized_context_never_launches_cli(self):
        for context in ([], {'value': float('nan')}, {'value': object()}, {'value':'x' * operator.MAX_CONTEXT_BYTES}):
            with patch.object(operator.shutil, 'which', return_value='/test/codex'), \
                    patch.object(operator.subprocess, 'Popen') as spawn, \
                    self.assertRaisesRegex(operator.CodexOperatorError, 'Invalid Codex test context'):
                operator.choose(context, self.cancel)
            spawn.assert_not_called()


if __name__ == '__main__':
    unittest.main()
