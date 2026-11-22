/* Recovered interface extensions. Group associations never own word records. */
let currentGroupId = null, GROUPS = [], groupTag = '', appSettings = {}, queueTimer;
let settingsPreview = null;
let settingsOpener = null;
let backgroundUploadRequest = 0;
const baseLoadWords = RECOVERED_BASE.loadWords, baseSelectWord = RECOVERED_BASE.selectWord, baseDetail = RECOVERED_BASE.renderWordDetail;
const baseWordModal = RECOVERED_BASE.openWordModal, baseLookup = RECOVERED_BASE.lookupWord, baseCloseModal = RECOVERED_BASE.closeModal;
function esc(value) { return String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }
function modal(html) { closeModal(); document.getElementById('modal-content').innerHTML = html; document.getElementById('modal-overlay').classList.remove('hidden'); }
function closeModal(e) {
  if (e && e.target !== document.getElementById('modal-overlay')) return;
  if (settingsPreview) { applyBackground(settingsPreview); settingsPreview = null; }
  clearInterval(queueTimer); queueTimer = null; baseCloseModal();
  settingsOpener?.focus();
  settingsOpener = null;
}
function initBackground(a) { applyBackground(a || {}); }
function applyBackground(a) {
  const image = document.getElementById('app-bg-image');
  if (a.background_type === 'custom' && a.background_image_path) {
    const source = appURL(a.background_image_path);
    if (image.getAttribute('src') !== source) {
      image.src = source;
      extractBgColors(a.background_image_path);
    }
    image.style.display = '';
    updateBgStyle(a.background_blur ?? 15, a.background_brightness ?? 75);
  } else {
    image.style.display = 'none';
    image.removeAttribute('src');
    resetAccentColors();
  }
  applyCardOpacity(a.card_opacity ?? 78); syncChatTheme();
}
function initTabs() {
  document.querySelectorAll('.tab-btn').forEach(b => b.onclick = () => activateTab(b.dataset.tab));
}
function activateTab(name) {
  const gid = name.startsWith('group-') ? Number(name.slice(6)) : null;
  currentGroupId = gid;
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.toggle('active', b.dataset.tab === name));
  document.querySelectorAll('.tab-content').forEach(p => p.classList.toggle('active', p.id === 'tab-' + (gid ? 'words' : name)));
  if (name === 'words' || gid) {
    document.getElementById('scope-label').textContent = gid ? (GROUPS.find(g => g.id === gid)?.name || '分组') : '全部单词';
    document.getElementById('group-link-button').classList.toggle('hidden', !gid); loadWords();
    document.getElementById('word-detail').innerHTML = '<p class="placeholder">选择一个单词，查看完整释义与学习进度</p>';
    STATE.selectedWordId = null;
  }
  if (name === 'groups') loadGroups();
  if (name === 'study') loadStats();
  if (name === 'reports') loadReports();
  if (name === 'chat') loadChat();
}
async function loadGroups() {
  try {
    GROUPS = await api('/api/groups'); renderGroups();
    const select = document.getElementById('study-group'), old = select.value;
    select.innerHTML = '<option value="">全部单词</option>' + GROUPS.map(g => `<option value="${g.id}">${esc(g.name)} (${g.word_count})</option>`).join(''); select.value = old;
    document.querySelectorAll('[data-tab^="group-"]').forEach(b => {
      const g = GROUPS.find(g => b.dataset.tab === 'group-' + g.id);
      if (g) b.querySelector('.group-tab-title').textContent = g.name; else b.remove();
    });
  } catch (e) { console.error(e); }
}
function renderGroups() {
  const search = document.getElementById('group-search').value.trim().toLowerCase();
  const shown = GROUPS.filter(g => (!groupTag || g.tags.includes(groupTag)) && (g.name + ' ' + g.tags.join(' ')).toLowerCase().includes(search));
  document.getElementById('group-count').textContent = `${shown.length} 个分组`;
  const tags = [...new Set(GROUPS.flatMap(g => g.tags))];
  const filters = document.getElementById('group-tag-filters'); filters.replaceChildren();
  ['', ...tags].forEach(tag => { const b = document.createElement('button'); b.className = 'filter-chip' + (tag === groupTag ? ' active' : ''); b.textContent = tag || '全部分组'; b.onclick = () => { groupTag = tag; renderGroups(); }; filters.append(b); });
  document.getElementById('group-grid').innerHTML = shown.map(g => `<article class="group-card" tabindex="0" onclick="openGroup(${g.id})" onkeydown="if(event.key==='Enter')openGroup(${g.id})"><div class="group-card-top"><span class="group-icon">▤</span><div class="group-card-menu" onclick="event.stopPropagation()"><button class="btn btn-sm btn-outline" aria-label="编辑分组" onclick="openGroupEditor(${g.id})">✎</button><button class="btn btn-sm btn-outline" aria-label="删除分组" onclick="removeGroup(${g.id})">×</button></div></div><h3>${esc(g.name)}</h3><p>${g.word_count} 个单词</p><div class="group-tags">${g.tags.map(t => `<span class="wi-tag">${esc(t)}</span>`).join('')}</div><div class="group-dates"><span>创建 ${esc(g.created_at.slice(0,10))}</span><span>修改 ${esc(g.updated_at.slice(0,10))}</span><span>学习 ${esc(g.learned_at?.slice(0,10) || '尚未学习')}</span></div></article>`).join('') || '<div class="empty-state"><h3>从一篇文章、一节课开始</h3><p>创建分组，将相关单词放在一起学习。单词进度全局共享。</p><button class="btn btn-primary" onclick="openGroupEditor()">＋ 创建第一个分组</button></div>';
}
function openGroup(id) {
  if (!document.querySelector(`[data-tab="group-${id}"]`)) {
    const b = document.createElement('button'); b.className = 'tab-btn group-tab'; b.dataset.tab = 'group-' + id;
    b.innerHTML = `<span class="group-tab-title">${esc(GROUPS.find(g => g.id === id)?.name)}</span><span class="tab-close" role="button" aria-label="关闭分组标签" tabindex="0">×</span>`;
    b.onclick = e => { if (e.target.closest('.tab-close')) { b.remove(); if (currentGroupId === id) activateTab('groups'); } else activateTab('group-' + id); };
    b.querySelector('.tab-close').onkeydown = e => { if (e.key === 'Enter') { e.stopPropagation(); b.remove(); if (currentGroupId === id) activateTab('groups'); } };
    document.querySelector('.tab-nav').append(b);
  }
  activateTab('group-' + id);
}
function openGroupEditor(id) {
  const g = GROUPS.find(g => g.id === id);
  modal(`<h3>${g ? '编辑分组' : '创建分组'}</h3><div class="form-group"><label>分组名称</label><input id="group-name" maxlength="100" value="${esc(g?.name)}" placeholder="例如：本周阅读 / Lesson 01"></div><div class="form-group"><label>标签（逗号分隔）</label><input id="group-tags" value="${esc(g?.tags.join(', '))}" placeholder="阅读, 工作, 课程"></div><div class="modal-actions"><button class="btn" onclick="closeModal()">取消</button><button class="btn btn-primary" onclick="saveGroup(${id || 'null'})">保存</button></div>`);
  document.getElementById('group-name').focus();
}
async function saveGroup(id) {
  const name = document.getElementById('group-name').value.trim(); if (!name) return toast('请输入名称','error');
  try { await api('/api/groups' + (id ? '/' + id : ''), {method:id ? 'PUT':'POST', body:JSON.stringify({name,tags:document.getElementById('group-tags').value.split(/[,，]/).map(t => t.trim()).filter(Boolean)})}); closeModal(); await loadGroups(); toast('分组已保存','success'); } catch (_) {}
}
async function removeGroup(id) {
  if (!confirm('删除此分组？其中的单词和学习进度仍保留在单词本中。')) return;
  try { await api('/api/groups/' + id,{method:'DELETE'}); if (currentGroupId === id) activateTab('groups'); await loadGroups(); } catch (_) {}
}
async function loadWords() {
  if (!currentGroupId) return baseLoadWords();
  const gid = currentGroupId;
  const query = new URLSearchParams({group_id:gid,sort:STATE.sort,search:document.getElementById('word-search').value.trim(),tag:document.getElementById('tag-filter').value});
  try { const words = await api('/api/words?' + query); if (currentGroupId !== gid) return; STATE.words = words; _offlineReadOnly = false; renderWordList(); document.getElementById('word-count').textContent = `共 ${words.length} 词`; }
  catch (_) { document.getElementById('word-list').innerHTML = '<p class="placeholder">无法加载分组，请检查连接后重试</p>'; }
}
async function selectWord(id) {
  if (!currentGroupId) return baseSelectWord(id);
  try { STATE.selectedWordId = id; renderWordList(); const w = await api(`/api/words/${id}?group_id=${currentGroupId}`); renderSelectedWord(w,false); } catch (_) {}
}
function renderWordDetail(w, readonly = false, fetchedAt) {
  baseDetail(w, readonly, fetchedAt);
  const detail = document.getElementById('word-detail');
  if (!appSettings.manual_tags) {
    const picker = document.getElementById('tag-preset-' + w.id); if (picker) picker.parentElement.style.display = 'none';
    detail.querySelectorAll('[data-action="remove-tag"]').forEach(b => { b.dataset.action = ''; b.textContent = b.textContent.replace(/ ×$/,''); b.style.cursor = 'default'; });
  }
  if (!readonly) {
    const retry = document.createElement('div'); retry.className = 'classification-note';
    retry.innerHTML = `<small>${w.classification_status === 'failed' ? esc(w.classification_error || '自动分类失败') : w.classification_status === 'pending' ? '正在自动分类…' : w.classification_status === 'local' ? '已按本地词表分类' : w.classification_status === 'unavailable' ? '本地未命中，配置 AI 后可补充分类' : '类别按难度与用途独立判定'}</small> <button class="btn btn-sm btn-outline" onclick="retryClassification(${w.id})">重新分类</button>`;
    detail.querySelector('.wd-pos').after(retry);
  }
  if (currentGroupId) {
    const context = document.createElement('div'); context.className = 'context-meaning-card';
    context.innerHTML = `<div class="wd-label">文中义 · 仅当前分组</div><p>${esc(w.context_meaning || '尚未设置，可从完整释义中点选')}</p><button class="btn btn-outline btn-sm" onclick="editGroupContext(${w.id})">选择 / 编辑文中义</button> <button class="btn btn-outline btn-sm" onclick="unlinkWord(${w.id})">移出此组</button>`;
    const meaning = detail.querySelector('.wd-section'); if (meaning) meaning.before(context); else detail.append(context);
  }
}
async function retryClassification(id) { try { toast('正在分类…'); await api('/api/words/classify',{method:'POST',body:JSON.stringify({word_id:id})}); await loadWords(); await loadTags(); await selectWord(id); toast('分类已完成','success'); } catch (_) {} }
async function loadTags() {
  try { _allTags = await api('/api/tags'); const s = document.getElementById('tag-filter'), value = s.value; s.innerHTML = '<option value="">全部分类</option>' + _allTags.map(t => `<option value="${esc(t.name)}">${esc(t.name)} (${t.count})</option>`).join(''); s.value = value; _studyModes = (await api('/api/study-modes')).tag_modes || {}; } catch (_) {}
}
function filterByTag(tag) { document.getElementById('tag-filter').value = tag; return loadWords(); }
function contextForm(value='') { return `<div class="form-group"><label>文中义（仅当前分组，可选）</label><textarea id="mf-context" placeholder="输入当前语境中的意思">${esc(value)}</textarea><div id="meaning-chips" class="meaning-chips"></div></div>`; }
function updateMeaningChips(meaning) {
  const box = document.getElementById('meaning-chips'); if (!box) return; box.replaceChildren();
  const values = [...new Set(meaningItems(meaning))];
  values.forEach(value => { const b = document.createElement('button'); b.type = 'button'; b.className = 'meaning-chip'; b.textContent = `${circledNumber(box.children.length + 1)} ${value}`; b.onclick = () => { document.getElementById('mf-context').value = value; }; box.append(b); });
}
function openWordModal(w) { baseWordModal(w); addModalAIControls(); if (currentGroupId) { const row = document.createElement('div'); row.innerHTML = contextForm(w?.context_meaning); document.querySelector('#modal-content .modal-actions').before(row); updateMeaningChips(w?.chinese_meaning || ''); document.getElementById('mf-meaning').oninput = e => updateMeaningChips(e.target.value); } }
async function lookupWord() { await baseLookup(); addModalAIControls(); updateMeaningChips(document.getElementById('mf-meaning')?.value); }
async function saveWord(id) {
  if(document.getElementById('mf-ai-controls')?.busy)return toast('请等待 AI 优化完成后再保存','error');
  const data = {}; for (const [k,field] of Object.entries({word:'word',phonetic:'phonetic',part_of_speech:'pos',chinese_meaning:'meaning',example_sentence:'example',example_translation:'trans',notes:'notes',source:'source'})) data[k] = document.getElementById('mf-' + field).value.trim();
  if (!data.word) return toast('请输入英文单词或短语','error');
  if (currentGroupId) { data.group_id = currentGroupId; data.context_meaning = document.getElementById('mf-context').value; }
  try {
    let response = await fetch(appURL('/api/words' + (id ? '/' + id : '')), {method:id ? 'PUT':'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)}), result = await response.json();
    if (response.status === 409 && result.exists && confirm(`「${data.word}」已存在。更新现有释义并保留学习进度${currentGroupId ? '，同时关联到当前分组' : ''}？`)) { data.update_existing = true; response = await fetch(appURL('/api/words'),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)}); result = await response.json(); }
    if (!response.ok) { if (response.status !== 409) toast(result.error || '保存失败','error'); return; }
    closeModal(); await loadWords(); await loadGroups(); await loadTags(); await loadStats(); selectWord(result.id); toast(result.updated ? '已更新，学习进度已保留' : '已录入','success');
  } catch (_) { toast('保存失败，请检查连接','error'); }
}
async function editGroupContext(id) { const w = await api(`/api/words/${id}?group_id=${currentGroupId}`); modal(`<h3>${esc(w.word)} · 文中义</h3>${contextForm(w.context_meaning)}<div class="modal-actions"><button class="btn" onclick="closeModal()">取消</button><button class="btn btn-primary" onclick="saveContext(${id})">保存</button></div>`); updateMeaningChips(w.chinese_meaning); }
async function saveContext(id) { try { await api(`/api/groups/${currentGroupId}/words/${id}`,{method:'PUT',body:JSON.stringify({context_meaning:document.getElementById('mf-context').value})}); closeModal(); await loadWords(); selectWord(id); } catch (_) {} }
async function unlinkWord(id) { if (!confirm('仅将此词移出当前分组？')) return; await api(`/api/groups/${currentGroupId}/words/${id}`,{method:'DELETE'}); await loadWords(); await loadGroups(); document.getElementById('word-detail').innerHTML = '<p class="placeholder">已移出分组，单词和进度仍保留</p>'; }
async function openLinkWords() {
  const words = await api('/api/words'); modal(`<h3>关联已有单词</h3><p class="modal-note">不复制单词，学习进度全局共享。</p><input class="search-input" placeholder="筛选单词" oninput="document.querySelectorAll('.link-word-row').forEach(r=>r.hidden=!r.textContent.toLowerCase().includes(this.value.toLowerCase()))"><div class="link-word-list">${words.map(w => `<label class="link-word-row"><input type="checkbox" value="${w.id}" ${STATE.words.some(x => x.id === w.id) ? 'checked disabled' : ''}> <b>${esc(w.word)}</b> ${esc(w.chinese_meaning.slice(0,65))}</label>`).join('')}</div><div class="modal-actions"><button class="btn" onclick="closeModal()">取消</button><button class="btn btn-primary" onclick="linkSelectedWords()">关联所选单词</button></div>`);
}
async function linkSelectedWords() { const ids = [...document.querySelectorAll('.link-word-row input:checked:not(:disabled)')].map(e => e.value); try { for (const id of ids) await api(`/api/groups/${currentGroupId}/words/${id}`,{method:'PUT',body:'{}'}); closeModal(); await loadWords(); await loadGroups(); toast(`已关联 ${ids.length} 个词`,'success'); } catch (_) {} }
function openQuickEntry() {
  modal(`<h3>⚡ 快速录入${currentGroupId ? ' · ' + esc(GROUPS.find(g => g.id === currentGroupId)?.name) : ''}</h3><p class="modal-note">每行一个单词或短语。用 | 分隔可选文中义。后台查词、补充例句并自动分类，关闭窗口后继续处理。</p><div class="form-group"><textarea id="quick-entries" rows="7" placeholder="serendipity | 意外的美好发现\ntake into account\nresilient"></textarea></div><label class="checkbox-label"><input type="checkbox" id="quick-update"> 更新已有单词的释义（保留学习进度）</label><div class="modal-actions"><button class="btn" onclick="closeModal()">关闭</button><button class="btn btn-primary" id="quick-submit" onclick="submitQuickEntry()">加入处理队列</button></div><div id="queue-list" class="queue-list"></div>`);
  refreshQueue(); queueTimer = setInterval(refreshQueue,2500);
}
async function submitQuickEntry() {
  const update = document.getElementById('quick-update').checked;
  const entries = document.getElementById('quick-entries').value.split(/\n/).filter(s => s.trim()).map(line => { const [word,...rest] = line.split('|'); return {word:word.trim(),...(rest.length ? {context_meaning:rest.join('|').trim()} : {}),update_existing:update}; });
  if (!entries.length) return toast('请先输入单词','error');
  const button = document.getElementById('quick-submit'); button.disabled = true;
  try { await api('/api/quick-entry',{method:'POST',body:JSON.stringify({entries,group_id:currentGroupId})}); document.getElementById('quick-entries').value = ''; toast('已加入后台队列','success'); refreshQueue(); } catch (_) {} finally { button.disabled = false; }
}
let queueSignature = '';
async function refreshQueue() {
  try { const jobs = await api('/api/jobs',{_silent:true}), box = document.getElementById('queue-list'); if (!box) return;
    box.innerHTML = '<h4>处理记录</h4>' + (jobs.slice(0,30).map(j => `<div class="queue-row"><div><b>${esc(j.payload.word || '自动分类')}</b><small>${esc(j.error || j.result?.message || '')}</small></div><span>${({pending:'排队中',running:'处理中',done:'已完成',failed:'失败'})[j.status]}</span>${j.status === 'failed' ? `<button class="btn btn-sm btn-outline" onclick="retryQueue('${j.id}')">重试</button>` : ''}</div>`).join('') || '<p class="modal-note">还没有任务</p>');
    const signature = jobs.filter(j => j.status === 'done').map(j => j.id).join(); if (signature !== queueSignature) { queueSignature = signature; loadWords(); loadGroups(); loadStats(); }
  } catch (_) {}
}
async function retryQueue(id) { try { await api(`/api/jobs/${id}/retry`,{method:'POST',body:'{}'}); refreshQueue(); } catch (_) {} }
async function updateQuota() {
  const input = document.getElementById('quota-input'), quota = Number(input.value);
  if (!Number.isInteger(quota) || quota < 1 || quota > 200) return toast('每日配额需为 1–200 的整数','error');
  try { await api('/api/settings',{method:'PUT',body:JSON.stringify({daily_quota:quota})}); await loadStats(); toast('配额已保存','success'); } catch (_) {}
}
async function learnNewWords() { return startReview('new'); }
async function startReview(trainingMode='review') {
  if (!ensureOnlineForWrite()) return;
  const button = document.getElementById('btn-start-review'); button.disabled = true;
  try {
    const group_id = Number(document.getElementById('study-group').value) || null;
    const question_source = document.getElementById('question-source').value;
    const response = await api('/api/quiz/sessions',{method:'POST',body:JSON.stringify({training_mode:trainingMode,group_id,question_source})});
    if (!response.total) return toast(response.message || '当前范围没有可学习的单词','info');
    STATE.quiz = {sessionId:response.session_id,words:response.words,index:0,question:null,results:[],preparationPolling:null,deletingSession:false,trainingMode,questionSource:response.question_source};
    document.getElementById('study-status').classList.add('hidden'); document.getElementById('quiz-preparing').classList.remove('hidden'); document.getElementById('quiz-prep-message').textContent=question_source==='ai'?'AI 正在生成语境和选项，请稍候…':'正在从本地词典准备题目…'; document.getElementById('quiz-panel').classList.add('hidden'); await loadQuizQuestion();
  } catch (_) {} finally { button.disabled = false; }
}
async function finishQuiz() {
  stopQuizPreparationPolling(); const q = STATE.quiz;
  if (q.sessionId) { try { await api('/api/quiz/sessions/' + q.sessionId,{method:'DELETE'}); } catch (_) {} }
  STATE.quiz.sessionId = null; document.getElementById('quiz-panel').classList.add('hidden'); document.getElementById('quiz-preparing').classList.add('hidden'); document.getElementById('study-status').classList.remove('hidden');
  try { await api('/api/session/end',{method:'POST',body:'{}'}); } catch (_) {}
  await loadStats(); await loadWords(); await loadGroups(); toast(`本次学习结束 · 完成 ${q.results.length} 次作答`,'success');
}
function settingField(label,id,value,type='text',extra='') { return `<div class="form-group"><label for="${id}">${label}</label><input id="${id}" type="${type}" value="${esc(value)}" ${extra}></div>`; }
const settingsSections = [
  ['appearance', '外观'], ['learning', '学习'], ['ai', 'AI 服务'],
  ['security', '访问'], ['data', '数据'], ['integration', '对话与 MCP'],
];
function settingsPane(name) {
  const settings = document.querySelector('.settings-window');
  for (const pane of settings.querySelectorAll('.settings-pane')) {
    pane.hidden = pane.dataset.pane !== name;
  }
  for (const button of settings.querySelectorAll('.settings-tab')) {
    if (button.dataset.pane === name) button.setAttribute('aria-current', 'true');
    else button.removeAttribute('aria-current');
  }
  settings.querySelector('.settings-content').scrollTop = 0;
}
function onSettingsKeydown(event) {
  if (event.key === 'Escape') {
    event.preventDefault();
    closeModal();
  }
  if (event.key !== 'Tab') return;
  const controls = [...event.currentTarget.querySelectorAll(
    'button:not(:disabled), input:not(:disabled), select:not(:disabled), a[href]'
  )].filter(control => control.getClientRects().length);
  const first = controls[0], last = controls.at(-1);
  if (event.shiftKey && event.target === first) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && event.target === last) {
    event.preventDefault();
    first.focus();
  }
}
async function openSettings() {
  const opener = document.activeElement;
  try {
    const [s, dictionaries] = await Promise.all([api('/api/settings'), api('/api/dictionaries')]), a = s.appearance; appSettings = s;
    previewBackground = null;
    modal(`<div class="settings-window" role="dialog" aria-modal="true" aria-labelledby="settings-title">
    <header class="settings-header"><h2 id="settings-title">设置</h2><button class="settings-close" type="button" aria-label="关闭设置" onclick="closeModal()">×</button></header>
    <div class="settings-layout">
    <nav class="settings-tabs" aria-label="设置分类">${settingsSections.map(([id,label]) => `<button type="button" class="settings-tab" data-pane="${id}" aria-controls="settings-${id}" onclick="settingsPane('${id}')">${label}</button>`).join('')}</nav>
    <div class="settings-content">
    <section class="settings-pane" id="settings-appearance" data-pane="appearance" aria-labelledby="settings-heading-appearance"><h3 id="settings-heading-appearance">外观</h3><h4>背景与透明度</h4><p class="setting-help">上传图片后自动提取主题色。调整滑块可实时预览，保存后生效。</p><label class="btn btn-outline file-action">选择背景图片<input class="visually-hidden" type="file" accept="image/*" onchange="uploadBackground(this)"></label> <button class="btn btn-outline" onclick="previewDefaultBackground()">恢复默认背景</button>
    ${[['模糊度','set-bg-blur',a.background_blur,0,30,'px'],['背景亮度','set-bg-brightness',a.background_brightness,20,100,'%'],['界面不透明度','set-card-opacity',a.card_opacity,15,100,'%']].map(([label,id,value,min,max,unit]) => `<div class="form-group range-setting"><label for="${id}">${label}<output id="${id}-out" for="${id}">${value}${unit}</output></label><input type="range" id="${id}" min="${min}" max="${max}" value="${value}" oninput="previewAppearance()"></div>`).join('')}</section>
    <section class="settings-pane" id="settings-learning" data-pane="learning" aria-labelledby="settings-heading-learning" hidden><h3 id="settings-heading-learning">学习</h3>${settingField('每日新词配额','set-quota',s.daily_quota,'number','min="1" max="200"')}<div class="form-group"><label>复习方向</label><select id="set-review-mode">${[['mixed','混合'],['en2cn','英 → 中'],['cn2en','中 → 英']].map(([v,t]) => `<option value="${v}" ${s.review_mode === v?'selected':''}>${t}</option>`).join('')}</select></div><div class="form-group"><label>记忆调度</label><select id="set-scheduling-mode"><option value="ebbinghaus">艾宾浩斯间隔</option><option value="fsrs" ${s.scheduling_mode === 'fsrs'?'selected':''}>FSRS 自适应</option></select></div>${settingField('FSRS 目标记忆保持率','set-fsrs-target-r',s.fsrs.target_R,'number','min="0.7" max="0.99" step="0.01"')}<label class="checkbox-label"><input id="set-auto-decay" type="checkbox" ${s.auto_decay?'checked':''}> 逾期自动衰减熟练度</label><label class="checkbox-label"><input id="set-manual-tags" type="checkbox" ${s.manual_tags?'checked':''}> 显示手动添加标签入口</label><h4>各分类的学习题型</h4>${[...new Set([..._allTags.map(t=>t.name),...Object.keys(s.study_modes)])].map(t=>`<div class="tag-mode-row"><span>${esc(t)}</span><select class="tag-mode-sel" data-tag="${esc(t)}">${[['full','全部题型'],['meaning_only','仅释义'],['choice_only','仅选择']].map(([v,n])=>`<option value="${v}" ${(s.study_modes[t]||'full')===v?'selected':''}>${n}</option>`).join('')}</select></div>`).join('')}</section>
    <section class="settings-pane" id="settings-ai" data-pane="ai" aria-labelledby="settings-heading-ai" hidden><h3 id="settings-heading-ai">AI 服务</h3><h4>本地词典与分类</h4><p class="setting-help">已有双解词典：${dictionaries.primary_ready ? '已就绪' : '索引准备中或未挂载'}<br>ECDICT：${(dictionaries.counts.entries || 0).toLocaleString()} 条词条<br>WordNet：${(dictionaries.counts.wordnet || 0).toLocaleString()} 条词形义项记录<br>补充分级词表：${(dictionaries.counts.labels || 0).toLocaleString()} 条标签记录</p><p class="setting-help">文字分析和本地查词不调用 AI。分类优先匹配本地词表，未命中才使用 AI；查词增强保留词典原文，AI 内容单独标注。</p>${settingField('兼容 OpenAI 的 API 地址','set-api-base',s.api_base)}${settingField('API Key（留空保留）','set-api-key','','password',`autocomplete="off" placeholder="${s.has_key?'已配置':'未配置'}"`)}${settingField('模型','set-model',s.model)}${settingField('HTTP / HTTPS 代理（可选）','set-proxy',s.proxy_url)}<button class="btn btn-outline" onclick="testAISettings(this)">测试已保存的连接</button></section>
    <section class="settings-pane" id="settings-security" data-pane="security" aria-labelledby="settings-heading-security" hidden><h3 id="settings-heading-security">访问</h3><p class="setting-help">普通登录保留 30 天，勾选记住设备保留 180 天。修改密码会使其他设备退出。</p>${s.has_password?settingField('原密码','set-old-pwd','','password'):''}${settingField(s.has_password?'新密码（留空保留）':'设置访问密码（至少 8 位）','set-new-pwd','','password')}<button class="btn btn-outline" onclick="logoutDevice()">退出当前设备</button></section>
    <section class="settings-pane" id="settings-data" data-pane="data" aria-labelledby="settings-heading-data" hidden><h3 id="settings-heading-data">数据</h3><h4>词条与分组备份</h4><p class="setting-help">JSON 可迁移词条、分组、复习进度。完整数据备份请同时保存 Docker 挂载目录。</p><button class="btn btn-outline" onclick="exportWords()">导出 JSON</button> <a class="btn btn-outline" href="${appURL('/api/backup/database')}">下载数据库快照</a><label class="btn btn-outline file-action">导入 JSON<input type="file" class="visually-hidden" accept=".json" onchange="importWords(this)"></label><label class="checkbox-label"><input type="checkbox" id="import-overwrite"> 覆盖现有词条及进度</label></section>
    <section class="settings-pane" id="settings-integration" data-pane="integration" aria-labelledby="settings-heading-integration" hidden><h3 id="settings-heading-integration">对话与 MCP</h3>${canLoadChat(s) ? '<p class="setting-help">对话、词库 MCP 与网络搜索已内置。容器启动时自动连接，新对话默认启用。</p>' : '<p class="setting-help">内置对话随完整服务启动，无需配置地址。当前仅启动了单词服务。</p>'}<p class="setting-help">以下地址和 Token 仅供外部 MCP 客户端使用；内置对话无需填写。</p>${settingField('MCP 服务地址','mcp-url',location.origin+appURL('/mcp'),'text','readonly')}<button class="btn btn-outline" onclick="revealAgentToken()">显示 Agent Token</button><div id="agent-token-area"></div></section>
    </div></div>
    <footer class="modal-actions settings-footer"><button class="btn btn-outline" onclick="closeModal()">取消</button><button class="btn btn-primary" onclick="saveSettings()">保存设置</button></footer></div>`);
    settingsPreview = structuredClone(a);
    settingsOpener = opener;
    document.querySelector('.settings-window').addEventListener('keydown', onSettingsKeydown);
    settingsPane('appearance');
    document.querySelector('.settings-tab').focus();
  } catch (_) {}
}
let previewBackground = null;
function previewAppearance() {
  const a = {...(previewBackground || appSettings.appearance)};
  for (const [id,key,unit] of [['set-bg-blur','background_blur','px'],['set-bg-brightness','background_brightness','%'],['set-card-opacity','card_opacity','%']]) { const e = document.getElementById(id); a[key] = Number(e.value); document.getElementById(id+'-out').textContent = e.value+unit; }
  applyBackground(a);
}
function previewDefaultBackground() {
  ++backgroundUploadRequest;
  previewBackground = {background_type:'default', background_image_path:''};
  previewAppearance();
}
async function uploadBackground(input) {
  const file = input.files[0];
  if (!file) return;
  const request = ++backgroundUploadRequest;
  const originalAppearance = settingsPreview;
  const form = new FormData();
  form.append('file', file);
  form.append('preview', '1');
  try {
    const response = await fetch(appURL('/api/settings/background/upload'), {method:'POST', body:form});
    const data = await response.json();
    if (settingsPreview !== originalAppearance || request !== backgroundUploadRequest) return;
    if (!response.ok) throw Error(data.error);
    previewBackground = {background_type:'custom', background_image_path:data.path};
    previewAppearance();
  } catch (error) {
    if (settingsPreview === originalAppearance && request === backgroundUploadRequest) {
      toast(error.message, 'error');
    }
  } finally {
    input.value = '';
  }
}
async function saveSettings() {
  const value = id => document.getElementById(id)?.value || '', checked = id => document.getElementById(id).checked;
  const quota = Number(value('set-quota')); if (!Number.isInteger(quota)||quota<1||quota>200) return toast('每日配额需为 1–200 的整数','error');
  const password = value('set-new-pwd'); if (password && password.length < 8) return toast('密码至少 8 位','error');
  const data = {api_base:value('set-api-base').trim(),model:value('set-model').trim(),proxy_url:value('set-proxy').trim(),daily_quota:quota,review_mode:value('set-review-mode'),scheduling_mode:value('set-scheduling-mode'),auto_decay:checked('set-auto-decay'),manual_tags:checked('set-manual-tags'),fsrs:{target_R:Number(value('set-fsrs-target-r'))},appearance:{...(previewBackground || appSettings.appearance),background_blur:Number(value('set-bg-blur')),background_brightness:Number(value('set-bg-brightness')),card_opacity:Number(value('set-card-opacity'))},study_modes:{}};
  document.querySelectorAll('.tag-mode-sel').forEach(e=>data.study_modes[e.dataset.tag]=e.value); if (value('set-api-key')) data.api_key = value('set-api-key');
  try {
    if(password) await api('/api/auth/change-password',{method:'POST',body:JSON.stringify({old_password:value('set-old-pwd'),new_password:password})});
    const saved=await api('/api/settings',{method:'PUT',body:JSON.stringify(data)}); appSettings = {...appSettings,...data,has_key:saved.has_key}; delete appSettings.api_key; _studyModes=data.study_modes;
    settingsPreview = null; previewBackground = null; closeModal(); applyBackground(data.appearance); await loadStats(); if(STATE.selectedWordId) selectWord(STATE.selectedWordId); toast('设置已保存','success');
  } catch (_) {}
}
async function testAISettings(button) { button.disabled = true; button.textContent='正在测试…'; try { await api('/api/settings/test-ai',{method:'POST',body:'{}'}); toast('AI 连接成功','success'); } catch (_) {} finally { button.disabled=false; button.textContent='测试已保存的连接'; } }
async function logoutDevice() { await api('/api/auth/logout',{method:'POST',body:'{}'}); location.href=appURL('/login'); }
async function revealAgentToken() { const d=await api('/api/extension/token-info'); document.getElementById('agent-token-area').innerHTML=settingField('仅向可信的 Agent 提供','ext-token',d.token,'password','readonly'); }
function canLoadChat(s) {
  return s.chat_enabled === true && s.openwebui_url === '/' &&
    new URL(appURL('/'), location.origin).pathname !== '/';
}
async function loadChat() {
  const s = await api('/api/settings'), frame = document.getElementById('chat-frame');
  const enabled = canLoadChat(s);
  document.getElementById('chat-placeholder').classList.toggle('hidden', enabled);
  frame.classList.toggle('hidden', !enabled);
  if (!enabled) {
    frame.onload = null;
    frame.removeAttribute('src');
    return;
  }
  if (frame.src !== new URL(s.openwebui_url, location.origin).href) {
    frame.src = s.openwebui_url;
    frame.onload = syncChatTheme;
  }
}
function syncChatTheme() { const frame=document.getElementById('chat-frame'); if(!frame?.getAttribute('src')) return; const rgb=getComputedStyle(document.documentElement).getPropertyValue('--theme-p').split(',').map(Number); const accent=rgb.length===3?'#'+rgb.map(v=>Math.max(0,Math.min(255,Math.round(v))).toString(16).padStart(2,'0')).join(''):'#6654d9'; frame.contentWindow?.postMessage({type:'anamnesis-theme',accent},new URL(frame.src).origin); }
document.addEventListener('DOMContentLoaded',async()=>{ new MutationObserver(syncChatTheme).observe(document.documentElement,{attributes:true,attributeFilter:['style']}); await loadGroups(); try { appSettings=await api('/api/settings'); }catch(_){}; if(new URLSearchParams(location.search).get('tab')==='chat') activateTab('chat'); });

