export const DECISION_OPTIONS = ['continue_monitoring', 'hold_review', 'defer'];

export function decisionStatusKey(event, enabled, notice = '') {
  if (event && notice === 'decision.saved') notice = '';
  return notice || (event ? `decision.${event.status}` : enabled ? 'decision.watching' : 'decision.disabled');
}

export function selectDecision(event, optionId) {
  if (event?.status !== 'ready' || !DECISION_OPTIONS.includes(optionId)
      || !event.report?.decision_options?.some(option => option.id === optionId)) return null;
  return {run_id:event.run_id,event_id:event.id,evidence_version:event.evidence_version,
    option_id:optionId,at_ms:event.at_ms,language:event.report.language};
}

export function decisionDraftStatus(draft, event, state, language) {
  if (!draft) return 'empty';
  if (!event || event.status !== 'ready' || draft.run_id !== state?.run_id
      || draft.run_id !== event.run_id || draft.event_id !== event.id
      || draft.evidence_version !== event.evidence_version || draft.at_ms !== state.at_ms
      || draft.language !== language || event.report?.language !== language
      || !event.report?.decision_options?.some(option => option.id === draft.option_id)) return 'stale';
  return 'ready';
}

export function decisionConfirmation(draft, event, state, language, reviewer, reason, confirmed = false) {
  if (!confirmed || decisionDraftStatus(draft,event,state,language) !== 'ready'
      || !reviewer.trim() || reviewer.trim().length > 80 || !reason.trim() || reason.trim().length > 1000) return null;
  return {action:'confirm',run_id:draft.run_id,event_id:draft.event_id,
    evidence_version:draft.evidence_version,option_id:draft.option_id,
    reviewer:reviewer.trim(),reason:reason.trim(),confirm:true};
}
