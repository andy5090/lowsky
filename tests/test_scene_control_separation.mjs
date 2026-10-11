import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {test} from 'node:test';
import {createAlertPriorityPolicy} from '../monitor/notifications.mjs';
import {messages} from '../monitor/i18n.mjs';

const html = readFileSync(new URL('../monitor/index.html', import.meta.url), 'utf8');
const app = readFileSync(new URL('../monitor/app.js', import.meta.url), 'utf8');
const paneSlice = id => {
  const start = html.indexOf(`<div id="${id}"`);
  assert.notEqual(start, -1, id);
  const next = html.indexOf('<div id="pane-', start + 10);
  return html.slice(start, next === -1 ? undefined : next);
};

test('scene control lives in the instructor area of Tools, collapsed, not in the trainee Decisions pane', () => {
  assert.doesNotMatch(paneSlice('pane-decision'), /id="exercise-panel"/);
  const tools = paneSlice('pane-tools');
  const tag = tools.match(/<details id="exercise-panel"[^>]*>/)?.[0];
  assert.ok(tag, 'exercise panel is inside the Tools pane');
  assert.doesNotMatch(tag, /\sopen[\s>]/, 'collapsed by default');
  assert.match(tag, /instructor-panel/);
  assert.match(tools, /data-i18n="exercise\.instructorNote"/);
});

test('no alert flow or map shortcut sends the trainee to scene control in the Decisions pane', () => {
  assert.doesNotMatch(app, /showPanel\('decision'\);\$\('exercise-panel'\)/);
  assert.match(app, /showPanel\('tools'\);\$\('exercise-panel'\)\.open=true/);
});

test('scene selections and scripted outcomes never raise priority alerts', () => {
  const policy = createAlertPriorityPolicy();
  const base = {run_id: 'r', at_ms: 1000, tracks: [], alerts: [], exercise: {selection: null, missions: []}};
  policy.observe(base);
  const changed = {...base, at_ms: 2000, exercise: {selection: {id: 's', status: 'applied'},
    missions: [{id: 'm', phase: 'complete', outcome: 'unresolved', result_at_ms: 1500}]}};
  const result = policy.observe(changed);
  assert.deepEqual([result.medium, result.high], [[], []]);
});

test('instructor labels exist in both languages', () => {
  for (const key of ['exercise.title', 'exercise.instructorBadge', 'exercise.instructorNote'])
    assert.ok(messages.en[key] && messages.ko[key], key);
  assert.match(messages.ko['exercise.title'], /교관/);
});
