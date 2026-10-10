import assert from 'node:assert/strict';
import {test} from 'node:test';
import {DASHBOARD_ACTIONS,DISMISS_REASONS,dashboardCard,dashboardDraft,dashboardDraftValid,dashboardConfirmation} from '../monitor/dashboard.mjs';
import {messages} from '../monitor/i18n.mjs';
const card={object_id:'received-1',status:'observed',version:'v1',remaining_ms:60000,actions:DASHBOARD_ACTIONS.map(id=>({id,enabled:true}))};
const state={run_id:'run1',dashboard:{scope:'simulation_review',cards:[card]}};
const draft=dashboardDraft(state,'received-1','continue_observe');
const change=overrides=>({...state,dashboard:{...state.dashboard,cards:[{...card,...overrides}]}});
test('dashboard only selects a received card and an enabled explicit action',()=>{
 assert.equal(dashboardCard(state,'hidden-1'),null);
 assert.equal(dashboardDraft(state,'hidden-1','continue_observe'),null);
 assert.equal(dashboardDraft(state,'received-1','fire'),null);
 assert.equal(dashboardDraft(state,'received-1','continue_observe',false),null);
 assert.equal(dashboardDraft(change({actions:[{id:'continue_observe',enabled:false}]}),'received-1','continue_observe'),null);
 assert.equal(dashboardConfirmation(state,draft),null);
 assert.deepEqual(dashboardConfirmation(state,draft,{confirmed:true}),{action:'dashboard_action',...draft,confirm:true});
});
test('draft closes on run, material version, stale, deadline, closed, disconnect changes',()=>{
 assert.equal(dashboardDraftValid({...state,run_id:'run2'},draft),false);
 for(const changed of [{version:'v2'},{status:'stale'},{status:'closed'},{remaining_ms:0}]) assert.equal(dashboardDraftValid(change(changed),draft),false);
 assert.equal(dashboardDraftValid(state,draft,false),false);
 assert.equal(dashboardDraftValid(change({remaining_ms:40000,evidence_ids:['new-receipt']}),draft),true);
 assert.equal(dashboardConfirmation(state,draft,{confirmed:'true'}),null);
});
test('dismissal requires a suggestion and retains opinion rather than verified identity',()=>{
 const dismissal=dashboardDraft(state,'received-1','dismiss');
 assert.equal(dashboardConfirmation(state,dismissal,{confirmed:true}),null);
 assert.equal(dashboardConfirmation(state,dismissal,{confirmed:true,reason:'hostile'}),null);
 for(const reason of DISMISS_REASONS) {
  const result=dashboardConfirmation(state,dismissal,{confirmed:true,reason});
  assert.equal(result.reason_code,reason);assert.equal(result.confirm,true);assert.equal(result.classification_verified,undefined);
 }
 const result=dashboardConfirmation(state,draft,{confirmed:true,reason:'bird',comment:'  optional note  ',reviewer:' Sam '});
 assert.equal(result.reason_code,undefined);assert.equal(result.comment,'optional note');assert.equal(result.reviewer,'Sam');
});
test('every dashboard label and action explanation is supplied in both languages',()=>{
 const keys=Object.keys(messages.en).filter(key=>key.startsWith('dashboard.'));
 for(const key of keys) assert.ok(messages.ko[key],key);
 for(const lang of ['en','ko']) for(const action of DASHBOARD_ACTIONS) {
  assert.ok(messages[lang][`dashboard.action.${action}`]);assert.ok(messages[lang][`dashboard.effect.${action}`]);
 }
 assert.equal(messages.en['dashboard.status.corroborated'],'Follow-up received');
});

