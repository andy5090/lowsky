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
