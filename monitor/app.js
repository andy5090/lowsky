import {localToGeo, mercator, unproject, pixelsPerMeter} from './geo.mjs';
import {radarFrame, replayTime} from './radar.mjs';
import {reviewQueue} from './review.mjs';
import {selectDecision, decisionDraftStatus, decisionConfirmation, decisionStatusKey} from './decisions.mjs';
import {testRunRequest, playbackRequest, repeatTestRequest} from './test_runs.mjs';
import {translate, readLanguage, saveLanguage, normalizeLanguage} from './i18n.mjs';
import {createNotificationController, NOTIFICATION_STORAGE_KEY} from './notifications.mjs';
const $ = id => document.getElementById(id);
const escape = value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let language = 'en';
try { language = readLanguage(localStorage); } catch { /* Storage may be unavailable. */ }
const t = (key, values) => translate(language, key, values);
const localized = value => value?.[language] || value?.en || '';
const qualityLabel = quality => t(`quality.${quality}`);
const sourceLabel = status => t(`source.${status}`);
let connected = null, connectionMessage = '';
const fmt = ms => `${String(Math.floor(ms / 60000)).padStart(2,'0')}:${String(Math.floor(ms / 1000) % 60).padStart(2,'0')}`;
let briefings = [], briefingSignature = '';
let situationSignature = '', situationRun = null, situationOptions = '', reviewPending = false;
let config, state, selected, mode = 'site', dataSignature = '', requestVersion = 0;
let controlChain = Promise.resolve();
let notifier, notificationBusy = false, notificationMessage = '', installPrompt;
let assessment = null, assessmentBusy = false, assessmentLastAttempt = 0, assessmentFailure = false;
let assessmentSignature = '';
let decisions = null, decisionBusy = false, decisionDraft = null, decisionError = '', decisionSignature = '';
let decisionLanguagePending = false, decisionAvailable = false;
let decisionNoticeRun = null;
let testOperator = null, operatorBusy = false, operatorError = '';
let queuePage = 0, queueFilter = 'all', queueRun = null;
let trackReviewBusy = false, reviewTargetKey = '', reviewTargetVersion = '';
let showPositions = false;
let radarVisible = true, clockReceivedAt = performance.now();
const plan = {x:0,z:0,zoom:1};
const region = {lat:49,lon:32,zoom:6};
const tileImages = new Map();
const map = $('map'), overlay = $('map-overlay'), markers = $('map-markers'), tiles = $('map-tiles');
const noTiles = new URLSearchParams(location.search).get('tiles') === 'off';
map.tabIndex = 0;
map.style.touchAction = 'none';

