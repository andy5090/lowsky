import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {test} from 'node:test';

const app = readFileSync(new URL('../monitor/app.js', import.meta.url), 'utf8');
const body = name => {
  const start = app.indexOf(`function ${name}(`);
  assert.notEqual(start, -1, name);
  return app.slice(start, app.indexOf('\n}\n', start));
};

test('the monitor publishes its language to the server for the 3D view, silently', () => {
  assert.match(app, /function publishLanguage\(\) \{ api\('\/api\/ui-language', \{language\}\)\.catch\(\(\) => \{\}\); \}/);
});

test('language is published on load and on every change through applyLanguage', () => {
  assert.match(body('applyLanguage'), /language = normalizeLanguage\(next\);[\s\S]*publishLanguage\(\);/);
  assert.match(app, /\napplyLanguage\(language\);\n/, 'initial load applies (and publishes) the stored language');
  assert.match(app, /\$\('language-select'\)\.onchange = event => \{applyLanguage\(event\.target\.value, true\)/);
});

test('language is republished after the server connection comes back or forgets it', () => {
  assert.match(body('connection'), /if \(ok && connected === false\) publishLanguage\(\);\n\s*connected = ok;/);
  assert.match(body('render'), /if \(data\.ui_language === null\) publishLanguage\(\);/);
});
