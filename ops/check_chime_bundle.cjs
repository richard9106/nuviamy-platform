// Load the actual vendored SDK, not a fake SDK. No camera or network is used.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const sandbox={console,TextEncoder,TextDecoder,URL,URLSearchParams,AbortController,setTimeout,clearTimeout,setInterval,clearInterval,
 navigator:{userAgent:'Mozilla/5.0 Chrome/130.0.0.0 Safari/537.36',platform:'Linux',maxTouchPoints:0},
 document:{createElement:()=>({canPlayType:()=>'',style:{}}),addEventListener(){},removeEventListener(){}},
 addEventListener(){},removeEventListener(){}};
sandbox.window=sandbox;sandbox.self=sandbox;
try {
 vm.runInNewContext(fs.readFileSync('static/telehealth/chime-sdk.js','utf8'),sandbox,{timeout:10000,filename:'chime-sdk.js'});
} catch(error) {
 throw new Error('Video SDK initialization failed: '+error.name+': '+error.message);
}
for(const name of ['DefaultMeetingSession','DefaultDeviceController','MeetingSessionConfiguration'])
 assert.equal(typeof sandbox.NuviaVideoSDK[name],'function',name+' must be exported');
const config=new sandbox.NuviaVideoSDK.MeetingSessionConfiguration({MeetingId:'synthetic',MediaPlacement:{AudioHostUrl:'synthetic.invalid',SignalingUrl:'wss://synthetic.invalid'}},{AttendeeId:'synthetic',JoinToken:'synthetic'});
assert.equal(config.meetingId,'synthetic');
console.log('Actual Chime browser bundle loads and exposes usable SDK constructors without network or media.');
