"""Per-user agent provider, model and API-key settings for the situation agent.

Saved settings live in one JSON file on this computer (owner-only permissions where the
OS supports it). API keys are write-only through the HTTP API: responses carry only
whether a key exists, where it came from and its last four characters. Keys are handed
directly to the model client for each request and are never copied into os.environ,
so subprocesses such as the Codex operator cannot inherit them.

Precedence: a saved provider/model/key wins. When nothing is saved for a provider, the
process environment (including the legacy .env loader) is used. With no saved provider
at all, LOW_SKY_AGENT_MODEL keeps its previous meaning.
"""
import copy
import json
import os
import tempfile
import threading
from pathlib import Path

SCHEMA_VERSION = 1
PROVIDERS = ('openai', 'anthropic', 'rules')
KEY_ENV = {'openai': 'OPENAI_API_KEY', 'anthropic': 'ANTHROPIC_API_KEY'}
BASE_URL_ENV = {'openai': 'OPENAI_BASE_URL', 'anthropic': 'ANTHROPIC_BASE_URL'}
DEFAULT_MODELS = {'openai': 'gpt-6.1-sol', 'anthropic': 'claude-opus-5'}
DEFAULT_MODEL_SETTING = 'openai:gpt-6.1-sol'
# Offered in the settings dialog; any other provider model ID can be typed as a custom value.
PRESETS = {
    'openai': [
        dict(id='gpt-6.1-sol', label=dict(en='GPT-6.1 Sol (default)', ko='GPT-6.1 Sol (기본)')),
    ],
    'anthropic': [
        dict(id='claude-opus-5', label=dict(en='Claude Opus 5 (recommended)', ko='Claude Opus 5 (권장)')),
        dict(id='claude-opus-5-5', label=dict(en='Claude Opus 5.5', ko='Claude Opus 5.5')),
        dict(id='claude-sonnet-5', label=dict(en='Claude Sonnet 5 (faster, lower cost)', ko='Claude Sonnet 5 (빠르고 저렴)')),
        dict(id='claude-fable-5-1', label=dict(en='Claude Fable 5.1 (most capable, highest cost)', ko='Claude Fable 5.1 (최고 성능, 최고 비용)')),
        dict(id='claude-haiku-4-5', label=dict(en='Claude Haiku 4.5 (fastest)', ko='Claude Haiku 4.5 (가장 빠름)')),
    ],
}
MAX_KEY_LENGTH = 400
MAX_MODEL_LENGTH = 120


def _clean_key(value):
    if not isinstance(value, str):
        raise ValueError('API key must be text')
    value = value.strip()
    if not value or len(value) > MAX_KEY_LENGTH or any(ord(c) < 33 or ord(c) > 126 for c in value):
        raise ValueError('API key must be 1-400 printable characters without spaces')
    return value


def _clean_model(value):
    if not isinstance(value, str):
        raise ValueError('Model must be text')
    value = value.strip()
    if not value or len(value) > MAX_MODEL_LENGTH or ':' in value or any(ord(c) < 33 or ord(c) > 126 for c in value):
        raise ValueError('Model ID must be 1-120 printable characters without spaces or a provider prefix')
    return value


def key_hint(value):
    return f'…{value[-4:]}' if value and len(value) >= 8 else ('…' if value else None)


