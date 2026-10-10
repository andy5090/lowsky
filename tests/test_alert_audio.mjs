import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createAlertAudioController, ALERT_AUDIO_STORAGE_KEY} from '../monitor/alert_audio.mjs';
import {createAlertPriorityPolicy} from '../monitor/notifications.mjs';

const state = (alerts = [], extra = {}) => ({run_id: 'run1', at_ms: 0, playing: true, alerts, ...extra});
const low = (zone = 'a', extra = {}) => ({id: `receipt-${zone}`, kind: 'early_warning', zone_id: zone, signal_status: 'single', ...extra});
const updates = (level, key, extra = {}) => ({[level]: [{key, ...extra}]});
function fixture(options = {}) {
  let time = 0, creations = 0;
  const stored = new Map(), oscillators = [], gains = [], changes = [];
  const param = () => ({values: [], setValueAtTime(value, at) {this.values.push(['set', value, at]);},
    linearRampToValueAtTime(value, at) {this.values.push(['ramp', value, at]);}, cancelScheduledValues() {this.cancelled = true;}});
  const context = {state: 'suspended', currentTime: 10, destination: {},
    resume() {this.state = 'running'; return Promise.resolve();},
    close() {this.closed = true; this.state = 'closed'; return Promise.resolve();},
    createOscillator() {const node = {frequency: param(), stops: [], disconnect() {this.disconnected = true;},
      connect(to) {this.target = to;}, start(at) {this.started = at;}, stop(at) {this.stops.push(at);}}; oscillators.push(node); return node;},
    createGain() {const node = {gain: param(), connect(to) {this.target = to;}, disconnect() {this.disconnected = true;}}; gains.push(node); return node;},
  };
  const controller = createAlertAudioController({storage: {getItem: key => stored.get(key), setItem: (key, value) => stored.set(key, value)},
    now: () => time, createContext: () => {creations++; return context;}, onChange: value => changes.push(value), ...options});
  const observe = (alerts = [], notices = {}, extra = {}) => controller.observe(state(alerts, {at_ms: time, ...extra}), notices);
  const ready = async () => {await controller.unlock(); observe();};
  return {controller, context, oscillators, gains, stored, changes, observe, ready,
    setTime: value => {time = value;}, creations: () => creations};
}

test('enabled preference never autoplays or creates context; gesture unlock establishes silent baseline', async () => {
  const f = fixture();
  assert.deepEqual(f.controller.getState(), {enabled: true, unlocked: false, supported: true, status: 'locked', error: ''});
  f.observe(); f.setTime(1000); f.observe([low()]);
  f.controller.setEnabled(true);
  assert.equal(f.creations(), 0);
  await f.controller.unlock();
  assert.equal(f.creations(), 1);
  assert.equal(f.oscillators.length, 0, 'Unlock never plays a sample or queued alert');
  assert.equal(f.observe([low('old-after-unlock')]).status, 'baseline');
  f.setTime(2000);
  assert.deepEqual(f.observe([low('new')]), {status: 'played', level: 'low'});
  assert.equal(f.oscillators.length, 1);
});

test('low, medium and high use distinct capped-envelope sine patterns and highest batch wins', async () => {
  for (const [level, count] of [['low', 1], ['medium', 2], ['high', 3]]) {
    const f = fixture({volume: 99}); await f.ready(); f.setTime(1000);
    const notices = level === 'low' ? {} : {...updates('medium', 'm'), ...(level === 'high' ? updates('high', 'h') : {})};
    assert.deepEqual(f.observe([low()], notices), {status: 'played', level});
    assert.equal(f.oscillators.length, count);
    for (const [index, oscillator] of f.oscillators.entries()) {
      assert.equal(oscillator.type, 'sine');
      assert(oscillator.stops[0] - oscillator.started < 0.3);
      assert(f.gains[index].gain.values.filter(value => value[0] === 'ramp').every(value => value[1] <= 0.08));
      assert.equal(f.gains[index].gain.values.at(-1)[1], 0);
    }
  }
});

test('shared priority policy drives importance; receipt/object churn never repeats a semantic sound', async () => {
  const f = fixture(), policy = createAlertPriorityPolicy(); await f.controller.unlock();
  let current = state(); f.controller.observe(current, policy.observe(current));
  f.setTime(1000); current = state([low()], {at_ms: 1000});
  assert.equal(f.controller.observe(current, policy.observe(current)).level, 'low');
  f.setTime(2000); current = state([low('a', {id: 'renewal'})], {at_ms: 2000});
  assert.equal(f.controller.observe(current, policy.observe(current)).status, 'empty');
  f.setTime(10000); current = state([], {at_ms: 10000}); f.controller.observe(current, policy.observe(current)); // silent catch-up
  f.setTime(11000); current = state([low('a', {signal_status: 'corroborated'})], {at_ms: 11000});
  assert.equal(f.controller.observe(current, policy.observe(current)).level, 'medium');
  f.setTime(12000); current = state([low('a', {id: 'more', signal_status: 'corroborated'})], {at_ms: 12000});
  assert.equal(f.controller.observe(current, policy.observe(current)).status, 'empty');
  assert.equal(f.oscillators.length, 3);
});