function addModalAIControls() {
  if(document.getElementById('mf-ai-controls'))return;
  const row=document.createElement('div');row.id='mf-ai-controls';row.className='ai-optimization';
  row.innerHTML='<p id="mf-ai-status">先查本地词典，再按需使用 AI 补充例句、搭配与用法；结果填入表单，保存后生效。</p><button id="mf-ai-button" type="button" class="btn btn-primary" onclick="optimizeModalWord()">使用 AI 优化</button><button id="mf-ai-restore" type="button" class="btn btn-outline hidden" onclick="restoreModalLocal()">恢复优化前内容</button>';
  document.querySelector('#modal-content .modal-actions').before(row);
}
function modalWordSnapshot() {
  return Object.fromEntries(['word','phonetic','pos','meaning','example','trans','notes','source'].map(k=>[k,document.getElementById('mf-'+k).value]));
}
function fillModalWord(d, source) {
  for(const [k,field] of Object.entries({phonetic:'phonetic',pos:'part_of_speech',meaning:'chinese_meaning',example:'example_sentence',trans:'example_translation',notes:'notes'}))document.getElementById('mf-'+k).value=d[field]||'';
  document.getElementById('mf-source').value=source;
  document.getElementById('mf-source-label').textContent=source;
  updateMeaningChips(d.chinese_meaning);
}
function restoreModalLocal() {
  const row=document.getElementById('mf-ai-controls'), snapshot=row?.snapshot;
  if(!snapshot||row.busy)return;
  if(document.getElementById('mf-word').value.trim()!==snapshot.word.trim())return toast('单词已更改，请重新查本地词典','error');
  for(const [k,v] of Object.entries(snapshot))document.getElementById('mf-'+k).value=v;
  document.getElementById('mf-source-label').textContent=snapshot.source;
  updateMeaningChips(snapshot.meaning);document.getElementById('mf-ai-status').textContent='已恢复优化前内容';
}
async function optimizeModalWord() {
  const word=document.getElementById('mf-word').value.trim(),row=document.getElementById('mf-ai-controls');
  if(!word)return toast('请先输入单词','error');
  if(row.busy)return;
  row.busy=true;const snapshot=modalWordSnapshot();
  const button=document.getElementById('mf-ai-button');button.disabled=true;button.textContent='正在优化…';
  try {
    const r=await api('/api/words/lookup',{method:'POST',body:JSON.stringify({word,enhance:true})});
    if(!row.isConnected||document.getElementById('mf-word').value.trim()!==word)return;
    if(r.warning){toast(r.warning,'error');return;}
    if(!r.found)throw Error(r.message||'未获取到释义');
    // Do not overwrite edits made while awaiting the network response.
    if(JSON.stringify(modalWordSnapshot())!==JSON.stringify(snapshot))return toast('表单已修改，请再次点击优化以更新结果','error');
    row.snapshot=snapshot;fillModalWord(r.data,r.source||r.data.source);
    document.getElementById('mf-ai-restore').classList.remove('hidden');
    document.getElementById('mf-ai-status').textContent='AI 优化完成，请检查例句和笔记。点击保存后生效，也可恢复优化前内容。';
  }catch(e){toast(e.message||'AI 优化失败，已保留原内容','error');}
  finally{row.busy=false;if(button.isConnected){button.disabled=false;button.textContent='使用 AI 优化';}}
}
