// Only received, current objects can be used in an explicitly confirmed branch.
export function exerciseConfirmation(state, draft, confirmed = false) {
  const exercise = state?.exercise;
  if (confirmed !== true || !draft || draft.run_id !== state?.run_id || exercise?.scope !== 'scripted_training' || exercise.selection) return null;
  if (!exercise.eligible_objects?.includes(draft.object_id)
      || !exercise.assets?.some(asset => asset.id === draft.asset_id)
      || !exercise.branches?.some(branch => branch.id === draft.branch_id)) return null;
  const mission=exerciseMissionRows(state).find(item=>item.object_id===draft.object_id);
  if(mission && mission.asset_id!==draft.asset_id)return null;
  const branch=exercise.branches.find(item=>item.id===draft.branch_id);
  if (Number.isFinite(state.at_ms) && Number.isFinite(state.duration_ms) && Number.isFinite(branch.delay_ms)
      && state.at_ms+branch.delay_ms>=state.duration_ms) return null;
  return {action:'exercise_branch',run_id:state.run_id,object_id:draft.object_id,asset_id:draft.asset_id,branch_id:draft.branch_id,confirm:true};
}

// Mission cards are authored scene descriptions, never inferred identity or future schedules.
export function exerciseMissionRows(state) {
  if(state?.exercise?.scope!=='scripted_training')return [];
  const received=new Map((state.tracks || []).map(track=>[track.object_id,track]));
  return (state.exercise.missions || []).filter(mission=>{
    const track=received.get(mission.object_id);
    const published=Number.isFinite(mission.result_at_ms) && mission.result_at_ms<=state.at_ms;
    return mission.synthetic===true && mission.scope==='scripted_training' && track
      && (track.last_known===false || published);
  }).map(mission=>{
    const published=Number.isFinite(mission.result_at_ms) && mission.result_at_ms<=state.at_ms;
    return {id:mission.id,object_id:mission.object_id,kind:mission.kind,asset_id:mission.asset_id,
      phase:mission.phase,outcome:published?mission.outcome:null,result_at_ms:published?mission.result_at_ms:null};
  });
}

// Only published facility states and the operator's own selection belong on the map.
export function exerciseMapAssets(state) {
  if (state?.exercise?.scope !== 'scripted_training') return [];
  const {assets = [], selection, branches = []} = state.exercise;
  return assets.filter(asset => asset.id === selection?.asset_id || ['restricted', 'unavailable'].includes(asset.status))
    .filter(asset => Array.isArray(asset.position) && asset.position.length === 3 && asset.position.every(Number.isFinite))
    .map(asset => ({...asset, selection: asset.id === selection?.asset_id ? selection : null,
      branch: asset.id === selection?.asset_id ? branches.find(branch => branch.id === selection.branch_id) : null}));
}

export const MAX_EXERCISE_UNITS = 12;
// Per-kind budget from the server catalog; without one, a single 12-unit total applies.
export function unitBudget(state, kind = 'infantry') {
  const units = state?.exercise?.units || [], kinds = state?.exercise?.unit_kinds;
  if (!Array.isArray(kinds) || !kinds.length) {
    if (!['infantry', 'radar', 'detection_phone', 'effector_team'].includes(kind)) return null;
    return {kind, budget: MAX_EXERCISE_UNITS, used: units.length, remaining: Math.max(0, MAX_EXERCISE_UNITS - units.length)};
  }
  const entry = kinds.find(item => item.id === kind);
  if (!entry || !Number.isFinite(entry.budget)) return null;
  const used = units.filter(unit => unit.kind === kind).length;
  return {kind, budget: entry.budget, used, remaining: Math.max(0, entry.budget - used)};
}
export function exerciseUnitCommand(state, draft, confirmed = false) {
  if (confirmed !== true || !draft || typeof state?.run_id !== 'string'
      || draft.run_id !== state.run_id || state.exercise?.scope !== 'scripted_training') return null;
  const units = state.exercise.units || [];
  const proposal = state.exercise.unit_proposal;
  if (draft.action === 'exercise_reoptimize_units') return {action: draft.action, run_id: state.run_id, confirm: true};
  if (['exercise_accept_units', 'exercise_manual_units'].includes(draft.action)) {
    if (!proposal || draft.proposal_id !== proposal.id
        || (draft.action === 'exercise_accept_units' && proposal.status !== 'pending')
        || (draft.action === 'exercise_manual_units' && !['pending', 'accepted'].includes(proposal.status))) return null;
    return {action: draft.action, run_id: state.run_id, proposal_id: proposal.id, confirm: true};
  }
  if (proposal?.status !== 'manual') return null;
  const existing = units.some(unit => unit.id === draft.unit_id);
  if (draft.action === 'exercise_remove_unit') {
    return existing ? {action: draft.action, run_id: state.run_id, unit_id: draft.unit_id, confirm: true} : null;
  }
  if (draft.action !== 'exercise_place_unit' || (draft.unit_id != null && !existing)) return null;
  if (!existing && !(unitBudget(state, draft.kind ?? 'infantry')?.remaining > 0)) return null;
  if (!Array.isArray(draft.position) || draft.position.length !== 3
      || !draft.position.every(Number.isFinite) || draft.position[1] !== 0
      || Math.abs(draft.position[0]) > 5000 || Math.abs(draft.position[2]) > 5000) return null;
  return {action: draft.action, run_id: state.run_id, confirm: true, position: [...draft.position],
    ...(existing ? {unit_id: draft.unit_id} : draft.kind != null ? {kind: draft.kind} : {})};
}