test('acknowledged lows and already promoted alerts do not leak into low sounds', async () => {
  const f = fixture(); await f.ready(); f.setTime(1000);
  assert.equal(f.observe([low('a', {acknowledged: true}), low('b', {signal_status: 'conflicting'})]).status, 'empty');
  f.setTime(2000); assert.equal(f.observe([low('a', {acknowledged: false})]).status, 'empty');
  assert.equal(f.oscillators.length, 0);
});

test('real-time cooldown discards bursts; high preempts low immediately and cleans old nodes', async () => {
  const f = fixture(); await f.ready(); f.setTime(1000); f.observe([low()]);
  const old = f.oscillators[0];
  f.setTime(1100); assert.equal(f.observe([low('b')]).status, 'cooldown');
  f.setTime(1200); assert.equal(f.observe([], updates('high', 'urgent')).status, 'played');
  assert(old.disconnected && f.gains[0].disconnected && old.stops.includes(undefined));
  f.setTime(2000); assert.equal(f.observe([], updates('high', 'burst')).status, 'cooldown');
  f.setTime(4300); assert.equal(f.observe([], updates('high', 'burst')).status, 'empty', 'Cooldown never queues suppressed notices');
  assert.equal(f.observe([], updates('high', 'next')).status, 'played');
  assert.equal(f.oscillators.length, 7);
});

test('medium waits 8 seconds and low waits 30 seconds across different semantic notices', async () => {
  for (const [level, interval] of [['medium', 8000], ['low', 30000]]) {
    const f = fixture(); await f.ready(); f.setTime(1000);
    const emit = key => f.observe(level === 'low' ? [low(key)] : [], level === 'medium' ? updates(level, key) : {});
    assert.equal(emit('first').status, 'played');
    for (let time = 2000; time < interval + 1000; time += 1000) {f.setTime(time); f.observe();}
    f.setTime(interval + 999); assert.equal(emit('too-soon').status, 'cooldown');
    f.setTime(interval + 1000); assert.equal(emit('next').status, 'played');
  }
});

test('first load, reset, rewind, forward seek and disconnected catch-up are silent', async () => {
  const f = fixture(); await f.controller.unlock();
  assert.equal(f.observe([low()], updates('high', 'initial')).status, 'baseline');
  f.setTime(1000); assert.equal(f.observe([low('new-run')], updates('high', 'seek'), {run_id: 'run2', at_ms: 500000}).status, 'baseline');
  f.setTime(2000); assert.equal(f.observe([low('rewind')], {}, {run_id: 'run2', at_ms: 100}).status, 'baseline');
  f.setTime(3000); assert.equal(f.observe([low('jump')], {}, {run_id: 'run2', at_ms: 600000}).status, 'baseline');
  f.setTime(4000); assert.equal(f.observe([low('offline')], {}, {connected: false}).status, 'baseline');
  f.setTime(5000); assert.equal(f.observe([low('reconnect')]).status, 'baseline');
  f.setTime(20000); assert.equal(f.observe([low('late')]).status, 'baseline');
  assert.equal(f.oscillators.length, 0);
});

test('paused and muted observations are consumed without catch-up, mute stops future scheduled pulses immediately', async () => {
  const f = fixture(); await f.ready(); f.setTime(1000);
  assert.equal(f.observe([low('paused')], {}, {playing: false}).status, 'paused');
  f.setTime(2000); assert.equal(f.observe([low('paused')]).status, 'empty');
  f.observe([], updates('high', 'h'));
  f.controller.setEnabled(false);
  assert.equal(f.stored.get(ALERT_AUDIO_STORAGE_KEY), '0');
  assert(f.oscillators.every(node => node.disconnected && node.stops.includes(undefined)));
  assert(f.gains.every(node => node.disconnected && node.gain.cancelled));
  f.setTime(3000); f.observe([low('muted')], updates('high', 'muted-high'));
  f.controller.setEnabled(true); f.observe([low('muted')], updates('high', 'muted-high'));
  f.setTime(4000); assert.equal(f.observe([low('muted')], updates('high', 'muted-high')).status, 'empty');
  assert.equal(f.oscillators.length, 3);
});

