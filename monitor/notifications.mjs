export const NOTIFICATION_STORAGE_KEY = 'lowsky.notifications.enabled';

// Permissions are requested by the UI's user gesture, never by this controller.
export function createNotificationController({registration, storage, getPermission = () => 'default',
  supported = true, formatMessage = alerts => ({title: 'LOW SKY · Simulation alert',
    body: `${alerts.length} unacknowledged monitoring alert(s). Open LOW SKY to review.`}),
  onChange = () => {}, send = sendNotification, alertFilter = () => true, alertKey = alert => alert.id} = {}) {
  let optedIn = false, error = '', runId = null, previousTime = null;
  let seen = new Set(), generation = 0;
  let queue = Promise.resolve();
  try { optedIn = storage?.getItem(NOTIFICATION_STORAGE_KEY) === '1'; } catch { /* Session-only choice. */ }
  const getState = () => {
    const permission = getPermission();
    return {enabled: supported && optedIn && permission === 'granted' && !error,
      optedIn, supported, permission, error};
  };
  const resetBaseline = () => { generation += 1; runId = null; previousTime = null; seen = new Set(); };
  const setEnabled = value => {
    error = '';
    optedIn = Boolean(value) && supported && getPermission() === 'granted';
    try { storage?.setItem(NOTIFICATION_STORAGE_KEY, optedIn ? '1' : '0'); } catch { /* Session-only choice. */ }
    resetBaseline();
    onChange(getState());
    return getState();
  };
  const receivedAlerts = state => [...new Map((state?.alerts || [])
    .filter(alert => typeof alert.id === 'string' && !alert.acknowledged && alertFilter(alert))
    .map(alert => [alertKey(alert), alert])).values()];
  const deliver = async (alerts, state) => {
    if (!alerts.length) return {status: 'empty', count: 0};
    // Keep UI polling responsive, but serialize delivery and check opt-out again.
    const deliveryGeneration = generation;
    const operation = queue.then(async () => {
      if (!getState().enabled) return {status: 'disabled', count: 0};
      try {
        const message = formatMessage(alerts, state);
        const activeRegistration = await registration;
        if (!getState().enabled || deliveryGeneration !== generation) return {status: 'disabled', count: 0};
        const result = await send(activeRegistration, {type: 'notify-alerts', runId: state.run_id,
          alertIds: alerts.map(alert => alert.id), title: message.title, body: message.body});
        if (!result?.ok) throw new Error(result?.error || 'Notification delivery failed');
        return {status: result.status, count: result.count};
      } catch (failure) {
        error = failure?.message || 'Notification delivery failed';
        onChange(getState());
        return {status: 'error', count: 0, error};
      }
    });
    queue = operation.catch(() => {});
    return operation;
  };
  const observe = async state => {
    if (!state || typeof state.run_id !== 'string') return {status: 'empty', count: 0};
    const alerts = receivedAlerts(state);
    const baseline = runId !== state.run_id || previousTime === null || state.at_ms < previousTime;
    runId = state.run_id;
    previousTime = state.at_ms;
    if (baseline) { generation += 1; seen = new Set(); }
    const fresh = alerts.filter(alert => !seen.has(alertKey(alert)));
    for (const alert of state.alerts || []) seen.add(alertKey(alert));
    if (baseline) return {status: 'baseline', count: 0};
    if (!getState().enabled) return {status: 'disabled', count: 0};
    if (!state.playing) return {status: 'paused', count: 0};
    return deliver(fresh, state);
  };
  const notifyCurrent = async state => {
    // Explicit user retry may recover a transient worker/OS failure.
    if (error && optedIn && supported && getPermission() === 'granted') {
      error = ''; onChange(getState());
    }
    if (!getState().enabled) return {status: 'disabled', count: 0};
    if (!state || typeof state.run_id !== 'string') return {status: 'empty', count: 0};
    return deliver(receivedAlerts(state), state);
  };
  return {getState, setEnabled, observe, notifyCurrent, resetBaseline};
}

