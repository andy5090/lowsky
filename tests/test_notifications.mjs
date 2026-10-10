import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {test} from 'node:test';
import vm from 'node:vm';
import {createNotificationController, NOTIFICATION_STORAGE_KEY, sendNotification} from '../monitor/notifications.mjs';

const alert = (id, acknowledged = false) => ({id, acknowledged});
const state = (alerts = [], changes = {}) => ({run_id: 'run-1', at_ms: 1000, playing: true, alerts, ...changes});
function controller(options = {}) {
  const calls = [], changes = [], stored = new Map();
  const engine = createNotificationController({registration: {}, getPermission: () => 'granted',
    storage: {getItem: key => stored.get(key), setItem: (key, value) => stored.set(key, value)},
    onChange: value => changes.push(value),
    send: async (_, message) => { calls.push(message); return {ok: true, status: 'sent', count: message.alertIds.length}; }, ...options});
  return {engine, calls, changes, stored};
}

test('opt-in is explicit; current unacknowledged alerts can be sent while paused', async () => {
  const {engine, calls, stored} = controller();
  assert.equal(engine.getState().enabled, false);
  assert.equal((await engine.notifyCurrent(state([alert('a')]))).status, 'disabled');
  engine.setEnabled(true);
  assert.equal(stored.get(NOTIFICATION_STORAGE_KEY), '1');
  assert.equal((await engine.observe(state([alert('a')]))).status, 'baseline');
  assert.equal(calls.length, 0);
  assert.equal((await engine.notifyCurrent(state([alert('a'), alert('b', true)], {playing: false}))).count, 1);
  assert.deepEqual(calls[0].alertIds, ['a']);
  assert.equal((await engine.notifyCurrent(state([]))).status, 'empty');
});

test('polls batch new alerts once, suppress acknowledgements and repeated IDs', async () => {
  const {engine, calls} = controller();
  engine.setEnabled(true);
  await engine.observe(state([alert('old')]));
  await engine.observe(state([alert('old'), alert('new'), alert('next'), alert('acked', true)]));
  await engine.observe(state([alert('new')]));
  await engine.observe(state([alert('old'), alert('new'), alert('next')]));
  assert.equal(calls.length, 1);
  assert.deepEqual(calls[0].alertIds, ['new', 'next']);
});

test('paused, reset, seek and re-enable establish baselines without flooding', async () => {
  const {engine, calls} = controller();
  engine.setEnabled(true);
  await engine.observe(state([]));
  await engine.observe(state([alert('paused')], {playing: false}));
  await engine.observe(state([alert('paused')]));
  await engine.observe(state([alert('reset')], {run_id: 'run-2'}));
  await engine.observe(state([alert('rewind')], {run_id: 'run-2', at_ms: 0}));
  engine.setEnabled(false);
  await engine.observe(state([alert('disabled')], {run_id: 'run-2'}));
  engine.setEnabled(true);
  await engine.observe(state([alert('enabled')], {run_id: 'run-2'}));
  assert.equal(calls.length, 0);
});

test('denied, unsupported, blocked storage and delivery failures are explicit', async () => {
  for (const options of [{getPermission: () => 'denied'}, {supported: false}]) {
    const {engine, calls} = controller(options);
    assert.equal(engine.setEnabled(true).enabled, false);
    assert.equal((await engine.notifyCurrent(state([alert('a')]))).status, 'disabled');
    assert.equal(calls.length, 0);
  }
  const {engine, changes} = controller({storage: {getItem() {throw Error();}, setItem() {throw Error();}},
    send: async () => ({ok: false, error: 'OS notification rejected'})});
  engine.setEnabled(true);
  assert.equal((await engine.notifyCurrent(state([alert('a')]))).status, 'error');
  assert.equal(engine.getState().enabled, false);
  assert.equal(changes.at(-1).error, 'OS notification rejected');
});

test('explicit current-alert retry recovers from a delivery failure', async () => {
  let failed = true;
  const {engine} = controller({send: async () => failed ? {ok: false, error: 'temporary'} : {ok: true, status: 'sent', count: 1}});
  engine.setEnabled(true);
  assert.equal((await engine.notifyCurrent(state([alert('a')]))).status, 'error');
  failed = false;
  assert.equal((await engine.notifyCurrent(state([alert('a')]))).status, 'sent');
  assert.equal(engine.getState().enabled, true);
});

test('reload honors saved opt-in but does not replay existing alerts automatically', async () => {
  const {engine, calls} = controller({storage: {getItem: () => '1'}});
  assert.equal(engine.getState().enabled, true);
  await engine.observe(state([alert('existing')]));
  assert.equal(calls.length, 0);
});

test('queued delivery is cancelled after disabling or changing replay run', async () => {
  let resolve;
  const registration = new Promise(done => { resolve = done; });
  const {engine, calls} = controller({registration});
  engine.setEnabled(true);
  await engine.observe(state([]));
  const pending = engine.observe(state([alert('a')]));
  await engine.observe(state([], {run_id: 'run-2'}));
  resolve({});
  assert.equal((await pending).status, 'disabled');
  assert.equal(calls.length, 0);
});

