// Review controls only accept received cards and explicit, current human choices.
export const DASHBOARD_ACTIONS = ['continue_observe','cue_sensor','raise_alert','dismiss','escalate','notify_mock','record_review','hold'];
export const DISMISS_REASONS = ['bird','civil_aircraft','friendly','sensor_error'];
export function dashboardCard(state, objectId) {
  if (state?.dashboard?.scope !== 'simulation_review') return null;
  return state.dashboard.cards?.find(card => card.object_id === objectId) || null;
}
export function dashboardDraft(state, objectId, choice, connected = true) {
  const card = dashboardCard(state, objectId);
  if (!connected || !card || ['stale','closed'].includes(card.status) || card.remaining_ms <= 0
      || !DASHBOARD_ACTIONS.includes(choice) || !card.actions?.some(action => action.id === choice && action.enabled)) return null;
  return {run_id:state.run_id,object_id:objectId,card_version:card.version,choice};
}
export function dashboardDraftValid(state, draft, connected = true) {
  if (!draft || draft.run_id !== state?.run_id) return false;
  const current = dashboardDraft(state,draft.object_id,draft.choice,connected);
  return Boolean(current && current.card_version === draft.card_version);
}
export function dashboardConfirmation(state, draft, {connected = true, confirmed = false, reason = '', comment = '', reviewer = ''} = {}) {
  if (confirmed !== true || !dashboardDraftValid(state,draft,connected)
      || (draft.choice === 'dismiss' && !DISMISS_REASONS.includes(reason))) return null;
  return {action:'dashboard_action',...draft,confirm:true,
    ...(draft.choice === 'dismiss' ? {reason_code:reason} : {}),
    ...(comment.trim() ? {comment:comment.trim().slice(0,1000)} : {}),
    ...(reviewer.trim() ? {reviewer:reviewer.trim().slice(0,80)} : {})};
}

// Summarize arrived area reports without exposing coordinates, future reports, or truth data.
export function earlyIndicationSummary(state) {
  const now=state?.at_ms ?? 0;
  const zones=(state?.early_warning?.zones || []).map(zone=>{
    const evidence=(zone.evidence || []).filter(row=>Number.isFinite(row.available_at_ms) && row.available_at_ms>=0 && row.available_at_ms<=now);
    const current=evidence.filter(row=>row.assessment==='current');
    const positive=current.filter(row=>row.object_present===true).length;
    const negative=current.filter(row=>row.object_present===false).length;
    return {id:zone.id,evidence_ids:evidence.map(row=>row.id),positive,negative,current:current.length,
      stale:evidence.filter(row=>row.assessment==='stale').length,
      unavailable:evidence.filter(row=>!['current','stale'].includes(row.assessment)).length,
      conflict:positive>0 && negative>0,
      latest_received_ms:evidence.length?Math.max(...evidence.map(row=>row.available_at_ms)):null};
  }).filter(zone=>zone.evidence_ids.length);
  const positive=zones.reduce((count,zone)=>count+zone.positive,0);
  return {stage:state?.tracks?.length?'received_observation':positive?'early_indication':'awaiting_evidence',
    track_count:state?.tracks?.length || 0,positive,zone_count:zones.length,
    conflict_count:zones.filter(zone=>zone.conflict).length,
    stale_count:zones.reduce((count,zone)=>count+zone.stale,0),
    unavailable_count:zones.reduce((count,zone)=>count+zone.unavailable,0),zones};
}
export function decisionCopyKey(event,part,option) {
  return `decision.${event?.stage==='early_indication'?'early.':''}${part}.${option}`;
}

export function indicationOverview(state, perimeter, viewport) {
  const received=new Set(earlyIndicationSummary(state).zones.filter(zone=>zone.positive>0).map(zone=>zone.id));
  const areas=(state?.early_warning?.zones || []).filter(zone=>received.has(zone.id)
    && Number.isFinite(zone.center?.[0]) && Number.isFinite(zone.center?.[2])
    && Number.isFinite(zone.radius_m) && zone.radius_m>0);
  if(!areas.length || !perimeter?.polygon?.length || viewport.width<=0 || viewport.height<=0)return null;
  const points=[...perimeter.polygon,...areas.flatMap(zone=>[
    [zone.center[0]-zone.radius_m,zone.center[2]-zone.radius_m],
    [zone.center[0]+zone.radius_m,zone.center[2]+zone.radius_m]])];
  const xs=points.map(point=>point[0]),zs=points.map(point=>point[1]);
  const left=Math.min(...xs),right=Math.max(...xs),top=Math.min(...zs),bottom=Math.max(...zs);
  const baseScale=Math.min(viewport.width/(perimeter.width_m*1.35),viewport.height/(perimeter.length_m*1.6));
  const fitScale=.8*Math.min(viewport.width/Math.max(1,right-left),viewport.height/Math.max(1,bottom-top));
  return {x:(left+right)/2,z:(top+bottom)/2,zoom:Math.min(30,fitScale/baseScale)};
}
