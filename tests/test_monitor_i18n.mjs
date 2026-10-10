import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {test} from 'node:test';
import {messages, normalizeLanguage, translate, readLanguage, saveLanguage, STORAGE_KEY} from '../monitor/i18n.mjs';

test('English is the default and only supported languages are selected', () => {
  for (const value of [undefined, null, '', 'fr', 'ko-KR', 'en']) {
    assert.equal(normalizeLanguage(value), 'en');
  }
  assert.equal(normalizeLanguage('ko'), 'ko');
  assert.equal(translate(undefined, 'monitorTitle'), 'Observation monitor');
  assert.equal(translate('ko', 'monitorTitle'), '관측 모니터');
});

test('all strings have complete English and Korean translations and matching parameters', () => {
  assert.deepEqual(Object.keys(messages.en).sort(), Object.keys(messages.ko).sort());
  for (const [key, english] of Object.entries(messages.en)) {
    assert.ok(english.trim(), key);
    assert.ok(messages.ko[key].trim(), key);
    assert.doesNotMatch(english, /[가-힣]/, key);
    const parameters = text => [...text.matchAll(/\{(\w+)\}/g)].map(match => match[1]).sort();
    assert.deepEqual(parameters(english), parameters(messages.ko[key]), key);
  }
});

test('interpolation preserves zero and translates map annotations', () => {
  assert.equal(translate('en', 'runway', {length: 2500, width: 45}), 'Runway 2500 × 45 m');
  assert.equal(translate('ko', 'runway', {length: 0, width: 45}), '활주로 0 × 45 m');
  assert.equal(translate('en', 'unknown-key'), 'unknown-key');
});

test('saved language survives a reload and blocked storage remains usable', () => {
  const values = new Map();
  const storage = {getItem: key => values.get(key), setItem: (key, value) => values.set(key, value)};
  assert.equal(readLanguage(storage), 'en');
  assert.equal(saveLanguage(storage, 'ko'), 'ko');
  assert.equal(values.get(STORAGE_KEY), 'ko');
  assert.equal(readLanguage(storage), 'ko');
  saveLanguage(storage, 'invalid');
  assert.equal(readLanguage(storage), 'en');
  const blocked = {getItem() { throw new Error('Blocked'); }, setItem() { throw new Error('Blocked'); }};
  assert.equal(readLanguage(blocked), 'en');
  assert.equal(saveLanguage(blocked, 'ko'), 'ko');
});

test('all static text and accessibility translation keys exist', () => {
  const html = readFileSync(new URL('../monitor/index.html', import.meta.url), 'utf8');
  for (const [, key] of html.matchAll(/data-i18n(?:-aria-label|-title)?="([^"]+)"/g)) {
    assert.ok(Object.hasOwn(messages.en, key), key);
    assert.ok(Object.hasOwn(messages.ko, key), key);
  }
  assert.match(html, /<html lang="en">/);
  assert.match(html, /id="language-select"/);
});

test('server-provided quality, alert, source and synthetic context values have translations', () => {
  const groups = {
    quality: ['consistent', 'contradictory', 'missing', 'not_comparable'],
    source: ['online', 'offline', 'stale', 'unknown'],
    alert: ['contradictory', 'not_comparable', 'stale', 'channel', 'unknown'],
    variant: ['consistent', 'contradictory', 'missing'],
    marker: ['circle', 'square', 'triangle', 'diamond'],
    context: ['context_001', 'context_002'],
  };
  for (const [group, values] of Object.entries(groups)) {
    for (const value of values) {
      for (const language of ['en', 'ko']) {
        assert.ok(Object.hasOwn(messages[language], `${group}.${value}`));
      }
    }
  }
  assert.match(translate('en', 'context.context_001'), /does not guarantee observation accuracy/);
  assert.match(translate('en', 'context.context_002'), /published late/);
});


test('every generated case briefing resolves in both languages', () => {
  const briefings=JSON.parse(readFileSync(new URL('../data/scenarios/v1/briefings.json',import.meta.url),'utf8'));
  for(const brief of briefings.cases){
    const keys=[...brief.timeline.map(step=>step.key),...['title','purpose','review'].map(part=>`brief.${part}.${brief.variant}`)];
    for(const language of ['en','ko'])for(const key of keys){
      assert.ok(Object.hasOwn(messages[language],key),`${brief.case_id} ${language} ${key}`);
      assert.doesNotMatch(translate(language,key,{group:brief.group,object:brief.comparison_object,marker:brief.original_marker,seconds:30}),/\{\w+\}/);
    }
  }
  assert.equal(translate('en','workspace'),'Decision making workspace');
  assert.equal(translate('ko','workspace'),'의사결정 워크스페이스');
});
