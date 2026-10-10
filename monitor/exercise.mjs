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
