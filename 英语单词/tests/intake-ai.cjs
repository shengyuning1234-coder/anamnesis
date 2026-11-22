const assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
const elements=new Map(), messages=[];let calls=0,resolveAI;
const get=id=>{if(!elements.has(id))elements.set(id,{innerHTML:'',textContent:'',value:'',disabled:false});return elements.get(id)};
const c=vm.createContext({console,Set,structuredClone,window:{},document:{addEventListener(){},getElementById:get},esc:v=>String(v??''),toast:m=>messages.push(m),api:()=>{calls++;return new Promise(resolve=>resolveAI=resolve)}});
vm.runInContext(fs.readFileSync(path.join(__dirname,'../web/static/meaning-format.js'),'utf8'),c);
vm.runInContext(fs.readFileSync(path.join(__dirname,'../web/static/intake.js'),'utf8'),c);
const run=script=>vm.runInContext(script,c);
run("INTAKE.words=[{word:'apple',count:1,loaded:true,found:true,data:{source:'local',chinese_meaning:'苹果',notes:'词典原文'}}]; renderIntakeDetail();");
assert.equal(calls,0);assert.match(get('intake-word-detail').innerHTML,/使用 AI 优化/);
// Only explicit invocation triggers a request, and duplicate clicks are ignored.
run('renderIntakeList=()=>renderIntakeDetail()');
(async()=>{
 const pending=run('queryIntakeAI(0)');await run('queryIntakeAI(0)');assert.equal(calls,1);
 resolveAI({found:true,data:{source:'local+ai',chinese_meaning:'苹果',notes:'词典原文\nAI 补充'}});await pending;
 assert.equal(run('INTAKE.words[0].data.source'),'local+ai');
 run('restoreIntakeLocal(0)');assert.equal(run('INTAKE.words[0].data.notes'),'词典原文');
 const failed=run('queryIntakeAI(0)');resolveAI({found:true,warning:'AI 不可用，保留本地释义'});await failed;
 assert.equal(run('INTAKE.words[0].data.source'),'local');assert.equal(messages.at(-1),'AI 不可用，保留本地释义');
 const stale=run('queryIntakeAI(0)');run('INTAKE.words=[]');resolveAI({found:true,data:{source:'ai',chinese_meaning:'旧请求'}});await stale;
 assert.equal(run('INTAKE.words.length'),0);
 console.log('PASS: local-only rendering, explicit AI opt-in, duplicate-click protection, restoration, failure preservation and stale results');
})().catch(e=>{console.error(e);process.exitCode=1});