test('stored mute, unavailable audio and inaccessible storage fail safely', async () => {
  const muted = fixture({storage: {getItem: () => '0'}});
  assert.equal(muted.controller.getState().status, 'muted'); await muted.controller.unlock(); assert.equal(muted.creations(), 0);
  const unsupported = fixture({supported: false}); await unsupported.controller.unlock(); assert.equal(unsupported.controller.getState().status, 'unsupported'); assert.equal(unsupported.creations(), 0);
  const storage = fixture({storage: {getItem() {throw Error();}, setItem() {throw Error();}}});
  assert.equal(storage.controller.getState().enabled, true); storage.controller.setEnabled(false); assert.equal(storage.controller.getState().status, 'muted');
});

test('unlock denial and playback failure expose safe codes and can retry only via gesture', async () => {
  const f = fixture(); f.context.resume = () => Promise.reject(new Error('private platform text'));
  await f.controller.unlock(); assert.equal(f.controller.getState().error, 'unlock_failed');
  assert.equal(f.oscillators.length, 0);
  f.context.resume = () => {f.context.state = 'running'; return Promise.resolve();};
  await f.ready(); assert.equal(f.controller.getState().status, 'ready');
  f.context.createGain = () => {throw new Error('private audio error');};
  f.setTime(1000); assert.equal(f.observe([low()]).status, 'error');
  assert.equal(f.controller.getState().error, 'playback_failed');
  assert(f.oscillators[0].disconnected);
});

test('ended nodes disconnect and disposal cancels an in-flight unlock without stale playback', async () => {
  const f = fixture(); await f.ready(); f.setTime(1000); f.observe([low()]);
  f.oscillators[0].onended(); assert(f.oscillators[0].disconnected && f.gains[0].disconnected);
  f.controller.dispose(); f.controller.dispose(); assert(f.context.closed); assert.equal(f.controller.getState().status, 'disposed');
  assert.equal(f.observe([low('x')]).status, 'disposed');
  const pending = fixture(); let finish;
  pending.context.resume = () => new Promise(resolve => {finish = resolve;});
  const unlocking = pending.controller.unlock(); pending.controller.dispose(); finish(); await unlocking;
  assert.equal(pending.controller.getState().status, 'disposed'); assert.equal(pending.oscillators.length, 0);
});

test('expired high notices, suspended context, policy reset and stop never schedule a catch-up sound', async () => {
  const f = fixture(); await f.ready(); f.setTime(1000);
  assert.equal(f.observe([], updates('high', 'expired', {expires_at_ms: 500})).status, 'empty');
  f.observe([low()], {reset: true}); assert.equal(f.oscillators.length, 0);
  f.setTime(2000); f.context.state = 'suspended'; f.context.onstatechange();
  f.observe([low('suspended')]); await f.controller.unlock(); f.observe([low('suspended')]);
  f.setTime(3000); assert.equal(f.observe([low('suspended')]).status, 'empty');
  f.controller.stop(); assert.equal(f.observe([low('stopped')]).status, 'baseline');
  assert.equal(f.oscillators.length, 0);
});

test('mute during a pending unlock prevents late readiness; no accumulated alert is replayed', async () => {
  const f = fixture(); let finish;
  f.context.resume = () => new Promise(resolve => {finish = () => {f.context.state = 'running'; resolve();};});
  const pending = f.controller.unlock();
  f.observe(); f.setTime(1000); f.observe([low()], updates('high', 'during-unlock'));
  f.controller.setEnabled(false); finish(); await pending;
  assert.equal(f.controller.getState().status, 'muted');
  assert.equal(f.controller.getState().unlocked, false);
  f.controller.setEnabled(true); assert.equal(f.controller.getState().status, 'locked');
  await f.controller.unlock(); f.observe([low()], updates('high', 'during-unlock'));
  f.setTime(2000); assert.equal(f.observe([low()], updates('high', 'during-unlock')).status, 'empty');
  assert.equal(f.oscillators.length, 0);
});

test('one failed oscillator cleans all already-scheduled notes and creation denial is safe', async () => {
  const f = fixture(); await f.ready(); const create = f.context.createOscillator.bind(f.context);
  f.context.createOscillator = () => {if (f.oscillators.length) throw Error('device failure'); return create();};
  f.setTime(1000); assert.equal(f.observe([], updates('high', 'h')).status, 'error');
  assert(f.oscillators[0].disconnected && f.gains[0].disconnected);
  const denied = fixture({createContext() {throw Error('not allowed');}});
  await denied.controller.unlock(); assert.equal(denied.controller.getState().error, 'unlock_failed');
});
