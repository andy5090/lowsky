// Visual-only sweep. Returns are received observations, never inferred world positions.
export function replayTime(state, receivedAt, now, connected) {
  if (!state) return 0;
  const elapsed = state.playing && connected ? Math.min(500, Math.max(0, now - receivedAt)) * state.speed : 0;
  return Math.min(state.duration_ms, state.at_ms + elapsed);
}

export function radarFrame(display, facilities, state, atMs) {
  if (!display || !state) return [];
  return display.stations.flatMap(station => {
    const facility = facilities.find(f => f.id === station.facility_id);
    if (!facility) return [];
    const health = state.sources.find(s => s.source_id === station.source_id)?.status || 'unknown';
    const returns = health === 'online' ? state.tracks.filter(track => track.last_known !== true).flatMap(track => track.records
      .filter(r => r.source_id === station.source_id && r.observed_at_ms <= state.at_ms
        && r.available_at_ms <= state.at_ms && atMs >= r.available_at_ms
        && atMs - r.available_at_ms < display.return_visible_ms)
      .map(r => ({id:r.id, position:r.position, progress:(atMs-r.available_at_ms)/display.return_visible_ms}))) : [];
    return [{id:station.id, position:facility.position, radius:station.display_radius_m,
      angle:((atMs / display.scan_period_ms * 360 + station.phase_deg) % 360) * Math.PI / 180,
      health, returns}];
  });
}
