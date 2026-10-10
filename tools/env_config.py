"""Load only the agent's local KEY=value settings, without shell expansion."""
import os
import shlex


AGENT_SETTINGS = {'OPENAI_API_KEY', 'OPENAI_BASE_URL', 'ANTHROPIC_API_KEY', 'ANTHROPIC_BASE_URL', 'LOW_SKY_AGENT_MODEL'}


def load_agent_env(path):
    if not path.is_file():
        return
    values = {}
    for number, line in enumerate(path.read_text(encoding='utf-8-sig').splitlines(), 1):
        line = line.strip()
        if line.startswith('export '):
            line = line[7:].lstrip()
        key, separator, raw = line.partition('=')
        key = key.strip()
        if not separator or key not in AGENT_SETTINGS:
            continue
        try:
            parts = shlex.split(raw, comments=True, posix=True)
        except ValueError:
            raise ValueError(f'Invalid agent .env setting on line {number}') from None
        if len(parts) > 1:
            raise ValueError(f'Invalid agent .env setting on line {number}')
        values[key] = parts[0] if parts else ''
    # Environment variables take precedence; parse before applying any settings.
    for key, value in values.items():
        os.environ.setdefault(key, value)
