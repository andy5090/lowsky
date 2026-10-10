import assert from 'node:assert/strict';
import {test} from 'node:test';
import {exerciseConfirmation} from '../monitor/exercise.mjs';
import {translate} from '../monitor/i18n.mjs';

const state={run_id:'run1',exercise:{scope:'scripted_training',eligible_objects:['observed1'],assets:[{id:'facility1'}],branches:[{id:'hold'}],selection:null}};
const draft={run_id:'run1',object_id:'observed1',asset_id:'facility1',branch_id:'hold'};
test('training branch requires explicit confirmation and current received object',()=>{
  assert.equal(exerciseConfirmation(state,draft),null);
  assert.equal(exerciseConfirmation(state,draft,'yes'),null);
  assert.equal(exerciseConfirmation(state,null,true),null);
  assert.deepEqual(exerciseConfirmation(state,draft,true),{action:'exercise_branch',...draft,confirm:true});
  for(const changed of [{run_id:'old'},{object_id:'hidden1'},{asset_id:'unknown'},{branch_id:'unknown'}]) {
    assert.equal(exerciseConfirmation(state,{...draft,...changed},true),null);
  }
  assert.equal(exerciseConfirmation({...state,exercise:{...state.exercise,eligible_objects:[]}},draft,true),null);
  assert.equal(exerciseConfirmation({...state,exercise:{...state.exercise,selection:{status:'pending'}}},draft,true),null);
  assert.equal(exerciseConfirmation({...state,exercise:{...state.exercise,scope:'other'}},draft,true),null);
});
test('branch wording and scenario counts remain plain and bilingual',()=>{
  for(const lang of ['en','ko']) {
    for(const key of ['exercise.title','exercise.predefined','exercise.confirm','exercise.pending','exercise.applied','exercise.status.available','exercise.status.restricted','exercise.status.unavailable','exercise.motion.continue','exercise.motion.hold','exercise.motion.withdraw']) assert.notEqual(translate(lang,key),key);
    const counts=translate(lang,'brief.counts',{total:12,received:3,current:2});
    assert.ok(counts.includes('12') && counts.includes('3') && counts.includes('2'));
  }
});