async function api(path, body) {
  const response = await fetch(path, body ? {method:'POST', headers:{'Content-Type':'application/json'},body:JSON.stringify(body)} : {});
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
  return data;
}
function connection(ok, message='') {
  connected = ok; connectionMessage = message;
  $('connection-status').textContent = ok ? t('connected') : t('disconnected');
  $('connection-status').classList.toggle('is-connected', ok);
  $('connection-status').classList.toggle('disconnected', !ok);
  for (const id of ['play-button','reset-button','case-select','timeline','speed-select','test-run-button','test-seed']) $(id).disabled = !ok;
  $('test-repeat-button').disabled = !ok || !repeatTestRequest(state || {});
  updateReviewAvailability();
  updateTrackReviewAvailability();
  renderNotificationSettings();
  if (!ok) { if (state) { delete state.simulation_positions; drawMap(); } $('sim-status').textContent = t(message || 'retainView'); drawRadar(state?.at_ms || 0); }
}
function control(body) {
  controlChain = controlChain.then(async () => {
    const version = ++requestVersion;
    try { const data = await api('/api/control', body); if(version === requestVersion) render(data); }
    catch(error) { connection(false, 'requestFailed'); }
  });
  return controlChain;
}
async function poll() {
  const version = ++requestVersion;
  try { const data = await api(showPositions ? '/api/state?show_positions=1' : '/api/state'); if(version === requestVersion) render(data); }
  catch { connection(false); }
  setTimeout(poll, 500);
}
function render(data) {
  state = data; clockReceivedAt = performance.now(); connection(true);
  renderPlayback(data);
  renderBriefing();
  renderSituation();
  renderWorkload();
  renderAssessment();
  renderDecisions();
  notifier?.observe(data);
  const signature = JSON.stringify([data.run_id,data.tracks,data.sources,data.alerts,data.contexts,data.early_warning,data.reviews,data.track_reviews,data.review_summary,data.simulation_positions]);
  if (signature !== dataSignature) {
    dataSignature = signature;
    if(!data.tracks.some(t => t.object_id === selected)) selected = data.tracks[0]?.object_id;
    renderDetails(); renderEarlyWarning(); drawMap();
  }
}
function renderPlayback(data) {
  $('case-select').value = data.case_id;
  $('sim-status').textContent = data.playing ? t('playing') : data.at_ms >= data.duration_ms ? t('finished') : t('paused');
  $('sim-status').classList.toggle('running', data.playing);
  $('play-button').textContent = data.playing ? t('pause') : t(data.test_run?.mode === 'seeded' ? (data.at_ms >= data.duration_ms ? 'test.restart' : 'play') : 'test.start');
  const run = data.test_run;
  $('test-run-summary').textContent = run?.mode === 'seeded' ? t('test.summary', {seed:run.seed,version:run.generator_version}) : t('test.fixture');
  $('test-run-summary').title = run?.input_digest ? t('test.digest',{digest:run.input_digest}) : '';
  $('test-current-seed').textContent = $('test-run-summary').textContent;
  $('test-current-seed').title = $('test-run-summary').title;
  $('time-label').textContent = `${fmt(data.at_ms)} / ${fmt(data.duration_ms)}`;
  $('timeline').max = data.duration_ms;
  if(document.activeElement !== $('timeline')) $('timeline').value = data.at_ms;
  $('speed-select').value = data.speed;
  drawRadar(data.at_ms);
}
function select(id) { selected = id; renderDetails(); drawMap(); }
function renderDetails() {
  if(!state) return;
  $('track-count').textContent = state.tracks.length;
  if (queueRun !== state.run_id) { queuePage = 0; queueRun = state.run_id; }
  const queue = reviewQueue(state.tracks, state.track_reviews, queueFilter, queuePage);
  queuePage = queue.page;
  $('queue-page').textContent = t('queue.page',{page:queue.page+1,pages:queue.pages,count:queue.total});
  $('queue-prev').disabled = queue.page === 0; $('queue-next').disabled = queue.page + 1 >= queue.pages;
  $('track-list').innerHTML = queue.items.map(t => `<button class="track-item ${selected===t.object_id?'is-selected':''}" aria-pressed="${selected===t.object_id}" data-track="${escape(t.object_id)}"><header><span class="track-name">${escape(t.object_id)}</span><span class="track-quality" data-quality="${escape(t.quality)}">${qualityLabel(t.quality)}</span></header><div class="track-meta">${t.last_known?translate(language,'lastKnown'):translate(language,'lastObservation')} · ${t.observed_at_ms===null?translate(language,'noRecord'):fmt(t.observed_at_ms)}</div></button>`).join('');
  $('track-list').querySelectorAll('[data-track]').forEach(b => b.onclick = () => select(b.dataset.track));
  const track = state.tracks.find(t => t.object_id === selected);
  if(track) {
    $('track-detail').innerHTML = `<h3>${escape(track.object_id)}</h3><p>${qualityLabel(track.quality)} · ${t('sampleInterval')}</p><dl class="detail-grid"><dt>${t('lastObservation')}</dt><dd>${track.observed_at_ms===null?t('none'):fmt(track.observed_at_ms)}</dd><dt>${t('positionSource')}</dt><dd>${escape(track.position_source || t('none'))}</dd><dt>${t('localXZ')}</dt><dd>${track.position ? `${track.position[0].toFixed(0)} / ${track.position[2].toFixed(0)} m` : t('none')}</dd></dl><button class="button button-secondary" id="focus-track">${t('focusTrack')}</button><div class="evidence-rows">${track.records.map(r=>`<p><strong>${escape(r.source_id)}</strong> · ${translate(language,'lastObservation')} ${fmt(r.observed_at_ms)} · ${translate(language,'early.received')} ${fmt(r.available_at_ms)} · ${escape(t(`marker.${r.marker_label}`))}<br><small>${t('evidence')} ${escape(r.id)}</small></p>`).join('')}</div>`;
    $('focus-track').onclick = () => { if(track.position){plan.x=track.position[0];plan.z=track.position[2];plan.zoom=8;setMode('site');} };
  }
  if(!track) $('track-detail').innerHTML = `<p class="empty-state">${t('awaitingDetection')}</p>`;
  if(!queue.items.length) $('track-list').innerHTML = `<p class="empty-state">${t(state.tracks.length?'queue.empty':'awaitingDetection')}</p>`;
  renderEvidenceExplanation(track);
  const pending = state.alerts.filter(a=>!a.acknowledged).length;
  $('alert-count').textContent = pending;
  const alertHTML = state.alerts.map(a=>{
    const early = a.kind === 'early_warning';
    const zone = state.early_warning?.zones.find(z=>z.id===a.zone_id);
    const title = early ? t('early.review') : t(['contradictory','not_comparable','stale','channel'].includes(a.kind)?`alert.${a.kind}`:'alert.unknown');
    const subject = early ? `${zoneLabel(zone)} · ${t(`early.${a.signal_status}`)}` : a.object_id || a.source_id;
    return `<li class="alert-item severity-warning ${a.acknowledged?'is-acknowledged':''}"><strong>${escape(title)}</strong><p>${escape(subject)} · ${t('evidence')} ${a.evidence_ids.map(escape).join(', ') || t('none')}</p>${early?`<p class="early-alert-note">${t('early.radarUnknown')}</p>`:''}<button class="button button-secondary" data-alert="${escape(a.id)}" ${a.acknowledged?'disabled':''}>${a.acknowledged?t('acknowledged'):t('acknowledge')}</button></li>`;
  }).join('') || `<li class="alert-item">${t('noAlerts')}</li>`;
  $('alert-list').innerHTML = alertHTML;
  $('active-alerts').innerHTML = alertHTML;
  document.querySelectorAll('[data-alert]').forEach(b=> b.onclick=()=>control({action:'ack',alert_id:b.dataset.alert,run_id:state.run_id}));
  $('source-status').textContent = state.sources.map(s=>`${s.source_id}: ${sourceLabel(s.status)}`).join(' · ');
  $('events-list').innerHTML = state.sources.map(s=>`<li class="event-item"><time>${s.evidence ? fmt(s.evidence.observed_at_ms) : '--:--'}</time>${escape(s.source_id)} · ${sourceLabel(s.status)}</li>`).join('') + state.contexts.map(c=>`<li class="event-item"><time>${t('published')} ${fmt(c.published_at_ms)}</time>${escape(['context_001','context_002'].includes(c.id)?t(`context.${c.id}`):c.text)}</li>`).join('');
  $('events-list').innerHTML += (state.reviews || []).map(r=>`<li class="event-item"><time>${fmt(r.at_ms)}</time>${escape(t('early.ackEvent',{id:r.alert_id}))}</li>`).join('');
}
function renderAssessment() {
  $('agent-mode').textContent = t(assessment?.mode==='llm'?'agent.llm':'agent.rules');
  const configurationError = assessment?.configuration_error;
  $('agent-assess').disabled = !connected || !state || assessmentBusy || Boolean(assessment?.running) || Boolean(configurationError);
  $('agent-auto').disabled = Boolean(configurationError) || Boolean(decisions?.enabled);
  if (decisions?.enabled) $('agent-auto').checked = false;
  let status = assessment?.running || assessmentBusy ? 'agent.running' : configurationError ? `agent.${configurationError}` : assessmentFailure || assessment?.error ? 'agent.failed' : assessment?.configured ? 'agent.ready' : 'agent.unconfigured';
  $('agent-status').textContent = `${t(status)}${assessment?.model ? ` (${assessment.model})` : ''}`;
  const report = assessment?.latest?.run_id===state?.run_id ? assessment.latest : null;
  const stale = report && (report.at_ms!==state.at_ms || report.language!==language);
  const signature = JSON.stringify([language,report,Boolean(stale)]);
  if(signature===assessmentSignature)return;
  assessmentSignature=signature;
  $('agent-report').innerHTML = report ? `<p class="agent-summary">${escape(report.summary)}</p><p class="muted">${escape(t('agent.basis',{caseId:report.case_id,time:fmt(report.at_ms),mode:report.mode==='llm'?report.model:t('agent.rules')}))}${stale?` · ${t('agent.stale')}`:''}</p><div class="agent-findings">${['known','uncertain','review_items'].map(section=>`<section><h3>${t(`agent.${section}`)}</h3><ul>${report[section].map(item=>`<li>${escape(item.text)}<small>${item.evidence_ids.map(escape).join(', ')}</small></li>`).join('') || `<li>${t('none')}</li>`}</ul></section>`).join('')}</div>` : `<p class="empty-state">${t('agent.empty')}</p>`;
}
async function runAssessment() {
  if(!connected || !state || assessmentBusy || assessment?.running || assessment?.configuration_error)return;
  const run=state.run_id;
  assessmentBusy=true;assessmentFailure=false;assessmentLastAttempt=performance.now();renderAssessment();
  try {
    const result=await api('/api/assessment',{run_id:run,language});
    if(state?.run_id===run)assessment=result;
  } catch {assessmentFailure=true;}
  finally {assessmentBusy=false;renderAssessment();}
}
async function pollAssessment() {
  const run=state?.run_id;
  try {
    const result=await api('/api/assessment');
    if(state?.run_id===run){assessment=result;assessmentFailure=false;renderAssessment();}
    if(!decisions?.enabled && $('agent-auto').checked && connected && state?.playing && !assessmentBusy && !assessment?.running
       && performance.now()-assessmentLastAttempt>=30000)runAssessment();
  } catch {assessmentFailure=true;renderAssessment();}
  setTimeout(pollAssessment,1500);
}
$('agent-assess').onclick=runAssessment;
$('agent-auto').onchange=()=>{if($('agent-auto').checked)runAssessment();};