test('indirect indications support review before any received track without leaking future/truth data',async()=>{
 const {earlyIndicationSummary}=await import('../monitor/dashboard.mjs');
 const positive={id:'a',available_at_ms:1000,assessment:'current',object_present:true};
 const snapshot={at_ms:2000,tracks:[],simulation_positions:[{id:'secret'}],early_warning:{zones:[
  {id:'area-a',center:[3,4,5],evidence:[positive,{id:'later',available_at_ms:3000,assessment:'current',object_present:true}]},
  {id:'future-zone',evidence:[{...positive,available_at_ms:9000}]}
 ]}};
 const result=earlyIndicationSummary(snapshot);
 assert.equal(result.stage,'early_indication');assert.equal(result.track_count,0);assert.equal(result.zone_count,1);assert.equal(result.positive,1);
 assert.deepEqual(result.zones[0].evidence_ids,['a']);assert.equal(result.zones[0].center,undefined);assert.ok(!JSON.stringify(result).includes('secret'));
 assert.equal(earlyIndicationSummary({...snapshot,tracks:[{object_id:'received'}]}).stage,'received_observation');
});
test('indirect summary distinguishes conflicting, old, and unusable reports rather than confirming identity',async()=>{
 const {earlyIndicationSummary}=await import('../monitor/dashboard.mjs');
 const evidence=[
  {id:'p',available_at_ms:1000,assessment:'current',object_present:true},
  {id:'n',available_at_ms:1000,assessment:'current',object_present:false},
  {id:'old',available_at_ms:1000,assessment:'stale',object_present:true},
  {id:'bad',available_at_ms:1000,assessment:'unavailable',object_present:true},
 ];
 const state={at_ms:2000,tracks:[],early_warning:{zones:[{id:'area-a',evidence}]}};
 const result=earlyIndicationSummary(state);
 assert.equal(result.conflict_count,1);assert.equal(result.stale_count,1);assert.equal(result.unavailable_count,1);assert.equal(result.positive,1);
 assert.equal(earlyIndicationSummary({...state,early_warning:{zones:[{id:'area-a',evidence:evidence.slice(2)}]}}).stage,'awaiting_evidence');
 assert.equal(earlyIndicationSummary(null).stage,'awaiting_evidence');
});
test('early-stage option wording stays distinct while using the existing decision contract',async()=>{
 const {decisionCopyKey}=await import('../monitor/dashboard.mjs');
 for(const option of ['continue_monitoring','hold_review','defer'])for(const part of ['option','effect']) {
  const key=decisionCopyKey({stage:'early_indication'},part,option);
  assert.ok(messages.en[key]);assert.ok(messages.ko[key]);assert.ok(key.includes('.early.'));
  assert.equal(decisionCopyKey({stage:'received_observation'},part,option),`decision.${part}.${option}`);
 }
});

test('indication overview fits the site and a remote received-positive area without future or hidden positions',async()=>{
 const {indicationOverview}=await import('../monitor/dashboard.mjs');
 const perimeter={width_m:3000,length_m:4000,polygon:[[-1500,-2000],[1500,-2000],[1500,2000],[-1500,2000]]};
 const viewport={width:600,height:450};
 const report={id:'r',available_at_ms:1000,assessment:'current',object_present:true};
 const snapshot={at_ms:2000,tracks:[],simulation_positions:[{position:[999999,0,999999]}],early_warning:{zones:[
  {id:'remote_reference',center:[0,0,-16000],radius_m:1800,evidence:[report]},
  {id:'future-area',center:[100000,0,-900000],radius_m:9000,evidence:[{...report,available_at_ms:3000}]},
  {id:'old-area',center:[-900000,0,0],radius_m:8000,evidence:[{...report,assessment:'stale'}]},
 ]}};
 const fit=indicationOverview(snapshot,perimeter,viewport);
 assert.ok(fit.zoom<.5);assert.ok(fit.z<0);assert.equal(fit.x,0);
 const scale=Math.min(viewport.width/(perimeter.width_m*1.35),viewport.height/(perimeter.length_m*1.6))*fit.zoom;
 for(const [x,z] of [...perimeter.polygon,[-1800,-17800],[1800,-14200]]){
  assert.ok(Math.abs((x-fit.x)*scale)<=viewport.width*.4+1e-9);
  assert.ok(Math.abs((z-fit.z)*scale)<=viewport.height*.4+1e-9);
 }
 assert.deepEqual(indicationOverview({...snapshot,simulation_positions:[]},perimeter,viewport),fit);
 assert.equal(indicationOverview({...snapshot,at_ms:0},perimeter,viewport),null);
 assert.equal(indicationOverview(snapshot,perimeter,{width:0,height:0}),null);
});
