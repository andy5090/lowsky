import assert from 'node:assert/strict';
import {test} from 'node:test';
import {TACTICS_ENUMS,UNIT_KINDS,tacticsTarget,allocationDraft,allocationDraftValid,allocationCommand,placementSummary,proposalPositions,formationRows} from '../monitor/tactics.mjs';
import {messages} from '../monitor/i18n.mjs';

const options=[
 {effector_id:'interceptor_drone',status:'penalized',suitability:.55,reasons:['resource_preservation'],cost_tier:'low',inventory_remaining:12},
 {effector_id:'laser',status:'recommended',suitability:1,reasons:[],cost_tier:'per_shot_low',inventory_remaining:null},
 {effector_id:'autocannon',status:'rejected',suitability:0,reasons:['debris_over_facilities'],cost_tier:'low',inventory_remaining:null},
];
const target={object_id:'object_1',identification:{lean:'attack_leaning',sector:'N'},response:{posture:'engage_candidate',primary:'laser',options,constraints:[],allocation:null,version:'v1'}};
const state={run_id:'run1',tactics:{scope:'rule_based_training_advice',targets:[target],formation:{posture:'respond',teams:[]}}};
const withResponse=changes=>({...state,tactics:{...state.tactics,targets:[{...target,response:{...target.response,...changes}}]}});

