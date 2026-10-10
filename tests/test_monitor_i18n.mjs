import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {test} from 'node:test';
import {messages, normalizeLanguage, translate, readLanguage, saveLanguage, triggerValue, triggerSubject, localizedValue, STORAGE_KEY} from '../monitor/i18n.mjs';

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

test('training provenance is explicit while routine controls use concise scenario copy', () => {
  assert.match(translate('en', 'syntheticBanner'), /TRAINING.*Generated.*No live sensor feed/);
  assert.match(translate('ko', 'syntheticBanner'), /훈련 환경.*생성된.*실시간 센서 연동 없음/);
  const routineKeys = ['scenarioSettings', 'playbackState', 'scenarioPlayback', 'scenarioTime', 'seekLabel',
    'priority.time', 'dashboard.saving', 'dashboard.scope', 'exercise.kind.impact_vignette', 'exercise.kind.drop_vignette'];
  for (const language of ['en', 'ko']) {
    for (const key of routineKeys) assert.doesNotMatch(translate(language, key), /simulation|fictional|시뮬레이션|가상/i, key);
    assert.match(translate(language, 'notify.notificationTitle', {count: 1}), /TRAINING|훈련/);
  }
});

test('scene controls avoid implementation jargon and seeded scope describes appearance-only variation', () => {
  for (const language of ['en', 'ko']) {
    for (const key of ['title', 'choose', 'confirm', 'predefined', 'outcome.unresolved', 'outcome.partial', 'outcome.prevented']) {
      assert.doesNotMatch(translate(language, `exercise.${key}`), /scripted|vignette|predefined|분기|사전 설정|미리 정해진/i);
    }
    for (const key of ['mapSelected', 'mapPending', 'open', 'facilities']) {
      assert.ok(Object.hasOwn(messages[language], `exercise.${key}`));
    }
  }
  assert.match(translate('en', 'exercise.scope'), /predefined.*not predictions of defense effectiveness/);
  assert.match(translate('en', 'test.scope'), /model appearances.*Roles, performance and routes stay fixed/);
  assert.match(translate('ko', 'test.scope'), /모델 외형.*역할·성능·비행 경로는 바뀌지 않습니다/);
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
  for (const [, key] of html.matchAll(/data-i18n(?:-aria-label|-title|-placeholder)?="([^"]+)"/g)) {
    assert.ok(Object.hasOwn(messages.en, key), key);
    assert.ok(Object.hasOwn(messages.ko, key), key);
  }
  assert.match(html, /<html lang="en">/);
  assert.match(html, /id="language-select"/);
});

test('visible static English copy and accessibility attributes cannot bypass localization', () => {
  const html = readFileSync(new URL('../monitor/index.html', import.meta.url), 'utf8');
  const stack = [];
  const voidTags = new Set(['area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr']);
  const unchangedNames = new Set(['LOW SKY','EN','OpenStreetMap']);
  for (const token of html.match(/<!--[\s\S]*?-->|<[^>]+>|[^<]+/g)) {
    if (token.startsWith('<!')) continue;
    if (token.startsWith('</')) { stack.pop(); continue; }
    if (token.startsWith('<')) {
      const tag = token.match(/^<([\w-]+)/)?.[1];
      for (const [,attribute,value] of token.matchAll(/\b(aria-label|title|placeholder)="([^"]*)"/g)) {
        if (!/[A-Za-z]/.test(value) || ['F6','F11'].includes(value)) continue;
        assert.ok(token.includes(`data-i18n-${attribute}=`), `Untranslated ${attribute}: ${value}`);
      }
      if (!voidTags.has(tag) && !token.endsWith('/>')) stack.push({tag,translated:/\bdata-i18n=/.test(token)});
      continue;
    }
    const text = token.trim();
    if (!/[A-Za-z]/.test(text) || stack.some(node => node.translated || ['script','style'].includes(node.tag))) continue;
    assert.ok(unchangedNames.has(text), `Untranslated static text: ${text}`);
  }
});

test('dynamic render copy uses defined keys and explicit semantic translations', () => {
  const app = readFileSync(new URL('../monitor/app.js', import.meta.url), 'utf8');
  for (const [,key] of app.matchAll(/\bt\(['"]([^'"]+)['"]/g)) {
    assert.ok(Object.hasOwn(messages.en,key), key);
    assert.ok(Object.hasOwn(messages.ko,key), key);
  }
  for (const value of [null,true,false,'single','corroborated','conflicting','no_current_positive','requested','online','offline','stale','unknown','waiting','lost']) {
    assert.match(triggerValue('ko',value), /[가-힣]/, String(value));
    assert.doesNotMatch(triggerValue('en',value), /[가-힣]/, String(value));
  }
  for (const value of ['received_tracks','received_situation','scripted_review']) assert.match(triggerSubject('ko',value), /[가-힣]/);
  assert.equal(triggerValue('ko',3),'3');
  assert.equal(triggerValue('ko','custom evidence text'),'custom evidence text');
  assert.equal(triggerSubject('ko','remote_reference'),'remote_reference');
  assert.equal(translate('ko','positions.marker',{id:'object_01'}),'가상 object_01');
  assert.match(app,/triggerValue\(language,trigger\.previous\)/);
  assert.match(app,/triggerSubject\(language,trigger\.subject\)/);
  assert.match(app,/t\('positions\.marker',\{id:drone\.object_id\}\)/);
  assert.match(app,/source\.title_ko \|\| source\.title/);
  assert.match(app,/stations\.find\(station=>station\.id===frame\.id\)\?\.label/);
});

test('bilingual server fields resolve without translating identifiers or authored original text', () => {
  assert.equal(localizedValue('ko',{en:'Radar A',ko:'레이더 A'}),'레이더 A');
  assert.equal(localizedValue('en',{en:'Radar A',ko:'레이더 A'}),'Radar A');
  assert.equal(localizedValue('ko',{en:'Original citation'}),'Original citation');
  assert.equal(localizedValue('ko','Operator entered this'),'Operator entered this');
  assert.equal(localizedValue('ko',null),'');
  assert.match(translate('ko','report.original',{language:translate('ko','report.language.en')}),/평가 원문.*영어/);
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