function currentDecision() {
  if (!decisions || !state || decisions.run_id !== state.run_id) return null;
  return (decisions.events || []).find(event=>!['decided','superseded'].includes(event.status)) || null;
}
function renderDecisions() {
  renderOperator();
  if (decisionNoticeRun !== state?.run_id) {
    if (decisionError === 'decision.saved') decisionError = '';
    decisionNoticeRun = state?.run_id;
  }
  const event = currentDecision();
  const waiting = (decisions && state && decisions.run_id === state.run_id ? decisions.events || [] : []).filter(item=>!['decided','superseded'].includes(item.status));
  $('decision-count').textContent = waiting.length;
  if (decisions) $('decision-enabled').checked = decisions.enabled;
  $('decision-enabled').disabled = !connected || decisionBusy;
  $('decision-assess').disabled = !connected || !state || decisionBusy || event?.status === 'evaluating';
  const statusKey = decisionStatusKey(event, decisions?.enabled, decisionError);
  $('decision-status').textContent = operatorActive() ? t('operator.autoNotice') : t(statusKey);
  $('decision-attention').hidden = !event;
  $('decision-attention-text').textContent = event ? (operatorActive() ? t('operator.autoNotice') : t(statusKey)) : '';
  const report = event?.report;
  const signature = JSON.stringify([language,event,decisionBusy,operatorActive(),decisionDraft?.event_id,decisionDraft?.option_id]);
  if (signature !== decisionSignature) {
    decisionSignature = signature;
    $('decision-event').innerHTML = event ? `<p class="muted">${escape(event.case_id)} · ${fmt(event.at_ms)} · ${escape(event.id)}</p>
      <ul class="decision-triggers">${(event.triggers || []).map(trigger=>`<li>${escape(t(`decision.trigger.${trigger.kind}`))} · ${escape(trigger.subject || '')} <span class="muted">(${escape(String(trigger.previous))} → ${escape(String(trigger.current))})</span><small>${(trigger.evidence_ids || []).map(escape).join(', ')}</small></li>`).join('')}</ul>
      ${report ? `<p class="agent-summary">${escape(report.summary)}</p><p class="muted">${escape(report.mode==='llm'?report.model:t('agent.rules'))}${report.language!==language?` · ${t('decision.languageMismatch')}`:''}</p><div class="decision-options">${(report.decision_options || []).filter(option=>['continue_monitoring','hold_review','defer'].includes(option.id)).map(option=>`<article><h3>${t(`decision.option.${option.id}`)}</h3>${report.recommended_option_id===option.id?`<span class="decision-recommendation">${t('decision.recommended')}</span>`:''}<p>${escape(option.reason)}</p><small>${(option.evidence_ids || []).map(escape).join(', ')}</small><p class="decision-effect">${t(`decision.effect.${option.id}`)}</p><button type="button" class="button button-secondary" data-decision-option="${option.id}" ${event.status!=='ready' || decisionBusy || operatorActive() || report.language!==language?'disabled':''}>${t(decisionDraft?.event_id===event.id && decisionDraft?.option_id===option.id?'decision.selected':'decision.select')}</button></article>`).join('')}</div><details class="decision-evidence"><summary>${t('decision.evidenceDetails')}</summary><div class="agent-findings">${['known','uncertain','review_items'].map(section=>`<section><h3>${t(`agent.${section}`)}</h3><ul>${(report[section] || []).map(item=>`<li>${escape(item.text)}<small>${(item.evidence_ids || []).map(escape).join(', ')}</small></li>`).join('') || `<li>${t('none')}</li>`}</ul></section>`).join('')}</div></details>`:''}
      ${['ready','failed'].includes(event.status)?`<button type="button" id="decision-retry" class="button button-secondary" ${decisionBusy?'disabled':''}>${t(event.status==='failed'?'decision.retry':'decision.reassess')}</button>`:''}` : `<p class="empty-state">${t('decision.empty')}</p>`;
    document.querySelectorAll('[data-decision-option]').forEach(button=>button.onclick=()=>{
      decisionDraft = selectDecision(currentDecision(),button.dataset.decisionOption);decisionError='';renderDecisions();
      $('decision-confirm').focus();
    });
    if ($('decision-retry')) $('decision-retry').onclick=()=>decisionAction({action:'retry',event_id:event.id,language});
  }
  $('decision-form').hidden = !decisionDraft;
  if (decisionDraft) {
    const status = decisionDraftStatus(decisionDraft,event,state,language);
    $('decision-confirm-summary').textContent = `${t(`decision.option.${decisionDraft.option_id}`)} · ${t(`decision.effect.${decisionDraft.option_id}`)} · ${fmt(decisionDraft.at_ms)} · ${decisionDraft.event_id}`;
    $('decision-draft-status').textContent = status === 'stale' ? t('decision.stale') : t('decision.confirmNote');
    $('decision-confirm').disabled = !connected || !decisionAvailable || decisionBusy || operatorActive() || status !== 'ready';
  }
  $('decision-history').innerHTML = (decisions && state && decisions.run_id===state.run_id ? decisions.history || [] : []).map(record=>`<li>${record.actor?.type==='automated_test'?`<strong>${t('operator.automated')}</strong> · `:''}${fmt(record.at_ms || 0)} · ${escape(t(`decision.option.${record.option_id}`))}<p>${escape(record.reason || '')}</p></li>`).join('') || `<li>${t('none')}</li>`;
}
async function decisionAction(body) {
  if (!connected || !state || decisionBusy) return false;
  const run = state.run_id;
  decisionBusy=true;decisionError='';renderDecisions();
  try {
    const result=await api('/api/decisions',{run_id:run,...body});
    if(state?.run_id===run){decisions=result;decisionAvailable=true;return true;}
    return false;
  } catch {decisionError='decision.failedRequest';return false;}
  finally {decisionBusy=false;renderDecisions();renderAssessment();}
}
async function syncDecisionLanguage() {
  if (!state || !decisions || decisionLanguagePending || decisions.language === language) return;
  decisionLanguagePending = true;
  try { await decisionAction({action:'configure',enabled:decisions.enabled,language}); }
  finally {decisionLanguagePending=false;}
}
async function pollDecisions() {
  const run=state?.run_id;
  try {
    const result=await api('/api/decisions');
    if(state?.run_id===run){decisions=result;decisionAvailable=true;if(decisionError==='decision.unavailable')decisionError='';renderDecisions();renderAssessment();await syncDecisionLanguage();}
  } catch {decisionAvailable=false;decisionError='decision.unavailable';renderDecisions();}
  try { testOperator=await api('/api/test-operator'); operatorError=''; renderDecisions(); }
  catch { operatorError='operator.unavailable'; renderOperator(); }
  setTimeout(pollDecisions,1500);
}
$('decision-enabled').onchange=()=>decisionAction({action:'configure',enabled:$('decision-enabled').checked,language});
$('decision-assess').onclick=()=>decisionAction({action:'assess_current',language});
$('decision-cancel').onclick=()=>{decisionDraft=null;decisionError='';renderDecisions();};
$('decision-form').onsubmit=async event=>{
  event.preventDefault();
  const body=decisionConfirmation(decisionDraft,currentDecision(),state,language,$('decision-reviewer').value,$('decision-reason').value,true);
  if(!body || !decisionAvailable || operatorActive()){renderDecisions();return;}
  if(await decisionAction(body)){decisionDraft=null;$('decision-reason').value='';$('decision-extra').open=false;decisionError='decision.saved';renderDecisions();}
};

function operatorActive() { return Boolean(testOperator?.active && testOperator.run_id === state?.run_id); }
function renderOperator() {
  const active = operatorActive();
  const config = testOperator?.configuration;
  $('operator-start').disabled = !connected || operatorBusy || active || !config?.available || state?.test_run?.mode !== 'seeded' || !decisions?.enabled || state?.at_ms >= state?.duration_ms;
  $('operator-stop').disabled = !connected || operatorBusy || !active;
  $('operator-stop').hidden = !active;
  $('operator-limit').disabled = active || operatorBusy;
  $('operator-status').textContent = `${t(`operator.status.${testOperator?.status || 'idle'}`)}${testOperator?.session_id ? ` · ${testOperator.completed} / ${testOperator.max_decisions}` : ''}${config?.model ? ` · Codex / ${config.model}` : ''}`;
  $('operator-error').textContent = operatorError ? t(operatorError) : !config?.available ? t('operator.unavailable') : state?.test_run?.mode !== 'seeded' ? t('operator.seededRequired') : '';
  $('operator-log').innerHTML = (testOperator?.decisions || []).map(item=>`<li><strong>${t('operator.automated')}</strong> · ${fmt(item.at_ms)} · ${escape(t(`decision.option.${item.option_id}`))}<p>${escape(item.reason)}</p></li>`).join('');
}
async function operatorCommand(action) {
  if (!state || operatorBusy) return;
  if(action==='start' && !$('operator-limit').reportValidity()) return;
  operatorBusy=true; operatorError=''; renderOperator();
  try { testOperator=await api('/api/test-operator',{action,run_id:state.run_id,confirm:action==='start',max_decisions:Number($('operator-limit').value)}); }
  catch { operatorError='operator.requestFailed'; }
  finally { operatorBusy=false; renderDecisions(); }
}
$('operator-start').onclick=()=>operatorCommand('start');
$('operator-stop').onclick=()=>operatorCommand('stop');