test('cards come only from the rule-based training scope and a received target',()=>{
 assert.equal(tacticsTarget(state,'object_1'),target);
 assert.equal(tacticsTarget(state,'hidden'),null);
 assert.equal(tacticsTarget({...state,tactics:{...state.tactics,scope:'other'}},'object_1'),null);
 assert.equal(tacticsTarget(null,'object_1'),null);
});
test('allocation draft binds run, aircraft, effector and card version; rejected, allocated or offline choices are refused',()=>{
 assert.deepEqual(allocationDraft(state,'object_1','laser'),{run_id:'run1',object_id:'object_1',effector_id:'laser',version:'v1'});
 assert.ok(allocationDraft(state,'object_1','interceptor_drone'));
 assert.equal(allocationDraft(state,'object_1','autocannon'),null);
 assert.equal(allocationDraft(state,'object_1','unknown'),null);
 assert.equal(allocationDraft(state,'object_1','laser',false),null);
 assert.equal(allocationDraft(state,'hidden','laser'),null);
 assert.equal(allocationDraft(withResponse({allocation:{id:'a',effector_id:'laser'}}),'object_1','laser'),null);
 assert.ok(allocationDraft(withResponse({posture:'hold'}),'object_1','laser'));
});
test('a draft expires on run change, card version change, new rejection, recorded allocation or disconnect',()=>{
 const draft=allocationDraft(state,'object_1','laser');
 assert.equal(allocationDraftValid(state,draft),true);
 assert.equal(allocationDraftValid({...state,run_id:'run2'},draft),false);
 assert.equal(allocationDraftValid(withResponse({version:'v2'}),draft),false);
 assert.equal(allocationDraftValid(withResponse({options:options.map(row=>row.effector_id==='laser'?{...row,status:'rejected'}:row)}),draft),false);
 assert.equal(allocationDraftValid(withResponse({allocation:{id:'a'}}),draft),false);
 assert.equal(allocationDraftValid(state,draft,false),false);
 assert.equal(allocationDraftValid(state,null),false);
});
test('allocation command needs strict confirmation and bounds the optional alias and comment',()=>{
 const draft=allocationDraft(state,'object_1','laser');
 assert.equal(allocationCommand(state,draft),null);
 assert.equal(allocationCommand(state,draft,{confirmed:'true'}),null);
 assert.equal(allocationCommand(state,draft,{confirmed:true,connected:false}),null);
 assert.deepEqual(allocationCommand(state,draft,{confirmed:true}),{action:'tactics_allocate',run_id:'run1',object_id:'object_1',effector_id:'laser',version:'v1',confirm:true});
 const body=allocationCommand(state,draft,{confirmed:true,reviewer:`  ${'r'.repeat(90)}  `,comment:` ${'c'.repeat(1200)} `});
 assert.equal(body.reviewer.length,80);assert.equal(body.comment.length,1000);
 const trimmed=allocationCommand(state,draft,{confirmed:true,reviewer:' Sam ',comment:'  note  '});
 assert.equal(trimmed.reviewer,'Sam');assert.equal(trimmed.comment,'note');
 const blank=allocationCommand(state,draft,{confirmed:true,reviewer:'   ',comment:''});
 assert.equal('reviewer' in blank,false);assert.equal('comment' in blank,false);
 assert.equal(allocationCommand(withResponse({version:'v2'}),draft,{confirmed:true}),null);
});
test('placement summary counts object-shaped proposal positions and placed units against per-kind budgets',()=>{
 const unit_kinds=[{id:'infantry',budget:12,display_range_m:0},{id:'radar',budget:2,display_range_m:5000},{id:'detection_phone',budget:10,display_range_m:1500},{id:'effector_team',budget:4,display_range_m:2500}];
 const positions=[{kind:'radar',position:[1,0,2]},{kind:'radar',position:[3,0,4]},{kind:'infantry',position:[5,0,6]},{kind:'effector_team',position:[NaN,0,0]}];
 const exercise={scope:'scripted_training',unit_kinds,units:[{id:'radar_1',kind:'radar'}],
  unit_proposal:{id:'p',status:'pending',positions,coverage:{radar:.8,detection_phone:.5,effector_team:1,infantry:.25},threat_basis:'received_picture'}};
 const summary=placementSummary({exercise});
 assert.equal(summary.status,'pending');assert.equal(summary.proposal_id,'p');assert.equal(summary.threat_basis,'received_picture');
 assert.deepEqual(summary.kinds.map(row=>row.kind),UNIT_KINDS);
 const radar=summary.kinds.find(row=>row.kind==='radar');
 assert.deepEqual({proposed:radar.proposed,placed:radar.placed,budget:radar.budget,remaining:radar.remaining,range_m:radar.range_m},{proposed:2,placed:1,budget:2,remaining:1,range_m:5000});
 assert.equal(summary.kinds.find(row=>row.kind==='effector_team').proposed,0);
 assert.equal(summary.coverage.radar,.8);
 assert.equal(placementSummary({exercise:{...exercise,scope:'other'}}),null);
 assert.equal(placementSummary({exercise:{...exercise,unit_proposal:null}}),null);
 assert.deepEqual(proposalPositions({positions:[[1,0,2]]}),[{kind:'infantry',position:[1,0,2]}]);
 const fallback=placementSummary({exercise:{...exercise,unit_kinds:undefined}});
 assert.deepEqual(fallback.kinds.map(row=>row.budget),[null,null,null,null]);
});
test('formation rows list teams in kind order and summarize long tasking',()=>{
 const tasking=Array.from({length:7},(_,i)=>({object_id:`object_${i}`,posture:i<5?'observe_preserve':'hold',primary:null}));
 const formation={posture:'observe',teams:[
  {id:'infantry:observation_post:N',kind:'infantry',role:'observation_post',sector:'N',unit_ids:['infantry_1'],tasking:[{object_id:'object_1',lean:'decoy_leaning'}]},
  {id:'effector_team:response:NE',kind:'effector_team',role:'response',sector:'NE',unit_ids:['effector_team_1','effector_team_2'],tasking},
  {id:'radar:surveillance:E',kind:'radar',role:'surveillance',sector:'E',unit_ids:['radar_1'],tasking:[]},
 ]};
 const rows=formationRows({tactics:{scope:'rule_based_training_advice',formation}});
 assert.deepEqual(rows.map(row=>row.kind),['infantry','radar','effector_team']);
 const team=rows[2];
 assert.equal(team.unit_count,2);assert.equal(team.tasking_count,7);assert.equal(team.tasking.length,5);
 assert.deepEqual(team.counts,{observe_preserve:5,hold:2});
 assert.deepEqual(rows[0].counts,{decoy_leaning:1});
 assert.deepEqual(formationRows({tactics:{scope:'other',formation}}),[]);
 assert.deepEqual(formationRows(null),[]);
});
test('every tactics and placement label exists in English and Korean, including each server enumeration',()=>{
 for(const prefix of ['tactics.','units.']) {
  const en=Object.keys(messages.en).filter(key=>key.startsWith(prefix)).sort();
  const ko=Object.keys(messages.ko).filter(key=>key.startsWith(prefix)).sort();
  assert.ok(en.length>10,prefix);assert.deepEqual(en,ko,prefix);
 }
 const groups={lean:'lean',profile:'profile',verification:'verification',posture:'posture',formation:'formation',status:'status',cue:'cue',uncertainty:'uncertainty',reason:'reason',constraint:'constraint',effector:'effector'};
 for(const lang of ['en','ko']) {
  for(const [group,prefix] of Object.entries(groups))for(const value of TACTICS_ENUMS[group])assert.ok(messages[lang][`tactics.${prefix}.${value}`],`${lang} tactics.${prefix}.${value}`);
  for(const kind of UNIT_KINDS)assert.ok(messages[lang][`units.kind.${kind}`],kind);
  for(const role of ['surveillance','picket','response','observation_post','quick_reaction','patrol'])assert.ok(messages[lang][`units.role.${role}`],role);
 }
 assert.equal(messages.ko['tactics.title'],'표적 식별·대응 권고');
 assert.equal(messages.ko['units.title'],'병력·센서 배치 최적화');
 assert.equal(messages.ko['tactics.lean.decoy_leaning'],'미끼 성향');
});
