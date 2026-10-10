import assert from 'node:assert/strict';
import {test} from 'node:test';
import {selectDecision,decisionDraftStatus,decisionConfirmation,decisionStatusKey} from '../monitor/decisions.mjs';
const event={id:'event_1',run_id:'run_1',at_ms:5000,evidence_version:'v1',status:'ready',report:{language:'en',decision_options:[{id:'hold_review'},{id:'defer'}]}};
const state={run_id:'run_1',at_ms:5000};
test('a previous confirmation notice never hides a new pending or ready event',()=>{
 for(const status of ['pending','evaluating','ready','failed']){
  assert.equal(decisionStatusKey({...event,id:'event_2',status},true,'decision.saved'),`decision.${status}`);
 }
 assert.equal(decisionStatusKey(null,true,'decision.saved'),'decision.saved');
 assert.equal(decisionStatusKey(event,true,'decision.unavailable'),'decision.unavailable');
});
test('a recommendation never selects or confirms a decision',()=>{
 assert.equal(selectDecision({...event,status:'evaluating'},'hold_review'),null);
 assert.equal(selectDecision(event,'continue_monitoring'),null);
 assert.equal(selectDecision(event,'unknown_action'),null);
 assert.equal(decisionConfirmation(null,event,state,'en','operator','Inspect evidence',true),null);
 const draft=selectDecision(event,'hold_review');
 assert.equal(decisionConfirmation(draft,event,state,'en','operator','Inspect evidence'),null);
 const body=decisionConfirmation(draft,event,state,'en',' operator ',' Inspect evidence ',true);
 assert.equal(body.confirm,true);assert.equal(body.option_id,'hold_review');assert.equal(body.reason,'Inspect evidence');assert.equal(body.evidence_version,'v1');
});
test('drafts cannot confirm after evidence, event, replay time, run or language changes',()=>{
 const draft=selectDecision(event,'hold_review');
 for(const changed of [{...event,evidence_version:'v2'},{...event,id:'event_2'},{...event,status:'decided'},{...event,status:'superseded'},{...event,report:{...event.report,decision_options:[]}}]){
  assert.equal(decisionDraftStatus(draft,changed,state,'en'),'stale');
  assert.equal(decisionConfirmation(draft,changed,state,'en','operator','reason',true),null);
 }
 assert.equal(decisionDraftStatus(draft,event,{...state,at_ms:5001},'en'),'stale');
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