function renderWorkload() {
  if (!state) return;
  const queue = reviewQueue(state.tracks, state.track_reviews);
  $('workload-summary').innerHTML = [['received',queue.received],['current',queue.current],['attention',queue.attention],['unreviewed',queue.unreviewed]].map(([key,count])=>`<div><strong>${count}</strong><span>${t(`workload.${key}`)}</span></div>`).join('');
  const fleet = state.sensor_fleet;
  $('fleet-groups').innerHTML = (fleet?.groups || []).map(group=>`<article><h3>${escape(localized(group.label))}</h3><strong>${group.total}</strong><p>${['online','offline','stale','waiting'].map(status=>`${t(`fleet.${status}`)} ${group.counts[status] || 0}`).join(' · ')}</p></article>`).join('');
  const received = (fleet?.sensors || []).filter(sensor=>sensor.last_seen_ms !== null && sensor.last_seen_ms !== undefined);
  const last = received.length ? fmt(Math.max(...received.map(sensor=>sensor.last_seen_ms))) : t('none');
  $('fleet-last-seen').textContent = t('fleet.lastSeen',{total:fleet?.total || 0,received:received.length,time:last});
}
function trackReviewStatus(key='') {
  $('track-review-status').dataset.i18n = key;
  $('track-review-status').textContent = key ? t(key) : '';
}
function updateTrackReviewAvailability() {
  const track = state?.tracks.find(track=>track.object_id===selected);
  const stale = track && reviewTargetVersion && track.evidence_version !== reviewTargetVersion;
  $('track-review-submit').disabled = !connected || trackReviewBusy || !track || Boolean(stale);
  if (stale && !trackReviewBusy) trackReviewStatus('review.changed');
}
function renderEvidenceExplanation(track) {
  const key = `${state.run_id}:${track?.object_id || ''}`;
  if (reviewTargetKey !== key) {
    const hadDraft = Boolean($('track-reason').value.trim());
    $('track-reason').value = '';
    reviewTargetKey = key; reviewTargetVersion = track?.evidence_version || '';
    trackReviewStatus(hadDraft ? 'situation.reset' : '');
  } else if (!$('track-reason').value.trim() && !trackReviewBusy) {
    reviewTargetVersion = track?.evidence_version || '';
  }
  const explanation = track?.explanation;
  $('evidence-explanation').innerHTML = explanation ? `<p class="explanation-status">${t('explain.observation')}: ${t(`explain.${explanation.observation_status}`)}<br>${t('explain.evidenceStatus')}: ${t(`explain.${explanation.evidence_status}`)}</p>` + ['known','uncertain','missing'].map(section=>`<section><h3>${t(`explain.${section}`)}</h3><ul>${explanation[section].map(item=>`<li>${escape(t(`rule.${item.code}`))}${item.source_id ? ` · ${escape(item.source_id)}` : ''}<small>${(item.evidence_ids || []).map(escape).join(', ') || t('none')}</small></li>`).join('') || `<li>${t('none')}</li>`}</ul></section>`).join('') : '';
  $('review-version').textContent = track ? t('review.version',{id:track.object_id,version:reviewTargetVersion.slice(0,12)}) : t('awaitingDetection');
  const summary = state.review_summary;
  $('audit-summary').textContent = t('review.counts',{current:summary?.current_run || 0,total:summary?.total_saved || 0});
  updateTrackReviewAvailability();
}
$('queue-filter').onchange = () => {queueFilter=$('queue-filter').value;queuePage=0;renderDetails();};
$('queue-prev').onclick = () => {queuePage--;renderDetails();};
$('queue-next').onclick = () => {queuePage++;renderDetails();};
$('track-reason').oninput = updateTrackReviewAvailability;
$('review-refresh').onclick = () => { $('track-reason').value=''; trackReviewStatus(); renderDetails(); };
$('track-review-form').onsubmit = event => {
  event.preventDefault();
  const track = state?.tracks.find(track=>track.object_id===selected);
  if (!connected || trackReviewBusy || !track || track.evidence_version !== reviewTargetVersion) return;
  const body = {action:'review_track',run_id:state.run_id,object_id:selected,evidence_version:reviewTargetVersion,
    reviewer:$('reviewer').value.trim(),decision:$('track-decision').value,reason:$('track-reason').value.trim()};
  if (!body.reviewer || !body.reason) return;
  const target = reviewTargetKey;
  trackReviewBusy=true;updateTrackReviewAvailability();trackReviewStatus('situation.saving');
  controlChain=controlChain.then(async()=>{
    const version=++requestVersion;
    try {
      const data=await api('/api/control',body);
      if(version===requestVersion)render(data);
      if(reviewTargetKey===target){$('track-reason').value='';trackReviewStatus('review.saved');}
    } catch { if(reviewTargetKey===target)trackReviewStatus('review.failed'); }
    finally {trackReviewBusy=false;updateTrackReviewAvailability();}
  });
};

function reviewStatus(key = '') {
  if (key) $('situation-review-status').dataset.i18n = key;
  else delete $('situation-review-status').dataset.i18n;
  $('situation-review-status').textContent = key ? t(key) : '';
}
function updateReviewAvailability() {
  const unavailable = !connected || reviewPending || !state?.situation?.events?.length;
  for (const id of ['situation-event-select','situation-decision','situation-reason','situation-submit']) $(id).disabled = unavailable;
}
function renderSituation() {
  const situation = state?.situation;
  const events = situation?.events || [];
  const eventSelect = $('situation-event-select');
  const previous = eventSelect.value;
  const changedRun = situationRun !== null && situationRun !== state.run_id;
  const removedEvent = previous && !events.some(event => event.id === previous);
  if (changedRun || removedEvent) {
    const hadDraft = $('situation-reason').value.trim().length > 0;
    $('situation-reason').value = '';
    $('situation-decision').value = 'noted';
    reviewStatus(hadDraft ? 'situation.reset' : '');
  }
  situationRun = state.run_id;
  const optionsSignature = JSON.stringify([language, state.run_id, events.map(event => [event.id,event.title])]);
  if (optionsSignature !== situationOptions) {
    situationOptions = optionsSignature;
    eventSelect.innerHTML = events.map(event => `<option value="${escape(event.id)}">${escape(localized(event.title))} · ${escape(event.id)}</option>`).join('');
    if (!changedRun && events.some(event => event.id === previous)) eventSelect.value = previous;
  }
  updateReviewAvailability();
  const signature = JSON.stringify([language, situation, config?.research_sources]);
  if (signature === situationSignature) return;
  situationSignature = signature;
  const latest = events.at(-1);
  $('situation-stage').textContent = latest ? localized(latest.title) : t('situation.waiting');
  $('situation-count').textContent = t('situation.counts', {count:events.length});
  $('situation-compression').textContent = localized(situation?.time_compression_note);
  const ids = values => (values || []).map(escape).join(', ') || t('none');
  $('situation-events').innerHTML = events.map(event => `<li class="situation-card">
    <h3>${escape(localized(event.title))}</h3><p class="situation-times">${t('situation.observed')} ${fmt(event.observed_at_ms)} · ${t('situation.received')} ${fmt(event.available_at_ms)}${event.story_time ? ` · ${t('situation.storyTime')} ${escape(localized(event.story_time))}` : ''}</p>
    <p>${escape(localized(event.summary))}</p><p class="situation-uncertainty"><strong>${t('situation.uncertainty')}:</strong> ${escape(localized(event.uncertainty))}</p>
    <dl><dt>${t('situation.evidence')}</dt><dd>${ids(event.evidence_ids)}</dd><dt>${t('situation.sourceIds')}</dt><dd>${ids(event.source_ids)}</dd>${event.related_event_id ? `<dt>${t('situation.related')}</dt><dd>${escape(event.related_event_id)}</dd>` : ''}</dl>
    <p class="muted">${escape(event.id)} · ${t('situation.linkedReviews')}: ${(event.related_reviews || []).length}</p>
  </li>`).join('') || `<li class="empty-state">${t('situation.empty')}</li>`;
  const reviews = situation?.review_log || [];
  const decisions = situation?.summary?.decisions || {};
  $('situation-review-counts').textContent = t('situation.reviewCounts', {total:reviews.length,noted:decisions.noted || 0,needs_review:decisions.needs_review || 0,dismissed:decisions.dismissed || 0});
  $('situation-reviews').innerHTML = reviews.map(review => `<li class="situation-card"><dl>
    <dt>${t('situation.event')}</dt><dd>${escape(review.event_id)}</dd>
    <dt>${t('situation.evidence')}</dt><dd>${ids(review.evidence_ids)}</dd>
    <dt>${t('situation.assessment')}</dt><dd>${escape(localized(review.assessment))}</dd>
    <dt>${t('situation.uncertainty')}</dt><dd>${escape(localized(review.uncertainty))}</dd>
    <dt>${t('situation.decision')}</dt><dd>${escape(t(`situation.${review.decision}`))}</dd>
    <dt>${t('situation.reason')}</dt><dd class="situation-reason-text">${escape(review.reason)}</dd>
    <dt>${t('situation.reviewTime')}</dt><dd>${fmt(review.reviewed_at_ms)}</dd>
    </dl><p class="muted">${t('situation.metadata')}: ${escape(review.id)} / ${escape(review.run_id)} / ${escape(review.case_id)}</p></li>`).join('') || `<li class="empty-state">${t('situation.emptyReviews')}</li>`;
  $('situation-sources').innerHTML = (config?.research_sources || []).map(source => {
    let link = escape(source.title);
    try { const url = new URL(source.url); if (['https:','http:'].includes(url.protocol)) link = `<a href="${escape(url.href)}" target="_blank" rel="noopener noreferrer">${link}</a>`; } catch { /* Keep an invalid reference as plain text. */ }
    return `<li class="situation-card"><h3>${link}</h3><p class="muted">${escape(source.publisher)} · ${escape(source.published_at)} · ${escape(source.id)}</p><p><strong>${t('situation.claim')}:</strong> ${escape(localized(source.claim))}</p><p><strong>${t('situation.use')}:</strong> ${escape(localized(source.simulation_use))}</p></li>`;
  }).join('') || `<li class="empty-state">${t('situation.noSources')}</li>`;
}
$('situation-event-select').onchange = () => {
  $('situation-reason').value = '';
  $('situation-decision').value = 'noted';
  reviewStatus();
};
$('situation-review-form').onsubmit = event => {
  event.preventDefault();
  if (reviewPending || !connected || !state?.situation?.events?.length) return;
  const reason = $('situation-reason').value.trim();
  if (!reason) { reviewStatus('situation.required'); $('situation-reason').focus(); return; }
  const body = {action:'review_event',run_id:state.run_id,event_id:$('situation-event-select').value,decision:$('situation-decision').value,reason};
  reviewPending = true; updateReviewAvailability();
  reviewStatus('situation.saving');
  controlChain = controlChain.then(async () => {
    const version = ++requestVersion;
    try {
      const data = await api('/api/control',body);
      if (version === requestVersion) render(data);
      if (state.run_id === body.run_id && $('situation-event-select').value === body.event_id) {
        $('situation-reason').value = '';
        reviewStatus('situation.saved');
      }
    } catch {
      reviewStatus('situation.failed');
    } finally { reviewPending = false; updateReviewAvailability(); }
  });
};

