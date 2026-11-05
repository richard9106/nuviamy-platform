// Exercise the actual browser controller with synthetic devices and SDK only.
const assert=require('node:assert/strict'), vm=require('node:vm'), fs=require('node:fs');
const source=fs.readFileSync('static/telehealth/room.js','utf8');
function setup(role='patient') {
  const elements={};
  const get=id=>elements[id] ||= {hidden:false,disabled:false,value:id,options:[],dataset:{},events:{},
    classList:{add(){},remove(){}}, addEventListener(n,f){this.events[n]=f},setAttribute(n,v){this[n]=v},
    replaceChildren(){this.options=[]},appendChild(o){this.options.push(o)}, play(){return Promise.resolve()}};
  get('video-app').dataset={role,api:'/synthetic/action/'};
  let calls=[], mediaCalls=[], starts=0, stopped=0, interval, response={state:'waiting'}, permissionResolve;
  const tracks=[{enabled:true,stop(){stopped++}},{enabled:true,stop(){stopped++}}];
  const stream={getTracks:()=>tracks,getAudioTracks:()=>[tracks[0]],getVideoTracks:()=>[tracks[1]]};
  const audioVideo=new Proxy({addObserver(){},getAllRemoteVideoTiles:()=>[]},{get(t,p){return t[p] || ((...args)=>{mediaCalls.push(p);return Promise.resolve()})}});
  const sandbox={crypto:{randomUUID:()=> 'synthetic-nonce'},Date,JSON,Promise,
    document:{getElementById:get,querySelector:()=>({value:'synthetic-csrf'}),createElement:()=>({})},
    navigator:{mediaDevices:{getUserMedia:()=>new Promise(r=>permissionResolve=r),enumerateDevices:async()=>[
      {kind:'audioinput',deviceId:'mic'},{kind:'videoinput',deviceId:'camera'}]}},
    fetch:async(url,options)=>{calls.push(options);return {ok:true,json:async()=>typeof response === 'function' ? response(JSON.parse(options.body).action) : response}},
    setInterval:f=>(interval=f,1),clearInterval(){},setTimeout:()=>1,clearTimeout(){},
    window:{addEventListener(){},NuviaVideoSDK:{DefaultDeviceController:class{destroy(){}},
      MeetingSessionConfiguration:class{constructor(){this.urls={}}},
      DefaultMeetingSession:class{constructor(){starts++;this.audioVideo=audioVideo}destroy(){}}}}};
  vm.runInNewContext(source,sandbox);
  return {get,calls,tracks,mediaCalls,ready:async()=>{const pending=get('test-devices').events.click();
    await Promise.resolve(); assert.equal(get('audio-only').disabled,true);permissionResolve(stream);await pending;},
    response:r=>response=r,poll:()=>interval(),starts:()=>starts,stopped:()=>stopped};
}
(async()=>{
  const app=setup(); assert.equal(app.calls.length,0);
  await app.ready(); assert.equal(app.get('join-session').disabled,false);
  await app.get('join-session').events.click(); assert.equal(app.starts(),0); // waiting: no SDK/media sent
  assert.equal(JSON.parse(app.calls[0].body).action,'join');
  assert.equal(app.calls[0].headers['X-CSRFToken'],'synthetic-csrf');
  app.get('toggle-mic').events.click(); assert.equal(app.tracks[0].enabled,false);
  await app.get('toggle-camera').events.click(); assert.equal(app.tracks[1].enabled,false);
  app.response(action=>action==='heartbeat' ? {state:'admitted'} :
    {state:'joined',Meeting:{},Attendee:{},expiresAt:new Date(Date.now()+60000).toISOString()});
  await app.poll();assert.equal(app.starts(),1);
  assert.ok(app.mediaCalls.includes('realtimeMuteLocalAudio'));
  assert.ok(!app.mediaCalls.includes('startVideoInput')); // camera-off survives admission
  await app.get('leave-session').events.click();assert.equal(app.stopped(),2);
  const host=setup('host');await host.ready();
  host.response({state:'joined',Meeting:{},Attendee:{},expiresAt:new Date(Date.now()+60000).toISOString()});
  await host.get('join-session').events.click();assert.equal(host.starts(),1);
  host.response({state:'superseded'});await host.poll();
  assert.match(host.get('video-status').textContent,/no longer available/);
  assert.equal(host.stopped(),2);
  console.log('Telehealth controller: local-only preview, device race guard, waiting privacy, CSRF, host connection and revocation passed.');
})().catch(error=>{console.error(error);process.exitCode=1});
