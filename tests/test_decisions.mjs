import assert from 'node:assert/strict';
import {test} from 'node:test';
import {activeDecision,decisionReport,selectDecision,decisionDraftStatus,decisionConfirmation,decisionStatusKey} from '../monitor/decisions.mjs';
const event={id:'event_1',run_id:'run_1',at_ms:5000,evidence_version:'v1',status:'ready',report:{language:'en',decision_options:[{id:'hold_review'},{id:'defer'}]}};
const state={run_id:'run_1',at_ms:5000};
test('frozen standard choices follow the UI language without rewriting model reports',()=>{
 const ko={...event.report,language:'ko',summary:'수신 자료 검토'};
 const pending={...event,status:'evaluating',report:null,choice_report:event.report,
   choice_report_i18n:{en:event.report,ko}};
 assert.equal(decisionReport(pending,'ko'),ko);
 assert.equal(decisionReport(pending),event.report);
 const draft=selectDecision(pending,'hold_review','ko');
 assert.equal(decisionDraftStatus(draft,pending,state,'ko'),'ready');
 assert.equal(decisionConfirmation(draft,pending,state,'ko','','',true).confirm,true);
 assert.equal(decisionDraftStatus(draft,pending,state,'en'),'stale');
 assert.equal(decisionReport({...pending,report:event.report},'ko'),event.report);
 assert.equal(decisionDraftStatus(draft,{...pending,report:event.report},state,'ko'),'stale');
});
test('a previous confirmation notice never hides a new pending or ready event',()=>{
 for(const status of ['pending','evaluating','ready','failed']){
  assert.equal(decisionStatusKey({...event,id:'event_2',status},true,'decision.saved'),`decision.${status}`);
 }
 assert.equal(decisionStatusKey(null,true,'decision.saved'),'decision.saved');
 assert.equal(decisionStatusKey(event,true,'decision.unavailable'),'decision.unavailable');
});
test('a recommendation never selects or confirms a decision',()=>{
 assert.equal(selectDecision({...event,status:'evaluating',report:null},'hold_review'),null);
 assert.equal(selectDecision(event,'continue_monitoring'),null);
 assert.equal(selectDecision(event,'unknown_action'),null);
 assert.equal(decisionConfirmation(null,event,state,'en','operator','Inspect evidence',true),null);
 const draft=selectDecision(event,'hold_review');
 assert.equal(decisionConfirmation(draft,event,state,'en','operator','Inspect evidence'),null);
 const body=decisionConfirmation(draft,event,state,'en',' operator ',' Inspect evidence ',true);
 assert.equal(body.confirm,true);assert.equal(body.option_id,'hold_review');assert.equal(body.reason,'Inspect evidence');assert.equal(body.evidence_version,'v1');
});
test('drafts cannot confirm after evidence, event, run or language changes',()=>{
 const draft=selectDecision(event,'hold_review');
 for(const changed of [{...event,evidence_version:'v2'},{...event,id:'event_2'},{...event,status:'decided'},{...event,status:'superseded'},{...event,report:{...event.report,decision_options:[]}}]){
  assert.equal(decisionDraftStatus(draft,changed,state,'en'),'stale');
  assert.equal(decisionConfirmation(draft,changed,state,'en','operator','reason',true),null);
 }
 assert.equal(decisionDraftStatus(draft,event,{...state,at_ms:5001},'en'),'ready');
 assert.equal(decisionDraftStatus(draft,event,{...state,run_id:'run_2'},'en'),'stale');
 assert.equal(decisionDraftStatus(draft,event,state,'ko'),'stale');
 assert.equal(draft.evidence_version,'v1');
});
test('confirmation accepts optional comments but bounds submitted text',()=>{
 const draft=selectDecision(event,'defer');
 for(const [reviewer,reason] of [['x'.repeat(81),'reason'],['alias','x'.repeat(1001)],[null,'reason'],['alias',null]]){
  assert.equal(decisionConfirmation(draft,event,state,'en',reviewer,reason,true),null);
 }
 assert.equal(decisionConfirmation(draft,event,state,'en','alias','Further evidence needed',true).option_id,'defer');
 const empty=decisionConfirmation(draft,event,state,'en','',' ',true);
 assert.equal(empty.option_id,'defer');assert.equal(empty.reason,'');assert.equal(empty.reviewer,'');
});

test('expired cards and elapsed deadlines cannot be confirmed',()=>{
 const timed={...event,expires_at_ms:35000};
 const draft=selectDecision(timed,'hold_review');
 assert.equal(decisionDraftStatus(draft,timed,{...state,at_ms:34999},'en'),'ready');
 assert.equal(decisionDraftStatus(draft,timed,{...state,at_ms:35000},'en'),'stale');
 assert.equal(decisionConfirmation(draft,{...timed,status:'expired'},state,'en','','',true),null);
});

test('standard choices remain selectable before an agent report and after failure',()=>{
 for(const status of ['pending','evaluating','failed']) {
  const pending={...event,status,report:null,choice_report:event.report};
  const draft=selectDecision(pending,'hold_review');
  assert.equal(draft.option_id,'hold_review');
  assert.equal(decisionConfirmation(draft,pending,state,'en','','',true).confirm,true);
 }
});

test('latest overall situation is shown unless a valid human choice is in progress',()=>{
 const newest={...event,id:'newest',at_ms:8000};
 assert.equal(activeDecision([newest,event]).id,'newest');
 const draft=selectDecision(event,'hold_review');
 assert.equal(activeDecision([newest,event],draft).id,event.id);
 assert.equal(activeDecision([newest,{...event,status:'expired'}],draft).id,'newest');
 assert.equal(activeDecision([{...event,status:'decided'}]),null);
});
