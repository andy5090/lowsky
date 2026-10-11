import {enhanceSelects} from './custom_selects.mjs';
import {CUSTOM_MODEL, modelOptions, modelsCommand, initialDraft, draftProblem, saveCommand, removeKeyCommand, testCommand, keyStatus} from './agent_settings.mjs';
import {desktopCommand, desktopShortcut, acceptDesktopState} from './desktop.mjs';
import {localToGeo, mercator, unproject, pixelsPerMeter, mapToLocal} from './geo.mjs';
import {radarFrame, replayTime} from './radar.mjs';
import {reviewQueue, commentSuggestions, reviewComment} from './review.mjs';
import {indicationOverview, earlyIndicationSummary, decisionCopyKey, DASHBOARD_ACTIONS, dashboardCard, dashboardDraft, dashboardDraftValid, dashboardConfirmation} from './dashboard.mjs';
import {exerciseConfirmation, exerciseMissionRows, exerciseMapAssets, exerciseUnitCommand, unitBudget, RADAR_ADJUSTMENT_ACTIONS, pendingRadarAdjustment, radarAdjustmentApplicable, radarAdjustmentCommand} from './exercise.mjs';
import {TACTICS_SCOPE, UNIT_KINDS, tacticsTarget, allocationDraft, allocationDraftValid, allocationCommand, placementSummary, proposalPositions, formationRows} from './tactics.mjs';
import {activeDecision, decisionReport, decisionOpen, selectDecision, decisionDraftStatus, decisionConfirmation, decisionStatusKey} from './decisions.mjs';
import {testRunRequest, playbackRequest, repeatTestRequest} from './test_runs.mjs';
import {translate, readLanguage, saveLanguage, normalizeLanguage, triggerValue, triggerSubject, localizedValue} from './i18n.mjs';
import {createAlertPriorityPolicy, priorityAlertKey, createNotificationController, NOTIFICATION_STORAGE_KEY} from './notifications.mjs';
import {createAlertAudioController, ALERT_AUDIO_STORAGE_KEY} from './alert_audio.mjs';
const $ = id => document.getElementById(id);
const customSelects=enhanceSelects(document);
let selectSyncQueued=false;
function syncSelects() {
  if(selectSyncQueued)return;
  selectSyncQueued=true;
  queueMicrotask(()=>{selectSyncQueued=false;customSelects.sync();});
}
const escape = value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let language = 'en';
try { language = readLanguage(localStorage); } catch { /* Storage may be unavailable. */ }
const t = (key, values) => translate(language, key, values);
const localized = value => localizedValue(language,value);
const qualityLabel = quality => t(`quality.${quality}`);
const sourceLabel = status => t(`source.${status}`);
let connected = null, connectionMessage = '';
let desktopState=null,desktopBusy=false,desktopConnected=false,desktopError=false,desktopRequestVersion=0;
const fmt = ms => `${String(Math.floor(ms / 60000)).padStart(2,'0')}:${String(Math.floor(ms / 1000) % 60).padStart(2,'0')}`;
let briefings = [], briefingSignature = '';
let situationSignature = '', situationRun = null, situationOptions = '', reviewPending = false;
let config, state, selected, mode = 'site', dataSignature = '', requestVersion = 0;
let controlChain = Promise.resolve();
let notifier, alertAudio, notificationBusy = false, notificationMessage = '', installPrompt;
let assessment = null, assessmentBusy = false, assessmentLastAttempt = 0, assessmentFailure = false;
let assessmentSignature = '';
let decisions = null, decisionBusy = false, decisionDraft = null, decisionError = '', decisionSignature = '';
let decisionLanguagePending = false, decisionAvailable = false;
let decisionNoticeRun = null;
const alertPriority=createAlertPriorityPolicy();
let priorityQueue=[],priorityExpiredChoice=null,priorityToastTimer=null;
let rehearsals = null, rehearsalRecords = null, rehearsalBusy = false, rehearsalError = false, rehearsalRequest = 0, rehearsalSignature = '';
let dashboardChoice = null, dashboardBusy = false, dashboardNotice = '', dashboardContext = '';
let exerciseExpired = false;
let exerciseDraft = null, exerciseRun = null, exerciseAt = 0, exerciseBusy = false, exerciseError = false;
let unitPlacement = null, unitBusy = false, unitNotice = '', unitRun = null, unitPendingAction = null;
let tacticsChoice = null, tacticsBusy = false, tacticsNotice = '', tacticsContext = '';
let testOperator = null, operatorBusy = false, operatorError = '';
let queuePage = 0, queueFilter = 'all', queueRun = null;
const selectedComments = {track:'',situation:''};
let trackReviewBusy = false, reviewTargetKey = '', reviewTargetVersion = '';
let showPositions = false, showCorridors = false, geographyCache = null;
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
function renderDesktop() {
  syncSelects();
  $('desktop-controls').hidden=desktopState?.available!==true;
  const options={busy:desktopBusy,connected:desktopConnected};
  $('desktop-open-3d').disabled=!desktopCommand(desktopState,'open_3d',options);
  $('desktop-close-3d').disabled=!desktopCommand(desktopState,'close_3d',options);
  $('desktop-fullscreen').disabled=!desktopCommand(desktopState,'toggle_monitor_fullscreen',options);
  $('desktop-fullscreen').textContent=t(desktopState?.fullscreen?'desktop.exitFullscreen':'desktop.enterFullscreen');
  $('desktop-fullscreen').setAttribute('aria-pressed',String(Boolean(desktopState?.fullscreen)));
  $('desktop-status').textContent=desktopBusy || desktopState?.pending?t('desktop.pending'):desktopError || desktopState?.error?t('desktop.failed'):'';
}
async function pollDesktop() {
  const version=desktopRequestVersion;
  if(!desktopBusy)try {
    const result=await api('/api/desktop');
    if(version===desktopRequestVersion){desktopState=acceptDesktopState(desktopState,result);desktopConnected=true;desktopError=false;renderDesktop();}
  }catch{if(version===desktopRequestVersion){desktopConnected=false;desktopError=desktopState?.available===true;renderDesktop();}}
  setTimeout(pollDesktop,1000);
}
async function desktopAction(action) {
  const body=desktopCommand(desktopState,action,{busy:desktopBusy,connected:desktopConnected});
  if(!body)return;
  desktopBusy=true;desktopError=false;const version=++desktopRequestVersion;renderDesktop();
  try {
    const result=await api('/api/desktop',body);
    if(version===desktopRequestVersion){desktopState=acceptDesktopState(desktopState,result);desktopConnected=true;}
  }catch{desktopError=true;desktopConnected=false;}
  finally{desktopBusy=false;renderDesktop();}
}
$('desktop-open-3d').onclick=()=>desktopAction('open_3d');
$('desktop-close-3d').onclick=()=>desktopAction('close_3d');
$('desktop-fullscreen').onclick=()=>desktopAction('toggle_monitor_fullscreen');
document.addEventListener('keydown',event=>{
  const body=desktopShortcut(event.key,desktopState,{busy:desktopBusy,connected:desktopConnected,
    editing:Boolean(event.target.closest?.('input,textarea,select,[role="combobox"],[role="listbox"],[contenteditable="true"]')),
    modal:Boolean(document.querySelector('dialog[open]')),repeat:event.repeat,
    modifier:event.altKey || event.ctrlKey || event.metaKey || event.shiftKey});
  if(body){event.preventDefault();desktopAction(body.action);}
});