class AgentSettings:
    """Thread-safe settings store. path=None keeps everything in memory (tests, env-only mode)."""

    def __init__(self, path=None, environ=None):
        self.path = Path(path) if path is not None else None
        self.environ = environ if environ is not None else os.environ
        self.lock = threading.Lock()
        self.data = self._empty()
        self.load_error = None
        if self.path is not None:
            self._remove_stale_temporaries()
            if self.path.is_file():
                try:
                    self.data = self._load()
                except ValueError:
                    # Never block startup on a damaged file: set it aside and start with no saved settings.
                    quarantine = self.path.with_name(self.path.name + '.corrupt')
                    try:
                        os.replace(self.path, quarantine)
                    except OSError:
                        pass
                    self.load_error = 'corrupt_settings_file'

    def _remove_stale_temporaries(self):
        # A crash between mkstemp and replace can leave a private copy behind; remove it on start.
        try:
            for leftover in self.path.parent.glob('.agent-settings-*'):
                leftover.unlink()
        except OSError:
            pass

    @staticmethod
    def _empty():
        return dict(schema_version=SCHEMA_VERSION, provider=None, models={}, keys={})

    def _load(self):
        try:
            raw = json.loads(self.path.read_text(encoding='utf-8'))
        except (OSError, ValueError) as error:
            raise ValueError(f'Unreadable agent settings file: {self.path}') from error
        if not isinstance(raw, dict) or raw.get('schema_version') != SCHEMA_VERSION:
            raise ValueError(f'Unsupported agent settings file: {self.path}')
        data = self._empty()
        if raw.get('provider') in PROVIDERS:
            data['provider'] = raw['provider']
        for provider in KEY_ENV:
            model = (raw.get('models') or {}).get(provider)
            key = (raw.get('keys') or {}).get(provider)
            try:
                if model:
                    data['models'][provider] = _clean_model(model)
                if key:
                    data['keys'][provider] = _clean_key(key)
            except ValueError as error:
                raise ValueError(f'Invalid agent settings file: {self.path}') from error
        return data

    def _persist(self, data):
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        encoded = json.dumps(data, ensure_ascii=False, indent=2) + '\n'
        # Write a private temporary file, then atomically replace the settings file.
        handle, temporary = tempfile.mkstemp(prefix='.agent-settings-', dir=self.path.parent)
        try:
            try:
                os.chmod(temporary, 0o600)
            except OSError:
                pass
            with os.fdopen(handle, 'w', encoding='utf-8') as stream:
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        except BaseException:
            try:
                os.unlink(temporary)
            except OSError:
                pass
            raise

    def _key(self, data, provider):
        saved = data['keys'].get(provider)
        if saved:
            return saved, 'settings'
        env = (self.environ.get(KEY_ENV[provider]) or '').strip()
        return (env, 'environment') if env else (None, None)

    def resolve(self):
        """Effective configuration for one request. Contains the API key: never serialize it."""
        with self.lock:
            data = copy.deepcopy(self.data)
        if data['provider'] == 'rules':
            return dict(provider='rules', model_id=None, model=None, api_key=None, key_source=None, base_url=None,
                        source='settings')
        if data['provider'] in KEY_ENV:
            provider = data['provider']
            model_id = data['models'].get(provider) or DEFAULT_MODELS[provider]
            source = 'settings'
        else:
            setting = self.environ.get('LOW_SKY_AGENT_MODEL', DEFAULT_MODEL_SETTING).strip()
            if not setting:
                return dict(provider='rules', model_id=None, model=None, api_key=None, key_source=None,
                            base_url=None, source='environment')
            provider, _, model_id = setting.partition(':')
            source = 'environment'
            if provider not in KEY_ENV or not model_id:
                # Keep unknown or malformed values visible so the status can report them.
                return dict(provider=provider or None, model_id=model_id or None, model=setting, api_key=None,
                            key_source=None, base_url=None, source=source)
        api_key, key_source = self._key(data, provider)
        base_url = (self.environ.get(BASE_URL_ENV[provider]) or '').strip() or None
        return dict(provider=provider, model_id=model_id, model=f'{provider}:{model_id}', api_key=api_key,
                    key_source=key_source, base_url=base_url, source=source)

    def public(self):
        """Safe view for the settings dialog: no key material beyond a four-character hint."""
        with self.lock:
            data = copy.deepcopy(self.data)
        effective = self.resolve()
        providers = {}
        for provider in KEY_ENV:
            key, key_source = self._key(data, provider)
            providers[provider] = dict(key_set=bool(key), key_source=key_source, key_hint=key_hint(key),
                                       saved_model=data['models'].get(provider), default_model=DEFAULT_MODELS[provider],
                                       presets=copy.deepcopy(PRESETS[provider]),
                                       environment_key_present=bool((self.environ.get(KEY_ENV[provider]) or '').strip()))
        return dict(schema_version=SCHEMA_VERSION, saved_provider=data['provider'],
                    provider=effective['provider'], model=effective['model'], source=effective['source'],
                    persistent=self.path is not None, load_error=self.load_error, providers=providers)

    def save(self, command):
        """Apply one explicit change. Omitted keys keep the saved key; clear_key removes it."""
        provider = command.get('provider')
        if provider not in PROVIDERS:
            raise ValueError('Choose OpenAI, Anthropic Claude or the rules-only overview')
        with self.lock:
            data = copy.deepcopy(self.data)
            data['provider'] = provider
            if provider in KEY_ENV:
                if command.get('model') is not None:
                    data['models'][provider] = _clean_model(command['model'])
                if command.get('clear_key') is True:
                    data['keys'].pop(provider, None)
                elif command.get('api_key') not in (None, ''):
                    data['keys'][provider] = _clean_key(command['api_key'])
            self._persist(data)
            self.data = data
            self.load_error = None
        return self.public()

    def remove_key(self, command):
        """Delete one provider's saved key without changing the active provider or models."""
        provider = command.get('provider')
        if provider not in KEY_ENV:
            raise ValueError('Choose OpenAI or Anthropic Claude')
        with self.lock:
            data = copy.deepcopy(self.data)
            data['keys'].pop(provider, None)
            self._persist(data)
            self.data = data
            self.load_error = None
        return self.public()

    def candidate(self, command):
        """Unsaved configuration for a connection test; falls back to the saved/env key."""
        provider = command.get('provider')
        if provider not in KEY_ENV:
            raise ValueError('Connection tests need OpenAI or Anthropic Claude')
        with self.lock:
            data = copy.deepcopy(self.data)
        model_id = _clean_model(command['model']) if command.get('model') else (
            data['models'].get(provider) or DEFAULT_MODELS[provider])
        if command.get('api_key') not in (None, ''):
            api_key, key_source = _clean_key(command['api_key']), 'unsaved'
        else:
            api_key, key_source = self._key(data, provider)
        base_url = (self.environ.get(BASE_URL_ENV[provider]) or '').strip() or None
        return dict(provider=provider, model_id=model_id, model=f'{provider}:{model_id}', api_key=api_key,
                    key_source=key_source, base_url=base_url, source='candidate')


