import assert from 'node:assert/strict';
import {test} from 'node:test';
import {moveOption,matchOption,menuPlacement} from '../monitor/custom_selects.mjs';

const options=[
 {index:0,value:'',label:'Choose an item'},
 {index:1,value:'a',label:'Alpha'},
 {index:2,value:'blocked',label:'Bravo blocked',disabled:true},
 {index:3,value:'b',label:'Bravo'},
 {index:4,value:'hidden',label:'Bravo hidden',hidden:true},
 {index:5,value:'c',label:'Charlie'},
 {index:6,value:'b2',label:'Beta'},
];
test('Arrow/Home/End exploration skips disabled and hidden options without mutating the native selection source',()=>{
 const original=structuredClone(options);
 assert.equal(moveOption(options,1,'next'),3);
 assert.equal(moveOption(options,3,'previous'),1);
 assert.equal(moveOption(options,6,'next'),0);
 assert.equal(moveOption(options,0,'previous'),6);
 assert.equal(moveOption(options,3,'first'),0);
 assert.equal(moveOption(options,3,'last'),6);
 assert.equal(moveOption(options,-1,'next'),0);
 assert.equal(moveOption([],0,'first'),-1);
 assert.equal(moveOption([{index:0,disabled:true}],0,'next'),-1);
 assert.deepEqual(options,original);
});
test('typeahead is case-insensitive, cycles matching entries and does not choose blocked or hidden options',()=>{
 assert.equal(matchOption(options,0,'b'),3);
 assert.equal(matchOption(options,3,'B'),6);
 assert.equal(matchOption(options,6,'br'),3);
 assert.equal(matchOption(options,3,'bravo blocked'),3);
 assert.equal(matchOption(options,3,'missing'),3);
 assert.equal(matchOption(options,3,''),3);
 assert.equal(matchOption([{index:4,label:'한국어'}],-1,'한'),4);
});
test('portaled menu fits a lower viewport edge and narrow screens rather than clipping inside an inspector',()=>{
 const rect={left:760,top:630,bottom:664,width:200};
 const fit=menuPlacement(rect,{width:980,height:700},240);
 assert.ok(fit.top<rect.top);
 assert.ok(fit.left+fit.width<=972);
 assert.ok(fit.top>=8);
 assert.equal(fit.maxHeight,320);
 const narrow=menuPlacement({left:290,top:100,bottom:130,width:100},{width:360,height:640},5);
 assert.ok(narrow.left+narrow.width<=352);
 assert.ok(narrow.top>=130);
 assert.ok(narrow.top+narrow.maxHeight<=632);
 const short=menuPlacement({left:10,top:30,bottom:60,width:200},{width:230,height:100},10);
 assert.ok(short.top+short.maxHeight<=92);
});

test('menu height uses measured wrapped content rather than assuming every option is one line',()=>{
 const rect={left:10,top:100,bottom:135,width:310};
 const measured=menuPlacement(rect,{width:800,height:700},3,214);
 assert.equal(measured.maxHeight,214);
 assert.equal(measured.top,139);
 const capped=menuPlacement(rect,{width:800,height:700},3,430);
 assert.equal(capped.maxHeight,320);
 const upward=menuPlacement({...rect,top:500,bottom:535},{width:800,height:700},3,214);
 assert.equal(upward.top,282);
});