function connection(ok, message='') {
  syncSelects();
  connected = ok; connectionMessage = message;
  $('connection-status').textContent = ok ? t('connected') : t('disconnected');
  $('connection-status').classList.toggle('is-connected', ok);
  $('connection-status').classList.toggle('disconnected', !ok);
  for (const id of ['play-button','reset-button','case-select','timeline','speed-select','test-run-button','test-seed']) $(id).disabled = !ok;
  $('test-repeat-button').disabled = !ok || !repeatTestRequest(state || {});
  updateReviewAvailability();
  updateTrackReviewAvailability();
  renderNotificationSettings();
  renderExercise();
  if (!ok) { renderDashboard(); renderDecisions(); renderTactics(); }
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
  syncSelects();
  state = data; clockReceivedAt = performance.now(); connection(true);
  renderPlayback(data);
  renderBriefing();
  renderSituation();
  renderWorkload();
  renderAssessment();
  renderDecisions();
  notifier?.observe(data);
  const signature = JSON.stringify([data.run_id,data.tracks,data.sources,data.alerts,data.contexts,data.early_warning,data.reviews,data.track_reviews,data.review_summary,data.simulation_positions,exerciseMapAssets(data),data.exercise?.units,data.exercise?.unit_proposal,data.exercise?.radar_adjustment,data.tactics]);
  if (signature !== dataSignature) {
    dataSignature = signature;
    if(!data.tracks.some(t => t.object_id === selected)) selected = data.tracks[0]?.object_id;
    renderDetails(); renderEarlyWarning(); drawMap();
  }
  renderDashboard();
  renderTactics();
}
function renderPlayback(data) {
  syncSelects();
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
function select(id) { selected = id; renderDetails(); drawMap(); renderDashboard(); renderTactics(); }
function renderDetails() {
  syncSelects();
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
    $('focus-track').onclick = () => { if(track.position){plan.x=track.position[0];plan.z=track.position[2];plan.zoom=8;revealMap();setMode('site');} };
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
  $('events-list').innerHTML = state.sources.map(s=>`<li class="event-item"><time>${s.evidence ? fmt(s.evidence.observed_at_ms) : '--:--'}</time>${escape(s.source_id)} · ${sourceLabel(s.status)}</li>`).join('') + state.contexts.map(c=>`<li class="event-item"><time>${t('published')} ${fmt(c.published_at_ms)}</time>${escape(['context_001','context_002'].includes(c.id)?t(`context.${c.id}`):localized(c.text))}</li>`).join('');
  $('events-list').innerHTML += (state.reviews || []).map(r=>`<li class="event-item"><time>${fmt(r.at_ms)}</time>${escape(t('early.ackEvent',{id:r.alert_id}))}</li>`).join('');
}
function originalReportLabel(report) {
  return t('report.original',{language:t(`report.language.${normalizeLanguage(report.language)}`)});
}
function reportLanguageHTML(report,html) {
  const lang=normalizeLanguage(report.language);
  if(lang===language)return html;
  return `<p class="muted">${escape(t('report.otherLanguage'))}</p><details><summary>${escape(originalReportLabel(report))}</summary><div lang="${lang}">${html}</div></details>`;
}
function renderAssessment() {
  syncSelects();
  $('agent-mode').textContent = t(assessment?.mode==='llm'?'agent.llm':'agent.rules');
  const configurationError = assessment?.configuration_error;
  $('agent-assess').disabled = !connected || !state || assessmentBusy || Boolean(assessment?.running) || Boolean(configurationError);
  $('agent-auto').disabled = Boolean(configurationError) || Boolean(decisions?.enabled);
  if (decisions?.enabled) $('agent-auto').checked = false;
  let status = assessment?.running || assessmentBusy ? 'agent.running' : configurationError ? `agent.${configurationError}` : assessmentFailure || assessment?.error ? 'agent.failed' : assessment?.configured ? 'agent.ready' : 'agent.unconfigured';
  $('agent-status').textContent = `${t(status)}${assessment?.model ? ` (${assessment.model})` : ''}`;
  $('agent-open-settings').hidden = !['missing_api_key','invalid_model','unsupported_provider'].includes(configurationError) && !assessmentFailure && !assessment?.error;
  const report = assessment?.latest?.run_id===state?.run_id ? assessment.latest : null;
  const stale = report && (report.at_ms!==state.at_ms || report.language!==language);
  const signature = JSON.stringify([language,report,Boolean(stale)]);
  if(signature===assessmentSignature)return;
  assessmentSignature=signature;
  $('agent-report').innerHTML = report ? reportLanguageHTML(report,`<p class="agent-summary">${escape(report.summary)}</p><p class="muted">${escape(t('agent.basis',{caseId:report.case_id,time:fmt(report.at_ms),mode:report.mode==='llm'?report.model:t(report.mode==='standard'?'decision.standard':'agent.rules')}))}${stale?` · ${t('agent.stale')}`:''}</p><div class="agent-findings">${['known','uncertain','review_items'].map(section=>`<section><h3>${t(`agent.${section}`)}</h3><ul>${report[section].map(item=>`<li>${escape(item.text)}<small>${item.evidence_ids.map(escape).join(', ')}</small></li>`).join('') || `<li>${t('none')}</li>`}</ul></section>`).join('')}</div>`) : `<p class="empty-state">${t('agent.empty')}</p>`;
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

// AI settings dialog: provider, model and a write-only API key kept on this computer by the server.
let agentSettings=null, settingsDraft=null, settingsBusy=false, settingsNotice='', settingsNoticeValues={};
let fetchedModels={openai:[],anthropic:[]};
function settingsLabel(row){
  if(row.id===CUSTOM_MODEL)return t('settings.customOption');
  return row.label?localized(row.label):row.id;
}
function readSettingsDraft(){
  if(!settingsDraft)return;
  settingsDraft.provider=document.querySelector('input[name="agent-provider"]:checked')?.value || settingsDraft.provider;
  settingsDraft.model=$('agent-settings-model').value || settingsDraft.model;
  settingsDraft.custom=$('agent-settings-custom').value;
  settingsDraft.api_key=$('agent-settings-key').value;
}
function renderAgentSettings(){
  syncSelects();
  const dialog=$('agent-settings-dialog');
  if(!dialog.open || !settingsDraft)return;
  const draft=settingsDraft, llm=draft.provider!=='rules';
  for(const input of document.querySelectorAll('input[name="agent-provider"]')){input.checked=input.value===draft.provider;input.disabled=settingsBusy;}
  $('agent-settings-llm').hidden=!llm;
  const options=llm?modelOptions(agentSettings,draft.provider,fetchedModels[draft.provider] || []):[];
  const signature=JSON.stringify([language,draft.provider,options]);
  if($('agent-settings-model').dataset.signature!==signature){
    $('agent-settings-model').dataset.signature=signature;
    $('agent-settings-model').innerHTML=options.map(row=>`<option value="${escape(row.id)}">${escape(settingsLabel(row))}</option>`).join('');
  }
  if(llm){
    if(!options.some(row=>row.id===draft.model)){draft.custom=draft.model;draft.model=CUSTOM_MODEL;$('agent-settings-custom').value=draft.custom;}
    $('agent-settings-model').value=draft.model;
  }
  $('agent-settings-custom-field').hidden=draft.model!==CUSTOM_MODEL;
  $('agent-settings-key').placeholder=t(draft.provider==='anthropic'?'settings.keyPlaceholder.anthropic':'settings.keyPlaceholder.openai');
  const status=keyStatus(agentSettings,draft.provider);
  $('agent-settings-key-status').textContent=t(status.key,{hint:status.hint || ''});
  $('agent-settings-load-error').hidden=agentSettings?.load_error!=='corrupt_settings_file';
  for(const id of ['agent-settings-model','agent-settings-custom','agent-settings-key'])$(id).disabled=settingsBusy;
  $('agent-settings-remove').hidden=!removeKeyCommand(agentSettings,draft);
  $('agent-settings-remove').disabled=settingsBusy;
  $('agent-settings-test').disabled=settingsBusy || !testCommand(agentSettings,draft);
  $('agent-settings-models').disabled=settingsBusy || !modelsCommand(agentSettings,draft);
  $('agent-settings-save').disabled=settingsBusy || !saveCommand(agentSettings,draft);
  const problem=draftProblem(agentSettings,draft);
  $('agent-settings-status').textContent=settingsBusy?t('settings.working'):settingsNotice?t(settingsNotice,settingsNoticeValues):problem?t(problem):'';
}
async function openAgentSettings(){
  const dialog=$('agent-settings-dialog');
  settingsNotice='';settingsNoticeValues={};
  try {agentSettings=await api('/api/agent-settings');}
  catch {agentSettings=null;settingsNotice='settings.loadFailed';}
  settingsDraft=initialDraft(agentSettings);
  fetchedModels={openai:[],anthropic:[]};
  $('agent-settings-key').value='';$('agent-settings-custom').value='';
  if(!dialog.open)dialog.showModal();
  renderAgentSettings();
  (document.querySelector('input[name="agent-provider"]:checked') || $('agent-settings-close')).focus();
}
function closeAgentSettings(){
  // Clear the key field so a typed secret does not linger in the page.
  $('agent-settings-key').value='';settingsDraft=null;
  if($('agent-settings-dialog').open)$('agent-settings-dialog').close();
}
async function agentSettingsRequest(body,kind){
  if(!body || settingsBusy)return;
  settingsBusy=true;settingsNotice='';settingsNoticeValues={};renderAgentSettings();
  try {
    const result=await api('/api/agent-settings',body);
    if(kind==='models'){
      if(result.ok){fetchedModels[body.provider]=result.models || [];settingsNotice=result.models?.length?'settings.models.loaded':'settings.models.empty';settingsNoticeValues={count:result.models?.length || 0};}
      else {settingsNotice=`settings.test.${result.code}`;settingsNoticeValues={model:'',status:result.status ?? ''};}
    } else if(kind==='test'){
      settingsNotice=`settings.test.${result.code}`;settingsNoticeValues={model:result.model || draftModel(settingsDraft),status:result.status ?? ''};
      // A working key can list the other models it may use, so offer them right away.
      const listing=result.ok?modelsCommand(agentSettings,settingsDraft):null;
      if(listing){const models=await api('/api/agent-settings',listing).catch(()=>null);if(models?.ok)fetchedModels[listing.provider]=models.models || [];}
    } else {
      agentSettings=result;
      const provider=settingsDraft.provider;
      settingsDraft={...initialDraft(result),provider,
        model:result.providers?.[provider]?.saved_model || result.providers?.[provider]?.default_model || settingsDraft.model};
      $('agent-settings-key').value='';
      settingsNotice=kind==='remove'?'settings.removed':'settings.saved';
      assessment=await api('/api/assessment').catch(()=>assessment);renderAssessment();
    }
  } catch(error) {settingsNotice='settings.failed';settingsNoticeValues={detail:String(error.message || '').slice(0,200)};}
  finally {settingsBusy=false;renderAgentSettings();}
}
function draftModel(draft){return draft?.model===CUSTOM_MODEL?draft.custom.trim():draft?.model;}
$('agent-settings-open').onclick=openAgentSettings;
$('agent-open-settings').onclick=openAgentSettings;
$('agent-settings-close').onclick=closeAgentSettings;
$('agent-settings-dialog').addEventListener('cancel',event=>{event.preventDefault();if(!settingsBusy)closeAgentSettings();});
$('agent-settings-form').addEventListener('submit',event=>event.preventDefault());
for(const input of document.querySelectorAll('input[name="agent-provider"]'))input.onchange=()=>{
  readSettingsDraft();
  const info=agentSettings?.providers?.[settingsDraft.provider];
  settingsDraft.model=info?.saved_model || info?.default_model || '';settingsDraft.custom='';settingsDraft.clear_key=false;
  $('agent-settings-key').value='';$('agent-settings-custom').value='';settingsDraft.api_key='';settingsNotice='';
  renderAgentSettings();
};
$('agent-settings-model').onchange=()=>{readSettingsDraft();settingsNotice='';renderAgentSettings();if(settingsDraft.model===CUSTOM_MODEL)$('agent-settings-custom').focus();};
for(const id of ['agent-settings-custom','agent-settings-key'])$(id).oninput=()=>{readSettingsDraft();settingsNotice='';renderAgentSettings();};
// A different key may see different models; drop the list loaded with the previous key.
$('agent-settings-key').addEventListener('change',()=>{if(settingsDraft)fetchedModels[settingsDraft.provider]=[];renderAgentSettings();});
$('agent-settings-save').onclick=()=>{readSettingsDraft();agentSettingsRequest(saveCommand(agentSettings,settingsDraft),'save');};
$('agent-settings-test').onclick=()=>{readSettingsDraft();agentSettingsRequest(testCommand(agentSettings,settingsDraft),'test');};
$('agent-settings-models').onclick=()=>{readSettingsDraft();agentSettingsRequest(modelsCommand(agentSettings,settingsDraft),'models');};
$('agent-settings-remove').onclick=()=>{readSettingsDraft();agentSettingsRequest(removeKeyCommand(agentSettings,settingsDraft),'remove');};
// The desktop menu and links can open the dialog directly.
window.addEventListener('lowsky:open-agent-settings',openAgentSettings);
if(location.hash==='#agent-settings')queueMicrotask(openAgentSettings);
$('agent-auto').onchange=()=>{if($('agent-auto').checked)runAssessment();};

function decisionText(key) {
  const primary = `<span lang="${language}">${escape(t(key))}</span>`;
  if (!$('decision-bilingual').checked) return primary;
  const other = language === 'en' ? 'ko' : 'en';
  return `${primary}<small class="decision-translation" lang="${other}">${escape(translate(other,key))}</small>`;
}
$('decision-bilingual').onchange=()=>{decisionSignature='';renderDecisions();};

function currentDecision() {
  if (!decisions || !state || decisions.run_id !== state.run_id) return null;
  return activeDecision(decisions.events || [], decisionDraft);
}
function renderIndications() {
  syncSelects();
  const summary=earlyIndicationSummary(state);
  $('indication-stage').textContent=t(`indication.stage.${summary.stage}`);
  $('indication-summary').textContent=t('indication.summary',{zones:summary.zone_count,positive:summary.positive,tracks:summary.track_count});
  $('indication-overview').disabled=!config || summary.positive===0;
  $('map-indication-overview').disabled=!config || summary.positive===0;
  $('indication-assess').disabled=!connected || !state || decisionBusy || !summary.zone_count || currentDecision()?.status==='evaluating';
  const signature=JSON.stringify([language,summary]);
  if($('indication-zones').dataset.signature!==signature) {
    $('indication-zones').dataset.signature=signature;
    const ranked=[...summary.zones].sort((a,b)=>Number(b.conflict)-Number(a.conflict) || b.positive-a.positive);
    $('indication-zones').innerHTML=ranked.slice(0,3).map(zone=>`<div><strong>${escape(zoneLabel(state.early_warning.zones.find(item=>item.id===zone.id)))}</strong><button type="button" class="button button-secondary" data-indication-focus="${escape(zone.id)}" aria-label="${escape(t('indication.focusArea',{area:zoneLabel(state.early_warning.zones.find(item=>item.id===zone.id))}))}">${escape(t('early.focus'))}</button><span>${escape(t('indication.quality',{current:zone.current,stale:zone.stale,unavailable:zone.unavailable}))}${zone.conflict?` · ${escape(t('indication.conflict'))}`:''}</span><small>${escape(t('indication.lastReceived',{time:fmt(zone.latest_received_ms)}))}</small></div>`).join('') || `<p class="muted">${escape(t('indication.empty'))}</p>`;
    $('indication-zones').querySelectorAll('[data-indication-focus]').forEach(button=>button.onclick=()=>focusZone(button.dataset.indicationFocus));
    if(ranked.length>3)$('indication-zones').innerHTML+=`<p class="muted">${escape(t('indication.more',{count:ranked.length-3}))}</p>`;
  }
}
$('indication-assess').onclick=()=>decisionAction({action:'assess_current',language});
$('indication-signals').onclick=()=>showPanel('signals');
function showIndicationOverview() {
  if(!config || !state)return;
  revealMap();
  // Georeferenced areas beyond the local terrain extent are shown on the regional map; schematic areas stay on the site plan.
  const schematic=(state.early_warning?.zones || []).some(schematicZone);
  const view=indicationOverview(state,config.site.perimeter,{width:map.clientWidth,height:map.clientHeight},schematic?Infinity:config.regional_map.terrain_extent_m ?? Infinity);
  if(!view)return;
  if(view.beyond_local){
    const [lat,lon]=localToGeo(view.x,view.z,config.regional_map.site_origin);
    const fit=Math.floor(Math.log2(.8*Math.min(map.clientWidth/Math.max(1,view.width_m),map.clientHeight/Math.max(1,view.height_m))/pixelsPerMeter(lat,0)));
    Object.assign(region,{lat,lon,zoom:Math.max(3,Math.min(18,Number.isFinite(fit)?fit:10))});setMode('region');
  } else {Object.assign(plan,{x:view.x,z:view.z,zoom:view.zoom});setMode('site');}
  map.focus({preventScroll:true});
}
$('indication-overview').onclick=showIndicationOverview;
$('map-indication-overview').onclick=showIndicationOverview;

function dismissPriority() {
  const key=$('priority-dialog').dataset.noticeKey;
  priorityQueue=priorityQueue.filter(notice=>notice.key!==key);
  if($('priority-dialog').open)$('priority-dialog').close();
}
function openPriority() {
  const notice=priorityQueue[0];
  if(!notice || document.hidden || document.querySelector('dialog[open]'))return;
  $('priority-dialog').dataset.noticeKey=notice.key;
  $('priority-message').textContent=t(`priority.${notice.kind}`);
  $('priority-context').textContent=t('priority.time',{time:fmt(state.at_ms)});
  $('priority-review').hidden=notice.kind==='choice_expired' && !currentDecision();
  $('priority-dialog').showModal();
  $('priority-toast').hidden=true;
}
function priorityToast(message) {
  clearTimeout(priorityToastTimer);
  $('priority-toast-text').textContent=message;
  $('priority-toast').hidden=false;
  priorityToastTimer=setTimeout(()=>{$('priority-toast').hidden=true;},8000);
}
function renderPriorityAlerts() {
  syncSelects();
  if(!state)return;
  const event=currentDecision();
  const updates=alertPriority.observe(state,event,{expiredChoice:priorityExpiredChoice});
  alertAudio?.observe({...state,connected},updates);
  priorityExpiredChoice=null;
  if(updates.reset){priorityQueue=[];$('priority-toast').hidden=true;clearTimeout(priorityToastTimer);}
  priorityQueue=priorityQueue.filter(notice=>connected && notice.run_id===state.run_id && notice.expires_at_ms>state.at_ms
    && (notice.kind==='choice_expired' || (event?.id===notice.event_id && decisionOpen(event))));
  if($('priority-dialog').open && !priorityQueue.some(notice=>notice.key===$('priority-dialog').dataset.noticeKey))$('priority-dialog').close();
  if(connected)for(const notice of updates.high) {
    priorityQueue.push({...notice,run_id:state.run_id});
    // The same opted-in delivery path handles minimized windows without low-priority noise.
    notifier?.notifyCurrent({...state,alerts:[{id:`priority:${notice.key}`,kind:notice.kind==='direct_transition'?'review_transition':'review_expired',acknowledged:false}]});
  }
  if(updates.medium.length && connected && !priorityQueue.length)priorityToast(t('priority.updated',{count:updates.medium.length}));
  if(priorityQueue.length && !$('priority-dialog').open) {
    const editing=document.activeElement?.matches('input,textarea,select,[role="combobox"],[role="listbox"],[contenteditable="true"]');
    if(!editing && !document.querySelector('dialog[open]'))openPriority();
    else if(updates.high.length)priorityToast(t('priority.queued'));
  }
  if($('priority-dialog').open)$('priority-context').textContent=t('priority.time',{time:fmt(state.at_ms)});
}
$('priority-ack').onclick=dismissPriority;
$('priority-dialog').addEventListener('cancel',dismissPriority);
$('priority-review').onclick=()=>{dismissPriority();showPanel('decision');$('decision-title').scrollIntoView({block:'nearest'});$('decision-title').focus({preventScroll:true});};
$('priority-toast-review').onclick=()=>{if(priorityQueue.length)openPriority();else showPanel('signals');$('priority-toast').hidden=true;};
$('priority-toast-dismiss').onclick=()=>{$('priority-toast').hidden=true;};

function decisionBriefHTML(event,report) {
  if(!report)return '';
  const mode=report.mode==='llm'?report.model:t(report.mode==='standard'?'decision.standard':'agent.rules');
  return reportLanguageHTML(report,`<section class="decision-overall"><h3>${escape(t('decision.overall'))}</h3><p class="agent-summary">${escape(report.summary || '')}</p><small class="decision-overall-basis">${escape(t('decision.capturedBasis',{time:fmt(event.at_ms),mode}))}${event.new_evidence_available?` · ${escape(t('decision.capturedOnly'))}`:''}${report.language!==language?` · ${escape(t('decision.languageMismatch'))}`:''}</small><div class="decision-brief-facts">${['uncertain'].map(kind=>`<div><h4>${escape(t(`agent.${kind}`))}</h4><ul>${(report[kind] || []).slice(0,1).map(item=>`<li>${escape(item.text)}</li>`).join('') || `<li>${escape(t('none'))}</li>`}</ul></div>`).join('')}</div></section>`);
}
function renderDecisions() {
  syncSelects();
  renderIndications();
  renderOperator();
  if($('rehearsal-panel').open)renderRehearsals();
  if (decisionNoticeRun !== state?.run_id) {
    if (decisionError === 'decision.saved') decisionError = '';
    decisionNoticeRun = state?.run_id;
  }
  const event = currentDecision();
  if(decisionDraft && (!connected || decisionDraftStatus(decisionDraft,event,state,language)!=='ready')) { const prior=decisions?.events?.find(item=>item.id===decisionDraft.event_id);if(connected && decisionDraft.run_id===state?.run_id && prior && (['expired','superseded'].includes(prior.status) || prior.expires_at_ms<=state.at_ms))priorityExpiredChoice=decisionDraft.event_id; decisionDraft=null; decisionError='dashboard.expired'; }
  const expired = decisions?.run_id===state?.run_id ? (decisions.events || []).find(item=>item.status==='expired' && item.run_id===state.run_id) : null;
  $('decision-expired').textContent = expired ? t('decision.expiredNotice',{time:fmt(expired.at_ms),reason:t(`decision.expiration.${expired.expiration_reason}`)}) : '';
  $('decision-expired').hidden = !expired;
  if(decisionDraft && decisions?.events?.some(item=>item.id===decisionDraft.event_id && item.status==='expired')) {decisionDraft=null;$('decision-reason').value='';}
  const waiting = (decisions && state && decisions.run_id === state.run_id ? decisions.events || [] : []).filter(item=>!['decided','superseded','expired'].includes(item.status));
  $('decision-count').textContent = waiting.length;
  $('panel-decision-count').textContent = waiting.length;
  $('panel-decision-count').hidden = !waiting.length;
  if (decisions) $('decision-enabled').checked = decisions.enabled;
  $('decision-enabled').disabled = !connected || decisionBusy;
  $('decision-assess').disabled = !connected || !state || decisionBusy || event?.status === 'evaluating';
  const statusKey = decisionStatusKey(event, decisions?.enabled, decisionError);
  $('decision-status').textContent = operatorActive() ? t('operator.autoNotice') : t(statusKey);
  $('decision-status').hidden = Boolean(event?.status === 'ready' && !decisionError && !operatorActive());
  $('decision-assess').parentElement.hidden = Boolean(event);
  $('decision-attention').hidden = true;
  $('decision-attention-text').textContent = event ? (operatorActive() ? t('operator.autoNotice') : t(statusKey)) : expired ? $('decision-expired').textContent : '';
  const report = decisionReport(event,language);
  $('decision-timing').textContent = event ? t('decision.timing',{captured:fmt(event.at_ms),now:fmt(state.at_ms),age:fmt(Math.max(0,state.at_ms-event.at_ms)),remaining:fmt(Math.max(0,event.expires_at_ms-state.at_ms)),count:(decisions.events || []).filter(item=>!['decided','superseded','expired'].includes(item.status)).length}) : '';
  $('decision-new-evidence').hidden=!event?.new_evidence_available;
  $('decision-new-evidence').textContent=t('indication.newEvidence',{time:fmt(event?.latest_evidence_at_ms || 0)});
  $('decision-bilingual-note').hidden = !$('decision-bilingual').checked;
  const signature = JSON.stringify([language,event,decisionBusy,operatorActive(),decisionDraft?.event_id,decisionDraft?.option_id]);
  if (signature !== decisionSignature) {
    decisionSignature = signature;
    $('decision-event').innerHTML = event ? `
      ${report ? `${decisionBriefHTML(event,report)}<div class="decision-options">${(report.decision_options || []).filter(option=>['continue_monitoring','hold_review','defer'].includes(option.id)).map(option=>`<article><button type="button" class="button button-secondary" data-decision-option="${option.id}" aria-pressed="${decisionDraft?.event_id===event.id && decisionDraft?.option_id===option.id}" ${!decisionOpen(event) || decisionBusy || operatorActive() || report.language!==language?'disabled':''}>${decisionText(decisionCopyKey(event,'option',option.id))}${report.recommended_option_id===option.id?`<span class="decision-recommendation">${t('decision.suggested')}</span>`:''}</button></article>`).join('')}</div><details class="decision-evidence"><summary>${t('decision.evidenceDetails')}${report.language!==language?` · ${escape(originalReportLabel(report))}`:''}</summary><div class="decision-option-reasons">${(report.decision_options || []).map(option=>`<p><strong>${decisionText(decisionCopyKey(event,'option',option.id))}</strong><br>${escape(option.reason)}</p>`).join('')}</div><div class="agent-findings">${['known','uncertain','review_items'].map(section=>`<section><h3>${t(`agent.${section}`)}</h3><ul>${(report[section] || []).map(item=>`<li>${escape(item.text)}<small>${(item.evidence_ids || []).map(escape).join(', ')}</small></li>`).join('') || `<li>${t('none')}</li>`}</ul></section>`).join('')}</div></details>`:''}
      <details class="decision-trigger-details"><summary>${escape(t('decision.triggerDetails'))}</summary><p class="muted">${escape(event.case_id)} · ${fmt(event.at_ms)} · ${escape(event.id)}</p><ul class="decision-triggers">${(event.triggers || []).map(trigger=>`<li>${escape(t(`decision.trigger.${trigger.kind}`))} · ${escape(triggerSubject(language,trigger.subject))} <span class="muted">(${escape(triggerValue(language,trigger.previous))} → ${escape(triggerValue(language,trigger.current))})</span><small>${(trigger.evidence_ids || []).map(escape).join(', ')}</small></li>`).join('')}</ul></details>
      ${['ready','failed'].includes(event.status)?`<button type="button" id="decision-retry" class="button button-secondary" ${decisionBusy?'disabled':''}>${t(event.status==='failed'?'decision.retry':'decision.reassess')}</button>`:''}` : `<p class="empty-state">${t('decision.empty')}</p>`;
    document.querySelectorAll('[data-decision-option]').forEach(button=>button.onclick=()=>{
      decisionDraft = selectDecision(currentDecision(),button.dataset.decisionOption,language);decisionError='';renderDecisions();
      if(decisionDraft && !$('decision-dialog').open) { $('decision-dialog').dataset.restoreChoice=decisionDraft.option_id; $('decision-dialog').showModal(); }
      $('decision-confirm').focus();
    });
    if ($('decision-retry')) $('decision-retry').onclick=()=>decisionAction({action:'retry',event_id:event.id,language});
  }
  if(!decisionDraft && $('decision-dialog').open) $('decision-dialog').close();
  $('decision-form').hidden = !decisionDraft;
  if (decisionDraft) {
    const status = decisionDraftStatus(decisionDraft,event,state,language);
    $('decision-confirm-summary').textContent = `${t(decisionCopyKey(event,'option',decisionDraft.option_id))} · ${t(decisionCopyKey(event,'effect',decisionDraft.option_id))}`;
    $('decision-modal-brief').innerHTML=decisionBriefHTML(event,report);
    $('decision-modal-context').textContent=t('dashboard.modalContext',{evidence:fmt(event.at_ms),now:fmt(state.at_ms),remaining:fmt(Math.max(0,event.expires_at_ms-state.at_ms))});
    $('decision-draft-status').textContent = status === 'stale' ? t('decision.stale') : t('decision.confirmNote');
    $('decision-confirm').disabled = !connected || !decisionAvailable || decisionBusy || operatorActive() || status !== 'ready';
  }
  $('decision-history').innerHTML = (decisions && state && decisions.run_id===state.run_id ? decisions.history || [] : []).map(record=>`<li>${record.actor?.type==='automated_test'?`<strong>${t('operator.automated')}</strong> · `:''}${fmt(record.at_ms || 0)} · ${escape(t(`decision.option.${record.option_id}`))}<p>${escape(record.reason || '')}</p></li>`).join('') || `<li>${t('none')}</li>`;
  renderPriorityAlerts();
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
$('decision-dialog').addEventListener('cancel',()=>{decisionDraft=null;decisionError='';renderDecisions();});
$('decision-cancel').onclick=()=>{decisionDraft=null;decisionError='';renderDecisions();};
$('decision-form').onsubmit=async event=>{
  event.preventDefault();
  const body=decisionConfirmation(decisionDraft,currentDecision(),state,language,$('decision-reviewer').value,$('decision-reason').value,true);
  if(!body || !decisionAvailable || operatorActive()){renderDecisions();return;}
  if(await decisionAction(body)){decisionDraft=null;$('decision-reason').value='';$('decision-extra').open=false;decisionError='decision.saved';renderDecisions();}
};

function renderRehearsals() {
  syncSelects();
  $('rehearsal-refresh').disabled = rehearsalBusy;
  $('rehearsal-run').disabled = rehearsalBusy || !rehearsals?.runs?.length;
  const selectedRun = $('rehearsal-run').value || rehearsals?.current_run_id;
  const run = rehearsals?.runs?.find(item=>item.run_id===selectedRun);
  const records = rehearsalRecords && rehearsalRecords.run_id===selectedRun ? rehearsalRecords.records : [];
  $('rehearsal-export').hidden = !run || rehearsalBusy || rehearsalError;
  if(run) $('rehearsal-export').href = `/api/rehearsals?run_id=${encodeURIComponent(run.run_id)}`;
  $('rehearsal-status').textContent = rehearsalBusy ? t('rehearsal.loading') : rehearsalError ? t('rehearsal.failed') : !records?.length ? t('rehearsal.empty') : t('rehearsal.count',{count:records.length,shown:Math.min(100,records.length)});
  if(rehearsals && state && rehearsals.current_run_id!==state.run_id && !rehearsalBusy && !rehearsalError) $('rehearsal-status').textContent += ' '+t('rehearsal.changed');
  if (rehearsals?.truncated && !rehearsalBusy && !rehearsalError) $('rehearsal-status').textContent += ' '+t('rehearsal.runsLimited',{shown:rehearsals.runs.length,total:rehearsals.total_runs});
  $('rehearsal-summary').innerHTML = run ? ['human','automated_test','unknown'].map(key=>`<span>${escape(t(`rehearsal.${key}`))} <strong>${run.actors[key]}</strong></span>`).join('')+['continue_monitoring','hold_review','defer'].map(key=>`<span>${escape(t(`decision.option.${key}`))} <strong>${run.choices[key]}</strong></span>`).join('') : '';
  const signature=JSON.stringify([language,rehearsalError,rehearsalBusy,selectedRun,(records || []).map(row=>row.id)]);
  if(signature===rehearsalSignature)return;
  rehearsalSignature=signature;
  $('rehearsal-records').innerHTML = rehearsalError || rehearsalBusy ? '' : (records || []).slice(-100).reverse().map(record=>{
    const f=record.fields, actor=f.decision.actor?.type || 'unknown';
    return `<li><details><summary>${fmt(f.time.simulation_ms)} · ${escape(t(`decision.option.${f.decision.option_id}`))} · ${escape(t(`rehearsal.${['human','automated_test'].includes(actor)?actor:'unknown'}`))}</summary><dl>
      <dt>${t('rehearsal.event')}</dt><dd>${escape(f.event.id)} · ${(f.event.triggers || []).map(item=>escape(t(`decision.trigger.${item.kind}`))).join(', ')}</dd>
      <dt>${t('rehearsal.evidenceTitle')}</dt><dd>${escape(t('rehearsal.evidence',{count:f.evidence.observations.total,version:record.evidence_version.slice(0,12)}))}<br>${t('rehearsal.evidenceLink')}</dd>
      <dt>${t('rehearsal.assessment')}</dt><dd lang="${f.assessment.language==='ko'?'ko':'en'}">${f.assessment.language!==language?`<small>${escape(originalReportLabel(f.assessment))}</small>`:''}${escape(f.assessment.summary || '')}</dd>
      <dt>${t('rehearsal.uncertainty')}</dt><dd>${(f.uncertainty || []).map(item=>escape(item.text)).join('<br>') || t('rehearsal.noUncertainty')}</dd>
      <dt>${t('rehearsal.decision')}</dt><dd>${escape(t(`decision.option.${f.decision.option_id}`))}</dd>
      <dt>${t('rehearsal.reason')}</dt><dd>${escape(f.reason || t('rehearsal.noComment'))}</dd>
      <dt>${t('rehearsal.time')}</dt><dd>${escape(t('rehearsal.recorded',{time:fmt(f.time.simulation_ms),date:new Date(f.time.recorded_at_unix_ms).toLocaleString(language)}))}</dd>
    </dl></details></li>`;
  }).join('');
}
function renderRehearsalRuns(selectedRun) {
  syncSelects();
  $('rehearsal-run').innerHTML = (rehearsals?.runs || []).map(run=>{
    const input=run.test_run;
    const provenance=input?.mode==='seeded'?t('rehearsal.seed',{seed:input.seed}):t(input?.mode==='fixture'?'rehearsal.baseline':'rehearsal.unknownSeed');
    return `<option value="${escape(run.run_id)}">${escape(run.case_id)} · ${escape(provenance)} · ${escape(run.run_id.slice(0,8))}</option>`;
  }).join('');
  if(rehearsals?.runs.some(run=>run.run_id===selectedRun)) $('rehearsal-run').value=selectedRun;
}
async function loadRehearsals(refresh=true) {
  const request=++rehearsalRequest;
  const selectedRun=$('rehearsal-run').value;
  rehearsalBusy=true;rehearsalError=false;renderRehearsals();
  try {
    if(refresh){
      const result=await api('/api/rehearsals');
      if(request!==rehearsalRequest)return;
      rehearsals=result;renderRehearsalRuns(selectedRun);
    }
    const run=$('rehearsal-run').value;
    const result=await api(`/api/rehearsals?run_id=${encodeURIComponent(run)}`);
    if(request===rehearsalRequest)rehearsalRecords=result;
  } catch {if(request===rehearsalRequest)rehearsalError=true;}
  finally {if(request===rehearsalRequest){rehearsalBusy=false;renderRehearsals();}}
}
$('rehearsal-panel').ontoggle=()=>{if($('rehearsal-panel').open)loadRehearsals();};
$('rehearsal-refresh').onclick=()=>loadRehearsals();
$('rehearsal-run').onchange=()=>loadRehearsals(false);

function operatorActive() { return Boolean(testOperator?.active && testOperator.run_id === state?.run_id); }
function renderOperator() {
  syncSelects();
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

for (const [dialogId,attribute,fallback] of [['tactics-dialog','data-tactics-allocate','tactics-object'],['dashboard-dialog','data-dashboard-action','dashboard-object'],['decision-dialog','data-decision-option','decision-assess'],['exercise-dialog','data-exercise-branch','exercise-object']]) {
  $(dialogId).addEventListener('close',()=>{
    const choice=$(dialogId).dataset.restoreChoice;
    const button=[...document.querySelectorAll(`[${attribute}]`)].find(item=>item.getAttribute(attribute)===choice && !item.disabled);
    (button || $(fallback)).focus();
  });
}

function renderDashboard() {
  syncSelects();
  const context = `${state?.run_id || ''}:${selected || ''}`;
  if (dashboardContext !== context && !dashboardChoice) {
    dashboardNotice=''; $('dashboard-comment').value=''; $('dashboard-reason').value='';
  }
  dashboardContext=context;
  const dashboard = state?.dashboard;
  const cards = dashboard?.scope === 'simulation_review' ? dashboard.cards || [] : [];
  const card = dashboardCard(state,selected);
  if(dashboardChoice && (!dashboardDraftValid(state,dashboardChoice,connected) || dashboardChoice.object_id !== selected)) {
    dashboardChoice=null;dashboardNotice='dashboard.expired';$('dashboard-reason').value='';
  }
  const optionsSignature=JSON.stringify([language,cards.map(item=>[item.object_id,item.status])]);
  if($('dashboard-object').dataset.signature!==optionsSignature) {
    $('dashboard-object').dataset.signature=optionsSignature;
    $('dashboard-object').innerHTML=cards.length ? cards.map(item=>`<option value="${escape(item.object_id)}">${escape(item.object_id)} · ${escape(t(`dashboard.status.${item.status}`))}</option>`).join('') : `<option value="">${escape(t('dashboard.waiting'))}</option>`;
  }
  $('dashboard-object').value=card?.object_id || '';
  $('dashboard-object').disabled=!cards.length || dashboardBusy;
  $('dashboard-empty').hidden=Boolean(card);
  $('dashboard-content').hidden=!card;
  $('dashboard-status').textContent=t(card?`dashboard.status.${card.status}`:'dashboard.waiting');
  $('dashboard-priority').hidden=!card?.priority;
  if(card) {
    $('dashboard-evidence-summary').textContent=t('dashboard.sourceSummary',{count:card.source_count,quality:qualityLabel(card.quality)});
    const evidenceSignature=JSON.stringify(card.evidence_ids);
    if($('dashboard-evidence').dataset.signature!==evidenceSignature) {
      $('dashboard-evidence').dataset.signature=evidenceSignature;
      $('dashboard-evidence').innerHTML=(card.evidence_ids || []).map(id=>`<li>${escape(id)}</li>`).join('');
    }
    $('dashboard-remaining').textContent=fmt(Math.max(0,card.remaining_ms));
    $('dashboard-next').textContent=card.next_review_at_ms===null ? '' : t('dashboard.next',{time:fmt(card.next_review_at_ms)});
    $('dashboard-action-summary').textContent=t('dashboard.available',{count:connected?card.actions.filter(action=>action.enabled).length:0});
    const followup=card.followup;
    $('dashboard-followup').textContent=followup?.status==='received' ? t('dashboard.received',{id:followup.id}) : followup?.status==='pending' ? t('dashboard.pending',{seconds:Math.ceil(Math.max(0,followup.available_at_ms-state.at_ms)/1000)}) : t('dashboard.schedule');
    $('dashboard-operator').textContent=$('dashboard-reviewer').value.trim() || t('dashboard.localOperator');
    const actionSignature=JSON.stringify([language,card.object_id,card.actions,connected,dashboardBusy,dashboardChoice?.choice]);
    if($('dashboard-actions').dataset.signature!==actionSignature) {
      $('dashboard-actions').dataset.signature=actionSignature;
      $('dashboard-actions').innerHTML=card.actions.filter(action=>DASHBOARD_ACTIONS.includes(action.id)).map(action=>`<div><button type="button" class="button button-secondary" data-dashboard-action="${escape(action.id)}" aria-pressed="${dashboardChoice?.choice===action.id}" ${!action.enabled || !connected || dashboardBusy?'disabled':''}>${escape(t(`dashboard.action.${action.id}`))}</button>${action.reason?`<small>${escape(t(`dashboard.block.${action.reason}`))}</small>`:''}</div>`).join('');
      $('dashboard-actions').querySelectorAll('[data-dashboard-action]').forEach(button=>button.onclick=()=>{
        dashboardChoice=dashboardDraft(state,selected,button.dataset.dashboardAction,connected);dashboardNotice='';$('dashboard-reason').value='';renderDashboard();
        if(dashboardChoice && !$('dashboard-dialog').open) { $('dashboard-dialog').dataset.restoreChoice=dashboardChoice.choice; $('dashboard-dialog').showModal(); }
      });
    }
  }
  if(!dashboardChoice && $('dashboard-dialog').open) $('dashboard-dialog').close();
  $('dashboard-form').hidden=!dashboardChoice;
  if(dashboardChoice) {
    $('dashboard-modal-effect').textContent=t(`dashboard.effect.${dashboardChoice.choice}`);
    $('dashboard-modal-context').textContent=t('dashboard.modalContext',{evidence:(card.evidence_ids || []).slice(0,3).join(', '),now:fmt(state.at_ms),remaining:fmt(card.remaining_ms)});
    $('dashboard-confirm-summary').textContent=`${dashboardChoice.object_id} · ${t(`dashboard.action.${dashboardChoice.choice}`)}`;
    $('dashboard-dismiss').hidden=dashboardChoice.choice!=='dismiss';
    $('dashboard-message').hidden=dashboardChoice.choice!=='notify_mock';
    $('dashboard-message-text').textContent=localized(card.mock_notice) || t('dashboard.mockDraft',{object:card.object_id,status:t(`dashboard.status.${card.status}`)});
  }
  $('dashboard-confirm').disabled=dashboardBusy || !dashboardConfirmation(state,dashboardChoice,{connected,confirmed:true,reason:$('dashboard-reason').value});
  $('dashboard-cancel').disabled=dashboardBusy;
  $('dashboard-notice').textContent=t(dashboardBusy?'dashboard.saving':!connected?'dashboard.offline':dashboardNotice || 'dashboard.scope');
  const recentSignature=JSON.stringify([language,dashboard?.recent]);
  if($('dashboard-history').dataset.signature!==recentSignature) {
    $('dashboard-history').dataset.signature=recentSignature;
    $('dashboard-history').innerHTML=(dashboard?.recent || []).slice(-20).reverse().map(record=>`<li>${fmt(record.at_ms)} · ${escape(record.object_id)} · ${escape(t(`dashboard.action.${record.decision}`))}${record.reason?`<p>${escape(['bird','civil_aircraft','friendly','sensor_error'].includes(record.reason)?t(`dashboard.reason.${record.reason}`):record.reason)}</p>`:''}</li>`).join('') || `<li>${escape(t('none'))}</li>`;
  }
}
$('dashboard-dialog').addEventListener('cancel',()=>{dashboardChoice=null;dashboardNotice='';renderDashboard();});
$('dashboard-object').onchange=event=>select(event.target.value);
$('dashboard-reason').onchange=()=>renderDashboard();
$('dashboard-reviewer').oninput=()=>renderDashboard();
$('dashboard-cancel').onclick=()=>{dashboardChoice=null;dashboardNotice='';renderDashboard();};
$('dashboard-form').onsubmit=event=>{
  event.preventDefault();
  if(dashboardBusy)return;
  const choice=dashboardChoice;
  const extras={connected,confirmed:true,reason:$('dashboard-reason').value,comment:$('dashboard-comment').value,reviewer:$('dashboard-reviewer').value};
  if(!dashboardConfirmation(state,choice,extras))return;
  dashboardBusy=true;dashboardNotice='';renderDashboard();
  controlChain=controlChain.then(async()=>{
    const body=dashboardConfirmation(state,choice,{...extras,connected});
    if(!body){dashboardBusy=false;dashboardNotice='dashboard.expired';renderDashboard();return;}
    const version=++requestVersion;
    try {
      const data=await api('/api/control',body);
      dashboardChoice=null;dashboardNotice='dashboard.saved';$('dashboard-comment').value='';$('dashboard-reason').value='';$('dashboard-extra').open=false;
      if(version===requestVersion)render(data);
    } catch {dashboardChoice=null;dashboardNotice='dashboard.failed';}
    finally {dashboardBusy=false;renderDashboard();}
  });
};

const tacticsLabel = (group, value) => {
  const key=`tactics.${group}.${value}`;
  return t(key)!==key ? t(key) : String(value ?? '');
};
const effectorLabel = id => localized(state?.tactics?.effectors?.find(item=>item.id===id)?.label) || tacticsLabel('effector',id);
const tacticsList = (items, empty) => items.length ? `<ul>${items.map(item=>`<li>${item}</li>`).join('')}</ul>` : `<p class="muted">${escape(empty)}</p>`;
const evidenceText = ids => (ids || []).length ? `<small>${escape(t('tactics.evidence',{ids:`${ids.slice(0,6).join(', ')}${ids.length>6?', …':''}`}))}</small>` : '';
function reportFields(fields = {}) {
  const parts=[];
  if(fields.airframe_class)parts.push(tacticsLabel('profile',fields.airframe_class));
  if(typeof fields.payload_visible==='boolean')parts.push(t(fields.payload_visible?'tactics.field.payloadVisible':'tactics.field.payloadHidden'));
  if(fields.signature)parts.push(tacticsLabel('field.signature',fields.signature));
  if(fields.rf_emission===true)parts.push(t('tactics.field.rfEmission'));
  if(fields.rf_emission===false)parts.push(t('tactics.field.rfNone'));
  if(fields.band)parts.push(tacticsLabel('field.band',fields.band));
  return parts.join(' · ');
}
function facilityLabel(id) {
  if(id==='runway')return t('tactics.facility.runway');
  return localized(config?.site?.facilities?.find(item=>item.id===id)?.label) || String(id ?? t('tactics.unknown'));
}
function tacticsCardHTML(target) {
  const ident=target.identification, response=target.response, kin=ident.kinematics || {};
  const value=(number,key)=>Number.isFinite(number)?t(key,{value:Math.round(number).toLocaleString(language)}):t('tactics.unknown');
  const cues=(ident.cues || []).map(cue=>`${escape(tacticsLabel('cue',cue.id))} <small>${escape(Object.entries(cue.effect || {}).map(([score,amount])=>`${tacticsLabel('score',score)} ${amount>0?'+':''}${amount}`).join(' · '))}</small>${evidenceText(cue.evidence_ids)}`);
  const uncertainty=(ident.uncertainty || []).map(id=>escape(tacticsLabel('uncertainty',id)));
  const reports=(ident.reports || []).map(report=>`<strong>${escape(tacticsLabel('sensor',report.sensor_type))}</strong> · ${escape(reportFields(report.fields))}<small>${escape(t('tactics.reportTime',{observed:fmt(report.observed_at_ms),received:fmt(report.available_at_ms)}))} · ${escape(report.id)}</small>`);
  const allocation=response.allocation;
  const options=(response.options || []).map(option=>{
    const draftable=Boolean(allocationDraft(state,target.object_id,option.effector_id,connected)) && !tacticsBusy;
    const effector=state.tactics.effectors?.find(item=>item.id===option.effector_id);
    const reasons=(option.reasons || []).map(reason=>tacticsLabel('reason',reason)).join('; ') || t('tactics.none');
    return `<tr data-status="${escape(option.status)}"><td><strong>${escape(effectorLabel(option.effector_id))}</strong><small>${escape(t('tactics.col.reasons'))}: ${escape(reasons)}</small>${effector?.cost_note?`<small>${escape(localized(effector.cost_note))}</small>`:''}</td><td data-status="${escape(option.status)}">${escape(tacticsLabel('status',option.status))}</td><td>${Math.round((option.suitability || 0)*100)}%</td><td>${option.inventory_remaining===null || option.inventory_remaining===undefined?escape(t('tactics.unlimited')):escape(option.inventory_remaining)}</td><td>${option.status==='rejected' || allocation?'':`<button type="button" class="button button-secondary" data-tactics-allocate="${escape(option.effector_id)}" aria-pressed="${tacticsChoice?.effector_id===option.effector_id}" ${draftable?'':'disabled'}>${escape(t('tactics.allocate'))}</button>`}</td></tr>`;
  }).join('');
  return `<h3>${escape(target.object_id)} <span class="tactics-badge" data-value="${escape(ident.lean)}">${escape(tacticsLabel('lean',ident.lean))}</span><span class="tactics-badge" data-value="${escape(response.posture)}">${escape(tacticsLabel('posture',response.posture))}</span></h3>
    <dl class="detail-grid"><dt>${escape(t('tactics.profileLabel'))}</dt><dd>${escape(tacticsLabel('profile',ident.profile))}</dd><dt>${escape(t('tactics.verificationLabel'))}</dt><dd>${escape(tacticsLabel('verification',ident.verification))}</dd><dt>${escape(t('tactics.group'))}</dt><dd data-kin="group">${escape(ident.group_size ?? t('tactics.unknown'))}</dd><dt>${escape(t('tactics.speed'))}</dt><dd data-kin="speed">${escape(value(kin.speed_kmh,'tactics.speedValue'))}</dd><dt>${escape(t('tactics.altitude'))}</dt><dd data-kin="altitude">${escape(value(kin.altitude_m,'tactics.metres'))}</dd><dt>${escape(t('tactics.sectorLabel'))}</dt><dd data-kin="sector">${escape(ident.sector || t('tactics.unknown'))}</dd><dt>${escape(t('tactics.nearest'))}</dt><dd data-kin="nearest">${escape(facilityLabel(kin.nearest_facility))} · ${escape(value(kin.facility_distance_m,'tactics.metres'))}</dd></dl>
    <h4>${escape(t('tactics.cues'))}</h4>${tacticsList(cues,t('tactics.noCues'))}
    <h4>${escape(t('tactics.uncertainty'))}</h4>${tacticsList(uncertainty,t('tactics.none'))}
    <h4>${escape(t('tactics.reports'))}</h4>${tacticsList(reports,t('tactics.noReports'))}
    <h4>${escape(t('tactics.constraints'))}</h4><p>${escape((response.constraints || []).map(id=>tacticsLabel('constraint',id)).join(' · ') || t('tactics.none'))}</p>
    <h4>${escape(t('tactics.posture'))}</h4><p>${escape(tacticsLabel('posture',response.posture))} · ${escape(response.primary?t('tactics.primary',{effector:effectorLabel(response.primary)}):t('tactics.noPrimary'))} · ${escape(t('tactics.authority'))}</p>
    ${allocation?`<p class="tactics-allocation">${escape(t('tactics.allocated',{effector:effectorLabel(allocation.effector_id),status:tacticsLabel('status',allocation.status_at_record),time:fmt(allocation.at_ms)}))}</p>`:''}
    <h4>${escape(t('tactics.options'))}</h4><table class="tactics-options"><thead><tr><th>${escape(t('tactics.col.effector'))}</th><th>${escape(t('tactics.col.status'))}</th><th>${escape(t('tactics.col.suitability'))}</th><th>${escape(t('tactics.col.inventory'))}</th><th></th></tr></thead><tbody>${options}</tbody></table>`;
}
function renderTactics() {
  syncSelects();
  const tactics=state?.tactics?.scope===TACTICS_SCOPE?state.tactics:null;
  const context=`${state?.run_id || ''}:${selected || ''}`;
  if(tacticsContext!==context && !tacticsChoice)tacticsNotice='';
  tacticsContext=context;
  const target=tacticsTarget(state,selected);
  if(tacticsChoice && (!allocationDraftValid(state,tacticsChoice,connected) || tacticsChoice.object_id!==selected)){tacticsChoice=null;tacticsNotice='tactics.expired';}
  if(!tacticsChoice && $('tactics-dialog').open)$('tactics-dialog').close();
  const targets=tactics?.targets || [];
  $('tactics-count').textContent=targets.length;
  $('tactics-summary').textContent=tactics?t('tactics.summary',{received:tactics.summary?.received ?? targets.length,reports:tactics.summary?.reports_received ?? 0}):t('tactics.unavailable');
  const objectSelect=$('tactics-object');
  const optionsSignature=JSON.stringify([language,targets.map(item=>[item.object_id,item.identification?.lean])]);
  if(objectSelect.dataset.signature!==optionsSignature){
    objectSelect.dataset.signature=optionsSignature;
    objectSelect.innerHTML=targets.length?targets.map(item=>`<option value="${escape(item.object_id)}">${escape(item.object_id)} · ${escape(tacticsLabel('lean',item.identification?.lean))}</option>`).join(''):`<option value="">${escape(t('tactics.waiting'))}</option>`;
  }
  objectSelect.value=target?.object_id || '';
  objectSelect.disabled=!targets.length || tacticsBusy;
  const formation=tactics?.formation, rows=formationRows(state);
  const formationSignature=JSON.stringify([language,formation?.posture,formation?.unit_count,rows]);
  if($('tactics-teams').dataset.signature!==formationSignature){
    $('tactics-teams').dataset.signature=formationSignature;
    $('tactics-formation-posture').textContent=formation?t('tactics.formationPosture',{posture:tacticsLabel('formation',formation.posture),count:formation.unit_count ?? 0}):'';
    const countLabel=key=>{for(const group of ['posture','lean']){const label=`tactics.${group}.${key}`;if(t(label)!==label)return t(label);}return key;};
    $('tactics-teams').innerHTML=rows.map(row=>`<li><strong>${unitIcon(row.kind)} ${escape(t('tactics.team',{kind:unitKindLabel(row.kind),role:t(`units.role.${row.role}`),sector:row.sector==='site'?t('tactics.sector.site'):row.sector,count:row.unit_count}))}</strong><small>${escape(row.tasking_count?`${t('tactics.tasking',{count:row.tasking_count,objects:`${row.tasking.join(', ')}${row.tasking_count>row.tasking.length?', …':''}`})} · ${Object.entries(row.counts).map(([key,count])=>`${countLabel(key)} ${count}`).join(' · ')}`:t('tactics.taskingNone'))}</small></li>`).join('') || `<li class="muted">${escape(t('tactics.formationEmpty'))}</li>`;
  }
  // Kinematic numbers change every tick; only material changes (versions, allocation, choice) rebuild the card.
  const cardSignature=JSON.stringify([language,connected,tacticsBusy,tacticsChoice?.effector_id,selected,Boolean(tactics),targets.length,
    target?.identification?.version,target?.response?.version,target?.response?.allocation,tactics?.effectors]);
  if($('tactics-card').dataset.signature!==cardSignature){
    $('tactics-card').dataset.signature=cardSignature;
    $('tactics-card').innerHTML=target?tacticsCardHTML(target):`<p class="empty-state">${escape(t(!tactics?'tactics.unavailable':targets.length?'tactics.noTarget':'tactics.waiting'))}</p>`;
    $('tactics-card').querySelectorAll('[data-tactics-allocate]').forEach(button=>button.onclick=()=>{
      tacticsChoice=allocationDraft(state,selected,button.dataset.tacticsAllocate,connected);tacticsNotice='';renderTactics();
      if(tacticsChoice && !$('tactics-dialog').open){$('tactics-dialog').dataset.restoreChoice=tacticsChoice.effector_id;$('tactics-dialog').showModal();}
    });
  } else if(target){
    const kin=target.identification.kinematics || {};
    const value=(number,key)=>Number.isFinite(number)?t(key,{value:Math.round(number).toLocaleString(language)}):t('tactics.unknown');
    const live={group:String(target.identification.group_size ?? t('tactics.unknown')),speed:value(kin.speed_kmh,'tactics.speedValue'),altitude:value(kin.altitude_m,'tactics.metres'),
      sector:target.identification.sector || t('tactics.unknown'),nearest:`${facilityLabel(kin.nearest_facility)} · ${value(kin.facility_distance_m,'tactics.metres')}`};
    for(const [key,text] of Object.entries(live)){const cell=$('tactics-card').querySelector(`[data-kin="${key}"]`);if(cell && cell.textContent!==text)cell.textContent=text;}
  }
  const allocations=tactics?.allocations || [];
  $('tactics-history-title').textContent=t('tactics.history',{count:allocations.length});
  const historySignature=JSON.stringify([language,allocations]);
  if($('tactics-history').dataset.signature!==historySignature){
    $('tactics-history').dataset.signature=historySignature;
    $('tactics-history').innerHTML=allocations.slice(-20).reverse().map(record=>`<li>${fmt(record.at_ms)} · ${escape(record.object_id)} · ${escape(effectorLabel(record.effector_id))} · ${escape(tacticsLabel('status',record.status_at_record))}${record.reviewer?` · ${escape(record.reviewer)}`:''}${record.reason?`<p>${escape(record.reason)}</p>`:''}</li>`).join('') || `<li>${escape(t('tactics.none'))}</li>`;
  }
  $('tactics-status').textContent=t(tacticsBusy?'tactics.saving':!connected?'tactics.offline':tacticsNotice || 'tactics.ready');
  $('tactics-form').hidden=!tacticsChoice;
  if(tacticsChoice && target){
    const option=target.response.options.find(row=>row.effector_id===tacticsChoice.effector_id);
    $('tactics-modal-summary').textContent=t('tactics.modalSummary',{object:target.object_id,effector:effectorLabel(option.effector_id),status:tacticsLabel('status',option.status)});
    $('tactics-modal-context').textContent=t('tactics.modalContext',{suitability:Math.round((option.suitability || 0)*100),time:fmt(state.at_ms),reasons:(option.reasons || []).map(reason=>tacticsLabel('reason',reason)).join('; ') || t('tactics.none')});
  }
  $('tactics-confirm').disabled=tacticsBusy || !allocationCommand(state,tacticsChoice,{connected,confirmed:true});
  $('tactics-cancel').disabled=tacticsBusy;
}
$('tactics-dialog').addEventListener('cancel',()=>{tacticsChoice=null;tacticsNotice='';renderTactics();});
$('tactics-object').onchange=event=>{if(event.target.value)select(event.target.value);};
$('tactics-cancel').onclick=()=>{tacticsChoice=null;tacticsNotice='';renderTactics();};
$('tactics-form').onsubmit=event=>{
  event.preventDefault();
  if(tacticsBusy)return;
  const choice=tacticsChoice;
  const extras={connected,confirmed:true,reviewer:$('tactics-reviewer').value,comment:$('tactics-comment').value};
  if(!allocationCommand(state,choice,extras))return;
  tacticsBusy=true;tacticsNotice='';renderTactics();
  controlChain=controlChain.then(async()=>{
    const body=allocationCommand(state,choice,{...extras,connected});
    if(!body){tacticsBusy=false;tacticsChoice=null;tacticsNotice='tactics.expired';renderTactics();return;}
    const version=++requestVersion;
    try {
      const data=await api('/api/control',body);
      tacticsChoice=null;tacticsNotice='tactics.saved';$('tactics-comment').value='';
      if(version===requestVersion)render(data);
    } catch {tacticsChoice=null;tacticsNotice='tactics.failed';}
    finally {tacticsBusy=false;renderTactics();}
  });
};

const unitKindLabel = kind => {
  const key=`units.kind.${kind}`;
  return t(key)!==key ? t(key) : localized(state?.exercise?.unit_kinds?.find(item=>item.id===kind)?.label) || String(kind);
};
// Acoustic listening posts use an inline microphone: text glyphs for it render inconsistently across engines.
const ACOUSTIC_ICON = '<svg class="unit-glyph" viewBox="0 0 16 16" aria-hidden="true"><rect x="5.5" y="1.5" width="5" height="8.5" rx="2.5" fill="currentColor"/><path d="M3.3 7.6a4.7 4.7 0 0 0 9.4 0M8 12.4v2.3M5.4 14.7h5.2" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>';
const unitIcon = kind => kind==='detection_phone' ? ACOUSTIC_ICON : escape(({radar:'◎',effector_team:'▲'})[kind] || '♟');
function renderUnits() {
  syncSelects();
  const exercise=state?.exercise, proposal=exercise?.unit_proposal, units=exercise?.units || [];
  if(unitRun!==state?.run_id){unitPlacement=null;unitNotice='';unitRun=state?.run_id;}
  if(!connected || proposal?.status!=='manual' || (unitPlacement?.unit_id && !units.some(unit=>unit.id===unitPlacement.unit_id)))unitPlacement=null;
  const available=connected && exercise?.scope==='scripted_training' && Boolean(proposal), manual=proposal?.status==='manual';
  const summary=placementSummary(state);
  const kinds=summary?.kinds || [];
  const totalBudget=kinds.reduce((sum,kind)=>sum+(kind.budget || 0),0);
  $('unit-count').textContent=t('units.count',{count:units.length,max:totalBudget || units.length});
  $('unit-proposal-label').textContent=proposal?.status==='pending'?t('units.proposal',{count:proposalPositions(proposal).length}):t('units.current');
  $('unit-threat-basis').textContent=['scenario_prior','received_picture'].includes(summary?.threat_basis)?t(`units.basis.${summary.threat_basis}`):'';
  $('unit-proposal-basis').textContent=localized(proposal?.basis) || t('units.scope');
  const radarCoverage=Number.isFinite(exercise?.radar_coverage)?exercise.radar_coverage:null;
  const coverageSignature=JSON.stringify([language,kinds,summary?.coverage,radarCoverage]);
  if($('unit-coverage').dataset.signature!==coverageSignature){
    $('unit-coverage').dataset.signature=coverageSignature;
    $('unit-coverage').innerHTML=kinds.map(kind=>{
      const coverage=summary.coverage?.[kind.kind];
      return `<li><strong>${unitIcon(kind.kind)} ${escape(unitKindLabel(kind.kind))}</strong><small>${escape(t('units.coverageRow',{proposed:kind.proposed,placed:kind.placed,budget:kind.budget ?? '–',coverage:Number.isFinite(coverage)?Math.round(coverage*100):'–'}))} · ${escape(kind.range_m>0?t('units.range',{range:(kind.range_m/1000).toLocaleString(language)}):t('units.noRange'))}</small>${kind.kind==='radar' && radarCoverage!==null?`<small class="unit-los">${escape(t('units.radarLos',{coverage:Math.round(radarCoverage*100)}))}</small>`:''}</li>`;
    }).join('');
  }
  const adjustment=pendingRadarAdjustment(state);
  if(unitPendingAction && (unitPendingAction.run_id!==state?.run_id || (unitPendingAction.unit_id && !units.some(unit=>unit.id===unitPendingAction.unit_id))
      || (unitPendingAction.action==='radar_apply' && unitPendingAction.adjustment_id!==adjustment?.id)))unitPendingAction=null;
  $('radar-adjust').disabled=!available || unitBusy;
  renderRadarAdjustment(adjustment,available);
  $('unit-accept').hidden=proposal?.status!=='pending';$('unit-accept').disabled=!available || unitBusy;
  $('unit-accept').textContent=t(unitPendingAction?.action==='replace'?'units.replaceConfirm':units.length?'units.replace':'units.accept');
  $('unit-accept').setAttribute('aria-pressed',String(unitPendingAction?.action==='replace'));
  $('unit-reoptimize').disabled=!available || unitBusy || manual;
  $('unit-reoptimize').title=manual?t('units.reoptimizeManual'):'';
  $('unit-manual').hidden=manual;$('unit-manual').disabled=!available || unitBusy;
  $('unit-manual').textContent=t(proposal?.status==='accepted'?'units.changeManual':'units.manual');
  const kindSelect=$('unit-kind');
  const kindSignature=JSON.stringify([language,kinds.map(kind=>[kind.kind,kind.remaining])]);
  if(kindSelect.dataset.signature!==kindSignature){
    const previous=kindSelect.value;
    kindSelect.dataset.signature=kindSignature;
    kindSelect.innerHTML=(kinds.length?kinds:UNIT_KINDS.map(kind=>({kind,remaining:null}))).map(kind=>`<option value="${escape(kind.kind)}">${escape(kind.remaining===null?unitKindLabel(kind.kind):t('units.kindOption',{kind:unitKindLabel(kind.kind),remaining:kind.remaining}))}</option>`).join('');
    if([...kindSelect.options].some(option=>option.value===previous))kindSelect.value=previous;
  }
  const chosenKind=unitPlacement?.kind || kindSelect.value || 'infantry';
  const budget=unitBudget(state,chosenKind);
  $('unit-place-controls').hidden=!manual;
  kindSelect.disabled=!available || unitBusy || Boolean(unitPlacement?.unit_id);
  $('unit-place').disabled=!available || unitBusy || !(budget?.remaining>0);
  $('unit-cancel').hidden=!unitPlacement;$('unit-cancel').disabled=unitBusy;
  const placingKind=unitPlacement?.unit_id?units.find(unit=>unit.id===unitPlacement.unit_id)?.kind:unitPlacement?.kind;
  const message=unitBusy?t('units.saving'):unitNotice?t(unitNotice):!connected?t('exercise.disconnected'):unitPlacement?t('units.click',{kind:unitKindLabel(placingKind || 'infantry')}):manual?(budget?.remaining>0?t('units.ready'):t('units.limit',{kind:unitKindLabel(chosenKind),max:budget?.budget ?? 0})):proposal?.status==='pending'?t('units.pending'):t('units.applied');
  $('unit-status').textContent=message;
  $('unit-map-status').hidden=!unitPlacement;$('unit-map-status').textContent=message;
  map.classList.toggle('is-placing-unit',Boolean(unitPlacement));
  const signature=JSON.stringify([language,units,kinds,manual,available,unitBusy,unitPlacement?.unit_id,unitPendingAction]);
  if($('unit-list').dataset.signature!==signature){
    $('unit-list').dataset.signature=signature;
    const disabled=manual && available && !unitBusy?'':'disabled';
    const groups=(kinds.length?kinds.map(kind=>kind.kind):UNIT_KINDS).map(kind=>({kind,rows:units.filter(unit=>unit.kind===kind),budget:kinds.find(item=>item.kind===kind)?.budget}))
      .filter(group=>group.rows.length);
    $('unit-list').innerHTML=groups.map(group=>`<section><h3><span>${unitIcon(group.kind)} ${escape(unitKindLabel(group.kind))}</span><span>${escape(t('units.groupCount',{placed:group.rows.length,budget:group.budget ?? '–'}))}</span></h3><ul>${group.rows.map(unit=>`<li><span><strong>${escape(localized(unit.label) || unit.id)}</strong><small>${unit.role?`${escape(t(`units.role.${unit.role}`))} · `:''}${escape(t('units.position',{x:Math.round(unit.position[0]),z:Math.round(unit.position[2])}))}</small></span><button type="button" class="button button-secondary" data-unit-focus="${escape(unit.id)}">${escape(t('exercise.focus'))}</button><button type="button" class="button button-secondary" data-unit-move="${escape(unit.id)}" ${disabled}>${escape(t('units.move'))}</button><button type="button" class="button button-secondary" data-unit-remove="${escape(unit.id)}" aria-pressed="${unitPendingAction?.action==='remove' && unitPendingAction.unit_id===unit.id}" ${disabled}>${escape(t(unitPendingAction?.action==='remove' && unitPendingAction.unit_id===unit.id?'units.removeConfirm':'units.remove'))}</button></li>`).join('')}</ul></section>`).join('') || `<p class="muted">${escape(t('units.listEmpty'))}</p>`;
    $('unit-list').querySelectorAll('[data-unit-focus]').forEach(button=>button.onclick=()=>{
      const unit=state.exercise.units.find(item=>item.id===button.dataset.unitFocus);if(!unit)return;
      plan.x=unit.position[0];plan.z=unit.position[2];plan.zoom=4;revealMap();setMode('site');
    });
    $('unit-list').querySelectorAll('[data-unit-move]').forEach(button=>button.onclick=()=>startUnitPlacement(button.dataset.unitMove));
    $('unit-list').querySelectorAll('[data-unit-remove]').forEach(button=>button.onclick=()=>{
      // Removal is a two-step choice: the first click arms the button, the second sends the command.
      const unitId=button.dataset.unitRemove;
      if(unitPendingAction?.action==='remove' && unitPendingAction.unit_id===unitId){unitPendingAction=null;sendUnitCommand({action:'exercise_remove_unit',run_id:state.run_id,unit_id:unitId});return;}
      unitPendingAction={action:'remove',unit_id:unitId,run_id:state.run_id};unitNotice='units.removeArmed';renderUnits();
    });
  }
}
function renderRadarAdjustment(adjustment,available) {
  const card=$('radar-adjustment');
  card.hidden=!adjustment;
  const applicable=adjustment?radarAdjustmentApplicable(state,adjustment):false;
  const armed=unitPendingAction?.action==='radar_apply';
  const signature=JSON.stringify([language,adjustment,applicable,armed,available,unitBusy]);
  if(card.dataset.signature===signature)return;
  card.dataset.signature=signature;
  if(!adjustment){card.innerHTML='';return;}
  const percent=value=>Number.isFinite(value)?Math.round(value*100):'–';
  const changes=[...adjustment.moves.map(move=>`<li>→ ${escape(t('units.radarMove',{label:localized(move.label) || move.unit_id,distance:Number.isFinite(move.distance_m)?Math.round(move.distance_m).toLocaleString(language):'–'}))}</li>`),
    ...adjustment.additions.map(addition=>`<li>+ ${escape(t('units.radarAdd',{label:localized(addition.label) || t('units.kind.radar')}))}</li>`)];
  const disabled=!available || unitBusy;
  card.innerHTML=`<h3>${escape(t('units.radarAdjustTitle'))}</h3>
    <p><strong>${escape(t('units.radarAdjustCoverage',{before:percent(adjustment.coverage_before),after:percent(adjustment.coverage_after)}))}</strong>${Number.isFinite(adjustment.computed_at_ms)?` <small>${escape(t('units.radarComputed',{time:fmt(adjustment.computed_at_ms)}))}</small>`:''}</p>
    ${changes.length?`<ul>${changes.join('')}</ul>`:`<p class="muted">${escape(t('units.radarNoChange'))}</p>`}
    ${['scenario_prior','received_picture'].includes(adjustment.threat_basis)?`<p class="muted">${escape(t(`units.basis.${adjustment.threat_basis}`))}</p>`:''}
    <p class="muted">${escape(localized(adjustment.basis))}</p>
    ${applicable?'':`<p class="radar-adjustment-stale">${escape(t('units.radarStale'))}</p>`}
    <div class="unit-actions"><button type="button" id="radar-apply" class="button button-primary" aria-pressed="${armed}" ${disabled || !applicable || !changes.length?'disabled':''}>${escape(t(armed?'units.radarApplyConfirm':'units.radarApply'))}</button><button type="button" id="radar-dismiss" class="button button-secondary" ${disabled?'disabled':''}>${escape(t('units.radarDismiss'))}</button></div>`;
  $('radar-apply').onclick=()=>{
    // Applying moves placed radars: the first click arms the button, the second sends the command.
    const current=pendingRadarAdjustment(state);if(!current)return;
    if(unitPendingAction?.action==='radar_apply' && unitPendingAction.adjustment_id===current.id){
      unitPendingAction=null;sendUnitCommand({action:'exercise_apply_radar_adjustment',run_id:state.run_id,adjustment_id:current.id});return;
    }
    unitPendingAction={action:'radar_apply',adjustment_id:current.id,run_id:state.run_id};unitNotice='units.radarApplyArmed';renderUnits();
    $('radar-apply')?.focus();
  };
  $('radar-dismiss').onclick=()=>{
    const current=pendingRadarAdjustment(state);if(!current)return;
    unitPendingAction=null;sendUnitCommand({action:'exercise_dismiss_radar_adjustment',run_id:state.run_id,adjustment_id:current.id});
  };
}
function startUnitPlacement(unitId) {
  if(!connected || unitBusy || state?.exercise?.unit_proposal?.status!=='manual')return;
  unitPlacement={run_id:state.run_id,...(unitId?{unit_id:unitId}:{kind:$('unit-kind').value || 'infantry'})};unitNotice='';renderUnits();revealMap();map.focus({preventScroll:true});
}
function cancelUnitPlacement() {unitPlacement=null;unitNotice='';renderUnits();}
function sendUnitCommand(draft) {
  if(!connected || unitBusy)return;
  const radar=RADAR_ADJUSTMENT_ACTIONS.includes(draft.action);
  const command=()=>radar?radarAdjustmentCommand(state,draft,true):exerciseUnitCommand(state,draft,true);
  const invalid=radar?'units.radarStale':'units.invalid';
  if(!command()){unitNotice=invalid;renderUnits();return;}
  unitBusy=true;unitNotice='';renderUnits();
  controlChain=controlChain.then(async()=>{
    const body=connected?command():null;
    if(!body){unitBusy=false;unitPlacement=null;unitNotice=invalid;renderUnits();return;}
    const version=++requestVersion;
    try {
      const data=await api('/api/control',body);
      if(version===requestVersion)render(data);
      if(state?.run_id===draft.run_id){unitPlacement=null;unitNotice=({exercise_reoptimize_units:'units.reoptimized',exercise_adjust_radars:'units.radarProposed',
        exercise_apply_radar_adjustment:'units.radarApplied',exercise_dismiss_radar_adjustment:'units.radarDismissed'})[draft.action] || 'units.saved';}
    } catch {if(state?.run_id===draft.run_id)unitNotice=radar?'units.radarFailed':'units.failed';}
    finally {unitBusy=false;renderUnits();drawMap();}
  });
}
$('unit-place').onclick=()=>startUnitPlacement();
$('unit-cancel').onclick=cancelUnitPlacement;
$('unit-kind').onchange=()=>{if(unitPlacement && !unitPlacement.unit_id)unitPlacement.kind=$('unit-kind').value;unitNotice='';renderUnits();};
$('unit-manual').onclick=()=>{unitPendingAction=null;sendUnitCommand({action:'exercise_manual_units',run_id:state.run_id,proposal_id:state.exercise.unit_proposal.id});};
$('unit-accept').onclick=()=>{
  // Applying over already placed units replaces them; ask for a second click in that case.
  const placed=(state?.exercise?.units || []).length>0;
  if(placed && unitPendingAction?.action!=='replace'){unitPendingAction={action:'replace',run_id:state.run_id};unitNotice='units.replaceArmed';renderUnits();return;}
  unitPendingAction=null;sendUnitCommand({action:'exercise_accept_units',run_id:state.run_id,proposal_id:state.exercise.unit_proposal.id});
};
$('unit-reoptimize').onclick=()=>sendUnitCommand({action:'exercise_reoptimize_units',run_id:state.run_id});
$('radar-adjust').onclick=()=>{unitPendingAction=null;sendUnitCommand({action:'exercise_adjust_radars',run_id:state.run_id});};
document.addEventListener('keydown',event=>{
  if(event.key!=='Escape' || unitBusy || $('tactics-dialog').open)return;
  if(unitPlacement){event.preventDefault();cancelUnitPlacement();}
  else if(unitPendingAction){unitPendingAction=null;unitNotice='';renderUnits();}
});

function renderExercise() {
  syncSelects();
  renderUnits();
  const exercise = state?.exercise;
  const available = exercise?.scope === 'scripted_training';
  if (exerciseRun !== state?.run_id || (state?.at_ms || 0) < exerciseAt) {
    exerciseExpired=Boolean(exerciseDraft);exerciseDraft = null; exerciseError = false;
    $('exercise-object').value = ''; $('exercise-asset').value = '';
  }
  exerciseRun = state?.run_id; exerciseAt = state?.at_ms || 0;
  const selectedBranch = exercise?.selection;
  if (exerciseDraft && (!connected || !exerciseConfirmation(state,exerciseDraft,true))) { exerciseDraft = null;exerciseExpired=true; }
  if(!exerciseDraft && $('exercise-dialog').open) $('exercise-dialog').close();
  const disabled = !connected || !available || exerciseBusy || Boolean(selectedBranch);
  const objects = exercise?.eligible_objects || [], assets = exercise?.assets || [], branches = exercise?.branches || [];
  const displayedObjects = selectedBranch ? [...new Set([selectedBranch.object_id,...objects])] : objects;
  const missions=exerciseMissionRows(state);
  const selectedMission=missions.find(mission=>mission.object_id===$('exercise-object').value);
  for (const [id, rows, label] of [['exercise-object',displayedObjects.map(id=>({id,label:id})),'exercise.chooseObject'],['exercise-asset',assets.map(asset=>({id:asset.id,label:localized(asset.label)})),'exercise.chooseAsset']]) {
    const select = $(id), signature = JSON.stringify([language,rows]);
    if (select.dataset.signature !== signature) {
      const previous = select.value;
      select.innerHTML = `<option value="">${escape(t(label))}</option>` + rows.map(row=>`<option value="${escape(row.id)}">${escape(row.label)}</option>`).join('');
      if(rows.some(row=>row.id===previous))select.value=previous;
      select.dataset.signature = signature;
    }
    if(id==='exercise-asset' && selectedMission)select.value=selectedMission.asset_id;
    if(selectedBranch)select.value=id==='exercise-object'?selectedBranch.object_id:selectedBranch.asset_id;
    select.disabled = disabled || !objects.length || (id==='exercise-asset' && Boolean(selectedMission));
  }
  $('exercise-fixed-asset').hidden=!selectedMission;
  const missionSignature=JSON.stringify([language,missions,disabled,objects,assets.map(asset=>[asset.id,asset.label])]);
  if($('exercise-missions').dataset.signature!==missionSignature) {
    $('exercise-missions').dataset.signature=missionSignature;
    $('exercise-missions').innerHTML=missions.map(mission=>`<article><strong>${escape(mission.object_id)} · ${escape(t(`exercise.kind.${mission.kind}`))}</strong><p>${escape(t(`exercise.phase.${mission.phase}`))} · ${escape(localized(assets.find(asset=>asset.id===mission.asset_id)?.label) || mission.asset_id)}</p><span>${escape(mission.outcome?t(`exercise.outcome.${mission.outcome}`):t('exercise.outcome.pending'))}${mission.result_at_ms===null?'':` · ${fmt(mission.result_at_ms)}`}</span><button type="button" class="button button-secondary" data-exercise-object="${escape(mission.object_id)}" ${disabled || !objects.includes(mission.object_id)?'disabled':''}>${escape(t('exercise.open'))}</button></article>`).join('') || `<p class="muted">${escape(t('exercise.missionEmpty'))}</p>`;
    $('exercise-missions').querySelectorAll('[data-exercise-object]').forEach(button=>button.onclick=()=>{
      $('exercise-object').value=button.dataset.exerciseObject;
      exerciseDraft=null;exerciseError=false;exerciseExpired=false;renderExercise();
      $('exercise-options').scrollIntoView({block:'nearest'});
      $('exercise-options').querySelector('button:not(:disabled)')?.focus();
    });
  }
  const assetSignature = JSON.stringify([language,assets]);
  if ($('exercise-assets').dataset.signature !== assetSignature) {
    $('exercise-assets').dataset.signature = assetSignature;
    $('exercise-assets').innerHTML = assets.map(asset=>`<li><strong>${escape(localized(asset.label))}</strong><span>${escape(localized(asset.role))}</span><span>${escape(t(`exercise.status.${asset.status}`))}</span><button type="button" class="button button-secondary" data-focus-asset="${escape(asset.id)}">${escape(t('exercise.focus'))}</button></li>`).join('');
    $('exercise-assets').querySelectorAll('[data-focus-asset]').forEach(button=>button.onclick=()=>{
      const asset=state?.exercise?.assets.find(item=>item.id===button.dataset.focusAsset);
      if(asset?.position){plan.x=asset.position[0];plan.z=asset.position[2];plan.zoom=8;revealMap();setMode('site');}
    });
  }
  const canChoose = !disabled && objects.includes($('exercise-object').value) && assets.some(asset=>asset.id===$('exercise-asset').value);
  const chosenBranch=selectedBranch?.branch_id || exerciseDraft?.branch_id;
  const optionsSignature = JSON.stringify([language,branches,canChoose,chosenBranch,selectedMission?.id]);
  if ($('exercise-options').dataset.signature !== optionsSignature) {
    $('exercise-options').dataset.signature = optionsSignature;
    $('exercise-options').innerHTML = branches.map(branch=>`<article><h3>${escape(localized(branch.label))}</h3><p>${escape(localized(branch.description))}</p><p class="decision-effect">${escape(t('exercise.predefined'))}<br>${escape(t(`exercise.motion.${branch.motion}`))}<br>${escape(t('exercise.facilityResult',{status:t(`exercise.status.${branch.asset_state}`)}))}<br>${escape(t((selectedMission?branch.mission_result_timing:branch.result_timing)==='finale'?'exercise.finaleDelay':'exercise.delay',{seconds:branch.delay_ms/1000}))}</p><button type="button" class="button button-secondary" data-exercise-branch="${escape(branch.id)}" aria-pressed="${chosenBranch===branch.id}" ${canChoose?'':'disabled'}>${escape(t(chosenBranch===branch.id?'exercise.chosen':'exercise.choose'))}</button></article>`).join('');
    $('exercise-options').querySelectorAll('[data-exercise-branch]').forEach(button=>button.onclick=()=>{
      exerciseDraft = {run_id:state.run_id,object_id:$('exercise-object').value,asset_id:$('exercise-asset').value,branch_id:button.dataset.exerciseBranch};
      exerciseError=false;exerciseExpired=false;renderExercise();
      if(exerciseDraft && !$('exercise-dialog').open) { $('exercise-dialog').dataset.restoreChoice=exerciseDraft.branch_id; $('exercise-dialog').showModal(); }
    });
  }
  $('exercise-confirm').disabled = disabled || !exerciseConfirmation(state,exerciseDraft,true);
  let status = exerciseBusy ? t('exercise.saving') : exerciseError ? t('exercise.failed') : exerciseExpired ? t('dashboard.expired') : !connected ? t('exercise.disconnected') : !available ? t('exercise.unavailable') : !objects.length ? t('exercise.waiting') : t('exercise.ready');
  if(selectedBranch) {
    const branch=branches.find(item=>item.id===selectedBranch.branch_id), asset=assets.find(item=>item.id===selectedBranch.asset_id);
    status = t(selectedBranch.status==='applied'?'exercise.applied':'exercise.pending',{object:selectedBranch.object_id,asset:localized(asset?.label),branch:localized(branch?.label),time:fmt(selectedBranch.effective_at_ms)});
  } else if(exerciseDraft && !exerciseBusy && !exerciseError) {
    status = t('exercise.confirmSummary',{object:exerciseDraft.object_id,asset:localized(assets.find(item=>item.id===exerciseDraft.asset_id)?.label),branch:localized(branches.find(item=>item.id===exerciseDraft.branch_id)?.label)});
  }
  $('exercise-status').textContent = status;
  $('exercise-modal-summary').textContent=status;
  $('exercise-modal-effect').textContent=localized(branches.find(item=>item.id===exerciseDraft?.branch_id)?.description);
  $('exercise-modal-context').textContent=state?t('exercise.modalTime',{now:fmt(state.at_ms),effective:fmt(state.at_ms+5000)}):'';
}
$('exercise-dialog').addEventListener('cancel',()=>{exerciseDraft=null;exerciseExpired=false;renderExercise();});
$('exercise-cancel').onclick=()=>{exerciseDraft=null;exerciseExpired=false;renderExercise();};
for (const id of ['exercise-object','exercise-asset']) $(id).onchange=()=>{exerciseDraft=null;exerciseError=false;exerciseExpired=false;renderExercise();};
$('exercise-confirm').onclick=()=>{
  if(!connected || exerciseBusy)return;
  const draft=exerciseDraft;
  if(!exerciseConfirmation(state,draft,true))return;
  exerciseBusy=true;exerciseError=false;renderExercise();
  controlChain=controlChain.then(async()=>{
    const body=connected && exerciseDraft===draft ? exerciseConfirmation(state,draft,true) : null;
    if(!body){exerciseBusy=false;exerciseDraft=null;exerciseExpired=true;renderExercise();return;}
    const version=++requestVersion;
    try {const data=await api('/api/control',body);if(version===requestVersion)render(data);exerciseDraft=null;}
    catch {exerciseError=true;}
    finally {exerciseBusy=false;renderExercise();}
  });
};

function renderWorkload() {
  syncSelects();
  if (!state) return;
  const queue = reviewQueue(state.tracks, state.track_reviews);
  $('workload-summary').innerHTML = [['received',queue.received],['current',queue.current],['attention',queue.attention],['unreviewed',queue.unreviewed]].map(([key,count])=>`<div><strong>${count}</strong><span>${t(`workload.${key}`)}</span></div>`).join('');
  const fleet = state.sensor_fleet;
  $('fleet-groups').innerHTML = (fleet?.groups || []).map(group=>`<article><h3>${escape(localized(group.label))}</h3><strong>${group.total}</strong><p>${['online','offline','stale','waiting'].map(status=>`${t(`fleet.${status}`)} ${group.counts[status] || 0}`).join(' · ')}</p></article>`).join('');
  const received = (fleet?.sensors || []).filter(sensor=>sensor.last_seen_ms !== null && sensor.last_seen_ms !== undefined);
  const last = received.length ? fmt(Math.max(...received.map(sensor=>sensor.last_seen_ms))) : t('none');
  $('fleet-last-seen').textContent = t('fleet.lastSeen',{total:fleet?.total || 0,received:received.length,time:last});
}
function renderCommentSuggestions(scope, keys, disabled=false) {
  syncSelects();
  const box=$(`${scope}-suggestions`);
  const selected=selectedComments[scope];
  const options=selected && !keys.includes(selected)?[...keys,selected]:keys;
  const signature=JSON.stringify([language,options,selected,disabled]);
  if(box.dataset.signature===signature)return;
  box.dataset.signature=signature;
  box.innerHTML=options.map(key=>`<button type="button" class="button button-secondary" data-comment="${key}" aria-pressed="${selected===key}" ${disabled?'disabled':''}>${escape(t(`review.suggest.${key}`))}</button>`).join('');
  box.querySelectorAll('[data-comment]').forEach(button=>button.onclick=()=>{
    selectedComments[scope]=selectedComments[scope]===button.dataset.comment?'':button.dataset.comment;
    if(scope==='track')renderDetails();else renderSituation();
  });
}
function trackReviewStatus(key='') {
  $('track-review-status').dataset.i18n = key;
  $('track-review-status').textContent = key ? t(key) : '';
}
function updateTrackReviewAvailability() {
  syncSelects();
  const track = state?.tracks.find(track=>track.object_id===selected);
  const stale = track && reviewTargetVersion && track.evidence_version !== reviewTargetVersion;
  $('track-review-submit').disabled = !connected || trackReviewBusy || !track || Boolean(stale);
  for(const id of ['reviewer','track-decision','track-reason','review-refresh']) $(id).disabled = !connected || trackReviewBusy || !track;
  document.querySelectorAll('#track-suggestions button').forEach(button=>button.disabled=!connected || trackReviewBusy || !track);
  if (stale && !trackReviewBusy) trackReviewStatus('review.changed');
}
function renderEvidenceExplanation(track) {
  syncSelects();
  const key = `${state.run_id}:${track?.object_id || ''}`;
  if (reviewTargetKey !== key) {
    const hadDraft = Boolean($('track-reason').value.trim() || selectedComments.track);
    selectedComments.track='';
    $('track-reason').value = '';
    reviewTargetKey = key; reviewTargetVersion = track?.evidence_version || '';
    trackReviewStatus(hadDraft ? 'situation.reset' : '');
  } else if (!$('track-reason').value.trim() && !selectedComments.track && !trackReviewBusy) {
    reviewTargetVersion = track?.evidence_version || '';
  }
  const explanation = track?.explanation;
  $('evidence-explanation').innerHTML = explanation ? `<p class="explanation-status">${t('explain.observation')}: ${t(`explain.${explanation.observation_status}`)}<br>${t('explain.evidenceStatus')}: ${t(`explain.${explanation.evidence_status}`)}</p>` + ['known','uncertain','missing'].map(section=>`<section><h3>${t(`explain.${section}`)}</h3><ul>${explanation[section].map(item=>`<li>${escape(t(`rule.${item.code}`))}${item.source_id ? ` · ${escape(item.source_id)}` : ''}<small>${(item.evidence_ids || []).map(escape).join(', ') || t('none')}</small></li>`).join('') || `<li>${t('none')}</li>`}</ul></section>`).join('') : '';
  $('review-version').textContent = track ? t('review.version',{id:track.object_id,version:reviewTargetVersion.slice(0,12)}) : t('awaitingDetection');
  const summary = state.review_summary;
  $('audit-summary').textContent = t('review.counts',{current:summary?.current_run || 0,total:summary?.total_saved || 0});
  renderCommentSuggestions('track',commentSuggestions(track),!track || trackReviewBusy || !connected);
  updateTrackReviewAvailability();
}
$('queue-filter').onchange = () => {queueFilter=$('queue-filter').value;queuePage=0;renderDetails();};
$('queue-prev').onclick = () => {queuePage--;renderDetails();};
$('queue-next').onclick = () => {queuePage++;renderDetails();};
$('track-reason').oninput = updateTrackReviewAvailability;
$('review-refresh').onclick = () => { selectedComments.track=''; $('track-reason').value=''; trackReviewStatus(); renderDetails(); };
$('track-review-form').onsubmit = event => {
  event.preventDefault();
  const track = state?.tracks.find(track=>track.object_id===selected);
  if (!connected || trackReviewBusy || !track || track.evidence_version !== reviewTargetVersion) return;
  const body = {action:'review_track',run_id:state.run_id,object_id:selected,evidence_version:reviewTargetVersion,
    reviewer:$('reviewer').value.trim(),decision:$('track-decision').value,reason:reviewComment(selectedComments.track,$('track-reason').value,t)};
  const target = reviewTargetKey;
  trackReviewBusy=true;updateTrackReviewAvailability();trackReviewStatus('situation.saving');
  controlChain=controlChain.then(async()=>{
    const version=++requestVersion;
    try {
      const data=await api('/api/control',body);
      if(version===requestVersion)render(data);
      if(reviewTargetKey===target){selectedComments.track='';$('track-reason').value='';renderDetails();trackReviewStatus('review.saved');}
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
  syncSelects();
  const unavailable = !connected || reviewPending || !state?.situation?.events?.length;
  for (const id of ['situation-event-select','situation-decision','situation-reason','situation-submit']) $(id).disabled = unavailable;
  document.querySelectorAll('#situation-suggestions button').forEach(button=>button.disabled=unavailable);
}
function renderSituation() {
  syncSelects();
  const situation = state?.situation;
  const events = situation?.events || [];
  const eventSelect = $('situation-event-select');
  const previous = eventSelect.value;
  const changedRun = situationRun !== null && situationRun !== state.run_id;
  const removedEvent = previous && !events.some(event => event.id === previous);
  if (changedRun || removedEvent) {
    const hadDraft = Boolean($('situation-reason').value.trim() || selectedComments.situation);
    selectedComments.situation='';
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
  renderCommentSuggestions('situation',['verify_source','more_evidence','revisit'],!connected || reviewPending || !events.length);
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
    let link = escape(language==='ko' ? source.title_ko || source.title : source.title);
    try { const url = new URL(source.url); if (['https:','http:'].includes(url.protocol)) link = `<a href="${escape(url.href)}" target="_blank" rel="noopener noreferrer">${link}</a>`; } catch { /* Keep an invalid reference as plain text. */ }
    return `<li class="situation-card"><h3>${link}</h3><p class="muted">${escape(source.publisher)} · ${escape(source.published_at)} · ${escape(source.id)}</p><p><strong>${t('situation.claim')}:</strong> ${escape(localized(source.claim))}</p><p><strong>${t('situation.use')}:</strong> ${escape(localized(source.simulation_use))}</p></li>`;
  }).join('') || `<li class="empty-state">${t('situation.noSources')}</li>`;
}
$('situation-event-select').onchange = () => {
  selectedComments.situation='';
  $('situation-reason').value = '';
  $('situation-decision').value = 'noted';
  reviewStatus();renderSituation();
};
$('situation-review-form').onsubmit = event => {
  event.preventDefault();
  if (reviewPending || !connected || !state?.situation?.events?.length) return;
  const reason = reviewComment(selectedComments.situation,$('situation-reason').value,t);
  const body = {action:'review_event',run_id:state.run_id,event_id:$('situation-event-select').value,decision:$('situation-decision').value,reason};
  reviewPending = true; updateReviewAvailability();
  reviewStatus('situation.saving');
  controlChain = controlChain.then(async () => {
    const version = ++requestVersion;
    try {
      const data = await api('/api/control',body);
      if (version === requestVersion) render(data);
      if (state.run_id === body.run_id && $('situation-event-select').value === body.event_id) {
        selectedComments.situation='';$('situation-reason').value = '';
        renderSituation();reviewStatus('situation.saved');
      }
    } catch {
      reviewStatus('situation.failed');
    } finally { reviewPending = false; updateReviewAvailability(); }
  });
};

function zoneLabel(zone) { return zone?.label?.[language] || zone?.label?.en || zone?.id || t('early.unknown'); }
// The forward reference area is site-plan-only unless the server marks it georeferenced.
function schematicZone(zone) { return zone?.id==='remote_reference' && zone.georeferenced!==true; }
function focusZone(id) {
  const zone = state?.early_warning?.zones.find(z=>z.id===id);
  if(!zone || !config)return;
  if(schematicZone(zone)) {
    revealMap();
    const received=earlyIndicationSummary(state).zones.some(item=>item.id===zone.id && item.positive>0);
    if(!received)return;
    const base=Math.min(map.clientWidth/(config.site.perimeter.width_m*1.35),map.clientHeight/(config.site.perimeter.length_m*1.6));
    Object.assign(plan,{x:zone.center[0],z:zone.center[2],zoom:Math.min(30,Math.min(map.clientWidth,map.clientHeight)*.7/(zone.radius_m*2*base))});
    setMode('site');map.focus({preventScroll:true});return;
  }
  revealMap();
  const [lat,lon]=localToGeo(zone.center[0],zone.center[2],config.regional_map.site_origin);
  // Fit about three area diameters (≈ zoom 11 for a 4 km forward area), never closer than the community view.
  const fit=Math.floor(Math.log2((Math.min(map.clientWidth,map.clientHeight) || 480)*.8/(zone.radius_m*6*pixelsPerMeter(lat,0))));
  Object.assign(region,{lat,lon,zoom:zone.deployment_type==='fixed_phone'?17:Math.max(3,Math.min(14,Number.isFinite(fit)?fit:14))});setMode('region');
}
function deviceHealthHTML(evidence) {
  if (!evidence.device_health) return '';
  const health = evidence.device_health;
  const power = ['external','battery'].includes(health.power_status) ? health.power_status : 'unknown';
  const network = ['online','offline'].includes(health.network_status) ? health.network_status : 'unknown';
  return `<small class="device-health">${t('early.healthAsReported')}: ${t('early.power')} ${t(`early.power.${power}`)} · ${t('early.network')} ${t(`early.network.${network}`)}</small>`;
}
function renderEarlyWarning() {
  syncSelects();
  const feed=state?.early_warning;
  if(!feed)return;
  $('early-count').textContent=feed.zones.filter(z=>z.positive_sources>0).length;
  $('panel-signal-count').textContent=$('early-count').textContent;
  $('panel-signal-count').hidden=Number($('early-count').textContent)===0;
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
function visibleSignalZones() {
  const positive=new Set(earlyIndicationSummary(state).zones.filter(zone=>zone.positive>0).map(zone=>zone.id));
  return (state?.early_warning?.zones || []).filter(zone=>!schematicZone(zone) || positive.has(zone.id));
}
// Boundary and corridor paths are projected once per config to zoom-0 Web Mercator; redraws only scale and offset them.
function geography() {
  if(geographyCache?.config===config)return geographyCache;
  const origin=config.regional_map.site_origin;
  const node=(x,z,latLon)=>{const [lat,lon]=Array.isArray(latLon) && latLon.length===2 && latLon.every(Number.isFinite)?latLon:localToGeo(x,z,origin);return [x,z,...mercator(lat,lon,0)];};
  const path=(local,latLon=[])=>(local || []).map((row,index)=>{const z=row?.[row.length-1];return Number.isFinite(row?.[0]) && Number.isFinite(z)?node(row[0],z,latLon[index]):null;}).filter(Boolean);
  const site=row=>Array.isArray(row) && row.length===3 && row.every(Number.isFinite)?node(row[0],row[2]):null;
  const lines=Object.entries(config.geography?.boundaries?.lines || {}).map(([id,line])=>({id,label:line.label,
    parts:(line.parts || []).map(part=>path(part.local,part.lat_lon)).filter(part=>part.length>1)})).filter(line=>line.parts.length);
  const corridors=(config.geography?.corridors?.corridors || []).map(row=>({id:row.id,label:row.label,centreline:path(row.centreline),launch:site(row.launch),gate:site(row.gate)}))
    .filter(row=>row.centreline.length>1);
  geographyCache={config,lines,corridors};
  return geographyCache;
}
function geographySVG(w,h) {
  const geo=geography();
  let project;
  if(mode==='region'){const k=2**region.zoom,[cx,cy]=mercator(region.lat,region.lon,region.zoom);project=n=>[w/2+n[2]*k-cx,h/2+n[3]*k-cy];}
  else {const s=planScale();project=n=>[w/2+(n[0]-plan.x)*s,h/2+(n[1]-plan.z)*s];}
  const inside=([x,y],margin=0)=>x>=margin && x<=w-margin && y>=margin && y<=h-margin;
  const polyline=points=>points.map(p=>`${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(' ');
  const text=(x,y,color,value,size=10)=>`<text x="${x.toFixed(1)}" y="${y.toFixed(1)}" fill="${color}" stroke="#0a151b" stroke-width="3" paint-order="stroke" font-size="${size}" font-weight="600">${escape(value)}</text>`;
  let svg='',visible=false;
  for(const line of geo.lines){
    const mdl=line.id==='mdl',color=mdl?'#e5675a':'#dfb86a';
    const parts=line.parts.map(part=>part.map(project)),points=parts.flat();
    const xs=points.map(p=>p[0]),ys=points.map(p=>p[1]);
    if(Math.max(...xs)<0 || Math.min(...xs)>w || Math.max(...ys)<0 || Math.min(...ys)>h)continue;
    visible=true;
    for(const part of parts)svg+=`<polyline class="geo-${escape(line.id)}" points="${polyline(part)}" fill="none" stroke="${color}" stroke-width="${mdl?2.2:1.5}" ${mdl?'':'stroke-dasharray="7 5"'} stroke-linejoin="round" opacity=".9"/>`;
    const anchor=points.filter(p=>inside(p,28)).sort((a,b)=>Math.abs(a[0]-w/2)-Math.abs(b[0]-w/2))[0];
    const key=`geo.${line.id}`;
    if(anchor)svg+=text(anchor[0]+6,anchor[1]+(line.id==='dmz_south'?14:-6),color,localized(line.label) || (t(key)!==key?t(key):line.id));
  }
  if(showCorridors)for(const corridor of geo.corridors){
    const color='#b9a2e8';
    svg+=`<polyline class="geo-corridor" points="${polyline(corridor.centreline.map(project))}" fill="none" stroke="${color}" stroke-width="1.6" stroke-dasharray="2 5" stroke-linecap="round" opacity=".85"/>`;
    if(corridor.launch){const [x,y]=project(corridor.launch);svg+=`<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="7" fill="${color}22" stroke="${color}" stroke-dasharray="3 3"/>${text(x+10,y+4,color,`${localized(corridor.label) || corridor.id} · ${t('geo.launch')}`,9)}`;}
    if(corridor.gate){const [x,y]=project(corridor.gate);svg+=`<path d="M${x.toFixed(1)} ${(y-6).toFixed(1)}l6 6l-6 6l-6-6z" fill="#0a151b" stroke="${color}" stroke-width="1.5"/>${text(x+9,y+3,color,t('geo.gate'),9)}`;}
  }
  $('geo-legend').hidden=!visible;
  $('corridor-legend').hidden=!showCorridors || !geo.corridors.length;
  return svg;
}
function drawSite() {
  const {site} = config, w=map.clientWidth,h=map.clientHeight,s=planScale();
  overlay.setAttribute('viewBox',`0 0 ${w} ${h}`);
  let svg = '<defs><pattern id="grid" width="50" height="50" patternUnits="userSpaceOnUse"><path d="M 50 0 L 0 0 0 50" fill="none" stroke="#48717a26" stroke-width="1"/></pattern></defs><rect width="100%" height="100%" fill="#0a151b"/><rect width="100%" height="100%" fill="url(#grid)"/>';
  if(mode==='region') svg='';
  svg+=geographySVG(w,h);
  const rect=(cx,cz,width,length,fill,stroke,extra='')=>{const [x,y]=point(cx-width/2,cz-length/2),[right,bottom]=point(cx+width/2,cz+length/2);return `<rect x="${x}" y="${y}" width="${right-x}" height="${bottom-y}" fill="${fill}" stroke="${stroke}" ${extra}/>`;};
  for(const z of visibleSignalZones()){
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
    const asset=connected?exerciseMapAssets(state).find(asset=>asset.id===f.id):null;
    const fill=asset?.status==='unavailable'?'#5b302c':asset?.status==='restricted'?'#85652c':'#617b74';
    svg+=rect(f.position[0],f.position[2],size[0]*f.scale[0],size[1]*f.scale[2],fill,asset?.status==='unavailable'?'#ff8866':'#a3b6a4');
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
  // Nominal rings for placed sensors and teams: display assumptions, drawn on the site plan only.
  const ringKinds=new Map((state?.exercise?.unit_kinds || []).filter(kind=>Number.isFinite(kind.display_range_m) && kind.display_range_m>0).map(kind=>[kind.id,kind.display_range_m]));
  const ringUnits=connected && mode==='site'?(state?.exercise?.units || []).filter(unit=>ringKinds.has(unit.kind) && Array.isArray(unit.position) && unit.position.every(Number.isFinite)):[];
  for(const unit of ringUnits){
    const [cx,cy]=point(unit.position[0],unit.position[2]);
    const color=({radar:'#8bc9cf',detection_phone:'#dfb86a',effector_team:'#ef9281'})[unit.kind] || '#9fb4bd';
    svg+=`<circle class="unit-range" cx="${cx}" cy="${cy}" r="${ringKinds.get(unit.kind)*s}" fill="${color}0d" stroke="${color}" stroke-opacity=".55" stroke-width="1" stroke-dasharray="5 6"/>`;
  }
  $('unit-range-legend').hidden=!ringUnits.length;
  // A pending radar re-adjustment previews each move as a dashed arrow; nothing moves until it is applied.
  const adjustment=connected?pendingRadarAdjustment(state):null;
  if(adjustment?.moves.length){
    svg+='<defs><marker id="radar-adjust-head" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0 0L10 5L0 10z" fill="#8bc9cf"/></marker></defs>';
    for(const move of adjustment.moves){
      const [x1,y1]=point(move.from_position[0],move.from_position[2]),[x2,y2]=point(move.to_position[0],move.to_position[2]);
      const length=Math.hypot(x2-x1,y2-y1),trim=length>24?10/length:0;
      svg+=`<line class="radar-adjust-arrow" x1="${x1}" y1="${y1}" x2="${x2-(x2-x1)*trim}" y2="${y2-(y2-y1)*trim}" stroke="#8bc9cf" stroke-width="2" stroke-dasharray="6 5" marker-end="url(#radar-adjust-head)"/><circle cx="${x2}" cy="${y2}" r="9" fill="none" stroke="#8bc9cf" stroke-width="1.5" stroke-dasharray="3 3"/>`;
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
  if(connected){
    const proposal=state?.exercise?.unit_proposal;
    const units=state?.exercise?.units || [];
    const proposed=proposal?.status==='pending'?proposalPositions(proposal).map((row,index)=>({...row,id:`proposal-${index}`,label:localized(row.label) || t('units.preview',{number:index+1}),preview:true})):[];
    const added=(pendingRadarAdjustment(state)?.additions || []).map((row,index)=>({kind:'radar',position:row.position,id:`radar-addition-${index}`,
      label:localized(row.label) || t('units.preview',{number:index+1}),preview:true,note:t('units.radarAdjustTitle')}));
    for(const unit of [...proposed,...added,...units]){
      if(!Array.isArray(unit.position) || !unit.position.every(Number.isFinite))continue;
      const [x,y]=point(unit.position[0],unit.position[2]);if(x<0||x>w||y<0||y>h)continue;
      const marker=document.createElement(unit.preview?'div':'button');
      marker.className=`infantry-marker unit-marker${unit.preview?' is-preview':''}`;marker.dataset.unitId=unit.id;marker.dataset.kind=unit.kind || 'infantry';
      marker.style.left=`${x}px`;marker.style.top=`${y}px`;
      const label=unit.preview?unit.label:localized(unit.label) || unit.id;
      const kind=unitKindLabel(unit.kind || 'infantry');
      marker.innerHTML=`<i aria-hidden="true">${unitIcon(unit.kind)}</i><span>${escape(label)}</span>`;
      marker.title=`${kind} · ${unit.preview?`${t('units.proposed')} · ${unit.note || localized(unit.basis) || t('units.pending')}`:t('units.positioned')}${ringKinds.has(unit.kind)?` · ${t('units.range',{range:(ringKinds.get(unit.kind)/1000).toLocaleString(language)})} · ${t('units.rangeLegend')}`:''}`;
      if(!unit.preview){marker.type='button';marker.setAttribute('aria-label',`${label} · ${kind} · ${t('units.positioned')}`);marker.onclick=()=>{showPanel('decision');$('unit-panel').scrollIntoView({block:'nearest'});};}
      markers.append(marker);
    }
  }
  if(connected) for(const asset of exerciseMapAssets(state)){
    const [x,y]=point(asset.position[0],asset.position[2]);
    if(x<0||x>w||y<0||y>h)continue;
    const marker=document.createElement('button');
    marker.className='facility-result-marker';marker.dataset.status=asset.status;
    marker.style.left=`${x}px`;marker.style.top=`${y}px`;
    const status=asset.selection?.status==='pending'?t('exercise.mapPending',{time:fmt(asset.selection.effective_at_ms)}):t(`exercise.status.${asset.status}`);
    marker.textContent=`${localized(asset.label)} · ${status}`;
    marker.title=asset.branch?t('exercise.mapSelected',{branch:localized(asset.branch.label)}):status;
    marker.onclick=()=>{showPanel('decision');$('exercise-panel').open=true;$('exercise-panel').scrollIntoView({block:'start'});};
    markers.append(marker);
  }
  for(const z of visibleSignalZones()){
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
    marker.onclick=()=>{select(t.object_id);showPanel('evidence');}; markers.append(marker);
  }
  if(showPositions && connected) for(const drone of state?.simulation_positions || []){
    const [x,y]=point(drone.position[0],drone.position[2]);
    if(x<0||x>w||y<0||y>h) continue;
    const marker=document.createElement('div');
    marker.className='truth-marker';
    marker.setAttribute('role','img');
    const markerLabel=t('positions.marker',{id:drone.object_id});
    marker.setAttribute('aria-label',markerLabel);
    marker.style.left=`${x}px`;marker.style.top=`${y}px`;
    marker.innerHTML=`<span>${escape(markerLabel)}</span>`;
    marker.title=`${markerLabel} · ${t('positions.warning')}`;
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
      <text x="${cx-8}" y="${cy-10}" text-anchor="end" fill="${color}" font-size="9">${escape(localized(config.radar_display.stations.find(station=>station.id===frame.id)?.label) || frame.id)}${online?'':` · ${escape(connected?sourceLabel(frame.health):t('disconnected'))}`}</text>
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
$('corridors-toggle').onclick=()=>{showCorridors=!showCorridors;$('corridors-toggle').classList.toggle('is-active',showCorridors);$('corridors-toggle').setAttribute('aria-pressed',String(showCorridors));drawMap();};
$('radar-toggle').onclick=()=>{radarVisible=!radarVisible;$('radar-toggle').classList.toggle('is-active',radarVisible);$('radar-toggle').setAttribute('aria-pressed',radarVisible);drawRadar(state?.at_ms || 0);};
function animateRadar(now) {
  if(state?.playing && radarVisible && connected && !$('monitor-view').hidden && map.clientWidth > 0)
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
function zoom(delta){ if(mode==='site')plan.zoom=Math.max(.01,Math.min(30,plan.zoom*(delta>0?1.35:1/1.35)));else region.zoom=Math.max(3,Math.min(18,region.zoom+delta)); drawMap(); }
$('site-plan-button').onclick=()=>setMode('site');$('region-map-button').onclick=()=>setMode('region');
$('zoom-in').onclick=()=>zoom(1);$('zoom-out').onclick=()=>zoom(-1);
$('recenter').onclick=()=>{plan.x=plan.z=0;plan.zoom=1;Object.assign(region,{lat:config.regional_map.center_lat,lon:config.regional_map.center_lon,zoom:config.regional_map.zoom});drawMap();};
let drag=null;
map.addEventListener('pointerdown',e=>{if(drag){drag.cancelled=true;return;}if(e.button!==0||e.target.closest('button,a,input,select,textarea'))return;drag={x:e.clientX,y:e.clientY,startX:e.clientX,startY:e.clientY,id:e.pointerId,moved:false,placement:unitPlacement};map.setPointerCapture(e.pointerId);});
map.addEventListener('pointermove',e=>{if(!drag || e.pointerId!==drag.id)return;
  drag.moved ||= Math.hypot(e.clientX-drag.startX,e.clientY-drag.startY)>6;
  if(!drag.moved)return;
  const dx=e.clientX-drag.x,dy=e.clientY-drag.y;drag.x=e.clientX;drag.y=e.clientY;
  if(mode==='site'){plan.x-=dx/planScale();plan.z-=dy/planScale();}
  else{const [x,y]=mercator(region.lat,region.lon,region.zoom);[region.lat,region.lon]=unproject(x-dx,y-dy,region.zoom);region.lat=Math.max(-85,Math.min(85,region.lat));region.lon=((region.lon+180)%360+360)%360-180;}
  drawMap();});
map.addEventListener('pointerup',e=>{
  if(!drag || e.pointerId!==drag.id)return;
  const gesture=drag;drag=null;
  if(!unitPlacement || unitPlacement!==gesture.placement || gesture.moved || gesture.cancelled || unitBusy
      || Math.hypot(e.clientX-gesture.startX,e.clientY-gesture.startY)>6)return;
  const bounds=map.getBoundingClientRect(),x=e.clientX-bounds.left,y=e.clientY-bounds.top;
  if(x<0||x>map.clientWidth||y<0||y>map.clientHeight)return;
  const position=mapToLocal(x,y,{mode,width:map.clientWidth,height:map.clientHeight,plan,scale:planScale(),region,origin:config.regional_map.site_origin});
  sendUnitCommand({action:'exercise_place_unit',...unitPlacement,position});
});
map.addEventListener('pointercancel',()=>drag=null);
map.addEventListener('lostpointercapture',()=>drag=null);
map.addEventListener('wheel',e=>{e.preventDefault();if(drag)drag.cancelled=true;zoom(e.deltaY<0?1:-1);},{passive:false});
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
// Panel navigation changes only presentation; the simulation clock keeps running.
const compactWorkspace = window.matchMedia('(max-width: 1099px)');
let activePanel = compactWorkspace.matches ? 'map' : 'decision';
function showPanel(panel) {
  syncSelects();
  activePanel = panel === 'map' && !compactWorkspace.matches ? 'decision' : panel;
  $('workbench').dataset.panel = activePanel;
  for (const button of document.querySelectorAll('[data-panel].panel-tab')) {
    button.setAttribute('aria-pressed', String(button.dataset.panel === activePanel));
  }
  for (const pane of document.querySelectorAll('.workspace-pane')) pane.hidden = pane.id !== `pane-${activePanel}`;
  drawMap();
}
for (const button of document.querySelectorAll('[data-panel].panel-tab')) button.onclick = () => showPanel(button.dataset.panel);
compactWorkspace.addEventListener('change', () => showPanel(activePanel));
showPanel(activePanel);
document.querySelector('#decision-attention a').onclick = event => {
  event.preventDefault();
  showPanel('decision');
  $('decision-title').scrollIntoView({block:'nearest'});
  $('decision-title').focus({preventScroll:true});
};
function revealMap() {
  showView('monitor');
  if (compactWorkspace.matches) showPanel('map');
}
function showView(view) {
  if (compactWorkspace.matches) showPanel('map');
  const monitor=view!=='alerts';$('monitor-view').hidden=!monitor;$('alerts-view').hidden=monitor;
  $(monitor?'map-events-host':'alerts-events-host').append($('received-events-panel'));
  for(const b of document.querySelectorAll('[data-view]')){const active=b.dataset.view===(monitor?'monitor':'alerts');b.classList.toggle('is-active',active);if(active)b.setAttribute('aria-current','page');else b.removeAttribute('aria-current');}drawMap();
}
for(const tab of document.querySelectorAll('[data-view]'))tab.onclick=()=>showView(tab.dataset.view);

function renderNotificationSettings() {
  renderAlertAudio();
  syncSelects();
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
    if(alert.kind==='review_transition')return t('priority.direct_transition');
    if(alert.kind==='review_expired')return t('priority.choice_expired');
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
  syncSelects();
  const caseId=state?.case_id || $('case-select').value;
  const brief=briefings.find(b=>b.case_id===caseId);
  if(!brief)return;
  const counts=reviewQueue(state?.tracks || []);
  $('brief-counts').textContent=t('brief.counts',{total:brief.object_count ?? brief.object_ids.length,received:counts.received,current:counts.current});
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
  syncSelects();
  if (!config) return;
  const current = state?.case_id || $('case-select').value;
  $('case-select').innerHTML = config.cases.map(c => `<option value="${escape(c.case_id)}">${escape(c.case_id)} · ${escape(localized(briefings.find(b=>b.case_id===c.case_id)?.name) || t(`variant.${c.variant}`))}</option>`).join('');
  if (current) $('case-select').value = current;
}
function applyLanguage(next, persist = false) {
  syncSelects();
  language = normalizeLanguage(next);
  if (persist) { try { saveLanguage(localStorage, language); } catch { /* Storage may be unavailable. */ } }
  document.documentElement.lang = language;
  document.title = t('title');
  if (typeof renderAgentSettings === 'function') queueMicrotask(renderAgentSettings);
  $('language-select').value = language;
  for (const element of document.querySelectorAll('[data-i18n]')) element.textContent = t(element.dataset.i18n);
  for (const attribute of ['aria-label','title','placeholder']) {
    for (const element of document.querySelectorAll(`[data-i18n-${attribute}]`)) {
      element.setAttribute(attribute, t(element.getAttribute(`data-i18n-${attribute}`)));
    }
  }
  for (const element of document.querySelectorAll('[data-empty]')) element.dataset.empty = t('waitingData');
  renderCases();
  renderBriefing();
  renderRehearsalRuns($('rehearsal-run').value);renderRehearsals();
  if (state) { renderPlayback(state); renderDetails(); renderEarlyWarning(); renderSituation(); renderWorkload(); renderAssessment(); renderDecisions(); renderDashboard(); renderTactics(); }
  drawMap();
  if (connected !== null) connection(connected, connectionMessage);
  if (!config && connected === false) $('map-status').textContent = t('requestFailed');
  renderNotificationSettings();
  renderDesktop();
}
$('language-select').onchange = event => {applyLanguage(event.target.value, true);syncDecisionLanguage();};
let notificationStorage;
try{notificationStorage=localStorage;}catch{ /* Session-only opt-in if storage is unavailable. */ }
alertAudio=createAlertAudioController({storage:notificationStorage,onChange:renderAlertAudio});
function renderAlertAudio() {
  if(!alertAudio)return;
  const status=alertAudio.getState();
  const button=$('alert-audio-toggle');
  button.textContent=t(`audio.${status.status}`);
  button.setAttribute('aria-pressed',String(status.enabled));
  button.title=t('audio.help');
  button.disabled=!status.supported;
}
$('alert-audio-toggle').onclick=()=>{
  const status=alertAudio.getState();
  if(status.status==='ready')alertAudio.setEnabled(false);
  else {alertAudio.setEnabled(true);alertAudio.unlock();}
};
// Start only inside a trusted gesture. The toggle handles its own gesture so
// clicking a locked control activates sound rather than immediately muting it.
function unlockAlertAudio(event) {
  if(!event.isTrusted || event.target.closest?.('#alert-audio-toggle'))return;
  if(alertAudio.getState().status==='locked')alertAudio.unlock();
}
document.addEventListener('pointerdown',unlockAlertAudio);
document.addEventListener('keydown',unlockAlertAudio);
window.addEventListener('pagehide',()=>alertAudio.stop());
window.addEventListener('storage',event=>{if(event.key===ALERT_AUDIO_STORAGE_KEY)alertAudio.setEnabled(event.newValue!=='0');});
const notificationSupported=isSecureContext && 'Notification' in window && 'serviceWorker' in navigator && 'MessageChannel' in window;
const registrationPromise=isSecureContext && 'serviceWorker' in navigator
  ? navigator.serviceWorker.register('/sw.js').catch(()=>null) : Promise.resolve(null);
notifier=createNotificationController({registration:registrationPromise,storage:notificationStorage,supported:notificationSupported,getPermission:()=>notificationSupported?Notification.permission:'default',formatMessage:notificationText,alertFilter:alert=>Boolean(priorityAlertKey(alert)),alertKey:priorityAlertKey,onChange:()=>renderNotificationSettings()});
if('serviceWorker' in navigator)navigator.serviceWorker.addEventListener('message',event=>{if(event.data?.type==='open-alerts')showView('alerts');});
if(new URLSearchParams(location.search).get('view')==='alerts')showView('alerts');
window.addEventListener('focus',()=>renderNotificationSettings());
window.addEventListener('storage',event=>{if(event.key===NOTIFICATION_STORAGE_KEY){notifier.setEnabled(event.newValue==='1');notificationMessage='';renderNotificationSettings();}});
applyLanguage(language);
pollDesktop();
try{
  config=await api('/api/config');
  renderCases();
  Object.assign(region,{lat:config.regional_map.center_lat,lon:config.regional_map.center_lon,zoom:config.regional_map.zoom});
  $('corridors-toggle').hidden=!config.geography?.corridors?.corridors?.length;
  setMode('site');poll();pollAssessment();pollDecisions();
  api('/api/briefings').then(data=>{briefings=data.cases;renderCases();renderBriefing();}).catch(()=>{$('brief-purpose').textContent=t('brief.unavailable');});
}catch(error){connection(false,'startServer');$('map-status').textContent=t('requestFailed');}