function zoneLabel(zone) { return zone?.label?.[language] || zone?.label?.en || zone?.id || t('early.unknown'); }
function focusZone(id) {
  const zone = state?.early_warning?.zones.find(z=>z.id===id);
  if(!zone)return;
  const [lat,lon]=localToGeo(zone.center[0],zone.center[2],config.regional_map.site_origin);
  Object.assign(region,{lat,lon,zoom:zone.deployment_type==='fixed_phone'?17:14});setMode('region');
}
function deviceHealthHTML(evidence) {
  if (!evidence.device_health) return '';
  const health = evidence.device_health;
  const power = ['external','battery'].includes(health.power_status) ? health.power_status : 'unknown';
  const network = ['online','offline'].includes(health.network_status) ? health.network_status : 'unknown';
  return `<small class="device-health">${t('early.healthAsReported')}: ${t('early.power')} ${t(`early.power.${power}`)} · ${t('early.network')} ${t(`early.network.${network}`)}</small>`;
}
function renderEarlyWarning() {
  const feed=state?.early_warning;
  if(!feed)return;
  $('early-count').textContent=feed.zones.filter(z=>z.positive_sources>0).length;
  // Preserve expanded evidence while incoming data refreshes the cards.
  const open=new Set([...$('early-zones').querySelectorAll('details[open]')].map(d=>d.dataset.zone));
  $('early-zones').innerHTML=feed.zones.map(z=>`<article class="early-zone${z.deployment_type==='fixed_phone'?' fixed-phone-zone':''}">
    <header><h3>${escape(zoneLabel(z))}</h3><button class="button button-secondary" data-zone-focus="${escape(z.id)}">${t('early.focus')}</button></header>
    <p class="deployment-label">${t(`early.deployment.${z.deployment_type === 'fixed_phone' ? 'fixed_phone' : 'community'}`)}</p>
    ${(z.installations || []).length ? `<p class="installation-list">${t('early.installations')}: ${(z.installations || []).map(installation => escape(t('early.mount',{id:installation.sensor_id,height:installation.mount_height_m}))).join(' · ')}</p>` : ''}
    <p><span class="early-status" data-status="${escape(z.status)}">${t(`early.${z.status}`)}</span> · ${t('early.sources',{count:z.positive_sources})}</p>
    <details data-zone="${escape(z.id)}" ${open.has(z.id)?'open':''}><summary>${t('early.evidence')}</summary><ul>${z.evidence.map(e=>`<li><strong>${escape(e.sensor_id)}</strong> · ${t(`early.${e.sensor_type}`)}<br><strong class="report-assessment">${t(e.assessment==='unavailable'?'early.sourceUnavailable':`early.${e.assessment}`)}</strong> · ${t(e.object_present===true?'early.present':e.object_present===false?'early.negative':'early.unknown')}<small>${t('lastObservation')} ${e.observed_at_ms===null?'--:--':fmt(e.observed_at_ms)} · ${t('early.received')} ${fmt(e.available_at_ms)}</small><small>${e.classifier_score===null?t('early.noScore'):t('early.score',{score:e.classifier_score.toFixed(2)})}</small>${deviceHealthHTML(e)}<small>${t('evidence')} ${escape(e.id)}</small></li>`).join('')||`<li>${t('early.empty')}</li>`}</ul></details>
  </article>`).join('')+`<div class="early-footer">${t('early.ttl',{seconds:feed.freshness_ms/1000})} · ${t('early.areaNote')}</div>`;
  $('early-zones').querySelectorAll('[data-zone-focus]').forEach(b=>b.onclick=()=>focusZone(b.dataset.zoneFocus));
}

