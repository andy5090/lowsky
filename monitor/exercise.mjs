// Only received, current objects can be used in an explicitly confirmed branch.
export function exerciseConfirmation(state, draft, confirmed = false) {
  const exercise = state?.exercise;
  if (confirmed !== true || !draft || draft.run_id !== state?.run_id || exercise?.scope !== 'scripted_training' || exercise.selection) return null;
  if (!exercise.eligible_objects?.includes(draft.object_id)
      || !exercise.assets?.some(asset => asset.id === draft.asset_id)
      || !exercise.branches?.some(branch => branch.id === draft.branch_id)) return null;
  return {action:'exercise_branch',run_id:state.run_id,object_id:draft.object_id,asset_id:draft.asset_id,branch_id:draft.branch_id,confirm:true};
}
