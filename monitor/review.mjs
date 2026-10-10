// Presentation-only queue: no threat scoring or automatic review decisions.
export function reviewQueue(tracks, reviews = [], filter = 'all', page = 0, size = 12) {
  const reviewed = new Set(reviews.map(r => `${r.object_id}:${r.evidence_version}`));
  const pending = track => !reviewed.has(`${track.object_id}:${track.evidence_version}`);
  const rows = tracks.filter(track => filter === 'attention' ? track.quality !== 'consistent'
    : filter === 'unreviewed' ? pending(track) : true);
  const pages = Math.max(1, Math.ceil(rows.length / size));
  const current = Math.max(0, Math.min(pages - 1, page));
  return {items:rows.slice(current * size, (current + 1) * size), page:current, pages, total:rows.length,
    received:tracks.length, current:tracks.filter(t => t.last_known === false).length,
    attention:tracks.filter(t => t.quality !== 'consistent').length, unreviewed:tracks.filter(pending).length};
}

// Optional wording suggestions, never automatically selected or saved.
export function commentSuggestions(track) {
  if (!track) return [];
  const keys = ['more_evidence'];
  if (track.quality === 'contradictory') keys.push('compare_sources');
  if (track.last_known || track.explanation?.missing?.some(item=>item.code==='observation_stale')) keys.push('fresh_report');
  if (track.explanation?.missing?.length) keys.push('check_missing');
  keys.push('identity_unknown');
  return keys;
}
export function reviewComment(suggestion, text, translate) {
  const known=['more_evidence','compare_sources','fresh_report','check_missing','identity_unknown','verify_source','revisit'];
  return [known.includes(suggestion)?translate(`review.suggest.${suggestion}`):'', text.trim()].filter(Boolean).join(' ');
}
