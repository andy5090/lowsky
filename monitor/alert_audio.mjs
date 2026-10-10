import {priorityAlertKey} from './notifications.mjs';

export const ALERT_AUDIO_STORAGE_KEY = 'lowsky.alertAudio.enabled';
const COOLDOWN_MS = {low: 30000, medium: 8000, high: 3000};
const RANK = {low: 1, medium: 2, high: 3};
// Finite, non-overlapping pulses with attack/release envelopes; no alert loops.
const TONES = {
  low: [[440, 0, 0.12]],
  medium: [[520, 0, 0.12], [660, 0.2, 0.14]],
  high: [[740, 0, 0.3], [980, 0.4, 0.3], [740, 0.8, 0.36]],
};
const nativeContext = () => new (globalThis.AudioContext || globalThis.webkitAudioContext)();
const lowKey = alert => {
  if (!alert || typeof alert.kind !== 'string' || priorityAlertKey(alert)) return null;
  // Receipt/object IDs must not turn one continuing situation into many tones.
  return JSON.stringify([alert.kind, alert.zone_id || alert.source_id || 'received-observations', alert.signal_status || '']);
};

/**
 * Call unlock() directly from a user gesture; creation, polling and setEnabled()
 * never create/resume audio. observe() consumes the SAME priority policy result
 * used by the UI. Pass state.connected=false during a connection loss.
 * Nothing queues: locked/muted/paused/catch-up alerts are consumed silently.
 */
