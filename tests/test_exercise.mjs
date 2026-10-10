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

test('a queued branch is revalidated against its actual delay, current run, and current eligibility',()=>{
 const initial={...state,at_ms:1000,duration_ms:10000,exercise:{...state.exercise,branches:[{id:'hold',delay_ms:5000}]}};
 assert.ok(exerciseConfirmation(initial,draft,true));
 assert.equal(exerciseConfirmation({...initial,at_ms:5000},draft,true),null);
 assert.equal(exerciseConfirmation({...initial,at_ms:4999},draft,true)?.action,'exercise_branch');
 assert.equal(exerciseConfirmation({...initial,run_id:'changed'},draft,true),null);
 assert.equal(exerciseConfirmation({...initial,exercise:{...initial.exercise,eligible_objects:[]}},draft,true),null);
 assert.equal(exerciseConfirmation({...initial,exercise:{...initial.exercise,branches:[{id:'hold',delay_ms:9000}]}},draft,true),null);
});

test('scene status exposes only received actors and already published outcomes, excluding future schedules',async()=>{
 const {exerciseMissionRows}=await import('../monitor/exercise.mjs');
 const mission={id:'m1',object_id:'observed1',kind:'impact_vignette',asset_id:'facility1',phase:'approach',scope:'scripted_training',synthetic:true,phase_start_ms:1000,phase_end_ms:90000,progress:.5,outcome:'unresolved',result_at_ms:90000};
 const current={...state,at_ms:10000,tracks:[{object_id:'observed1',last_known:false}],exercise:{...state.exercise,missions:[mission,{...mission,id:'hidden',object_id:'hidden1'}]}};
 const rows=exerciseMissionRows(current);
 assert.equal(rows.length,1);assert.equal(rows[0].phase,'approach');assert.equal(rows[0].outcome,null);assert.equal(rows[0].result_at_ms,null);
 assert.equal(rows[0].phase_end_ms,undefined);assert.equal(rows[0].progress,undefined);
 assert.deepEqual(exerciseMissionRows({...current,tracks:[]}),[]);
 assert.deepEqual(exerciseMissionRows({...current,tracks:[{object_id:'observed1',last_known:true}]}),[]);
 const published={...current,at_ms:90000,tracks:[{object_id:'observed1',last_known:true}]};
 assert.equal(exerciseMissionRows(published)[0].outcome,'unresolved');
 assert.deepEqual(exerciseMissionRows({...current,exercise:{...current.exercise,missions:[{...mission,synthetic:false}]}}),[]);
});

test('an observed authored scene keeps its predefined facility while other actors remain selectable',()=>{
 const scoped={...state,at_ms:1000,tracks:[{object_id:'observed1',last_known:false}],exercise:{...state.exercise,assets:[{id:'facility1'},{id:'other'}],missions:[{id:'m1',object_id:'observed1',kind:'drop_vignette',asset_id:'facility1',phase:'approach',scope:'scripted_training',synthetic:true,result_at_ms:null}]}};
 assert.ok(exerciseConfirmation(scoped,draft,true));
 assert.equal(exerciseConfirmation(scoped,{...draft,asset_id:'other'},true),null);
 assert.ok(exerciseConfirmation({...scoped,exercise:{...scoped.exercise,missions:[]}},{...draft,asset_id:'other'},true));
});
