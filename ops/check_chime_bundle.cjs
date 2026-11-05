// Load the actual vendored SDK, not a fake SDK. No camera or network is used.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
class SyntheticRtpSender { static getCapabilities(){return {codecs:[]}} }
const sandbox={RTCRtpSender:SyntheticRtpSender,console,TextEncoder,TextDecoder,URL,URLSearchParams,AbortController,setTimeout,clearTimeout,setInterval,clearInterval,
 crypto:require('node:crypto').webcrypto,
 navigator:{mediaDevices:{addEventListener(){},removeEventListener(){},enumerateDevices:async()=>[],getSupportedConstraints:()=>({}),getUserMedia(){throw Error('Smoke check must not request media')}},userAgent:'Mozilla/5.0 Chrome/130.0.0.0 Safari/537.36',platform:'Linux',maxTouchPoints:0},
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
(async()=>{
 const logger={info(){},warn(){},error(){},debug(){},setLogLevel(){},getLogLevel(){return 4}};
 const events={addObserver(){},removeObserver(){},async publishEvent(){}};
 const controller=new sandbox.NuviaVideoSDK.DefaultDeviceController(logger);
 const session=new sandbox.NuviaVideoSDK.DefaultMeetingSession(config,logger,controller,events);
 assert.ok(session.audioVideo);
 await session.destroy();
 console.log('Actual Chime SDK loads, constructs and destroys a meeting session without network or media.');
})().catch(error=>{console.error(error.name+': '+error.message);process.exitCode=1});