function waitForActive(registration, timeoutMs) {
  return new Promise((resolve, reject) => {
    if (registration?.active) { resolve(); return; }
    const worker = registration?.installing || registration?.waiting;
    if (!worker) { reject(new Error('Notification service worker is not active')); return; }
    const finish = error => {
      clearTimeout(timer);
      worker.removeEventListener('statechange', changed);
      if (error) reject(error); else resolve();
    };
    const changed = () => {
      if (registration.active) finish();
      else if (worker.state === 'redundant') finish(new Error('Notification service worker failed to activate'));
    };
    const timer = setTimeout(() => finish(new Error('Notification service worker activation timed out')), timeoutMs);
    worker.addEventListener('statechange', changed);
    changed();
  });
}

export async function sendNotification(registration, message, timeoutMs = 5000) {
  await waitForActive(registration, timeoutMs);
  return new Promise((resolve, reject) => {
    if (!registration?.active) { reject(new Error('Notification service worker is not active')); return; }
    const channel = new MessageChannel();
    const finish = (callback, value) => {
      clearTimeout(timer);
      channel.port1.close();
      callback(value);
    };
    const timer = setTimeout(() => finish(reject, new Error('Notification delivery timed out')), timeoutMs);
    channel.port1.onmessage = event => finish(resolve, event.data);
    channel.port1.onmessageerror = () => finish(reject, new Error('Notification response could not be read'));
    try { registration.active.postMessage(message, [channel.port2]); }
    catch (error) { finish(reject, error); }
  });
}


// Importance describes human review needs, not a threat classification.
export function priorityAlertKey(alert) {
  if(['review_transition','review_expired'].includes(alert.kind))return alert.id;
  if(alert.kind==='early_warning') {
    return ['corroborated','conflicting'].includes(alert.signal_status) ? `area:${alert.zone_id}:${alert.signal_status}` : null;
  }
  return ['contradictory','not_comparable','stale','channel'].includes(alert.kind) ? `${alert.kind}:${alert.source_id || 'received-observations'}` : null;
}
export function createAlertPriorityPolicy() {
  let run=null,previousTime=null,seen=new Set(),hadIndirect=false,directNotified=false;
  return {observe(state,event,{expiredChoice=null}={}) {
    if(!state)return {reset:false,medium:[],high:[]};
    const baseline=run!==state.run_id || previousTime===null || state.at_ms<previousTime;
    if(baseline){run=state.run_id;seen=new Set();hadIndirect=false;directNotified=Boolean(state.tracks?.length);}
    previousTime=state.at_ms;
    const hasPositive=(state.early_warning?.zones || []).some(zone=>zone.positive_sources>0);
    if(!state.tracks?.length && hasPositive)hadIndirect=true;
    const medium=[];
    for(const alert of state.alerts || []) {
      const key=priorityAlertKey(alert);
      if(!key || seen.has(key))continue;
      seen.add(key);
      if(!baseline && !alert.acknowledged)medium.push({key,kind:alert.kind,subject:alert.zone_id || alert.source_id || null});
    }
    const high=[];
    const report=event?.report || event?.choice_report;
    const actionable=event?.run_id===state.run_id && ['pending','evaluating','ready','failed'].includes(event.status)
      && event.expires_at_ms>state.at_ms && report?.decision_options?.length>0;
    if(!baseline && !directNotified && hadIndirect && state.tracks?.length && actionable && event.stage==='received_observation') {
      directNotified=true;high.push({key:`direct:${run}`,kind:'direct_transition',event_id:event.id,expires_at_ms:event.expires_at_ms});
    }
    if(expiredChoice && !baseline && !seen.has(`expired:${expiredChoice}`)) {
      seen.add(`expired:${expiredChoice}`);high.push({key:`expired:${expiredChoice}`,kind:'choice_expired',event_id:expiredChoice,expires_at_ms:state.at_ms+30000});
    }
    return {reset:baseline,medium,high};
  }};
}
