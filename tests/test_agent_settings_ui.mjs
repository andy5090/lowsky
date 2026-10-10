import assert from 'node:assert/strict';
import {test} from 'node:test';
import {CUSTOM_MODEL, modelOptions, initialDraft, draftProblem, saveCommand, removeKeyCommand, testCommand, keyStatus} from '../monitor/agent_settings.mjs';
import {messages} from '../monitor/i18n.mjs';

const view = {saved_provider:null, provider:'openai', providers:{
  openai:{key_set:false, key_source:null, key_hint:null, saved_model:null, default_model:'gpt-6.1-sol', presets:[{id:'gpt-6.1-sol', label:{en:'GPT', ko:'GPT'}}]},
  anthropic:{key_set:true, key_source:'settings', key_hint:'…CRET', saved_model:'claude-sonnet-5', default_model:'claude-opus-5',
    presets:[{id:'claude-opus-5', label:{en:'Opus', ko:'Opus'}}, {id:'claude-sonnet-5', label:{en:'Sonnet', ko:'Sonnet'}}]}}};

test('model list keeps presets, adds saved/default IDs once and ends with a custom entry', () => {
  assert.deepEqual(modelOptions(view,'anthropic').map(row => row.id), ['claude-opus-5','claude-sonnet-5',CUSTOM_MODEL]);
  const saved = {...view, providers:{...view.providers, openai:{...view.providers.openai, saved_model:'gpt-custom'}}};
  assert.deepEqual(modelOptions(saved,'openai').map(row => row.id), ['gpt-6.1-sol','gpt-custom',CUSTOM_MODEL]);
  assert.deepEqual(modelOptions(view,'rules'), []);
});

test('save needs a key unless one is already available, and never sends an empty key', () => {
  const openai = initialDraft(view);
  assert.equal(openai.provider,'openai');
  assert.equal(draftProblem(view,openai),'settings.problem.noKey');
  assert.equal(saveCommand(view,openai),null);
  assert.equal(testCommand(view,openai),null);
  assert.deepEqual(saveCommand(view,{...openai, api_key:'  sk-test-1234  '}),{action:'save',provider:'openai',model:'gpt-6.1-sol',api_key:'sk-test-1234'});
  const claude = {...openai, provider:'anthropic', model:'claude-sonnet-5'};
  assert.deepEqual(saveCommand(view,claude),{action:'save',provider:'anthropic',model:'claude-sonnet-5'});
  assert.deepEqual(testCommand(view,claude),{action:'test',provider:'anthropic',model:'claude-sonnet-5'});
  assert.deepEqual(saveCommand(view,{...openai, provider:'rules'}),{action:'save',provider:'rules'});
});

test('custom model IDs are validated and a provider prefix or spaces are rejected', () => {
  const draft = {provider:'anthropic', model:CUSTOM_MODEL, custom:' claude-opus-4-8 ', api_key:'', clear_key:false};
  assert.equal(saveCommand(view,draft).model,'claude-opus-4-8');
  for (const custom of ['','anthropic:claude-opus-5','has space','x'.repeat(121)]) assert.equal(saveCommand(view,{...draft,custom}),null,custom);
  assert.equal(draftProblem(view,{...draft, custom:'claude-opus-5', api_key:'bad key'}),'settings.problem.key');
  const openai = {provider:'openai', model:'gpt-6.1-sol', custom:'', api_key:'sk-ant-pasted-in-wrong-slot', clear_key:false};
  assert.equal(draftProblem(view,openai),'settings.problem.wrongProvider');
  assert.equal(saveCommand(view,openai),null);
  assert.equal(testCommand(view,openai),null, 'An Anthropic key is never sent to OpenAI');
});

test('remove only applies to keys saved here, and status shows only the hint', () => {
  assert.equal(removeKeyCommand(view,{provider:'openai', model:'gpt-6.1-sol', custom:''}),null);
  assert.deepEqual(removeKeyCommand(view,{provider:'anthropic', model:'claude-sonnet-5', custom:''}),
    {action:'remove_key',provider:'anthropic'}, 'Removing a key never changes the active provider');
  assert.deepEqual(keyStatus(view,'anthropic'),{key:'settings.key.saved',hint:'…CRET'});
  assert.deepEqual(keyStatus(view,'openai'),{key:'settings.key.none'});
});

test('every settings label exists in English and Korean, including all connection-test results', () => {
  for (const key of Object.keys(messages.en).filter(key => key.startsWith('settings.'))) assert.ok(messages.ko[key], key);
  for (const code of ['ok','missing_api_key','missing_dependencies','invalid_key','permission_denied','model_not_found','rate_limited','network','provider_error'])
    assert.ok(messages.en[`settings.test.${code}`] && messages.ko[`settings.test.${code}`], code);
  for (const error of ['missing_api_key','missing_dependencies','invalid_model','unsupported_provider']) assert.ok(messages.ko[`agent.${error}`], error);
});