function planScale() {
  if(mode==='region') return pixelsPerMeter(config.regional_map.site_origin.lat,region.zoom);
  const p = config.site.perimeter;
  return Math.min(map.clientWidth/(p.width_m*1.35), map.clientHeight/(p.length_m*1.6))*plan.zoom;
}
function point(x,z) {
  if(mode==='region') {
    const [lat,lon]=localToGeo(x,z,config.regional_map.site_origin);
    const [px,py]=mercator(lat,lon,region.zoom),[cx,cy]=mercator(region.lat,region.lon,region.zoom);
    return [map.clientWidth/2+px-cx,map.clientHeight/2+py-cy];
  }
  const s=planScale();return [map.clientWidth/2+(x-plan.x)*s,map.clientHeight/2+(z-plan.z)*s];
}
function drawSite() {
  const {site} = config, w=map.clientWidth,h=map.clientHeight,s=planScale();
  overlay.setAttribute('viewBox',`0 0 ${w} ${h}`);
  let svg = '<defs><pattern id="grid" width="50" height="50" patternUnits="userSpaceOnUse"><path d="M 50 0 L 0 0 0 50" fill="none" stroke="#48717a26" stroke-width="1"/></pattern></defs><rect width="100%" height="100%" fill="#0a151b"/><rect width="100%" height="100%" fill="url(#grid)"/>';
  if(mode==='region') svg='';
  const rect=(cx,cz,width,length,fill,stroke,extra='')=>{const [x,y]=point(cx-width/2,cz-length/2),[right,bottom]=point(cx+width/2,cz+length/2);return `<rect x="${x}" y="${y}" width="${right-x}" height="${bottom-y}" fill="${fill}" stroke="${stroke}" ${extra}/>`;};
  for(const z of state?.early_warning?.zones || []){
    const [cx,cy]=point(z.center[0],z.center[2]);
    const active=z.positive_sources>0,color=active?'#dfb86a':'#8bc9cf';
    svg+=`<circle cx="${cx}" cy="${cy}" r="${z.radius_m*s}" fill="${color}18" stroke="${color}" stroke-width="1.5" stroke-dasharray="4 5"/>`;
  }
  const boundary=site.perimeter.polygon.map(([x,z])=>point(x,z).join(',')).join(' ');
  if(mode==='region'){
    svg+=`<polygon points="${boundary}" fill="#263c32" stroke="#263c32" stroke-width="${site.terrain_grading.margin_m*2*s}" stroke-linejoin="round"/>`;
    const [zx,zy]=point(-site.perimeter.width_m/2,site.perimeter.length_m/2+site.terrain_grading.margin_m);
    svg+=`<text x="${zx+5}" y="${zy+17}" fill="#e2eacb" stroke="#14261c" stroke-width="3" paint-order="stroke" font-size="11">${t('site.modified')}</text>`;
  }
  svg+=`<polygon points="${boundary}" fill="${mode==='region'?'#263c32':'#172b2e'}" stroke="#b3c38b" stroke-width="2" stroke-dasharray="6 4"/>`;
  for(const [paths,color] of [[site.roads,'#697569'],[site.taxiways,'#435b60']]){
    for(const path of paths){
      const pts=path.points.map(([x,z])=>point(x,z).join(',')).join(' ');
      svg+=`<polyline points="${pts}" fill="none" stroke="${color}" stroke-width="${Math.max(1,path.width_m*s)}" stroke-linejoin="round"/>`;
      if(paths===site.taxiways)svg+=`<polyline points="${pts}" fill="none" stroke="#c5b77a" stroke-width="0.6"/>`;
    }
  }
  const [sx,sy]=point(-site.perimeter.width_m/2,-site.perimeter.length_m/2);
  svg+=`<text x="${sx+8}" y="${sy+17}" fill="#c4d39a" font-size="11" font-weight="600">${t('sitePlan')}</text>`;
  const r=site.runway;
  svg+=rect(r.center[0],r.center[2],r.width_m,r.length_m,'#354c58','#8fa5ad');
  const [rx,y1]=point(r.center[0],r.center[2]-r.length_m/2+80),[,y2]=point(r.center[0],r.center[2]+r.length_m/2-80);
  svg+=`<line x1="${rx}" y1="${y1}" x2="${rx}" y2="${y2}" stroke="#d9e4e3" stroke-width="1" stroke-dasharray="8 8"/>`;
  for(const a of site.aprons)svg+=rect(a.center[0],a.center[2],a.width_m,a.length_m,'#314743','#78938d');
  const [lx,ly]=point(r.center[0]+80,r.center[2]+r.length_m/2);
  svg+=`<text x="${lx}" y="${ly}" fill="#acc2c8" font-size="10">${t('runway',{length:r.length_m.toLocaleString(language),width:r.width_m})}</text>`;
  for(const f of site.facilities){
    if(f.asset_id==='phone_sensor_pole')continue; // Installation symbols below stay legible at overview scale.
    const size=({hangar:[10,12],arched_hangar:[10.6,12.7],office_building:[6,8],service_building:[6,8],utility_building:[6,8],control_tower:[5.8,5.8],observation_station:[3,3]})[f.asset_id] || [8,8];
    svg+=rect(f.position[0],f.position[2],size[0]*f.scale[0],size[1]*f.scale[2],'#617b74','#a3b6a4');
  }
  for(const zone of site.display_zones || []){
    if(s<0.3 || zone.id==='phone_pilot')continue;
    const [x,y]=point(zone.position[0],zone.position[2]);
    const color=/^#[0-9a-f]{6}$/i.test(zone.color) ? zone.color : '#b5c3be';
    svg+=`<text class="site-zone-label" x="${x}" y="${y}" fill="${color}" font-size="10">${escape(localized(zone.label))}</text>`;
  }
  for(const zone of state?.early_warning?.zones || []){
    for(const installation of zone.installations || []){
      const [x,y]=point(installation.position[0],installation.position[2]);
      const title=t('early.mount',{id:installation.sensor_id,height:installation.mount_height_m});
      svg+=`<g class="fixed-phone-point"><title>${escape(title)}</title><path d="M ${x} ${y+8} V ${y-4}" stroke="#d1c49b" stroke-width="2"/><rect x="${x-3}" y="${y-9}" width="6" height="9" fill="#172b2e" stroke="#d1c49b" stroke-width="1.5"/></g>`;
    }
  }
  for(const t of (state?.tracks || []).filter(track => connected && track.last_known === false)){
    if (state.tracks.length > 48 && t.object_id !== selected) continue;
    const coords=t.history.map(r=>point(r.position[0],r.position[2]).join(',')).join(' ');
    svg+=`<polyline points="${coords}" fill="none" stroke="${t.object_id===selected?'#dfb86a':'#8bc9cf'}" stroke-width="1.5" stroke-dasharray="4 4"/>`;
  }
  svg+=`<text x="20" y="${h-52}" fill="#acc2c8" font-size="10">${t('perimeter',{width:site.perimeter.width_m.toLocaleString(language),length:site.perimeter.length_m.toLocaleString(language)})}</text><text x="${w-28}" y="92" fill="#acc2c8" font-size="11">${t('north')}</text>`;
  overlay.innerHTML=svg;
  markers.replaceChildren();
  markers.classList.toggle('dense-tracks',(state?.tracks.length || 0)>48);
  for(const z of state?.early_warning?.zones || []){
    const [x,y]=point(z.center[0],z.center[2]);
    if(x<0||x>w||y<0||y>h)continue;
    const marker=document.createElement('button');marker.className='area-marker';marker.dataset.status=z.status;
    marker.style.left=`${x}px`;marker.style.top=`${y+(z.deployment_type==='fixed_phone'?-60:0)}px`;
    marker.textContent=zoneLabel(z);marker.title=`${zoneLabel(z)} · ${t(`early.${z.status}`)}`;
    marker.setAttribute('aria-label',`${zoneLabel(z)} · ${t(`early.${z.status}`)} · ${t('early.focus')}`);
    marker.onclick=()=>focusZone(z.id);markers.append(marker);
  }
  for(const t of (state?.tracks || []).filter(track => connected && track.last_known === false)){
    if(!t.position) continue;
    const [x,y]=point(t.position[0],t.position[2]);
    if(x<0||x>w||y<0||y>h) continue;
    const marker=document.createElement('button');
    marker.className=`map-marker ${t.object_id===selected?'is-selected':''}`;
    marker.style.left=`${x}px`;marker.style.top=`${y}px`;
    marker.setAttribute('aria-label',`${t.object_id} ${qualityLabel(t.quality)}`);
    marker.title=`${t.object_id} · ${translate(language,'lastObservation')} ${fmt(t.observed_at_ms)}`;
    marker.classList.toggle('is-stale', Boolean(t.last_known));
    marker.innerHTML=`<span>${escape(t.object_id)}</span>`;
    marker.onclick=()=>select(t.object_id); markers.append(marker);
  }
  if(showPositions && connected) for(const drone of state?.simulation_positions || []){
    const [x,y]=point(drone.position[0],drone.position[2]);
    if(x<0||x>w||y<0||y>h) continue;
    const marker=document.createElement('div');
    marker.className='truth-marker';
    marker.setAttribute('role','img');
    marker.setAttribute('aria-label',`SIM ${drone.object_id}`);
    marker.style.left=`${x}px`;marker.style.top=`${y}px`;
    marker.innerHTML=`<span>SIM ${escape(drone.object_id)}</span>`;
    marker.title=`SIM ${drone.object_id} · ${t('positions.warning')}`;
    markers.append(marker);
  }
  $('map-status').textContent=mode==='region'?t('mapRegionStatus'):t('mapSiteStatus');
}
function drawRegion() {
  drawSite();
  if(noTiles){ $('map-status').textContent=t('mapTestStatus');return; }
  const z=region.zoom,n=2**z,[cx,cy]=mercator(region.lat,region.lon,z),w=map.clientWidth,h=map.clientHeight;
  const left=cx-w/2,top=cy-h/2,needed=new Set();
  $('map-status').textContent=t('mapRegionStatus');
  for(let y=Math.floor(top/256);y<=Math.floor((top+h)/256);y++) for(let x=Math.floor(left/256);x<=Math.floor((left+w)/256);x++){
    if(y<0||y>=n) continue;
    const tx=((x%n)+n)%n,key=`${z}/${x}/${y}`;needed.add(key);
    let img=tileImages.get(key);
    if(!img){
      img=new Image(); img.alt='';img.draggable=false;img.width=256;img.height=256;
      img.style.position='absolute';img.referrerPolicy='strict-origin-when-cross-origin';
      img.src=config.regional_map.tile_url.replace('{z}',z).replace('{x}',tx).replace('{y}',y);
      img.onerror=()=>{if(mode==='region')$('map-status').textContent=t('mapTileError');};
      tileImages.set(key,img);tiles.append(img);
    }
    img.style.left=`${x*256-left}px`;img.style.top=`${y*256-top}px`;
  }
  for(const [key,img] of tileImages) if(!needed.has(key)){img.remove();tileImages.delete(key);}
}
function drawMap(){if(!config)return; if(mode==='site')drawSite();else drawRegion(); drawRadar(state?.at_ms || 0);}
function drawRadar(atMs) {
  if(!config || !state)return;
  const layer=$('radar-overlay');layer.toggleAttribute('hidden',!radarVisible);$('radar-status').hidden=!radarVisible;
  if(!radarVisible)return;
  const frames=radarFrame(config.radar_display,config.site.facilities,state,atMs),s=planScale();
  layer.setAttribute('viewBox',`0 0 ${map.clientWidth} ${map.clientHeight}`);
  layer.innerHTML=frames.map(frame=>{
    const [cx,cy]=point(frame.position[0],frame.position[2]),r=frame.radius*s;
    const online=frame.health==='online'&&connected,color=online?'#8bc9cf':'#71858e';
    const edge=angle=>[cx+Math.sin(angle)*r,cy-Math.cos(angle)*r];
    const [ex,ey]=edge(frame.angle),[tx,ty]=edge(frame.angle-.45);
    return `<circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="${color}" stroke-opacity=".45" stroke-width="1" stroke-dasharray="3 6"/>
      <circle cx="${cx}" cy="${cy}" r="${r/2}" fill="none" stroke="${color}" stroke-opacity=".18"/>
      ${online?`<path d="M${cx} ${cy} L${tx} ${ty} A${r} ${r} 0 0 1 ${ex} ${ey} Z" fill="${color}" fill-opacity=".09"/><path d="M${cx} ${cy}L${ex} ${ey}" stroke="${color}" stroke-opacity=".7"/>`:''}
      <path d="M${cx-4} ${cy}h8 M${cx} ${cy-4}v8" stroke="${color}" stroke-width="2"/>
      <text x="${cx-8}" y="${cy-10}" text-anchor="end" fill="${color}" font-size="9">${escape(frame.id)}${online?'':` · ${escape(connected?sourceLabel(frame.health):t('disconnected'))}`}</text>
      ${online?frame.returns.map(hit=>{const [x,y]=point(hit.position[0],hit.position[2]);return `<circle cx="${x}" cy="${y}" r="${7+hit.progress*17}" fill="none" stroke="#b3eeb6" stroke-width="2" opacity="${1-hit.progress*.8}"/>`;}).join(''):''}`;
  }).join('');
  const count=frames.reduce((n,f)=>n+(connected?f.returns.length:0),0);
  const status=`${t('radar.note')} · ${t(state.playing&&connected?'radar.live':'radar.paused')} · ${t('radar.returns',{count})}`;
  if($('radar-status').textContent!==status)$('radar-status').textContent=status;
}
$('positions-toggle').onclick=async()=>{
  showPositions=!showPositions;
  $('positions-toggle').classList.toggle('is-active',showPositions);
  $('positions-toggle').setAttribute('aria-pressed',showPositions);
  $('positions-status').hidden=!showPositions;
  if(state) delete state.simulation_positions;
  drawMap();
  const version=++requestVersion;
  try {
    const data=await api(showPositions?'/api/state?show_positions=1':'/api/state');
    if(version===requestVersion) render(data);
  } catch { if(version===requestVersion) connection(false); }
};
$('radar-toggle').onclick=()=>{radarVisible=!radarVisible;$('radar-toggle').classList.toggle('is-active',radarVisible);$('radar-toggle').setAttribute('aria-pressed',radarVisible);drawRadar(state?.at_ms || 0);};
function animateRadar(now) {
  if(state?.playing && radarVisible && connected && !$('monitor-view').hidden)
    drawRadar(replayTime(state,clockReceivedAt,now,connected));
  requestAnimationFrame(animateRadar);
}
requestAnimationFrame(animateRadar);

