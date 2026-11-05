const assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
const source=fs.readFileSync('static/security-session.js','utf8');
function setup(video=true,pending=false){
 let now=0;const listeners={},timers=[],requests=[],navigation=[];
 const sandbox={Date:{now:()=>now,parse:Date.parse},Number,AbortSignal,
 document:{currentScript:{dataset:{pending:String(pending),videoSession:String(video),idleSeconds:'3600',deadlineSeconds:'28800'}},cookie:'csrftoken=synthetic',querySelector(){return {value:'synthetic'}},body:{replaceChildren(){}},addEventListener(){}},
 window:{addEventListener(n,f){listeners[n]=f},location:{assign(url){navigation.push(url)}}},
 fetch:async(url)=>{requests.push(url);return {status:200,redirected:false}},setInterval(fn,ms){timers.push({fn,ms})}};
 vm.runInNewContext(source,sandbox);
 return {time:v=>now=v,activity:expiry=>listeners['nuvia:live-video-activity']({detail:{expiresAt:expiry}}),check:()=>timers.find(t=>t.ms===1000).fn(),requests,navigation};
}
(async()=>{
 let p=setup();p.time(59*60000);p.activity(new Date(89*60000).toISOString());p.time(61*60000);p.check();await Promise.resolve();assert.equal(p.requests.length,0); // a connected call crosses idle threshold
 p.time(120*60000);p.check();await Promise.resolve();assert.ok(p.requests.includes('/logout/')); // stopping activity restores ordinary idle expiry
 p=setup(false);p.time(59*60000);p.activity(new Date(89*60000).toISOString());p.time(61*60000);p.check();await Promise.resolve();assert.ok(p.requests.includes('/logout/'));
 for(const expiry of ['invalid',new Date(1).toISOString(),new Date(999999999).toISOString()]){
  p=setup();p.time(59*60000);p.activity(expiry);p.time(61*60000);p.check();await Promise.resolve();assert.ok(p.requests.includes('/logout/'));
 }
 p=setup();p.time(28799*1000);p.activity(new Date(28801*1000).toISOString());p.time(28801*1000);p.check();await Promise.resolve();assert.ok(p.requests.includes('/logout/')); // absolute expiry wins
 p=setup(true,true);p.time(28799*1000);p.activity(new Date(28801*1000).toISOString());p.time(28801*1000);p.check();await Promise.resolve();assert.ok(p.requests.includes('/logout/'));
 console.log('Video activity: connected-call continuity, ordinary idle expiry, invalid activity and absolute/challenge expiry passed.');
})().catch(e=>{console.error(e);process.exitCode=1});
