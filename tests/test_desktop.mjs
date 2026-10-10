import assert from 'node:assert/strict';
import {test} from 'node:test';
import {readFileSync} from 'node:fs';
import {desktopCommand,desktopShortcut,acceptDesktopState} from '../monitor/desktop.mjs';
const current={available:true,view:'monitor',fullscreen:false,three_d_open:false,pending:null,error:null,revision:1};
test('native actions require desktop availability and exclude simulation commands',()=>{
 assert.deepEqual(desktopCommand(current,'open_3d'),{action:'open_3d'});
 assert.deepEqual(desktopCommand({...current,three_d_open:true},'open_3d'),{action:'open_3d'});
 assert.equal(desktopCommand(current,'close_3d'),null);
 assert.deepEqual(desktopCommand({...current,three_d_open:true},'close_3d'),{action:'close_3d'});
 for(const action of ['play','pause','reset','seek'])assert.equal(desktopCommand(current,action),null);
 for(const status of [null,{available:false},{...current,pending:{id:'in-flight'}}])assert.equal(desktopCommand(status,'open_3d'),null);
 assert.equal(desktopCommand(current,'open_3d',{busy:true}),null);
 assert.equal(desktopCommand(current,'open_3d',{connected:false}),null);
});
test('desktop shortcuts preserve typing, modal choices and standalone browser behavior',()=>{
 assert.deepEqual(desktopShortcut('F6',current),{action:'open_3d'});
 assert.deepEqual(desktopShortcut('F11',current),{action:'toggle_monitor_fullscreen'});
 assert.deepEqual(desktopShortcut('F11',{...current,view:'3d'}),{action:'toggle_monitor_fullscreen'});
 for(const option of ['editing','modal','repeat','modifier','busy'])assert.equal(desktopShortcut('F6',current,{[option]:true}),null);
 assert.equal(desktopShortcut('F11',{available:false}),null);
 assert.equal(desktopShortcut('F6',current,{connected:false}),null);
 assert.equal(desktopShortcut('Escape',current),null);
});
test('native acknowledgements supersede pending state without accepting stale poll responses',()=>{
 const pending={...current,revision:2,pending:{action:'open_3d'}};
 assert.equal(acceptDesktopState(pending,current),pending);
 const acknowledged={...current,revision:3,three_d_open:true,view:'3d'};
 assert.equal(acceptDesktopState(pending,acknowledged),acknowledged);
 assert.equal(acceptDesktopState(pending,null),pending);
 assert.deepEqual(acceptDesktopState(pending,{available:false}),{available:false});
 assert.deepEqual(desktopCommand({...acknowledged,fullscreen:true},'toggle_monitor_fullscreen'),{action:'toggle_monitor_fullscreen'});
});

test('desktop controls remain inside the visible app header, outside the clipped workspace heading',()=>{
 const html=readFileSync(new URL('../monitor/index.html',import.meta.url),'utf8');
 const headerStart=html.indexOf('<header class="app-header">');
 const headerEnd=html.indexOf('</header>',headerStart);
 const controls=html.indexOf('id="desktop-controls"');
 const clippedHeading=html.indexOf('<div class="workspace-heading">');
 assert.ok(headerStart>=0 && controls>headerStart && controls<headerEnd);
 assert.ok(controls<clippedHeading);
 for(const id of ['desktop-open-3d','desktop-close-3d','desktop-fullscreen']) {
  const button=html.indexOf(`id="${id}"`);
  assert.ok(button>controls && button<headerEnd,id);
 }
});
