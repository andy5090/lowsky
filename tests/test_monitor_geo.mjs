import assert from 'node:assert/strict';
import {test} from 'node:test';
import {localToGeo, geoToLocal, mercator, mapToLocal} from '../monitor/geo.mjs';

const near=(actual,expected)=>actual.forEach((value,index)=>assert(Math.abs(value-expected[index])<1e-6,`${value} != ${expected[index]}`));
test('local and geographic coordinates roundtrip east and south across origins',()=>{
  for(const origin of [{lat:37.5,lon:127},{lat:-30,lon:45}])for(const [x,z] of [[0,0],[4500,-3500],[-800,1200]]){
    const [lat,lon]=localToGeo(x,z,origin);near(geoToLocal(lat,lon,origin),[x,z]);
  }
});
test('plan placement undoes viewport translation and zoom',()=>{
  for(const scale of [.04,1,4])for(const [x,z] of [[0,0],[120,-500]]){
    const options={mode:'site',width:1024,height:768,plan:{x:110,z:-200},scale};
    near(mapToLocal(512+(x-110)*scale,384+(z+200)*scale,options),[x,0,z]);
  }
});
test('regional placement roundtrips mercator at each zoom and off-center viewport',()=>{
  const origin={lat:37.5,lon:127};
  for(const zoom of [6,13,18])for(const [x,z] of [[0,0],[4200,-3600]]){
    const region={lat:37.51,lon:127.03,zoom};
    const [lat,lon]=localToGeo(x,z,origin),[px,py]=mercator(lat,lon,zoom),[cx,cy]=mercator(region.lat,region.lon,zoom);
    near(mapToLocal(500+px-cx,350+py-cy,{mode:'region',width:1000,height:700,region,origin}),[x,0,z]);
  }
});
test('hidden viewport and invalid plan scale cannot yield a placement',()=>{
  for(const extra of [{width:0},{height:0},{scale:0},{scale:NaN}])assert.equal(mapToLocal(10,10,{mode:'site',width:100,height:100,scale:1,plan:{x:0,z:0},...extra}),null);
});
