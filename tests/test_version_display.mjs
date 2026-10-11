import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {test} from 'node:test';
import {messages, translate} from '../monitor/i18n.mjs';

const html = readFileSync(new URL('../monitor/index.html', import.meta.url), 'utf8');
const app = readFileSync(new URL('../monitor/app.js', import.meta.url), 'utf8');

test('the settings dialog ends with a muted version line, hidden until the server reports one', () => {
  const start = html.indexOf('<dialog id="agent-settings-dialog"');
  const dialog = html.slice(start, html.indexOf('</dialog>', start));
  assert.match(dialog, /<p id="agent-settings-version" class="muted settings-note" hidden><\/p>\s*<\/form>/);
});

test('the version line is filled from /api/config and hidden without a version', () => {
  const start = app.indexOf('function renderAgentSettings(');
  const render = app.slice(start, app.indexOf('\n}\n', start));
  assert.match(render, /\$\('agent-settings-version'\)\.hidden=!config\?\.version;/);
  assert.match(render, /\$\('agent-settings-version'\)\.textContent=config\?\.version\?t\('settings\.version',\{version:config\.version\}\):'';/);
});

test('the version label exists in both languages', () => {
  assert.equal(translate('en', 'settings.version', {version: '0.2.0'}), 'LOW SKY · Version 0.2.0');
  assert.equal(translate('ko', 'settings.version', {version: '0.2.0'}), 'LOW SKY · 버전 0.2.0');
  assert.ok(messages.en['settings.version'] && messages.ko['settings.version']);
});
