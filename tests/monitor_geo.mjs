import assert from 'node:assert/strict';
import {localToGeo, mercator, unproject, pixelsPerMeter} from '../monitor/geo.mjs';
const origin = {lat:36.5,lon:127.8};
assert.deepEqual(localToGeo(0,0,origin),[36.5,127.8]);
const east = localToGeo(1000,0,origin), south = localToGeo(0,1000,origin);
assert(east[1] > origin.lon && east[0] === origin.lat);
assert(south[0] < origin.lat && south[1] === origin.lon);
for(const zoom of [3,13,18]) {
  const center=mercator(origin.lat,origin.lon,zoom);
  const roundtrip=unproject(...center,zoom);
  assert(Math.abs(roundtrip[0]-origin.lat)<1e-9 && Math.abs(roundtrip[1]-origin.lon)<1e-9);
  const endpoint=mercator(...east,zoom);
  assert(Math.abs((endpoint[0]-center[0])/pixelsPerMeter(origin.lat,zoom)-1000)<1e-6);
  const north=mercator(...localToGeo(0,-1250,origin),zoom);
  const south=mercator(...localToGeo(0,1250,origin),zoom);
  assert(Math.abs((south[1]-north[1])/pixelsPerMeter(origin.lat,zoom)-2500)<0.001);
}
console.log('PASS: fictional origin, east/south axes, projection roundtrip, 1km scale and 2.5km runway at three zoom levels');
