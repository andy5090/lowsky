// Agent provider settings. The browser never receives a saved key; it only sends a new one.
export const SETTINGS_PROVIDERS = ['openai', 'anthropic', 'rules'];
export const CUSTOM_MODEL = '__custom__';

export function providerView(view, provider) {
  return view?.providers?.[provider] || null;
}

// Preset IDs first, then saved/default IDs, then models loaded from the provider, then the custom entry.
export function modelOptions(view, provider, fetched = []) {
  const info = providerView(view, provider);
  if (!info) return [];
  const rows = (info.presets || []).map(preset => ({id: preset.id, label: preset.label}));
  for (const id of [info.saved_model, info.default_model, ...(Array.isArray(fetched) ? fetched : [])]) {
    if (typeof id === 'string' && MODEL_PATTERN.test(id) && !id.includes(':') && !rows.some(row => row.id === id))
      rows.push({id, label: null, fetched: fetched.includes(id)});
  }
  return [...rows, {id: CUSTOM_MODEL, label: null}];
}

// Ask the provider which models this key can use; works with the typed key or a saved/environment key.
export function modelsCommand(view, draft) {
  if (!['openai', 'anthropic'].includes(draft?.provider)) return null;
  const key = (draft.api_key || '').trim();
  if (key && (!KEY_PATTERN.test(key) || (draft.provider === 'openai' && key.startsWith('sk-ant-')))) return null;
  if (!key && !providerView(view, draft.provider)?.key_set) return null;
  return {action: 'models', provider: draft.provider, ...(key ? {api_key: key} : {})};
}

export function initialDraft(view) {
  const provider = SETTINGS_PROVIDERS.includes(view?.saved_provider) ? view.saved_provider
    : SETTINGS_PROVIDERS.includes(view?.provider) ? view.provider : 'openai';
  const info = providerView(view, provider);
  return {provider, model: info?.saved_model || info?.default_model || '', custom: '', api_key: '', clear_key: false};
}

export function draftModel(draft) {
  return draft.model === CUSTOM_MODEL ? draft.custom.trim() : draft.model;
}

const MODEL_PATTERN = /^[\x21-\x7e]{1,120}$/;
const KEY_PATTERN = /^[\x21-\x7e]{1,400}$/;

export function draftProblem(view, draft) {
  if (!SETTINGS_PROVIDERS.includes(draft?.provider)) return 'settings.problem.provider';
  if (draft.provider === 'rules') return null;
  const model = draftModel(draft);
  if (!MODEL_PATTERN.test(model) || model.includes(':')) return 'settings.problem.model';
  const key = draft.api_key.trim();
  if (key && !KEY_PATTERN.test(key)) return 'settings.problem.key';
  // Avoid sending an Anthropic key to OpenAI's endpoint by mistake.
  if (key && draft.provider === 'openai' && key.startsWith('sk-ant-')) return 'settings.problem.wrongProvider';
  if (!key && (draft.clear_key || !providerView(view, draft.provider)?.key_set)) return 'settings.problem.noKey';
  return null;
}

// Save requires a key for LLM providers unless one is already saved or present in the environment.
export function saveCommand(view, draft) {
  if (draftProblem(view, draft)) return null;
  if (draft.provider === 'rules') return {action: 'save', provider: 'rules'};
  const key = draft.api_key.trim();
  return {action: 'save', provider: draft.provider, model: draftModel(draft),
    ...(key ? {api_key: key} : {}), ...(draft.clear_key && !key ? {clear_key: true} : {})};
}

export function removeKeyCommand(view, draft) {
  const info = providerView(view, draft?.provider);
  if (!info || info.key_source !== 'settings') return null;
  return {action: 'remove_key', provider: draft.provider};
}

export function testCommand(view, draft) {
  if (draft?.provider === 'rules') return null;
  const problem = draftProblem(view, draft);
  if (problem && problem !== 'settings.problem.noKey') return null;
  const key = draft.api_key.trim();
  if (!key && !providerView(view, draft.provider)?.key_set) return null;
  return {action: 'test', provider: draft.provider, model: draftModel(draft), ...(key ? {api_key: key} : {})};
}

export function keyStatus(view, provider) {
  const info = providerView(view, provider);
  if (!info) return {key: 'settings.key.none'};
  if (!info.key_set) return {key: 'settings.key.none'};
  return {key: info.key_source === 'settings' ? 'settings.key.saved' : 'settings.key.environment', hint: info.key_hint || ''};
}