test('MessageChannel failures and timeouts are surfaced', async () => {
  await assert.rejects(sendNotification(null, {}), /not active/);
  await assert.rejects(sendNotification({active: {postMessage() {throw Error('post failed');}}}, {}), /post failed/);
  await assert.rejects(sendNotification({active: {postMessage() {}}}, {}, 5), /timed out/);
  const result = await sendNotification({active: {postMessage(_, ports) {ports[0].postMessage({ok: true, status: 'sent', count: 1}); ports[0].close();}}}, {});
  assert.equal(result.ok, true);
});

test('delivery waits for first worker activation and reports activation timeout', async () => {
  const worker = new EventTarget();
  const registration = {installing: worker};
  const waiting = sendNotification(registration, {}, 100);
  setImmediate(() => {
    registration.active = {postMessage(_, ports) {ports[0].postMessage({ok: true}); ports[0].close();}};
    worker.dispatchEvent(new Event('statechange'));
  });
  assert.equal((await waiting).ok, true);
  await assert.rejects(sendNotification({installing: new EventTarget()}, {}, 5), /activation timed out/);
});

// Small asynchronous IndexedDB protocol fixture; receipt transactions in the worker
// are serialized by its delivery queue, matching this fixture's transaction lifetime.
function fakeIndexedDB(records = new Map()) {
  const db = {createObjectStore() {}, transaction() {
    let pending = 0, scheduled = false;
    const transaction = {objectStore: () => store};
    const complete = () => {
      if (scheduled) return;
      scheduled = true;
      setImmediate(() => { scheduled = false; if (!pending) transaction.oncomplete?.(); else complete(); });
    };
    const request = result => {
      pending += 1;
      const req = {};
      setImmediate(() => { req.result = result(); req.onsuccess?.(); pending -= 1; complete(); });
      return req;
    };
    const store = {get: id => request(() => records.get(id)),
      put: record => {records.set(record.id, record); complete();},
      delete: id => {records.delete(id); complete();}, openCursor: () => request(() => null)};
    complete(); return transaction;
  }};
  return {open() {const req = {}; setImmediate(() => {req.result = db; req.onupgradeneeded?.(); req.onsuccess?.();}); return req;}};
}
function worker({records = new Map(), failShow = false, existingClient = true} = {}) {
  const handlers = {}, shown = [], opened = [], posted = [], focused = [];
  const client = {id: 'local-client', type: 'window', url: 'http://localhost:8765/',
    focus: async () => focused.push(true), postMessage: message => posted.push(message)};
  const self = {location: {origin: 'http://localhost:8765'}, addEventListener: (name, handler) => {handlers[name] = handler;},
    skipWaiting: async () => {}, clients: {claim: async () => {},
      get: async id => id === 'remote' ? {...client, url: 'https://evil.example/'} : client,
      matchAll: async () => existingClient ? [client] : [], openWindow: async url => opened.push(url)},
    registration: {showNotification: async (title, options) => {if (failShow) throw Error('Show failed'); shown.push({title, ...options});}}};
  vm.runInNewContext(readFileSync(new URL('../monitor/sw.js', import.meta.url), 'utf8'), {self, indexedDB: fakeIndexedDB(records), URL, Date, Promise, Set});
  const send = async (changes = {}, source = 'local-client') => {
    let lifetime, response;
    handlers.message({data: {type: 'notify-alerts', runId: 'run-1', alertIds: ['a'], title: 'Simulation alert', body: 'Review received alert', ...changes},
      source: {id: source}, ports: [{postMessage: value => {response = value;}}], waitUntil: promise => {lifetime = promise;}});
    await lifetime; return response;
  };
  const click = async () => {
    let lifetime, closed = false;
    handlers.notificationclick({notification: {data: {url: 'https://evil.example'}, close: () => {closed = true;}}, waitUntil: promise => {lifetime = promise;}});
    await lifetime; assert.equal(closed, true);
  };
  return {send, click, shown, opened, posted, focused, records};
}

test('service worker deduplicates concurrent clients and persists receipts across restart', async () => {
  const first = worker();
  const results = await Promise.all([first.send(), first.send()]);
  assert.deepEqual(results.map(result => result.status), ['sent', 'duplicate']);
  assert.equal(first.shown.length, 1);
  assert.equal(first.shown[0].silent, true); // App tones own severity and mute.
  const restarted = worker({records: first.records});
  assert.equal((await restarted.send()).status, 'duplicate');
  assert.equal((await restarted.send({runId: 'run-2'})).status, 'sent');
  assert.equal(restarted.shown[0].data.view, 'alerts');
});

