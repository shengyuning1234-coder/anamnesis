const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const elements=new Map();
function element(){return {innerHTML:'',textContent:'',value:'',disabled:false,children:[],style:{},classList:{add(){},remove(){},toggle(){}},appendChild(child){this.children.push(child)},replaceChildren(){this.children=[]}}}
const get=id=>{if(!elements.has(id))elements.set(id,element());return elements.get(id)};
const c=vm.createContext({console,URLSearchParams,setTimeout,clearTimeout,clearInterval,
 window:{addEventListener(){},innerWidth:1280},navigator:{onLine:true},
 document:{addEventListener(){},getElementById:get,createElement:element,querySelectorAll:()=>[]},
 location:{origin:'http://localhost',search:''}});
const run=code=>vm.runInContext(code,c);
for(const name of ['meaning-format.js','app.js'])vm.runInContext(fs.readFileSync(path.join(__dirname,'../web/static/'+name),'utf8'),c);
assert.equal(run("formatMeanings('快乐；幸福\\n愉快')"),'① 快乐\n② 幸福\n③ 愉快');
assert.equal(run("formatMeanings('① 苹果\\n② 苹果树')"),'① 苹果\n② 苹果树');
assert.equal(run("formatMeanings('1. 苹果\\n2. 苹果树')"),'① 苹果\n② 苹果树');
assert.equal(run("formatMeanings('① 苹果 ② 苹果树')"),'① 苹果\n② 苹果树');
assert.equal(run("formatMeanings('苹果, 苹果树')"),'① 苹果, 苹果树');
assert.equal(run("formatMeanings('苹果\\\\n苹果树')"),'① 苹果\n② 苹果树');
assert.equal(run('circledNumber(21)'),'㉑');assert.equal(run('circledNumber(36)'),'㊱');assert.equal(run('circledNumber(51)'),'(51)');
run("STATE.quiz={index:0,words:[{id:1}],results:[]};renderQuiz({type:'choice',generation_source:'ai',mode:'choice_en2cn',prompt:'Sentence',answer:'苹果',options:['苹果','椅子','河流','音乐'],explanation:'仅作答后可见'}, {id:1})");
assert.equal(get('quiz-dynamic').children.length,4);
assert.ok(!get('quiz-extra').textContent.includes('仅作答后可见'));
assert.match(get('quiz-mode').textContent,/AI/);
run("showQuizFeedback(true,'正确',{answer:'苹果',explanation:'仅作答后可见'},1)");
assert.equal(get('quiz-feedback').children[0].textContent,'AI 解析：仅作答后可见');
// Load the real extension: both global and group starts must carry explicit source.
run('window.RECOVERED_BASE=undefined');
run('var RECOVERED_BASE={loadWords,selectWord,renderWordDetail,openWordModal,lookupWord,closeModal};');
vm.runInContext(fs.readFileSync(path.join(__dirname,'../web/static/upgrade.js'),'utf8'),c);
get('study-group').value='7';get('question-source').value='ai';
run("var sent;api=async (url,options)=>{sent=JSON.parse(options.body);return {total:1,session_id:'session',words:[{id:1}],question_source:sent.question_source}};loadQuizQuestion=async()=>{};ensureOnlineForWrite=()=>true");
(async()=>{
 await run("startReview('new')");
 assert.equal(run('sent.group_id'),7);assert.equal(run('sent.question_source'),'ai');assert.equal(run('STATE.quiz.questionSource'),'ai');
 get('question-source').value='local';get('study-group').value='';
 await run("startReview('new')");assert.equal(run('sent.question_source'),'local');assert.equal(run('sent.group_id'),null);
 console.log('PASS: circled numbering, no duplicate labels, post-answer explanation, explicit AI/local session selection with groups');
})().catch(error=>{console.error(error);process.exitCode=1});
