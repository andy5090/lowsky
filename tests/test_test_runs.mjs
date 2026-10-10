import test from 'node:test';
import assert from 'node:assert/strict';
import {testRunRequest, playbackRequest, repeatTestRequest} from '../monitor/test_runs.mjs';

test('blank seed delegates randomness to server; zero and max are reproducible seeds', () => {
  assert.deepEqual(testRunRequest(' ', 'case_001'), {action:'start_test',case_id:'case_001'});
  assert.equal(testRunRequest('0').seed, 0);
  assert.equal(testRunRequest('2147483647').seed, 2147483647);
  for (const value of ['-1', '1.5', '1e3', '2147483648', 'NaN', '9007199254740993']) {
    assert.throws(() => testRunRequest(value), RangeError);
  }
});

test('initial fixture starts a test, while pause/resume retain current inputs', () => {
  const fixture = {case_id:'case_001',playing:false,test_run:{mode:'fixture',seed:null}};
  assert.deepEqual(playbackRequest(fixture, '42'), {action:'start_test',seed:42,case_id:'case_001'});
  assert.deepEqual(playbackRequest({...fixture,playing:true}, 'bad'), {action:'pause'});
  assert.deepEqual(playbackRequest({...fixture,test_run:{mode:'seeded',seed:42}}, '99'), {action:'play'});
});

test('repeat uses the current server seed and template, never the edited input', () => {
  assert.equal(repeatTestRequest({test_run:{mode:'fixture',seed:null}}), null);
  assert.deepEqual(repeatTestRequest({case_id:'case_003',test_run:{mode:'seeded',seed:0}}), {action:'start_test',seed:0,case_id:'case_003'});
});
