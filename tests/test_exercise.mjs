import assert from 'node:assert/strict';
import {test} from 'node:test';
import {exerciseConfirmation, exerciseMapAssets} from '../monitor/exercise.mjs';
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

test('map shows only selected or published affected facilities and clears on reset',()=>{
 const assets=[{id:'a',position:[1,2,3],status:'available'},
   {id:'b',position:[4,5,6],status:'unavailable'},
   {id:'c',position:[7,8,9],status:'restricted'},
   {id:'d',position:[0,0,0],status:'available'}];
 const selection={asset_id:'a',branch_id:'hold',status:'pending',effective_at_ms:5000};
 const current={exercise:{scope:'scripted_training',assets,selection,branches:[{id:'hold'}]}};
 const rows=exerciseMapAssets(current);
 assert.deepEqual(rows.map(row=>row.id),['a','b','c']);
 assert.equal(rows[0].selection.status,'pending');
 assert.equal(rows[0].branch.id,'hold');
 assert.equal(rows[1].selection,null);
 assert.deepEqual(exerciseMapAssets({exercise:{...current.exercise,selection:null,assets:assets.map(asset=>({...asset,status:'available'}))}}),[]);
 assert.deepEqual(exerciseMapAssets({exercise:{...current.exercise,scope:'unknown'}}),[]);
 assert.deepEqual(exerciseMapAssets({exercise:{...current.exercise,selection:null,assets:[{id:'invalid',status:'unavailable',position:[NaN,0,0]}]}}),[]);
});

