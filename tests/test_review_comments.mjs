import assert from 'node:assert/strict';
import {test} from 'node:test';
import {commentSuggestions,reviewComment} from '../monitor/review.mjs';
import {translate} from '../monitor/i18n.mjs';
test('suggestions use received quality gaps without asserting identity',()=>{
 assert.deepEqual(commentSuggestions(null),[]);
 const normal=commentSuggestions({quality:'consistent',last_known:false,explanation:{missing:[]}});
 assert.deepEqual(normal,['more_evidence','identity_unknown']);
 const conflict=commentSuggestions({quality:'contradictory',last_known:false,explanation:{missing:[]}});
 assert.ok(conflict.includes('compare_sources'));
 assert.ok(!conflict.includes('fresh_report'));
 const stale=commentSuggestions({quality:'missing',last_known:true,explanation:{missing:[{code:'source_offline'}]}});
 assert.ok(stale.includes('fresh_report'));assert.ok(stale.includes('check_missing'));
});
test('suggestions require explicit selection and free text is optional',()=>{
 const t=key=>translate('en',key);
 assert.equal(reviewComment('','',t),'');
 assert.equal(reviewComment('',' Custom comment ',t),'Custom comment');
 assert.equal(reviewComment('more_evidence','',t),'More evidence is needed.');
 assert.equal(reviewComment('more_evidence',' Check source B. ',t),'More evidence is needed. Check source B.');
 assert.equal(reviewComment('invented','',t),'');
 for(const key of ['more_evidence','compare_sources','fresh_report','check_missing','identity_unknown','verify_source','revisit']){
   for(const lang of ['en','ko']) assert.ok(reviewComment(key,'x'.repeat(800),k=>translate(lang,k)).length<=1000);
 }
});