function setMode(next){
  mode=next;
  map.dataset.mode=mode;
  $('site-plan-button').classList.toggle('is-active',mode==='site');$('site-plan-button').setAttribute('aria-pressed',mode==='site');
  $('region-map-button').classList.toggle('is-active',mode==='region');$('region-map-button').setAttribute('aria-pressed',mode==='region');
  tiles.hidden=mode!=='region';$('map-attribution').hidden=mode!=='region';
  document.querySelector('.map-legend').hidden=false; drawMap();
}
function zoom(delta){ if(mode==='site')plan.zoom=Math.max(.5,Math.min(30,plan.zoom*(delta>0?1.35:1/1.35)));else region.zoom=Math.max(3,Math.min(18,region.zoom+delta)); drawMap(); }
$('site-plan-button').onclick=()=>setMode('site');$('region-map-button').onclick=()=>setMode('region');
$('zoom-in').onclick=()=>zoom(1);$('zoom-out').onclick=()=>zoom(-1);
$('recenter').onclick=()=>{plan.x=plan.z=0;plan.zoom=1;Object.assign(region,{lat:config.regional_map.center_lat,lon:config.regional_map.center_lon,zoom:config.regional_map.zoom});drawMap();};
let drag=null;
map.addEventListener('pointerdown',e=>{if(e.button!==0||e.target.closest('button,a'))return;drag={x:e.clientX,y:e.clientY};map.setPointerCapture(e.pointerId);});
map.addEventListener('pointermove',e=>{if(!drag)return;const dx=e.clientX-drag.x,dy=e.clientY-drag.y;drag={x:e.clientX,y:e.clientY};
  if(mode==='site'){plan.x-=dx/planScale();plan.z-=dy/planScale();}
  else{const [x,y]=mercator(region.lat,region.lon,region.zoom);[region.lat,region.lon]=unproject(x-dx,y-dy,region.zoom);region.lat=Math.max(-85,Math.min(85,region.lat));region.lon=((region.lon+180)%360+360)%360-180;}
  drawMap();});
map.addEventListener('pointerup',()=>drag=null);map.addEventListener('pointercancel',()=>drag=null);
map.addEventListener('wheel',e=>{e.preventDefault();zoom(e.deltaY<0?1:-1);},{passive:false});
map.addEventListener('keydown',e=>{if(e.key==='+'||e.key==='=')zoom(1);else if(e.key==='-')zoom(-1);});
new ResizeObserver(drawMap).observe(map);
function runTestRequest(makeBody) {
  try {
    const body = makeBody();
    if (!body) return;
    $('test-run-error').textContent = '';
    return control(body);
  } catch {
    $('test-run-error').textContent = t('test.invalidSeed');
    $('test-seed').focus();
  }
}
$('test-run-form').onsubmit=event=>{event.preventDefault();runTestRequest(()=>testRunRequest($('test-seed').value,state?.case_id));};
$('test-repeat-button').onclick=()=>runTestRequest(()=>repeatTestRequest(state));
$('test-seed').oninput=()=>{$('test-run-error').textContent='';};
$('play-button').onclick=()=>{
  if (!state.playing && state.test_run?.mode !== 'seeded' && !$('test-seed').reportValidity()) return;
  return runTestRequest(()=>playbackRequest(state,$('test-seed').value));
};
$('reset-button').onclick=()=>control({action:'reset'});
$('case-select').onchange=e=>control({action:'case',case_id:e.target.value});
$('speed-select').onchange=e=>control({action:'speed',speed:Number(e.target.value)});
$('timeline').onchange=e=>control({action:'seek',at_ms:Number(e.target.value)});
$('timeline').oninput=e=>$('time-label').textContent=`${fmt(Number(e.target.value))} / ${fmt(state?.duration_ms || 0)}`;
function showView(view) {
  const monitor=view!=='alerts';$('monitor-view').hidden=!monitor;$('alerts-view').hidden=monitor;
  $(monitor?'map-events-host':'alerts-events-host').append($('received-events-panel'));
  for(const b of document.querySelectorAll('[data-view]')){const active=b.dataset.view===(monitor?'monitor':'alerts');b.classList.toggle('is-active',active);if(active)b.setAttribute('aria-current','page');else b.removeAttribute('aria-current');}drawMap();
}
for(const tab of document.querySelectorAll('[data-view]'))tab.onclick=()=>showView(tab.dataset.view);

