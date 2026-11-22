/* Personal accounts, durable learning, task progress and model routing. */
let signedInUser = null,
  progressTimer = null,
  activeSession = null,
  providerDraft = null;
let imageGroupDraft = [];
const accountFetch = window.fetch.bind(window);
window.fetch = async function (input, options = {}) {
  const url = new URL(
    typeof input === "string" ? input : input.url,
    location.href,
  );
  const isAPI =
    url.origin === location.origin && url.pathname.startsWith(appURL("/api/"));
  if (
    isAPI &&
    !/\/api\/auth\/(status|login|setup|register)$/.test(url.pathname)
  ) {
    if (!signedInUser) {
      const status = await accountFetch(appURL("/api/auth/status"), {
        cache: "no-store",
      });
      const data = await status.json();
      signedInUser = data.user;
    }
    if (signedInUser) {
      const headers = new Headers(
        options.headers ||
          (typeof input !== "string" ? input.headers : undefined),
      );
      headers.set("X-Account-ID", signedInUser.id);
      options = { ...options, headers };
    }
  }
  const response = await accountFetch(input, options);
  if (isAPI && response.status === 409) {
    const error = await response
      .clone()
      .json()
      .catch(() => ({}));
    if (error.account_changed) {
      location.reload();
      throw Error(error.error);
    }
  }
  const owner = response.headers?.get("X-Account-ID");
  if (isAPI && owner && signedInUser && owner !== signedInUser.id) {
    location.reload();
    throw Error("账号已切换，请刷新后继续");
  }
  return response;
};
const previousLoadQuestion = loadQuizQuestion,
  previousStartReview = startReview;
const previousNextQuestion = nextQuizQuestion,
  previousFinishQuiz = finishQuiz;
const previousFeedback = showQuizFeedback,
  previousOpenSettings = openSettings;
