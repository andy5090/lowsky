import {localToGeo, mercator, unproject, pixelsPerMeter} from './geo.mjs';
import {translate, readLanguage, saveLanguage, normalizeLanguage} from './i18n.mjs';
const $ = id => document.getElementById(id);
const escape = value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let language = 'en';
try { language = readLanguage(localStorage); } catch { /* Storage may be unavailable. */ }
const t = (key, values) => translate(language, key, values);
const qualityLabel = quality => t(`quality.${quality}`);
const sourceLabel = status => t(`source.${status}`);
let connected = null, connectionMessage = '';
const fmt = ms => `${String(Math.floor(ms / 60000)).padStart(2,'0')}:${String(Math.floor(ms / 1000) % 60).padStart(2,'0')}`;
let config, state, selected, mode = 'site', dataSignature = '', requestVersion = 0;
let controlChain = Promise.resolve();
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
  for (const id of ['play-button','reset-button','case-select','timeline','speed-select']) $(id).disabled = !ok;
  if (!ok) $('sim-status').textContent = t(message || 'retainView');
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
  try { const data = await api('/api/state'); if(version === requestVersion) render(data); }
  catch { connection(false); }
  setTimeout(poll, 500);
}
function render(data) {
  state = data; connection(true);
  renderPlayback(data);
  const signature = JSON.stringify([data.run_id,data.tracks,data.sources,data.alerts,data.contexts]);
  if (signature !== dataSignature) {
    dataSignature = signature;
    if(!data.tracks.some(t => t.object_id === selected)) selected = data.tracks[0]?.object_id;
    renderDetails(); drawMap();
  }
}
function renderPlayback(data) {
  $('case-select').value = data.case_id;
  $('sim-status').textContent = data.playing ? t('playing') : data.at_ms >= data.duration_ms ? t('finished') : t('paused');
  $('sim-status').classList.toggle('running', data.playing);
  $('play-button').textContent = data.playing ? t('pause') : t('play');
  $('time-label').textContent = `${fmt(data.at_ms)} / ${fmt(data.duration_ms)}`;
  if(document.activeElement !== $('timeline')) $('timeline').value = data.at_ms;
  $('speed-select').value = data.speed;
}
function select(id) { selected = id; renderDetails(); drawMap(); }
function renderDetails() {
  if(!state) return;
  $('track-count').textContent = state.tracks.length;
  $('track-list').innerHTML = state.tracks.map(t => `<button class="track-item ${selected===t.object_id?'is-selected':''}" aria-pressed="${selected===t.object_id}" data-track="${escape(t.object_id)}"><header><span class="track-name">${escape(t.object_id)}</span><span class="track-quality" data-quality="${escape(t.quality)}">${qualityLabel(t.quality)}</span></header><div class="track-meta">${t.last_known?translate(language,'lastKnown'):translate(language,'lastObservation')} · ${t.observed_at_ms===null?translate(language,'noRecord'):fmt(t.observed_at_ms)}</div></button>`).join('');
  $('track-list').querySelectorAll('[data-track]').forEach(b => b.onclick = () => select(b.dataset.track));
  const track = state.tracks.find(t => t.object_id === selected);
  if(track) {
    $('track-detail').innerHTML = `<h3>${escape(track.object_id)}</h3><p>${qualityLabel(track.quality)} · ${t('sampleInterval')}</p><dl class="detail-grid"><dt>${t('lastObservation')}</dt><dd>${track.observed_at_ms===null?t('none'):fmt(track.observed_at_ms)}</dd><dt>${t('positionSource')}</dt><dd>${escape(track.position_source || t('none'))}</dd><dt>${t('localXZ')}</dt><dd>${track.position ? `${track.position[0].toFixed(0)} / ${track.position[2].toFixed(0)} m` : t('none')}</dd></dl><button class="button button-secondary" id="focus-track">${t('focusTrack')}</button><div class="evidence-rows">${track.records.map(r=>`<p><strong>${escape(r.source_id)}</strong> · ${fmt(r.observed_at_ms)} · ${escape(t(`marker.${r.marker_label}`))}<br><small>${t('evidence')} ${escape(r.id)}</small></p>`).join('')}</div>`;
    $('focus-track').onclick = () => { if(track.position){plan.x=track.position[0];plan.z=track.position[2];plan.zoom=8;setMode('site');} };
  }
  const pending = state.alerts.filter(a=>!a.acknowledged).length;
  $('alert-count').textContent = pending;
  const alertHTML = state.alerts.map(a=>`<li class="alert-item severity-warning ${a.acknowledged?'is-acknowledged':''}"><strong>${escape(t(['contradictory','not_comparable','stale','channel'].includes(a.kind)?`alert.${a.kind}`:'alert.unknown'))}</strong><p>${escape(a.object_id || a.source_id)} · ${t('evidence')} ${a.evidence_ids.map(escape).join(', ') || t('none')}</p><button class="button button-secondary" data-alert="${escape(a.id)}" ${a.acknowledged?'disabled':''}>${a.acknowledged?t('acknowledged'):t('acknowledge')}</button></li>`).join('') || `<li class="alert-item">${t('noAlerts')}</li>`;
  $('alert-list').innerHTML = alertHTML;
  $('active-alerts').innerHTML = alertHTML;
  document.querySelectorAll('[data-alert]').forEach(b=> b.onclick=()=>control({action:'ack',alert_id:b.dataset.alert,run_id:state.run_id}));
  $('source-status').textContent = state.sources.map(s=>`${s.source_id}: ${sourceLabel(s.status)}`).join(' · ');
  $('events-list').innerHTML = state.sources.map(s=>`<li class="event-item"><time>${s.evidence ? fmt(s.evidence.observed_at_ms) : '--:--'}</time>${escape(s.source_id)} · ${sourceLabel(s.status)}</li>`).join('') + state.contexts.map(c=>`<li class="event-item"><time>${t('published')} ${fmt(c.published_at_ms)}</time>${escape(['context_001','context_002'].includes(c.id)?t(`context.${c.id}`):c.text)}</li>`).join('');
}
function planScale() {
  if(mode==='region') return pixelsPerMeter(config.regional_map.site_origin.lat,region.zoom);
  const p = config.site.perimeter;
  return Math.min(map.clientWidth/(p.width_m*1.35), map.clientHeight/(p.length_m*1.25))*plan.zoom;
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
  svg+=rect(0,0,site.perimeter.width_m,site.perimeter.length_m,mode==='region'?'#b3c38b1f':'#172b2e',mode==='region'?'#c4d39a':'#b3c38b','stroke-width="2.5" stroke-dasharray="6 4"');
  const [sx,sy]=point(-site.perimeter.width_m/2,-site.perimeter.length_m/2);
  svg+=`<text x="${sx+8}" y="${sy+17}" fill="#c4d39a" font-size="11" font-weight="600">${t('sitePlan')}</text>`;
  const r=site.runway,a=site.apron;
  svg+=rect(r.center[0],r.center[2],r.width_m,r.length_m,'#354c58','#8fa5ad');
  const [rx,y1]=point(r.center[0],r.center[2]-r.length_m/2+80),[,y2]=point(r.center[0],r.center[2]+r.length_m/2-80);
  svg+=`<line x1="${rx}" y1="${y1}" x2="${rx}" y2="${y2}" stroke="#d9e4e3" stroke-width="1" stroke-dasharray="8 8"/>`;
  svg+=rect(a.center[0],a.center[2],a.width_m,a.length_m,'#314743','#78938d');
  const [lx,ly]=point(r.center[0]+80,r.center[2]+r.length_m/2);
  svg+=`<text x="${lx}" y="${ly}" fill="#acc2c8" font-size="10">${t('runway',{length:r.length_m.toLocaleString(language),width:r.width_m})}</text>`;
  for(const f of site.facilities){
    const size=({hangar:[10,12],utility_building:[6,8],control_tower:[5.8,5.8],observation_station:[3,3]})[f.asset_id] || [8,8];
    svg+=rect(f.position[0],f.position[2],size[0]*f.scale[0],size[1]*f.scale[2],'#617b74','#a3b6a4');
  }
  for(const t of state?.tracks || []){
    const coords=t.history.map(r=>point(r.position[0],r.position[2]).join(',')).join(' ');
    svg+=`<polyline points="${coords}" fill="none" stroke="${t.object_id===selected?'#dfb86a':'#8bc9cf'}" stroke-width="1.5" stroke-dasharray="4 4"/>`;
  }
  svg+=`<text x="20" y="${h-52}" fill="#acc2c8" font-size="10">${t('perimeter',{width:site.perimeter.width_m.toLocaleString(language),length:site.perimeter.length_m.toLocaleString(language)})}</text><text x="${w-28}" y="92" fill="#acc2c8" font-size="11">${t('north')}</text>`;
  overlay.innerHTML=svg;
  markers.replaceChildren();
  for(const t of state?.tracks || []){
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
function drawMap(){if(!config)return; if(mode==='site')drawSite();else drawRegion();}
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
$('play-button').onclick=()=>control({action:state.playing?'pause':'play'});
$('reset-button').onclick=()=>control({action:'reset'});
$('case-select').onchange=e=>control({action:'case',case_id:e.target.value});
$('speed-select').onchange=e=>control({action:'speed',speed:Number(e.target.value)});
$('timeline').onchange=e=>control({action:'seek',at_ms:Number(e.target.value)});
$('timeline').oninput=e=>$('time-label').textContent=`${fmt(Number(e.target.value))} / 02:00`;
for(const tab of document.querySelectorAll('[data-view]'))tab.onclick=()=>{
  const monitor=tab.dataset.view==='monitor';$('monitor-view').hidden=!monitor;$('alerts-view').hidden=monitor;
  for(const b of document.querySelectorAll('[data-view]')){b.classList.toggle('is-active',b===tab);if(b===tab)b.setAttribute('aria-current','page');else b.removeAttribute('aria-current');}drawMap();
};
function renderCases() {
  if (!config) return;
  const current = state?.case_id || $('case-select').value;
  $('case-select').innerHTML = config.cases.map(c => `<option value="${escape(c.case_id)}">${escape(c.case_id)} · ${t(`variant.${c.variant}`)}</option>`).join('');
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
  if (state) { renderPlayback(state); renderDetails(); }
  drawMap();
  if (connected !== null) connection(connected, connectionMessage);
  if (!config && connected === false) $('map-status').textContent = t('requestFailed');
}
$('language-select').onchange = event => applyLanguage(event.target.value, true);
applyLanguage(language);
try{
  config=await api('/api/config');
  renderCases();
  Object.assign(region,{lat:config.regional_map.center_lat,lon:config.regional_map.center_lon,zoom:config.regional_map.zoom});
  setMode('site');poll();
}catch(error){connection(false,'startServer');$('map-status').textContent=t('requestFailed');}
