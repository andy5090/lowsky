// Rule-based training advice: cards come from the server; the client only selects and confirms.
export const TACTICS_SCOPE = 'rule_based_training_advice';
export const UNIT_KINDS = ['infantry','radar','detection_phone','effector_team'];
export const TACTICS_ENUMS = {
  lean:['decoy_leaning','attack_leaning','reconnaissance_leaning','indeterminate','insufficient_data'],
  profile:['jet','multirotor','light_airframe','fixed_wing','unclassified'],
  verification:['observed_class','suspected'],
  posture:['observe_preserve','hold','engage_candidate'],
  formation:['ready','observe','respond','hold'],
  status:['recommended','penalized','rejected'],
  cue:['group_structure','first_wave','terminal_maneuver','jet_speed','rf_emission','loiter','acoustic_jet','eo_fixed_wing','eo_light_airframe'],
  uncertainty:['group_from_received_positions_only','jet_decoy_possible','payload_not_visible','eo_conflict','no_eo_report','rf_absent_not_fiber_proof','single_source_position','attack_decoy_not_separable'],
  reason:['stale_track','runway_overflight','debris_over_facilities','own_radar_interference','no_rf_link_evidence','rf_emission_unknown','inventory_exhausted','speed_disadvantage','resource_preservation','single_target_queue','preferred_for_jet','no_effector_team_placed','coverage_gap'],
  constraint:['stale_track','runway_overflight','over_facilities','own_radar_nearby','fuel_like_facility_nearby'],
  effector:['interceptor_drone','laser','autocannon','rf_jammer'],
};

export function tacticsTarget(state, objectId) {
  if (state?.tactics?.scope !== TACTICS_SCOPE) return null;
  return state.tactics.targets?.find(target => target.object_id === objectId) || null;
}
export function allocationDraft(state, objectId, effectorId, connected = true) {
  const target = tacticsTarget(state, objectId);
  if (!connected || !target || typeof state.run_id !== 'string' || target.response?.allocation) return null;
  const option = target.response?.options?.find(row => row.effector_id === effectorId);
  if (!option || option.status === 'rejected' || typeof target.response.version !== 'string') return null;
  return {run_id:state.run_id,object_id:objectId,effector_id:effectorId,version:target.response.version};
}
export function allocationDraftValid(state, draft, connected = true) {
  if (!draft || draft.run_id !== state?.run_id) return false;
  const current = allocationDraft(state,draft.object_id,draft.effector_id,connected);
  return Boolean(current && current.version === draft.version);
}
export function allocationCommand(state, draft, {connected = true, confirmed = false, reviewer = '', comment = ''} = {}) {
  if (confirmed !== true || !allocationDraftValid(state,draft,connected)) return null;
  const alias = String(reviewer ?? '').trim().slice(0,80), note = String(comment ?? '').trim().slice(0,1000);
  return {action:'tactics_allocate',run_id:draft.run_id,object_id:draft.object_id,effector_id:draft.effector_id,
    version:draft.version,confirm:true,...(alias ? {reviewer:alias} : {}),...(note ? {comment:note} : {})};
}

// Proposal positions are objects; legacy [x,y,z] rows count as infantry.
export function proposalPositions(proposal) {
  return (proposal?.positions || []).map(row => Array.isArray(row) ? {kind:'infantry',position:row} : row)
    .filter(row => Array.isArray(row?.position) && row.position.length === 3 && row.position.every(Number.isFinite));
}
export function placementSummary(state) {
  const exercise = state?.exercise, proposal = exercise?.unit_proposal;
  if (exercise?.scope !== 'scripted_training' || !proposal) return null;
  const units = exercise.units || [], positions = proposalPositions(proposal);
  const kinds = Array.isArray(exercise.unit_kinds) && exercise.unit_kinds.length ? exercise.unit_kinds : UNIT_KINDS.map(id => ({id}));
  return {status:proposal.status,proposal_id:proposal.id,threat_basis:proposal.threat_basis || null,coverage:{...(proposal.coverage || {})},
    kinds:kinds.map(kind => {
      const placed = units.filter(unit => unit.kind === kind.id).length;
      const budget = Number.isFinite(kind.budget) ? kind.budget : null;
      return {kind:kind.id,label:kind.label || null,proposed:positions.filter(row => row.kind === kind.id).length,placed,budget,
        remaining:budget === null ? null : Math.max(0,budget-placed),range_m:Number.isFinite(kind.display_range_m) ? kind.display_range_m : 0};
    })};
}
// Teams are listed in unit-kind order; long tasking lists are summarized rather than dumped.
export function formationRows(state, limit = 5) {
  if (state?.tactics?.scope !== TACTICS_SCOPE) return [];
  const order = kind => UNIT_KINDS.includes(kind) ? UNIT_KINDS.indexOf(kind) : UNIT_KINDS.length;
  return (state.tactics.formation?.teams || []).map(team => {
    const tasking = team.tasking || [];
    const counts = {};
    for (const row of tasking) {
      const key = row.posture || row.lean;
      if (key) counts[key] = (counts[key] || 0) + 1;
    }
    return {id:team.id,kind:team.kind,role:team.role,sector:team.sector,unit_count:(team.unit_ids || []).length,
      unit_ids:[...(team.unit_ids || [])],tasking_count:tasking.length,tasking:tasking.slice(0,limit).map(row => row.object_id),counts};
  }).sort((a,b) => order(a.kind)-order(b.kind) || String(a.sector).localeCompare(String(b.sector)) || String(a.role).localeCompare(String(b.role)));
}
