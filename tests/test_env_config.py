import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.env_config import load_agent_env


class AgentEnvTests(unittest.TestCase):
    def test_allowlisted_values_quotes_comments_and_environment_precedence(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'OPENAI_API_KEY': 'existing'}, clear=True):
            path = Path(folder) / '.env'
            path.write_text('export OPENAI_API_KEY="file-key"\nLOW_SKY_AGENT_MODEL="" # offline\n'
                            'UNRELATED=ignored\nOPENAI_BASE_URL="https://example.invalid/$UNEXPANDED"\n')
            load_agent_env(path)
            self.assertEqual(os.environ['OPENAI_API_KEY'], 'existing')
            self.assertEqual(os.environ['LOW_SKY_AGENT_MODEL'], '')
            self.assertNotIn('UNRELATED', os.environ)
            self.assertEqual(os.environ['OPENAI_BASE_URL'], 'https://example.invalid/$UNEXPANDED')

    def test_missing_file_and_invalid_value_never_expose_or_partially_apply_keys(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {}, clear=True):
            path = Path(folder) / '.env'
            load_agent_env(path)
            path.write_text('OPENAI_API_KEY=test-secret\nLOW_SKY_AGENT_MODEL="unterminated-secret\n')
            with self.assertRaises(ValueError) as error:
                load_agent_env(path)
            self.assertNotIn('secret', str(error.exception))
            self.assertNotIn('OPENAI_API_KEY', os.environ)
