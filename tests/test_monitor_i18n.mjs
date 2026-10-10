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
    for(const language of ['en','ko']){
      for(const field of ['name','summary','objective','composition','count_basis']){
        assert.ok(brief[field][language]?.length>0,`${brief.case_id} ${language} ${field}`);
      }
      for(const step of brief.timeline)assert.ok(step.text[language]?.length>0);
    }
  }
  assert.equal(translate('en','workspace'),'Decision making workspace');
  assert.equal(translate('ko','workspace'),'의사결정 워크스페이스');
});


test('human review decisions and all seven audit fields resolve in both languages', () => {
  const keys = ['event','evidence','assessment','uncertainty','decision','reason','reviewTime',
    'noted','needs_review','dismissed','saving','saved','failed','reset','synthetic','referenceNote'];
  for (const language of ['en','ko']) {
    for (const key of keys) assert.ok(Object.hasOwn(messages[language], `situation.${key}`), `${language} ${key}`);
    const counts = translate(language, 'situation.reviewCounts', {total:0,noted:0,needs_review:0,dismissed:0});
    assert.doesNotMatch(counts, /\{\w+\}/);
  }
  assert.match(translate('en','situation.synthetic'), /not measured detection or decision accuracy/);
  assert.match(translate('en','situation.referenceNote'), /not live sensor evidence/);
});


test('fixed phone deployments and last-reported health resolve in both languages', () => {
  const keys = ['early.deployment.community','early.deployment.fixed_phone','early.fixed_phone_acoustic',
    'early.healthAsReported','early.power.external','early.power.battery','early.power.unknown',
    'early.network.online','early.network.offline','early.network.unknown','early.stale','situation.linkedReviews'];
  for (const language of ['en','ko']) {
    for (const key of keys) assert.ok(Object.hasOwn(messages[language],key), `${language} ${key}`);
    const mount=translate(language,'early.mount',{id:'phone_01',height:3});
    assert.match(mount,/phone_01/);assert.match(mount,/3 m/);
  }
  assert.match(translate('en','early.areaNote'),/not drone positions or sensor range/);
});
