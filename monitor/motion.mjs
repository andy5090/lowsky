// Author-view animation only. Never use these positions as sensor evidence.
export function motionFrame(world, atMs) {
  const time = Math.max(0, Math.min(world.duration_ms, atMs));
  return world.objects.map(object => {
    const frames = object.keyframes;
    let index = 0;
    while (index < frames.length - 2 && frames[index + 1].at_ms <= time) index++;
    const a = frames[index], b = frames[index + 1];
    const ratio = Math.max(0, Math.min(1, (time - a.at_ms) / (b.at_ms - a.at_ms)));
    const position = a.position.map((value, axis) => value + (b.position[axis] - value) * ratio);
    return {object_id: object.object_id, position,
      heading: Math.atan2(b.position[0] - a.position[0], -(b.position[2] - a.position[2])) * 180 / Math.PI,
      trail: [...frames.filter(frame => frame.at_ms < time).map(frame => frame.position), position]};
  });
}
