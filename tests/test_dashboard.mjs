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
