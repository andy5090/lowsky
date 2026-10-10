export function testRunRequest(seedText = '', caseId) {
  const text = String(seedText).trim();
  const body = {action: 'start_test'};
  if (text) {
    if (!/^\d+$/.test(text) || !Number.isSafeInteger(Number(text)) || Number(text) > 2147483647) {
      throw new RangeError('Seed must be an integer between 0 and 2147483647.');
    }
    body.seed = Number(text);
  }
  if (caseId) body.case_id = caseId;
  return body;
}

export function playbackRequest(state, seedText = '') {
  if (state.playing) return {action: 'pause'};
  return state.test_run?.mode === 'seeded' ? {action: 'play'} : testRunRequest(seedText, state.case_id);
}

export function repeatTestRequest(state) {
  const seed = state.test_run?.seed;
  if (state.test_run?.mode !== 'seeded' || !Number.isInteger(seed)) return null;
  return testRunRequest(seed, state.case_id);
}