function renderNotificationSettings() {
  if(!notifier)return;
  const status=notifier.getState();
  $('notification-toggle').textContent=t(status.optedIn?'notify.disable':'notify.enable');
  $('notification-toggle').setAttribute('aria-pressed',String(status.enabled));
  $('notification-toggle').disabled=notificationBusy || (!status.supported && !status.optedIn);
  $('notification-current').disabled=notificationBusy || !status.optedIn || status.permission!=='granted' || !connected;
  const key=notificationBusy?'notify.pending':!status.supported?'notify.unsupported':status.permission==='denied'?'notify.denied':status.error?'notify.failed':notificationMessage || (status.enabled?(connected?'notify.on':'notify.disconnected'):'notify.off');
  $('notification-status').textContent=t(key);
}
function notificationText(alerts, snapshot) {
  const subjects=alerts.slice(0,3).map(alert=>{
    if(alert.kind==='early_warning')return zoneLabel(snapshot.early_warning?.zones.find(z=>z.id===alert.zone_id));
    return `${alert.object_id || alert.source_id || ''} · ${t(['contradictory','not_comparable','stale','channel'].includes(alert.kind)?`alert.${alert.kind}`:'alert.unknown')}`;
  });
  if(alerts.length>3)subjects.push(t('notify.more',{count:alerts.length-3}));
  return {title:t('notify.notificationTitle',{count:alerts.length}),body:t('notify.notificationBody',{caseId:snapshot.case_id,time:fmt(snapshot.at_ms),subjects:subjects.join(' · ')})};
}
async function notifyCurrentAlerts() {
  // Read fresh received evidence; never send a disconnected cached screen.
  const version=++requestVersion;
  const data=await api('/api/state');
  if(version!==requestVersion){notificationMessage='notify.failed';return;}
  render(data);
  const result=await notifier.notifyCurrent(data);
  notificationMessage=({sent:'notify.sent',duplicate:'notify.duplicate',empty:'notify.empty',error:'notify.failed'})[result.status] || '';
}
$('notification-toggle').onclick=async()=>{
  if(notifier.getState().optedIn){notifier.setEnabled(false);notificationMessage='';renderNotificationSettings();return;}
  notificationBusy=true;notificationMessage='';renderNotificationSettings();
  try {
    // Keep requestPermission in the user gesture, before any network/worker await.
    const permission=Notification.permission==='granted'?'granted':await Notification.requestPermission();
    if(permission==='granted'){
      notifier.setEnabled(true);
      notifier.resetBaseline();
      await notifyCurrentAlerts();
    }else notificationMessage=permission==='denied'?'notify.denied':'notify.dismissed';
  }catch{notificationMessage='notify.failed';}
  finally{notificationBusy=false;renderNotificationSettings();}
};
$('notification-current').onclick=async()=>{
  notificationBusy=true;renderNotificationSettings();
  try{await notifyCurrentAlerts();}catch{notificationMessage='notify.failed';}
  finally{notificationBusy=false;renderNotificationSettings();}
};
window.addEventListener('beforeinstallprompt',event=>{event.preventDefault();installPrompt=event;$('pwa-install').hidden=false;});
$('pwa-install').onclick=async()=>{
  const prompt=installPrompt;if(!prompt)return;
  installPrompt=null;$('pwa-install').hidden=true;
  try{await prompt.prompt();}catch{ /* Browser menu remains available. */ }
};
window.addEventListener('appinstalled',()=>{$('pwa-install').hidden=true;installPrompt=null;});
function renderBriefing() {
  const caseId=state?.case_id || $('case-select').value;
  const brief=briefings.find(b=>b.case_id===caseId);
  if(!brief)return;
  const seeded = state?.test_run?.mode === 'seeded';
  const signature=`${caseId}:${language}:${seeded}`;
  if(signature===briefingSignature)return;
  briefingSignature=signature;
  const values={group:brief.group,object:brief.comparison_object || '',marker:brief.original_marker?t(`marker.${brief.original_marker}`):'',seconds:brief.sample_interval_ms/1000};
  $('brief-title').textContent=`${brief.case_id} · ${localized(brief.name) || t(`brief.title.${brief.variant}`,values)}`;
  $('brief-purpose').textContent=localized(brief.summary) || t(`brief.purpose.${brief.variant}`,values);
  $('brief-meta').textContent=t('brief.meta',{duration:fmt(brief.duration_ms),objects:brief.object_ids.length,sources:brief.source_ids.length});
  $('brief-preview-note').textContent=t(seeded?'test.templateReference':'brief.preview');
  $('brief-timeline').classList.toggle('reference-timeline',seeded);
  $('brief-timeline').innerHTML=brief.timeline.map(step=>`<li>${seeded?'':`<time>${fmt(step.at_ms)}</time>`}<span>${escape(localized(step.text) || t(step.key,values))}</span></li>`).join('');
  $('brief-review').textContent=localized(brief.objective) || t(`brief.review.${brief.variant}`,values);
  $('brief-objects').textContent=[localized(brief.composition),localized(brief.count_basis)].filter(Boolean).join(' ');
}

function renderCases() {
  if (!config) return;
  const current = state?.case_id || $('case-select').value;
  $('case-select').innerHTML = config.cases.map(c => `<option value="${escape(c.case_id)}">${escape(c.case_id)} · ${escape(localized(briefings.find(b=>b.case_id===c.case_id)?.name) || t(`variant.${c.variant}`))}</option>`).join('');
  if (current) $('case-select').value = current;
}
function applyLanguage(next, persist = false) {
  language = normalizeLanguage(next);
  if (persist) { try { saveLanguage(localStorage, language); } catch { /* Storage may be unavailable. */ } }
  document.documentElement.lang = language;
  document.title = t('title');
  $('language-select').value = language;
  for (const element of document.querySelectorAll('[data-i18n]')) element.textContent = t(element.dataset.i18n);
  for (const attribute of ['aria-label','title']) {
    for (const element of document.querySelectorAll(`[data-i18n-${attribute}]`)) {
      element.setAttribute(attribute, t(element.getAttribute(`data-i18n-${attribute}`)));
    }
  }
  for (const element of document.querySelectorAll('[data-empty]')) element.dataset.empty = t('waitingData');
  renderCases();
  renderBriefing();
  if (state) { renderPlayback(state); renderDetails(); renderEarlyWarning(); renderSituation(); renderWorkload(); renderAssessment(); renderDecisions(); }
  drawMap();
  if (connected !== null) connection(connected, connectionMessage);
  if (!config && connected === false) $('map-status').textContent = t('requestFailed');
  renderNotificationSettings();
}
$('language-select').onchange = event => {applyLanguage(event.target.value, true);syncDecisionLanguage();};
let notificationStorage;
try{notificationStorage=localStorage;}catch{ /* Session-only opt-in if storage is unavailable. */ }
const notificationSupported=isSecureContext && 'Notification' in window && 'serviceWorker' in navigator && 'MessageChannel' in window;
const registrationPromise=isSecureContext && 'serviceWorker' in navigator
  ? navigator.serviceWorker.register('/sw.js').catch(()=>null) : Promise.resolve(null);
notifier=createNotificationController({registration:registrationPromise,storage:notificationStorage,supported:notificationSupported,getPermission:()=>notificationSupported?Notification.permission:'default',formatMessage:notificationText,onChange:()=>renderNotificationSettings()});
if('serviceWorker' in navigator)navigator.serviceWorker.addEventListener('message',event=>{if(event.data?.type==='open-alerts')showView('alerts');});
if(new URLSearchParams(location.search).get('view')==='alerts')showView('alerts');
window.addEventListener('focus',()=>renderNotificationSettings());
window.addEventListener('storage',event=>{if(event.key===NOTIFICATION_STORAGE_KEY){notifier.setEnabled(event.newValue==='1');notificationMessage='';renderNotificationSettings();}});
applyLanguage(language);
try{
  config=await api('/api/config');
  renderCases();
  Object.assign(region,{lat:config.regional_map.center_lat,lon:config.regional_map.center_lon,zoom:config.regional_map.zoom});
  setMode('site');poll();pollAssessment();pollDecisions();
  api('/api/briefings').then(data=>{briefings=data.cases;renderCases();renderBriefing();}).catch(()=>{$('brief-purpose').textContent=t('brief.unavailable');});
}catch(error){connection(false,'startServer');$('map-status').textContent=t('requestFailed');}
