const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../web/static/upgrade.js'), 'utf8');
const functions = source.slice(source.indexOf('function canLoadChat('), source.indexOf('function syncChatTheme('));

async function check(settings, prefix, expected) {
  const frame = {src: 'http://localhost/', onload() {}, classList: {toggle(k, v) {this.hidden = v;}}, removeAttribute(k) {delete this[k];}};
  const placeholder = {classList: {toggle(k, v) {this.hidden = v;}}};
  const context = vm.createContext({URL, location: {origin: 'http://localhost'}, appURL: p => prefix + p,
    api: async () => settings, syncChatTheme() {}, document: {getElementById: id => id === 'chat-frame' ? frame : placeholder}});
  vm.runInContext(functions, context);
  await vm.runInContext('loadChat()', context);
  assert.equal(frame.classList.hidden, !expected);
  assert.equal(placeholder.classList.hidden, expected);
  if (!expected) {assert.equal(frame.src, undefined); assert.equal(frame.onload, null);}
}
(async () => {
  await check({openwebui_url: '/'}, '', false);
  await check({openwebui_url: '/', chat_enabled: false}, '', false);
  await check({openwebui_url: '/', chat_enabled: true}, '', false);
  await check({openwebui_url: '/', chat_enabled: true}, '/words', true);
  console.log('PASS: stale chat URL never embeds standalone word page; bundled chat remains available');
})().catch(error => {console.error(error); process.exitCode = 1;});
