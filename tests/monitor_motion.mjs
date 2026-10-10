import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {motionFrame} from '../monitor/motion.mjs';
import {replayTime} from '../monitor/radar.mjs';
const root = new URL('../data/scenarios/v1/', import.meta.url);
const read = path => JSON.parse(readFileSync(new URL(path, root)));
const layout = JSON.parse(readFileSync(new URL('../data/site_layout.json', import.meta.url)));
for(const {case_id} of read('manifest.json').cases) {
  const world = read(`cases/${case_id}/world.json`);
  const initial = motionFrame(world, 0), middle = motionFrame(world, 15000), final = motionFrame(world, 120000);
  assert.equal(initial.length, 3);
  for(let i=0; i<3; i++) {
    assert.ok(initial[i].position[2] < -layout.perimeter.length_m/2);
    assert.ok(Math.abs(final[i].position[2]) < layout.perimeter.length_m/2);
    assert.equal(middle[i].position[2], (world.objects[i].keyframes[0].position[2] + world.objects[i].keyframes[1].position[2])/2);
    assert.notDeepEqual(initial[i].position, middle[i].position);
    assert.equal(middle[i].trail.length, 2); // No future path shown.
  }
  assert.deepEqual(motionFrame(world, -1), initial);
  assert.deepEqual(motionFrame(world, 130000), final);
  const paused={at_ms:15000,duration_ms:120000,playing:false,speed:4};
  assert.deepEqual(motionFrame(world,replayTime(paused,100,200,true)), middle);
}
console.log('Motion: all 12 cases approach from outside, interpolate, clamp and freeze correctly.');
