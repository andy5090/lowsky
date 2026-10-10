export const DECISION_OPTIONS = ['continue_monitoring', 'hold_review', 'defer'];

export function decisionStatusKey(event, enabled, notice = '') {
  if (event && notice === 'decision.saved') notice = '';
  return notice || (event ? `decision.${event.status}` : enabled ? 'decision.watching' : 'decision.disabled');
}

export function decisionReport(event) { return event?.report || event?.choice_report; }
export function decisionOpen(event) { return ['pending','evaluating','ready','failed'].includes(event?.status); }

export function selectDecision(event, optionId) {
  if (!decisionOpen(event) || !DECISION_OPTIONS.includes(optionId)
      || !decisionReport(event)?.decision_options?.some(option => option.id === optionId)) return null;
  return {run_id:event.run_id,event_id:event.id,evidence_version:event.evidence_version,
    option_id:optionId,at_ms:event.at_ms,language:decisionReport(event).language};
}

export function decisionDraftStatus(draft, event, state, language) {
  if (!draft) return 'empty';
  if (!event || !decisionOpen(event) || draft.run_id !== state?.run_id
      || draft.run_id !== event.run_id || draft.event_id !== event.id
      || draft.evidence_version !== event.evidence_version || draft.at_ms !== event.at_ms
      || (Number.isFinite(event.expires_at_ms) && state.at_ms >= event.expires_at_ms)
      || draft.language !== language || decisionReport(event)?.language !== language
      || !decisionReport(event)?.decision_options?.some(option => option.id === draft.option_id)) return 'stale';
  return 'ready';
}

export function decisionConfirmation(draft, event, state, language, reviewer, reason, confirmed = false) {
  if (!confirmed || decisionDraftStatus(draft,event,state,language) !== 'ready'
      || typeof reviewer !== 'string' || reviewer.trim().length > 80
      || typeof reason !== 'string' || reason.trim().length > 1000) return null;
  return {action:'confirm',run_id:draft.run_id,event_id:draft.event_id,
    evidence_version:draft.evidence_version,option_id:draft.option_id,
    reviewer:reviewer.trim(),reason:reason.trim(),confirm:true};
}
