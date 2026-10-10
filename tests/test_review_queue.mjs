import assert from 'node:assert/strict';
import {test} from 'node:test';
import {reviewQueue} from '../monitor/review.mjs';
const tracks=Array.from({length:240},(_,i)=>({object_id:`object_${i}`,evidence_version:'v1',last_known:i===0,quality:i%3?'consistent':'missing'}));
test('240 received tracks are paginated without hiding their total',()=>{
 const queue=reviewQueue(tracks,[],'all',3);
 assert.equal(queue.items.length,12);assert.equal(queue.pages,20);assert.equal(queue.received,240);assert.equal(queue.current,239);
 assert.equal(queue.items[0].object_id,'object_36');
});
test('filters retain source order and clamp pages after evidence changes',()=>{
 const queue=reviewQueue(tracks,[],'attention',100);
 assert.equal(queue.attention,80);assert.equal(queue.total,80);assert.equal(queue.page,6);
 assert.ok(queue.items.every(t=>t.quality==='missing'));
 assert.equal(reviewQueue([],[],'all',20).page,0);
});
test('reviewed state is bound to evidence version, never just object identity',()=>{
 const reviews=[{object_id:'object_0',evidence_version:'v1'}];
 assert.equal(reviewQueue(tracks,reviews,'unreviewed').total,239);
 const changed=tracks.map((t,i)=>i? t:{...t,evidence_version:'v2'});
 assert.equal(reviewQueue(changed,reviews,'unreviewed').total,240);
 assert.equal(reviewQueue([],reviews).received,0);
});