test('service worker validates origins/payloads and permits retry after OS rejection', async () => {
  const failed = worker({failShow: true});
  assert.equal((await failed.send({}, 'remote')).ok, false);
  assert.equal((await failed.send({alertIds: []})).ok, false);
  assert.equal((await failed.send()).error, 'Show failed');
  assert.equal(failed.records.size, 0);
  const retry = worker({records: failed.records});
  assert.equal((await retry.send()).status, 'sent');
});

test('notification click only focuses alerts or opens fixed local URL, never acknowledges', async () => {
  const existing = worker();
  await existing.click();
  assert.equal(existing.focused.length, 1);
  assert.equal(existing.posted[0].type, 'open-alerts');
  assert.equal(existing.opened.length, 0);
  const absent = worker({existingClient: false});
  await absent.click();
  assert.deepEqual(absent.opened, ['/?view=alerts']);
  assert.equal(absent.posted.length, 0);
});

test('priority policy suppresses routine reports and aggregates semantic bursts, not objects or new receipt IDs',async()=>{
 const {createAlertPriorityPolicy}=await import('../monitor/notifications.mjs');
 const policy=createAlertPriorityPolicy();
 policy.observe(state([],{at_ms:0,tracks:[]}));
 const single={id:'s',kind:'early_warning',zone_id:'area1',signal_status:'single'};
 assert.deepEqual(policy.observe(state([single],{at_ms:1000,tracks:[]})).medium,[]);
 const changes=[{...single,id:'a',signal_status:'corroborated'},...Array.from({length:48},(_,i)=>({id:`conflict${i}`,kind:'contradictory',object_id:`object${i}`}))];
 const result=policy.observe(state(changes,{at_ms:2000,tracks:[]}));
 assert.equal(result.medium.length,2);assert.equal(result.high.length,0);
 assert.equal(policy.observe(state(changes.map(row=>({...row,id:`new-${row.id}`})),{at_ms:3000,tracks:[]})).medium.length,0);
 assert.equal(policy.observe(state(changes,{run_id:'run2',at_ms:500,tracks:[]})).reset,true);
 assert.equal(policy.observe(state(changes,{run_id:'run2',at_ms:400,tracks:[]})).medium.length,0);
});
test('first direct receipt raises highest review notice with a current checkpoint, even without indirect evidence',async()=>{
 const {createAlertPriorityPolicy}=await import('../monitor/notifications.mjs');
 const event={id:'event1',run_id:'run-1',stage:'received_observation',status:'pending',expires_at_ms:100000,choice_report:{decision_options:[{id:'continue_monitoring'}]}};
 const direct=state([],{at_ms:3000,tracks:[{object_id:'received'}]});
 const policy=createAlertPriorityPolicy();
 policy.observe(state([],{at_ms:0,tracks:[]}));
 policy.observe(state([],{at_ms:1000,tracks:[],early_warning:{zones:[{positive_sources:1}]}}));
 assert.equal(policy.observe(direct,null).high.length,0);
 assert.equal(policy.observe({...direct,at_ms:4000},event).high[0].kind,'direct_transition');
 assert.equal(policy.observe({...direct,at_ms:5000},{...event,id:'event2'}).high.length,0);
 const ordinary=createAlertPriorityPolicy();ordinary.observe(state([],{at_ms:0,tracks:[]}));
 assert.equal(ordinary.observe(direct,event).high.length,1);
 assert.equal(ordinary.observe({...direct,at_ms:4000},event).high.length,0);
 const loaded=createAlertPriorityPolicy();assert.equal(loaded.observe(direct,event).high.length,0);
});
test('selection expiry only interrupts when an active human draft explicitly expired, once per draft',async()=>{
 const {createAlertPriorityPolicy}=await import('../monitor/notifications.mjs');
 const policy=createAlertPriorityPolicy();policy.observe(state([],{at_ms:0}));
 assert.equal(policy.observe(state([],{at_ms:2000})).high.length,0);
 const update=policy.observe(state([],{at_ms:3000}),null,{expiredChoice:'draft1'});
 assert.equal(update.high[0].kind,'choice_expired');
 assert.equal(policy.observe(state([],{at_ms:4000}),null,{expiredChoice:'draft1'}).high.length,0);
});
test('opted-in OS delivery uses the same low-priority suppression and semantic deduplication',async()=>{
 const {priorityAlertKey}=await import('../monitor/notifications.mjs');
 const {engine,calls}=controller({alertFilter:row=>Boolean(priorityAlertKey(row)),alertKey:priorityAlertKey});
 engine.setEnabled(true);await engine.observe(state([],{at_ms:0}));
 const low={id:'low',kind:'early_warning',zone_id:'area1',signal_status:'single'};
 await engine.observe(state([low],{at_ms:1000}));assert.equal(calls.length,0);
 const medium={...low,id:'medium',signal_status:'corroborated'};
 await engine.observe(state([low,medium,{...medium,id:'another-receipt'}],{at_ms:2000}));
 assert.equal(calls.length,1);assert.equal(calls[0].alertIds.length,1);
 await engine.observe(state([{...medium,id:'third-receipt'}],{at_ms:3000}));assert.equal(calls.length,1);
});