function setChromeCollapsed(part, collapsed) {
  document.body.classList.toggle(part + "-collapsed", collapsed);
  const button = document.getElementById("toggle-" + part);
  button.textContent =
    (collapsed ? "展开" : "收起") + (part === "header" ? "顶栏" : "标签栏");
  button.setAttribute("aria-expanded", String(!collapsed));
}
function toggleChrome(part) {
  const collapsed = !document.body.classList.contains(part + "-collapsed");
  const restoreFocused = document.activeElement?.closest(".layout-restore");
  setChromeCollapsed(part, collapsed);
  if (restoreFocused) {
    document.querySelector(part === "header" ? "#page-header button" : "#page-tabs .tab-btn.active")?.focus();
  }
  if (signedInUser)
    localStorage.setItem(
      "anamnesis-layout:" + signedInUser.id + ":" + part,
      String(collapsed),
    );
}
function openGuide() {
  modal(
    `<h3>忆溯使用指南</h3><ol class="guide-list"><li><b>收集单词：</b>单词本可手动录词，快速录入可批量后台查词；「录入」支持文字与图片材料。导入前核对释义。</li><li><b>整理分组：</b>一个单词可关联多个分组。文中义仅在当前分组使用，学习记录在自己的分组间共享。</li><li><b>开始学习：</b>选择范围和本地或 AI 出题。AI 会在后台准备整套题目，失败时使用本地题。下方色块显示准备、作答和跳过状态。</li><li><b>继续学习：</b>刷新或关闭页面不会结束任务，回到学习页点击「继续上次学习」。点击结束才会关闭会话；会话保留 30 天。</li><li><b>配置 AI：</b>设置中配置个人 Key，或在「多模型与场景」中为出题、识图等任务选模型。个人 Key 调用单独统计，不扣平台额度。额度按平台发起的 AI 请求次数计，含失败请求，网络重试不重复扣。</li><li><b>管理账号：</b>「账号」可查看登录设备并撤销登录，管理员可创建、停用账号和设置额度。旧版账号名为 admin，原密码仍可使用。</li><li><b>使用对话与工具：</b>一体化部署通过平台身份进入 OpenWebUI。外部 MCP 客户端使用设置中自己的服务地址和 Agent Token。工具能操作自己的词库、分组和录入任务。</li><li><b>安装与词典：</b>支持的浏览器可将网页安装到设备；账号中心可导入 JSON 字典并切换优先查词来源。安装不代表 AI 可离线使用。</li></ol><button class="btn" onclick="closeModal()">知道了</button>`,
  );
}
function reviewImageGroups(groups) {
  imageGroupDraft = groups;
  modal(
    `<h3>图片识词与分组预览</h3><p class="feature-note">请核对 AI 识别内容，取消不需要的词。确认后创建分组并录入；已有词保留原词条和进度，图片释义保存为分组文中义。</p>${groups.map((g, gi) => `<div class="provider-card"><input aria-label="分组名称" data-image-group="${gi}" value="${esc(g.name)}">${g.entries.map((e, ei) => `<label class="feature-row"><input type="checkbox" data-image-entry="${gi}:${ei}" checked><b>${esc(e.word)}</b><input aria-label="${esc(e.word)} 的中文释义" data-image-meaning="${gi}:${ei}" value="${esc(e.chinese_meaning)}"></label>`).join("")}</div>`).join("")}<div class="modal-actions"><button class="btn" onclick="closeModal()">取消</button><button class="btn btn-primary" id="save-image-groups">确认建组并录入</button></div>`,
  );
  document.getElementById("save-image-groups").onclick = async (e) => {
    e.target.disabled = true;
    try {
      const selected = imageGroupDraft
        .map((g, gi) => ({
          name: document.querySelector('[data-image-group="' + gi + '"]').value,
          entries: g.entries
            .filter(
              (x, ei) =>
                document.querySelector(
                  '[data-image-entry="' + gi + ":" + ei + '"]',
                ).checked,
            )
            .map((x) => {
              const ei = g.entries.indexOf(x);
              return {
                ...x,
                chinese_meaning: document.querySelector(
                  '[data-image-meaning="' + gi + ":" + ei + '"]',
                ).value,
              };
            }),
        }))
        .filter((g) => g.entries.length);
      const r = await api("/api/intake/image/save", {
        method: "POST",
        body: JSON.stringify({ groups: selected }),
      });
      closeModal();
      await loadGroups();
      await loadWords();
      toast(
        `已创建 ${r.group_ids.length} 组，新增 ${r.added} 词、关联 ${r.linked} 词`,
        "success",
      );
    } finally {
      e.target.disabled = false;
    }
  };
}
async function openAccountCenter() {
  try {
    const [status, devices, usage] = await Promise.all([
      api("/api/auth/status"),
      api("/api/devices"),
      api("/api/ai/usage"),
    ]);
    signedInUser = status.user;
    modal(
      `<h3>${esc(signedInUser.username)} · ${signedInUser.role === "admin" ? "管理员" : "个人账号"}</h3><p class="feature-note">今日平台 AI 请求 ${usage.platform_calls} / ${usage.unlimited ? "不限" : usage.allowance} 次，个人 Key 请求 ${usage.own_calls} 次。仅统计单词平台发起的调用。</p><div class="feature-section"><button class="btn btn-outline" onclick="openProviders()">多模型与场景</button> <button class="btn btn-outline" onclick="openDictionaries()">导入与切换字典</button> ${signedInUser.role === "admin" ? '<button class="btn btn-outline" onclick="openUsers()">用户管理</button>' : ""} <button class="btn" onclick="logoutDevice()">退出 / 切换账号</button></div><h4>登录设备</h4><p class="feature-note">显示 IP、浏览器标识和活动时间。同一设备重复登录可能出现多条会话记录。</p>${devices.map((d) => `<div class="feature-row"><div><b>${d.current ? "当前登录" : "其他登录"}</b><small>${esc(d.ip)} · ${esc(d.ua)}</small><small>最近活动 ${esc(d.seen_at)} · 登录于 ${esc(d.created_at)}</small></div><button class="btn btn-outline" data-device="${esc(d.id)}">撤销</button></div>`).join("")}<div class="modal-actions"><button class="btn" onclick="closeModal()">关闭</button></div>`,
    );
    document.querySelectorAll("[data-device]").forEach(
      (b) =>
        (b.onclick = async () => {
          await api("/api/devices/" + encodeURIComponent(b.dataset.device), {
            method: "DELETE",
          });
          if (devices.find((d) => d.id === b.dataset.device)?.current)
            location.href = appURL("/login");
          else openAccountCenter();
        }),
    );
  } catch (_) {}
}
async function openUsers() {
  const [users, policy] = await Promise.all([
    api("/api/admin/users"),
    api("/api/admin/policy"),
  ]);
  modal(
    `<h3>用户管理</h3><p class="feature-note">停用账号会立即撤销登录，保留数据以便备份。新用户拥有独立词库、设置和进度。</p><label><input type="checkbox" id="registration-open" ${policy.registration ? "checked" : ""}> 开放注册</label>${settingField("新用户默认平台 AI 次数 / 日", "default-ai-allowance", policy.default_allowance, "number", 'min="0" max="1000000"')}<button class="btn btn-outline" onclick="saveUserPolicy()">保存注册策略</button><h4>创建普通用户</h4><div class="feature-grid">${settingField("账号", "new-username", "")}${settingField("初始密码（至少 8 位）", "new-user-password", "", "password")}</div><button class="btn btn-primary" onclick="createUser()">创建账号</button><h4>现有用户</h4>${users.map((u) => `<div class="feature-row"><div><b>${esc(u.username)} ${u.active ? "" : "（已停用）"}</b><small>${u.role === "admin" ? "管理员" : "普通用户"} · ${u.allowance} 次/日</small><small>OpenWebUI：${esc(u.webui_email || "自动创建独立账号")}</small></div>${u.active ? `<button class="btn btn-sm" onclick="editUser('${u.id}')">编辑</button>${u.id !== "admin" ? `<button class="btn btn-sm" onclick="disableUser('${u.id}')">停用</button>` : ""}` : ""}</div>`).join("")}<div class="modal-actions"><button class="btn" onclick="openAccountCenter()">返回</button></div>`,
  );
}
async function saveUserPolicy() {
  await api("/api/admin/policy", {
    method: "PUT",
    body: JSON.stringify({
      registration: document.getElementById("registration-open").checked,
      default_allowance: Number(
        document.getElementById("default-ai-allowance").value,
      ),
    }),
  });
  toast("注册策略已保存", "success");
}
async function createUser() {
  await api("/api/admin/users", {
    method: "POST",
    body: JSON.stringify({
      username: document.getElementById("new-username").value,
      password: document.getElementById("new-user-password").value,
    }),
  });
  openUsers();
}
async function editUser(id) {
  const users = await api("/api/admin/users"),
    u = users.find((u) => u.id === id);
  modal(
    `<h3>编辑 ${esc(u.username)}</h3>${settingField("平台 AI 次数 / 日", "edit-allowance", u.allowance, "number", 'min="0" max="1000000"')}${settingField("重置密码（留空保留）", "edit-password", "", "password")}${settingField("绑定已有 OpenWebUI 账号邮箱（留空不修改）", "edit-webui-email", u.webui_email || "", "email")}<p class="feature-note">绑定前请核对账号归属。已有聊天记录保留在对应的 OpenWebUI 账号内。</p><div class="modal-actions"><button class="btn" onclick="openUsers()">返回</button><button class="btn btn-primary" id="save-user">保存</button></div>`,
  );
  document.getElementById("save-user").onclick = async () => {
    const data = {
        allowance: Number(document.getElementById("edit-allowance").value),
      },
      password = document.getElementById("edit-password").value,
      email = document.getElementById("edit-webui-email").value.trim();
    if (password) data.password = password;
    if (email) data.webui_email = email;
    await api("/api/admin/users/" + id, {
      method: "PUT",
      body: JSON.stringify(data),
    });
    openUsers();
  };
}
async function disableUser(id) {
  if (!confirm("停用此账号并撤销其全部登录？词库数据会保留。")) return;
  await api("/api/admin/users/" + id, { method: "DELETE" });
  openUsers();
}
openSettings = async function () {
  await previousOpenSettings();
  const pane = document.querySelector('[data-pane="ai"].settings-pane');
  if (pane) {
    const b = document.createElement("button");
    b.className = "btn btn-outline";
    b.textContent = "多模型与场景";
    b.onclick = openProviders;
    pane.append(b);
  }
  const integration = document.querySelector(
    '[data-pane="integration"].settings-pane',
  );
  if (integration && canLoadChat(appSettings)) {
    const status = document.createElement("p");
    status.className = "setting-help";
    status.textContent = "正在检查内置 MCP 与网络搜索…";
    integration.prepend(status);
    api("/api/chat/integration-status").then(d => {
      status.textContent = d.configured
        ? "已接通：个人词库 MCP、免密钥网络搜索。新对话默认启用，无需填写地址或 Token。"
        : "内置集成正在初始化，请稍后刷新。";
      if (d.embedding) status.textContent += " 本地中英文向量模型已接入（384 维）；原生记忆按账号共享，尚未按助手隔离。";
      if (d.automatic_memory) status.textContent += " 默认自动提炼跨对话记忆；每次回复后由当前模型检查长期信息。";
    }).catch(() => { status.textContent = "暂时无法检查内置集成，请稍后刷新。"; });
  }
};
async function openProviders() {
  providerDraft = await api("/api/ai/providers");
  renderProviders();
}
function renderProviders() {
  modal(
    `<h3>多模型与场景</h3><p class="feature-note">这里保存你的供应商。个人配置优先使用，未配置时使用管理员提供的服务。密钥留空保留已保存值。</p><div id="provider-list">${providerDraft.providers.map((p, i) => `<div class="provider-card" data-provider="${i}"><div class="feature-grid">${settingField("名称", "provider-name-" + i, p.name)}${settingField("API 地址", "provider-base-" + i, p.base)}${settingField("Key（留空保留）", "provider-key-" + i, "", "password", `placeholder="${p.has_key ? "已配置" : "未配置"}"`)}${settingField("模型（逗号分隔）", "provider-models-" + i, p.models.join(","))}</div><button class="btn btn-sm" data-remove="${i}">移除</button></div>`).join("")}</div><button class="btn btn-outline" id="add-provider">添加供应商</button><h4>场景分配</h4><p class="feature-note">添加或修改模型后先保存，再选择场景。默认表示使用单一 AI 配置或管理员服务。</p>${providerDraft.scenes.map((scene) => `<div class="form-group"><label>${{ general: "通用", quiz: "情境出题", vision: "图片识词", lookup: "查词增强", classification: "自动分类", report: "学习报告" }[scene]}</label><select data-scene="${scene}"><option value="">默认</option>${providerDraft.providers.flatMap((p) => p.models.map((m) => `<option value="${esc(JSON.stringify([p.id, m]))}" ${providerDraft.routes[scene]?.provider === p.id && providerDraft.routes[scene]?.model === m ? "selected" : ""}>${esc(p.name)} / ${esc(m)}</option>`)).join("")}</select></div>`).join("")}<div class="modal-actions"><button class="btn" onclick="openAccountCenter()">返回</button><button class="btn btn-primary" onclick="saveProviders()">保存</button></div>`,
  );
  document.getElementById("add-provider").onclick = () => {
    captureProviders();
    providerDraft.providers.push({
      id: crypto.randomUUID(),
      name: "新供应商",
      base: "https://api.openai.com/v1",
      models: ["gpt-4o-mini"],
    });
    renderProviders();
  };
  document.querySelectorAll("[data-remove]").forEach(
    (b) =>
      (b.onclick = () => {
        captureProviders();
        const [removed] = providerDraft.providers.splice(
          Number(b.dataset.remove),
          1,
        );
        for (const s of Object.keys(providerDraft.routes))
          if (providerDraft.routes[s].provider === removed.id)
            delete providerDraft.routes[s];
        renderProviders();
      }),
  );
}
function captureProviders() {
  providerDraft.providers.forEach((p, i) => {
    p.name = document.getElementById("provider-name-" + i).value;
    p.base = document.getElementById("provider-base-" + i).value;
    p.key = document.getElementById("provider-key-" + i).value || p.key || "";
    p.models = document
      .getElementById("provider-models-" + i)
      .value.split(/[,，]/)
      .map((s) => s.trim())
      .filter(Boolean);
  });
  providerDraft.routes = {};
  document.querySelectorAll("[data-scene]").forEach((s) => {
    if (s.value) {
      const [provider, model] = JSON.parse(s.value);
      providerDraft.routes[s.dataset.scene] = { provider, model };
    }
  });
}
async function saveProviders() {
  captureProviders();
  await api("/api/ai/providers", {
    method: "PUT",
    body: JSON.stringify(providerDraft),
  });
  toast("模型配置已保存", "success");
  openProviders();
}
async function openDictionaries() {
  const d = await api("/api/dictionaries/imported");
  modal(
    `<h3>个人字典</h3><p class="feature-note">导入 JSON 数组，每项含 word、chinese_meaning，可附音标、例句等词条字段；也支持「英文单词: 中文释义」映射。优先字典未命中时继续查询内置词典。</p><label class="btn btn-outline file-action">导入 JSON 字典<input type="file" class="visually-hidden" accept=".json" id="dictionary-file"></label><div class="form-group"><label>优先查词来源</label><select id="dictionary-selected"><option value="">内置词典</option>${d.dictionaries.map((x) => `<option value="${x.id}" ${d.selected === x.id ? "selected" : ""}>${esc(x.name)} · ${x.entries} 词</option>`).join("")}</select></div><div class="modal-actions"><button class="btn" onclick="openAccountCenter()">返回</button><button class="btn btn-primary" id="save-dictionary-choice">保存选择</button></div>`,
  );
  document.getElementById("dictionary-file").onchange = async (e) => {
    const form = new FormData();
    form.append("file", e.target.files[0]);
    const r = await fetch(appURL("/api/dictionaries/imported"), {
        method: "POST",
        body: form,
      }),
      d = await r.json();
    if (!r.ok) return toast(d.error, "error");
    openDictionaries();
  };
  document.getElementById("save-dictionary-choice").onclick = async () => {
    await api("/api/dictionaries/selected", {
      method: "PUT",
      body: JSON.stringify({
        id: document.getElementById("dictionary-selected").value || null,
      }),
    });
    toast("查词来源已保存", "success");
  };
}
function stopProgress() {
  clearInterval(progressTimer);
  progressTimer = null;
}
async function updateQuizProgress() {
  const sid = STATE.quiz.sessionId;
  if (!sid) return stopProgress();
  try {
    const p = await api("/api/quiz/sessions/" + sid, { _silent: true });
    if (sid !== STATE.quiz.sessionId) return;
    let box = document.getElementById("quiz-map");
    if (!box) {
      box = document.createElement("div");
      box.id = "quiz-map";
      document.getElementById("quiz-panel").after(box);
    }
    box.innerHTML = `<small>已准备 ${p.prepared}/${p.total} · 紫色：可作答 · 绿色：已作答 · 黄色：已跳过</small><div class="quiz-map">${p.progress.map((x, i) => `<span class="quiz-cell ${x.ready ? "ready" : ""} ${x.answered ? "answered" : ""} ${x.skipped ? "skipped" : ""} ${i === STATE.quiz.index ? "current" : ""}" title="第 ${i + 1} 题 · ${x.answered ? "已作答" : x.skipped ? "已跳过" : x.ready ? "已就绪" : "准备中"} · ${x.source === "ai" ? "AI" : "本地"}">${i + 1}</span>`).join("")}</div>`;
  } catch (_) {}
}
function watchQuiz() {
  stopProgress();
  updateQuizProgress();
  progressTimer = setInterval(updateQuizProgress, 2500);
  document.getElementById("resume-banner")?.remove();
}
startReview = async function (mode = "review") {
  await previousStartReview(mode);
  if (STATE.quiz.sessionId) watchQuiz();
};
loadQuizQuestion = async function () {
  await previousLoadQuestion();
  const q = STATE.quiz,
    prior = q.serverResults?.[String(q.index)];
  if (prior && q.question) {
    q.results.length = q.index;
    previousFeedback(
      prior.correct,
      prior.feedback,
      q.question,
      q.words[q.index].id,
      prior,
    );
    document
      .querySelectorAll("#quiz-dynamic .choice-btn,#quiz-dynamic input")
      .forEach((b) => (b.disabled = true));
    document.querySelectorAll("#quiz-dynamic button").forEach((b) => {
      if (b.textContent !== "▶ 下一题") b.disabled = true;
    });
  }
  updateQuizProgress();
};
function saveCursor(keepalive = false) {
  const q = STATE.quiz;
  if (!q.sessionId) return;
  fetch(appURL("/api/quiz/sessions/" + q.sessionId + "/cursor"), {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      index: q.index,
      skipped: q.results
        .map((r, i) => (r?.skipped ? i : -1))
        .filter((i) => i >= 0),
    }),
    keepalive,
  }).catch(() => {});
}
nextQuizQuestion = function () {
  previousNextQuestion();
  saveCursor();
};
showQuizFeedback = function (...args) {
  previousFeedback(...args);
  saveCursor();
  updateQuizProgress();
};
finishQuiz = async function () {
  stopProgress();
  document.getElementById("quiz-map")?.remove();
  document.getElementById("resume-banner")?.remove();
  await previousFinishQuiz();
  activeSession = null;
};
async function resumeQuiz() {
  if (!activeSession) return;
  const p = await api("/api/quiz/sessions/" + activeSession);
  STATE.quiz = {
    sessionId: activeSession,
    words: p.words,
    index: p.index,
    question: null,
    results: [],
    serverResults: p.results,
    trainingMode: p.training,
    questionSource: p.question_source,
    deletingSession: false,
  };
  for (let i = 0; i < p.index; i++)
    STATE.quiz.results.push({
      ...p.results[String(i)],
      skipped: !p.results[String(i)],
      wordId: p.words[i].id,
    });
  activateTab("study");
  document.getElementById("study-status").classList.add("hidden");
  watchQuiz();
  await loadQuizQuestion();
}
async function offerResume() {
  const r = await api("/api/quiz/active", { _silent: true });
  activeSession = r.session_id;
  if (!activeSession) return;
  const p = await api("/api/quiz/sessions/" + activeSession, { _silent: true });
  if (!p.total) return;
  const box = document.createElement("div");
  box.className = "resume-banner";
  box.id = "resume-banner";
  box.innerHTML = `<span>上次学习：已作答 ${Object.keys(p.results).length}/${p.total}，已准备 ${p.prepared}/${p.total}</span><button class="btn btn-primary" onclick="resumeQuiz()">继续上次学习</button>`;
  document.getElementById("study-status").prepend(box);
}
window.addEventListener("pagehide", () => saveCursor(true));
document.addEventListener("DOMContentLoaded", async () => {
  try {
    const s = await api("/api/auth/status");
    signedInUser = s.user;
    for (const part of ["header", "nav"])
      if (
        localStorage.getItem(
          "anamnesis-layout:" + signedInUser.id + ":" + part,
        ) === "true"
      )
        setChromeCollapsed(part, true);
    await offerResume();
    if ("serviceWorker" in navigator)
      navigator.serviceWorker
        .register(appURL("/service-worker.js"), { scope: appURL("/") })
        .catch(() => {});
  } catch (_) {}
});