test('unit placement requires manual choice, explicit confirmation, a current run and bounded finite coordinates',async()=>{
  const {exerciseUnitCommand}=await import('../monitor/exercise.mjs');
  const current={run_id:'run1',exercise:{scope:'scripted_training',unit_proposal:{id:'p1',status:'manual'},units:[]}};
  const place={action:'exercise_place_unit',run_id:'run1',position:[10,0,-20]};
  assert.equal(exerciseUnitCommand(current,place),null);
  assert.deepEqual(exerciseUnitCommand(current,place,true),{...place,confirm:true});
  for(const changes of [{run_id:'stale'},{position:[1,2,3]},{position:[Infinity,0,0]},{position:[NaN,0,0]},{position:[0,0]},{position:[5000.01,0,0]},{position:[0,0,-5001]},{unit_id:'missing'},{action:'unknown'}])assert.equal(exerciseUnitCommand(current,{...place,...changes},true),null);
  assert.ok(exerciseUnitCommand(current,{...place,position:[-5000,0,5000]},true));
  for(const status of ['pending','accepted'])assert.equal(exerciseUnitCommand({...current,exercise:{...current.exercise,unit_proposal:{id:'p1',status}}},place,true),null);
});
test('proposal confirmation applies by id only; no response or manual selection applies positions implicitly',async()=>{
  const {exerciseUnitCommand}=await import('../monitor/exercise.mjs');
  const current={run_id:'r',exercise:{scope:'scripted_training',unit_proposal:{id:'p',status:'pending',positions:[[1,0,2]]},units:[]}};
  const accept={action:'exercise_accept_units',run_id:'r',proposal_id:'p'};
  assert.equal(exerciseUnitCommand(current,accept),null);
  assert.deepEqual(exerciseUnitCommand(current,accept,true),{...accept,confirm:true});
  assert.equal(exerciseUnitCommand(current,{...accept,proposal_id:'stale'},true),null);
  assert.equal(exerciseUnitCommand(current,{...accept,run_id:'stale'},true),null);
  const manual={...accept,action:'exercise_manual_units'};
  assert.deepEqual(exerciseUnitCommand(current,manual,true),{...manual,confirm:true});
  const accepted={...current,exercise:{...current.exercise,unit_proposal:{...current.exercise.unit_proposal,status:'accepted'}}};
  assert.equal(exerciseUnitCommand(accepted,accept,true),null);
  assert.ok(exerciseUnitCommand(accepted,manual,true));
});
test('unit limit blocks additions while preserving move/delete and reset invalidates old unit ids',async()=>{
  const {exerciseUnitCommand}=await import('../monitor/exercise.mjs');
  const current={run_id:'r',exercise:{scope:'scripted_training',unit_proposal:{status:'manual'},units:Array.from({length:12},(_,i)=>({id:`u${i}`}))}};
  const place={action:'exercise_place_unit',run_id:'r',position:[0,0,0]};
  assert.equal(exerciseUnitCommand(current,place,true),null);
  assert.ok(exerciseUnitCommand(current,{...place,unit_id:'u0'},true));
  const remove={action:'exercise_remove_unit',run_id:'r',unit_id:'u0'};
  assert.deepEqual(exerciseUnitCommand(current,remove,true),{...remove,confirm:true});
  assert.equal(exerciseUnitCommand(current,{...remove,unit_id:'missing'},true),null);
  assert.equal(exerciseUnitCommand({...current,run_id:'new'},remove,true),null);
  assert.equal(exerciseUnitCommand({...current,exercise:{...current.exercise,units:[]}},remove,true),null);
});
test('per-kind budgets from the server catalog limit additions by kind and keep moves available',async()=>{
  const {exerciseUnitCommand,unitBudget}=await import('../monitor/exercise.mjs');
  const unit_kinds=[{id:'infantry',budget:12},{id:'radar',budget:2},{id:'detection_phone',budget:10},{id:'effector_team',budget:4}];
  const units=[{id:'radar_1',kind:'radar'},{id:'radar_2',kind:'radar'},{id:'infantry_1',kind:'infantry'}];
  const current={run_id:'r',exercise:{scope:'scripted_training',unit_proposal:{id:'p',status:'manual'},units,unit_kinds}};
  const place={action:'exercise_place_unit',run_id:'r',position:[100,0,-200]};
  assert.deepEqual(unitBudget(current,'radar'),{kind:'radar',budget:2,used:2,remaining:0});
  assert.equal(unitBudget(current,'infantry').remaining,11);
  assert.equal(unitBudget(current,'tank'),null);
  assert.equal(exerciseUnitCommand(current,{...place,kind:'radar'},true),null);
  assert.equal(exerciseUnitCommand(current,{...place,kind:'tank'},true),null);
  assert.deepEqual(exerciseUnitCommand(current,{...place,kind:'detection_phone'},true),{...place,kind:'detection_phone',confirm:true});
  assert.deepEqual(exerciseUnitCommand(current,place,true),{...place,confirm:true});
  const move=exerciseUnitCommand(current,{...place,kind:'radar',unit_id:'radar_1'},true);
  assert.deepEqual(move,{...place,unit_id:'radar_1',confirm:true});
  const full={...current,exercise:{...current.exercise,units:[...units,...Array.from({length:11},(_,i)=>({id:`infantry_${i+2}`,kind:'infantry'}))]}};
  assert.equal(exerciseUnitCommand(full,{...place,kind:'infantry'},true),null);
  assert.ok(exerciseUnitCommand(full,{...place,kind:'effector_team'},true));
  for(const changes of [{position:[1,2,3]},{position:[5001,0,0]},{position:[NaN,0,0]},{run_id:'old'}])assert.equal(exerciseUnitCommand(current,{...place,kind:'effector_team',...changes},true),null);
});
test('re-optimization needs only the current run and explicit confirmation, in any proposal status',async()=>{
  const {exerciseUnitCommand}=await import('../monitor/exercise.mjs');
  const draft={action:'exercise_reoptimize_units',run_id:'r'};
  for(const status of ['pending','accepted','manual']) {
    const current={run_id:'r',exercise:{scope:'scripted_training',unit_proposal:{id:'p',status},units:[]}};
    assert.equal(exerciseUnitCommand(current,draft),null);
    assert.equal(exerciseUnitCommand(current,draft,'yes'),null);
    assert.deepEqual(exerciseUnitCommand(current,draft,true),{action:'exercise_reoptimize_units',run_id:'r',confirm:true});
    assert.equal(exerciseUnitCommand(current,{...draft,run_id:'stale'},true),null);
    assert.equal(exerciseUnitCommand({...current,exercise:{...current.exercise,scope:'other'}},draft,true),null);
  }
});