def test_connection(config, timeout=15):
    """Check key and model access without generating tokens (models.retrieve on each provider)."""
    provider, model_id, api_key = config['provider'], config['model_id'], config['api_key']
    if not api_key:
        return dict(ok=False, code='missing_api_key')
    try:
        if provider == 'anthropic':
            import anthropic
            client = anthropic.Anthropic(api_key=api_key, base_url=config.get('base_url'), timeout=timeout, max_retries=0)
            errors = anthropic
        else:
            import openai
            client = openai.OpenAI(api_key=api_key, base_url=config.get('base_url'), timeout=timeout, max_retries=0)
            errors = openai
    except ImportError:
        return dict(ok=False, code='missing_dependencies')
    try:
        model = client.models.retrieve(model_id)
    except errors.AuthenticationError:
        return dict(ok=False, code='invalid_key')
    except errors.PermissionDeniedError:
        return dict(ok=False, code='permission_denied')
    except errors.NotFoundError:
        return dict(ok=False, code='model_not_found')
    except errors.RateLimitError:
        return dict(ok=False, code='rate_limited')
    except errors.APIConnectionError:
        return dict(ok=False, code='network')
    except errors.APIStatusError as error:
        return dict(ok=False, code='provider_error', status=getattr(error, 'status_code', None))
    except Exception:
        # Unexpected SDK/transport failures are reported generically; exception text may echo request details.
        return dict(ok=False, code='provider_error', status=None)
    return dict(ok=True, code='ok', model=getattr(model, 'id', model_id))