export function createAlertAudioController({storage, now = () => globalThis.performance.now(),
  createContext = nativeContext, supported = createContext !== nativeContext || Boolean(globalThis.AudioContext || globalThis.webkitAudioContext),
  onChange = () => {}, volume = 0.14, maxObservationGapMs = 5000} = {}) {
  let enabled = true, unlocked = false, error = '', disposed = false, context = null;
  let run = null, previousTime = null, previousWall = null, wasConnected = true, needsBaseline = true;
  let seen = new Set(), generation = 0, unlocking = null, lastPlayed = -Infinity, lastLevel = null;
  const lastByLevel = {low: -Infinity, medium: -Infinity, high: -Infinity};
  const active = new Set();
  const gainLimit = Math.max(0, Math.min(0.2, Number.isFinite(volume) ? volume : 0.14));
  try { enabled = storage?.getItem(ALERT_AUDIO_STORAGE_KEY) !== '0'; } catch { /* Session-only preference. */ }
  const getState = () => {
    const ready = unlocked && context?.state === 'running';
    const status = disposed ? 'disposed' : !supported ? 'unsupported' : !enabled ? 'muted' : error ? 'error' : ready ? 'ready' : 'locked';
    return {enabled, unlocked: ready, supported, status, error};
  };
  const changed = () => onChange(getState());
  const clean = entry => {
    if (!active.delete(entry)) return;
    entry.oscillator.onended = null;
    try { entry.oscillator.disconnect(); } catch { /* Already released. */ }
    try { entry.gain.disconnect(); } catch { /* Already released. */ }
  };
  const silence = () => {
    for (const entry of [...active]) {
      try { entry.gain.gain.cancelScheduledValues(0); entry.gain.gain.setValueAtTime(0, context.currentTime); } catch { /* Closed context. */ }
      try { entry.oscillator.stop(); } catch { /* Ended oscillator. */ }
      clean(entry);
    }
  };
  const stop = () => { silence(); needsBaseline = true; };
  const setEnabled = value => {
    if (disposed) return getState();
    enabled = Boolean(value); error = ''; generation += 1;
    stop();
    try { storage?.setItem(ALERT_AUDIO_STORAGE_KEY, enabled ? '1' : '0'); } catch { /* Session-only preference. */ }
    changed();
    return getState();
  };
  const unlock = () => {
    if (disposed || !enabled || !supported) return Promise.resolve(getState());
    if (unlocking) return unlocking;
    const ticket = generation;
    error = ''; needsBaseline = true;
    // Run creation/resume synchronously inside this call, preserving user activation.
    try {
      if (!context || context.state === 'closed') {
        context = createContext();
        context.onstatechange = () => {
          if (context.state !== 'running') { unlocked = false; stop(); }
          changed();
        };
      }
      const resumed = context.state === 'running' ? Promise.resolve() : context.resume();
      unlocking = Promise.resolve(resumed).then(() => {
        if (disposed || ticket !== generation) return getState();
        if (context.state !== 'running') throw new Error('Audio did not start');
        unlocked = true; needsBaseline = true; changed();
        return getState();
      }).catch(() => {
        if (!disposed && ticket === generation) { unlocked = false; error = 'unlock_failed'; stop(); changed(); }
        return getState();
      }).finally(() => { unlocking = null; });
      return unlocking;
    } catch {
      error = 'unlock_failed'; unlocked = false; stop(); changed();
      return Promise.resolve(getState());
    }
  };
  const play = level => {
    silence();
    const start = context.currentTime + 0.01;
    for (const [frequency, offset, length] of TONES[level]) {
      const oscillator = context.createOscillator();
      let gain;
      try { gain = context.createGain(); } catch (failure) { oscillator.disconnect(); throw failure; }
      const entry = {oscillator, gain};
      active.add(entry);
      oscillator.onended = () => clean(entry);
      oscillator.type = level === 'high' ? 'triangle' : 'sine';
      oscillator.frequency.setValueAtTime(frequency, start + offset);
      const at = start + offset;
      const peak = gainLimit * (level === 'low' ? 0.22 : level === 'medium' ? 0.45 : 1);
      gain.gain.setValueAtTime(0, at);
      gain.gain.linearRampToValueAtTime(peak, at + 0.018);
      if (level === 'high') gain.gain.setValueAtTime(peak, at + length - 0.06);
      gain.gain.linearRampToValueAtTime(0, at + length);
      oscillator.connect(gain); gain.connect(context.destination);
      oscillator.start(at); oscillator.stop(at + length + 0.01);
    }
  };
  const observe = (state, priorityUpdates = {}) => {
    if (disposed) return {status: 'disposed', level: null};
    if (!state || typeof state.run_id !== 'string' || !Number.isFinite(state.at_ms)) return {status: 'empty', level: null};
    const wall = now(), connected = state.connected !== false;
    const gap = previousWall === null ? 0 : wall - previousWall;
    const jumped = previousTime !== null && state.at_ms - previousTime > Math.max(0, gap) * Math.max(1, Number(state.speed) || 1) + 2000;
    const baseline = needsBaseline || priorityUpdates.reset || run !== state.run_id || previousTime === null
      || state.at_ms < previousTime || gap > maxObservationGapMs || gap < 0 || jumped || !wasConnected || !connected;
    if (run !== state.run_id || state.at_ms < previousTime) seen = new Set();
    run = state.run_id; previousTime = state.at_ms; previousWall = wall; wasConnected = connected; needsBaseline = false;
    const fresh = {low: [], medium: [], high: []};
    for (const level of ['high', 'medium']) {
      for (const notice of priorityUpdates[level] || []) {
        if (typeof notice.key !== 'string') continue;
        const key = `priority:${notice.key}`;
        if (!seen.has(key) && (!Number.isFinite(notice.expires_at_ms) || notice.expires_at_ms > state.at_ms)) fresh[level].push(key);
        seen.add(key);
      }
    }
    for (const alert of state.alerts || []) {
      const promoted = priorityAlertKey(alert), semantic = lowKey(alert);
      if (promoted) seen.add(`priority:${promoted}`);
      if (!semantic) continue;
      const key = `low:${semantic}`;
      if (!seen.has(key) && !alert.acknowledged) fresh.low.push(key);
      seen.add(key);
    }
    if (baseline || !connected || !state.playing) {
      silence();
      return {status: baseline ? 'baseline' : 'paused', level: null};
    }
    if (getState().status !== 'ready') return {status: getState().status, level: null};
    const level = ['high', 'medium', 'low'].find(value => fresh[value].length);
    if (!level) return {status: 'empty', level: null};
    const preempts = level === 'high' && RANK[lastLevel] < RANK.high;
    if (wall - lastByLevel[level] < COOLDOWN_MS[level] || (!preempts && wall - lastPlayed < COOLDOWN_MS[level])) {
      return {status: 'cooldown', level};
    }
    try {
      play(level); lastPlayed = wall; lastByLevel[level] = wall; lastLevel = level;
      return {status: 'played', level};
    } catch {
      error = 'playback_failed'; stop(); changed();
      return {status: 'error', level: null};
    }
  };
  const dispose = () => {
    if (disposed) return;
    disposed = true; generation += 1; stop();
    if (context) {
      context.onstatechange = null;
      try { Promise.resolve(context.close()).catch(() => {}); } catch { /* Already closed. */ }
    }
    unlocked = false; changed();
  };
  return {unlock, setEnabled, getState, observe, stop, dispose};
}
