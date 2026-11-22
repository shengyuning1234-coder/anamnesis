/* ============================================================
   Anamnesis / 忆溯 — Web 前端逻辑
   ============================================================ */

// ======= 全局状态 =======
const STATE = {
  words: [],
  selectedWordId: null,
  quiz: { sessionId: null, words: [], index: 0, question: null, results: [], preparationPolling: null, deletingSession: false },
  mobileDetailOpen: false,
  sort: "time_desc",
};

// ======= 移动端检测 =======
function isMobile() {
  return window.innerWidth <= 768 || ('ontouchstart' in window) && window.innerWidth <= 1024;
}
window.addEventListener('resize', () => {
  // 窗口变大后关闭移动端覆盖层
  if (!isMobile() && STATE.mobileDetailOpen) {
    closeMobileDetail();
  }
});

function closeMobileDetail() {
  const wordPane = document.querySelector('.word-detail-pane');
  const reportPane = document.querySelector('.report-detail-pane');
  [wordPane, reportPane].forEach(pane => {
    if (pane) pane.classList.remove('mobile-overlay');
  });
  const wasOpen = STATE.mobileDetailOpen;
  STATE.mobileDetailOpen = false;
  // 保留 selectedWordId 以维持列表高亮，仅在其他 Tab/搜索时清除
  if (wasOpen) {
    const detail = document.getElementById('word-detail');
    if (detail && detail.innerHTML.includes('mobile-back-btn')) {
      detail.innerHTML = '<p class="placeholder">👆 点击单词查看详情</p>';
    }
  }
}

// ======= 初始化 =======
document.addEventListener("DOMContentLoaded", async () => {
  initTabs();
  await initOfflineReadCache();
  initBackground(window.__INITIAL_APPEARANCE__);
  loadTags();
  loadStats();
  loadWords();
  initReviewOperationQueue();
  if (!navigator.onLine) showOfflineBanner();
});

// ======= 背景系统 =======
function initBackground(initialAppearance) {
  const appearance = initialAppearance || {};
  if (appearance.background_type === "custom" && appearance.background_image_path) {
    applyBackground(appearance);
  }
}

function applyBackground(app) {
  const bgImg = document.getElementById("app-bg-image");
  if (!bgImg) return;
  if (app.background_type === "custom" && app.background_image_path) {
    bgImg.src = appURL(app.background_image_path);
    bgImg.style.display = "";
    updateBgStyle(app.background_blur || 15, app.background_brightness || 60);
    // 提取主色调
    extractBgColors(app.background_image_path);
  } else {
    bgImg.style.display = "none";
    bgImg.style.filter = "none";
    resetAccentColors();
  }
  // 卡片透明度
  applyCardOpacity(app.card_opacity != null ? app.card_opacity : 100);
  if (app.background_type !== "custom") {
    try { localStorage.removeItem("anamnesis-background-theme"); } catch (_) { /* 忽略存储不可用 */ }
  }
}

function applyCardOpacity(opacity) {
  const root = document.documentElement;
  const alpha = opacity / 100;
  root.style.setProperty('--card-opacity', alpha.toFixed(2));
}

function updateCursorColor(rgb = [91, 74, 224]) {
  const [r, g, b] = rgb;
  const dark = [Math.round(r * .68), Math.round(g * .68), Math.round(b * .68)];
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" viewBox="0 0 28 28"><defs><linearGradient id="g" x1="5" y1="3" x2="21" y2="25" gradientUnits="userSpaceOnUse"><stop stop-color="rgb(${Math.min(255, r + 35)},${Math.min(255, g + 35)},${Math.min(255, b + 35)})"/><stop offset="1" stop-color="rgb(${dark.join(',')})"/></linearGradient><filter id="s" x="0" y="0" width="28" height="28"><feDropShadow dx="0" dy="1" stdDeviation=".8" flood-color="rgb(${dark.join(',')})" flood-opacity=".35"/></filter></defs><path d="M5.1 3.2 22.2 14l-8.1 2.5-3.7 8.3Z" fill="url(#g)" stroke="#fff" stroke-width="1.45" stroke-linejoin="round" filter="url(#s)"/><path d="m14.1 16.5 3.7 6" stroke="rgba(255,255,255,.7)" stroke-width="1.5" stroke-linecap="round"/></svg>`;
  const themeColor = '#' + rgb.map(value => value.toString(16).padStart(2, '0')).join('');
  document.querySelector('meta[name="theme-color"]')?.setAttribute('content', themeColor);
  document.documentElement.style.setProperty('--cursor-ui', `url("data:image/svg+xml,${encodeURIComponent(svg)}") 5 3, auto`);
}

let backgroundColorRequest = 0;
// Sample locally so theme extraction works without a CDN or third-party script.
function extractImagePalette(img) {
  const canvas = document.createElement('canvas');
  canvas.width = canvas.height = 64;
  const ctx = canvas.getContext('2d', {willReadFrequently:true});
  ctx.drawImage(img, 0, 0, 64, 64);
  const pixels = ctx.getImageData(0, 0, 64, 64).data, buckets = new Map();
  for (let i = 0; i < pixels.length; i += 4) {
    if (pixels[i+3] < 128) continue;
    const rgb = [pixels[i], pixels[i+1], pixels[i+2]];
    const key = rgb.map(v => v >> 5).join(',');
    const b = buckets.get(key) || {count:0, sum:[0,0,0]};
    b.count++; rgb.forEach((v,j) => b.sum[j] += v); buckets.set(key,b);
  }
  const colors = [...buckets.values()].sort((a,b) => b.count-a.count)
    .map(b => b.sum.map(v => Math.round(v/b.count)));
  const palette = [];
  for (const rgb of colors) {
    if (palette.every(c => c.reduce((n,v,j) => n+(v-rgb[j])**2,0) > 1600)) palette.push(rgb);
    if (palette.length === 6) break;
  }
  if (!palette.length) return null;
  if (palette.length === 1) palette.push([...palette[0]]);
  return palette;
}
function extractBgColors(imagePath) {
  const request = ++backgroundColorRequest;
  const img = new Image();
  // 仅跨域 URL 设置 crossOrigin；同源/相对路径不设置，避免 Canvas 安全沙箱报错
  if (/^https?:\/\//.test(imagePath)) {
    const pageOrigin = location.origin;
    if (!imagePath.startsWith(pageOrigin)) {
      img.crossOrigin = "anonymous";
    }
  }
  img.onload = () => {
    if (request !== backgroundColorRequest) return;
    try {
      const palette = extractImagePalette(img);
      if (!palette || palette.length < 2) return;

      // Keep white button labels readable even for snow or very bright photos.
      const readable = rgb => {
        const color = [...rgb];
        const luminance = () => color.map(v => {v/=255; return v<=.04045?v/12.92:((v+.055)/1.055)**2.4;})
          .reduce((n,v,i) => n+v*[.2126,.7152,.0722][i],0);
        while (luminance() > .183) color.forEach((v,i) => color[i] = Math.floor(v*.92));
        return color;
      };
      const primary = readable(palette[0]), secondary = readable(palette[1]);
      const [pr, pg, pb] = primary;
      const [sr, sg, sb] = secondary;
      const accent = palette.length > 2 ? palette[2] : palette[1];

      const darken = (r, g, b, ratio) => [Math.round(r*(1-ratio)), Math.round(g*(1-ratio)), Math.round(b*(1-ratio))];
      const lighten = (r, g, b, ratio) => [r+Math.round((255-r)*ratio), g+Math.round((255-g)*ratio), b+Math.round((255-b)*ratio)];

      // 字体主色：从提取色派生，确保在白色卡片上可读
      const textPrimary = (() => {
        const lum = 0.299 * pr + 0.587 * pg + 0.114 * pb;
        if (lum > 170) return darken(pr, pg, pb, 0.35);  // 太浅→加深
        if (lum < 50)  return lighten(pr, pg, pb, 0.5);  // 太暗→提亮
        return [pr, pg, pb];
      })();

      const primaryDark = darken(pr, pg, pb, 0.25);
      const primaryLight = lighten(pr, pg, pb, 0.85);
      const accentDark = darken(sr, sg, sb, 0.25);
      const accentLight = lighten(sr, sg, sb, 0.88);
      // 互补色用于 danger
      const [cr, cg, cb] = accent;
      const cHSL = rgbToHsl(cr, cg, cb);
      const compRGB = hslToRgb((cHSL[0] + 150) % 360, Math.min(100, cHSL[1] + 10), Math.min(100, cHSL[2] + 5));
      const dangerDark = darken(...compRGB, 0.2);
      const dangerLight = lighten(...compRGB, 0.88);


      const root = document.documentElement;
      const setRgb = (k, rgb) => root.style.setProperty(k, rgb.join(','));
      updateCursorColor(primary);
      setRgb('--theme-p', primary);
      setRgb('--theme-s', secondary);
      setRgb('--theme-p-text', textPrimary);
      setRgb('--theme-p-dark', primaryDark);
      setRgb('--theme-p-light', primaryLight);
      setRgb('--theme-s-dark', accentDark);
      setRgb('--theme-s-light', accentLight);
      setRgb('--theme-danger', compRGB);
      setRgb('--theme-danger-dark', dangerDark);
      setRgb('--theme-danger-light', dangerLight);
      const [tpr, tpg, tpb] = textPrimary;
      root.style.setProperty('--tag-bg', `rgba(${tpr},${tpg},${tpb}, 0.15)`);
      root.style.setProperty('--bg-mode', 'image');

      const top = palette.length > 3 ? palette[3] : palette[0];
      const bot = palette.length > 4 ? palette[4] : palette[1];
      root.style.setProperty('--bg-from-img', `rgb(${top.join(',')})`);
      root.style.setProperty('--bg-mid', `rgb(${palette[0].join(',')})`);
      root.style.setProperty('--bg-bot', `rgb(${bot.join(',')})`);
      root.dataset.backgroundTheme = "ready";
      cacheBackgroundTheme(imagePath);
    } catch (e) {
      console.log('[Background palette] extraction failed:', e);
    }
  };
  img.src = appURL(imagePath);
}

function cacheBackgroundTheme(imagePath) {
  const root = document.documentElement;
  const propertyNames = [
    '--theme-p', '--theme-s', '--theme-p-text', '--theme-p-dark', '--theme-p-light',
    '--theme-s-dark', '--theme-s-light', '--theme-danger', '--theme-danger-dark',
    '--theme-danger-light', '--tag-bg',
    '--bg-mode', '--bg-from-img', '--bg-mid', '--bg-bot', '--card-opacity',
  ];
  const properties = Object.fromEntries(propertyNames.map(name => [name, root.style.getPropertyValue(name)]));
  try {
    localStorage.setItem("anamnesis-background-theme", JSON.stringify({ imagePath, properties }));
  } catch (_) { /* 存储不可用时仅本次页面应用主题 */ }
}

// HSL 转换工具
function rgbToHsl(r, g, b) {
  r /= 255; g /= 255; b /= 255;
  const max = Math.max(r, g, b), min = Math.min(r, g, b);
  let h = 0, s = 0, l = (max + min) / 2;
  if (max !== min) {
    const d = max - min;
    s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
    switch (max) {
      case r: h = ((g - b) / d + (g < b ? 6 : 0)) / 6; break;
      case g: h = ((b - r) / d + 2) / 6; break;
      case b: h = ((r - g) / d + 4) / 6; break;
    }
  }
  return [Math.round(h * 360), Math.round(s * 100), Math.round(l * 100)];
}

function hslToRgb(h, s, l) {
  h /= 360; s /= 100; l /= 100;
  const hue2rgb = (p, q, t) => {
    if (t < 0) t += 1; if (t > 1) t -= 1;
    if (t < 1/6) return p + (q - p) * 6 * t;
    if (t < 1/2) return q;
    if (t < 2/3) return p + (q - p) * (2/3 - t) * 6;
    return p;
  };
  const q = l < 0.5 ? l * (1 + s) : l + s - l * s;
  const p = 2 * l - q;
  return [
    Math.round(hue2rgb(p, q, h + 1/3) * 255),
    Math.round(hue2rgb(p, q, h) * 255),
    Math.round(hue2rgb(p, q, h - 1/3) * 255),
  ];
}

function resetAccentColors() {
  ++backgroundColorRequest;
  const root = document.documentElement;
  updateCursorColor();
  root.style.setProperty('--bg-mode', 'default');
  delete root.dataset.backgroundTheme;
  try { localStorage.removeItem('anamnesis-background-theme'); } catch (_) {}
  ['--theme-p','--theme-s','--theme-p-text','--theme-p-dark','--theme-p-light','--theme-s-dark',
   '--theme-s-light','--theme-danger','--theme-danger-dark','--theme-danger-light',
   '--tag-bg', '--header-text','--bg-from-img','--bg-mid','--bg-bot'].forEach(v => {
    root.style.removeProperty(v);
  });
}

function updateBgStyle(blur, brightness) {
  const bgImg = document.getElementById("app-bg-image");
  if (bgImg) bgImg.style.filter = `blur(${blur}px) brightness(${brightness}%) contrast(95%)`;
}

function resetBackground() {
  if (!ensureOnlineForWrite()) return;
  document.getElementById("app-bg-image").style.display = "none";
  saveAppearance({ background_type: "default", background_image_path: "" });
}

async function saveAppearance(app) {
  try {
    await api("/api/settings", { method: "PUT", body: JSON.stringify({ appearance: app }) });
  } catch (e) { console.error("[saveAppearance] 失败:", e); /* ignore */ }
}

async function uploadBackground(input) {
  const file = input.files[0];
  if (!file) return;
  if (file.size > 5 * 1024 * 1024) { toast("图片不能超过 5MB", "error"); input.value = ""; return; }
  const formData = new FormData();
  formData.append("file", file);
  try {
    const resp = await fetch(appURL("/api/settings/background/upload"), { method: "POST", body: formData });
    const data = await resp.json();
    if (data.ok) {
      applyBackground({ background_type: "custom", background_image_path: data.path, background_blur: 15, background_brightness: 60 });
      updateBgStyle(15, 60);
      const blurEl = document.getElementById("set-bg-blur");
      const brightEl = document.getElementById("set-bg-brightness");
      if (blurEl) blurEl.value = 15;
      if (brightEl) brightEl.value = 60;
      toast("背景已更新", "success");
    } else {
      toast(data.error || "上传失败", "error");
    }
  } catch (e) { toast("上传失败", "error"); }
  input.value = "";
}

// ======= Tab 切换 =======
function initTabs() {
  document.querySelectorAll(".tab-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
      document.querySelectorAll(".tab-content").forEach(c => c.classList.remove("active"));
      btn.classList.add("active");
      document.getElementById(`tab-${btn.dataset.tab}`).classList.add("active");
      if (btn.dataset.tab === "words") loadWords();
      if (btn.dataset.tab === "study") loadStats();
      if (btn.dataset.tab === "reports") loadReports();
    });
  });
}

// ======= Toast =======
function toast(msg, type = "info") {
  const el = document.getElementById("toast");
  el.textContent = msg; el.className = `toast ${type}`;
  el.classList.remove("hidden");
  setTimeout(() => el.classList.add("hidden"), 2800);
}

// ======= API 封装 =======
async function api(url, opts = {}) {
  const silent = opts._silent; delete opts._silent;
  try {
    const res = await fetch(appURL(url), { headers: { "Content-Type": "application/json" }, ...opts });
    if (!res.ok) {
      if (res.status === 401) {
        const body = await res.json().catch(() => ({}));
        if (body.need_login) { window.location.href = appURL("/login"); throw new Error(""); }
      }
      const e = await res.json().catch(() => ({}));
      const error = new Error(e.error || `HTTP ${res.status}`); error.status = res.status; throw error;
    }
    const data = await res.json();
    if (url === "/api/auth/logout" && data.ok) {
      const owner = _offlineCacheOwner;
      _offlineCacheOwner = null;
      _offlineReadOnly = false;
      STATE.words = [];
      STATE.selectedWordId = null;
      clearOfflineReadCache(owner).catch(() => {}); // 复习队列保留，由其服务端同步语义管理
    }
    return data;
  } catch (err) {
    if (err.message && !silent) toast(err.message, "error");
    throw err;
  }
}

// ============================================================
//  离线只读词表缓存（与复习操作队列完全独立）
// ============================================================

const OFFLINE_READ_DB = "anamnesis-offline-read-v1";
const OFFLINE_LIST_STORE = "list-snapshots";
const OFFLINE_DETAIL_STORE = "detail-snapshots";
const OFFLINE_META_STORE = "meta";
let _offlineReadDb = null;
let _offlineReadUnavailable = false;
let _offlineCacheOwner = null;
let _offlineReadOnly = false;

function isNetworkFailure(error) { return navigator.onLine === false || error instanceof TypeError; }
function offlineTime(value) { return value ? new Date(value).toLocaleString() : "未知时间"; }
function offlineListKey(sort) { return `${_offlineCacheOwner}:${sort}`; }
function offlineDetailKey(id) { return `${_offlineCacheOwner}:${id}`; }

function openOfflineReadDb() {
  if (_offlineReadUnavailable || !("indexedDB" in window)) return Promise.reject(new Error("此浏览器无法使用离线词表缓存"));
  if (_offlineReadDb) return Promise.resolve(_offlineReadDb);
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(OFFLINE_READ_DB, 1);
    request.onupgradeneeded = () => {
      const db = request.result;
      db.createObjectStore(OFFLINE_LIST_STORE, { keyPath: "key" });
      db.createObjectStore(OFFLINE_DETAIL_STORE, { keyPath: "key" });
      db.createObjectStore(OFFLINE_META_STORE, { keyPath: "key" });
    };
    request.onsuccess = () => { _offlineReadDb = request.result; resolve(_offlineReadDb); };
    request.onerror = () => { _offlineReadUnavailable = true; reject(new Error("无法打开离线词表缓存")); };
  });
}

async function offlineStorePut(storeName, value) {
  const db = await openOfflineReadDb();
  return new Promise((resolve, reject) => {
    const request = db.transaction(storeName, "readwrite").objectStore(storeName).put(value);
    request.onsuccess = () => resolve(); request.onerror = () => reject(request.error);
  });
}
async function offlineStoreGet(storeName, key) {
  const db = await openOfflineReadDb();
  return new Promise((resolve, reject) => {
    const request = db.transaction(storeName).objectStore(storeName).get(key);
    request.onsuccess = () => resolve(request.result || null); request.onerror = () => reject(request.error);
  });
}
async function cacheWordList(words) {
  if (!_offlineCacheOwner) return;
  const snapshot = { key: offlineListKey(STATE.sort), owner: _offlineCacheOwner, sort: STATE.sort, words, fetchedAt: Date.now() };
  await offlineStorePut(OFFLINE_LIST_STORE, snapshot);
  await offlineStorePut(OFFLINE_META_STORE, { key: `${_offlineCacheOwner}:latest-list`, fetchedAt: snapshot.fetchedAt });
}
async function cacheWordDetail(word) {
  if (!_offlineCacheOwner || !word?.id) return;
  await offlineStorePut(OFFLINE_DETAIL_STORE, { key: offlineDetailKey(word.id), owner: _offlineCacheOwner, wordId: word.id, word, fetchedAt: Date.now() });
}
async function getCachedWordList() {
  const exact = await offlineStoreGet(OFFLINE_LIST_STORE, offlineListKey(STATE.sort));
  if (exact || !_offlineCacheOwner) return exact;
  const db = await openOfflineReadDb();
  return new Promise((resolve, reject) => {
    const request = db.transaction(OFFLINE_LIST_STORE).objectStore(OFFLINE_LIST_STORE).openCursor();
    request.onsuccess = () => { const cursor = request.result; if (!cursor) return resolve(null); if (cursor.value.owner === _offlineCacheOwner) return resolve(cursor.value); cursor.continue(); };
    request.onerror = () => reject(request.error);
  });
}
async function getCachedWordDetail(id) { return offlineStoreGet(OFFLINE_DETAIL_STORE, offlineDetailKey(id)); }
async function clearOfflineReadCache(owner) {
  if (!owner || _offlineReadUnavailable) return;
  const db = await openOfflineReadDb();
  await Promise.all([OFFLINE_LIST_STORE, OFFLINE_DETAIL_STORE, OFFLINE_META_STORE].map(storeName => new Promise((resolve, reject) => {
    const store = db.transaction(storeName, "readwrite").objectStore(storeName);
    const request = store.openCursor();
    request.onsuccess = () => { const cursor = request.result; if (!cursor) return resolve(); if (String(cursor.key).startsWith(`${owner}:`)) cursor.delete(); cursor.continue(); };
    request.onerror = () => reject(request.error);
  })));
}
async function initOfflineReadCache() {
  try {
    const status = await api("/api/auth/status", { _silent: true });
    _offlineCacheOwner = status.authenticated && typeof status.offline_cache_owner === "string" ? status.offline_cache_owner : null;
  } catch (error) {
    _offlineCacheOwner = null; // 无法确认身份时绝不读取缓存
  }
}
function localMatchesWord(word, keyword) {
  const needle = keyword.toLowerCase();
  return [word.word, word.chinese_meaning, word.phonetic, word.part_of_speech, word.example_sentence, word.example_translation, word.notes, ...(word.tags || [])].join(" ").toLowerCase().includes(needle);
}
function sortCachedWords(words) {
  return [...words].sort((a, b) => STATE.sort === "word_asc" ? String(a.word).localeCompare(String(b.word)) : STATE.sort === "word_desc" ? String(b.word).localeCompare(String(a.word)) : STATE.sort === "time_asc" ? (a.id - b.id) : (b.id - a.id));
}
function applyOfflineWordFilters(words) {
  const keyword = document.getElementById("word-search")?.value.trim() || "";
  const tag = document.getElementById("tag-filter")?.value || "";
  return sortCachedWords(words.filter(word => (!keyword || localMatchesWord(word, keyword)) && (!tag || (word.tags || []).includes(tag))));
}
function ensureOnlineForWrite() {
  if (navigator.onLine) return true;
  toast("离线只读：此操作需要联网", "error");
  return false;
}

// ============================================================
//  IndexedDB 离线复习操作队列
// ============================================================

const REVIEW_QUEUE_DB = "anamnesis-review-operations-v1";
const REVIEW_QUEUE_STORE = "operations-v1";
const REVIEW_QUEUE_MAX_OPERATIONS = 500;
const REVIEW_QUEUE_MAX_ATTEMPTS = 8;
const REVIEW_QUEUE_BATCH_SIZE = 50;
const REVIEW_QUEUE_BACKOFF_MAX_MS = 30 * 60 * 1000;
let _reviewQueueDb = null;
let _reviewQueueUnavailable = false;
let _reviewDrainRunning = false;

function reviewQueueBackoffMs(attempts) {
  return Math.min(REVIEW_QUEUE_BACKOFF_MAX_MS, 1000 * (2 ** Math.min(Math.max(attempts - 1, 0), 10)));
}

function reviewQueueDue(operation, now = Date.now()) {
  return operation.status !== "action_required" && (!operation.next_attempt_at || operation.next_attempt_at <= now);
}

function reviewQueueMarkFailure(operation, error, requiresAction = false) {
  operation.attempts = (operation.attempts || 0) + 1;
  operation.last_error = error || "同步失败";
  operation.updated_at = Date.now();
  if (requiresAction || operation.attempts >= REVIEW_QUEUE_MAX_ATTEMPTS) {
    operation.status = "action_required";
    operation.next_attempt_at = 0;
  } else {
    operation.status = "pending";
    operation.next_attempt_at = Date.now() + reviewQueueBackoffMs(operation.attempts);
  }
  return operation;
}

function openReviewQueueDb() {
  if (_reviewQueueUnavailable || !("indexedDB" in window)) {
    _reviewQueueUnavailable = true;
    return Promise.reject(new Error("此浏览器无法使用离线复习保存"));
  }
  if (_reviewQueueDb) return Promise.resolve(_reviewQueueDb);
  return new Promise((resolve, reject) => {
    if (!_offlineCacheOwner) return reject(new Error('请先联网确认当前账号，再保存离线复习'));
    const request = indexedDB.open(REVIEW_QUEUE_DB + ':' + _offlineCacheOwner, 1);
    request.onupgradeneeded = () => {
      const db = request.result;
      const store = db.createObjectStore(REVIEW_QUEUE_STORE, { keyPath: "operation_id" });
      store.createIndex("created_at", "created_at");
    };
    request.onsuccess = () => { _reviewQueueDb = request.result; resolve(_reviewQueueDb); };
    request.onerror = () => {
      _reviewQueueUnavailable = true;
      reject(new Error("无法打开离线复习保存"));
    };
  });
}

async function reviewQueueCount() {
  const db = await openReviewQueueDb();
  return new Promise((resolve, reject) => {
    const request = db.transaction(REVIEW_QUEUE_STORE).objectStore(REVIEW_QUEUE_STORE).count();
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(new Error("无法读取离线复习记录"));
  });
}

async function reviewQueueAdd(operation) {
  if (await reviewQueueCount() >= REVIEW_QUEUE_MAX_OPERATIONS) {
    throw new Error(`离线复习队列已满（最多 ${REVIEW_QUEUE_MAX_OPERATIONS} 条），请联网同步后再继续`);
  }
  operation.status = "pending";
  operation.next_attempt_at = 0;
  operation.updated_at = Date.now();
  const db = await openReviewQueueDb();
  return new Promise((resolve, reject) => {
    const request = db.transaction(REVIEW_QUEUE_STORE, "readwrite").objectStore(REVIEW_QUEUE_STORE).add(operation);
    request.onsuccess = () => resolve();
    request.onerror = () => reject(new Error("离线复习保存失败"));
  });
}

async function reviewQueueList(limit = 50) {
  const db = await openReviewQueueDb();
  return new Promise((resolve, reject) => {
    const items = [];
    const request = db.transaction(REVIEW_QUEUE_STORE).objectStore(REVIEW_QUEUE_STORE).index("created_at").openCursor();
    request.onsuccess = () => {
      const cursor = request.result;
      if (!cursor || items.length >= limit) return resolve(items);
      items.push(cursor.value);
      cursor.continue();
    };
    request.onerror = () => reject(new Error("无法读取离线复习记录"));
  });
}

async function reviewQueueDelete(operationId) {
  const db = await openReviewQueueDb();
  return new Promise((resolve, reject) => {
    const request = db.transaction(REVIEW_QUEUE_STORE, "readwrite").objectStore(REVIEW_QUEUE_STORE).delete(operationId);
    request.onsuccess = () => resolve();
    request.onerror = () => reject(new Error("无法更新离线复习记录"));
  });
}

async function reviewQueueUpdate(operation) {
  const db = await openReviewQueueDb();
  return new Promise((resolve, reject) => {
    const request = db.transaction(REVIEW_QUEUE_STORE, "readwrite").objectStore(REVIEW_QUEUE_STORE).put(operation);
    request.onsuccess = () => resolve();
    request.onerror = () => reject(new Error("无法更新离线复习记录"));
  });
}

function createOperationId() {
  if (window.crypto && typeof window.crypto.randomUUID === "function") return window.crypto.randomUUID();
  return "op-" + Date.now().toString(36) + "-" + Math.random().toString(36).slice(2) + Math.random().toString(36).slice(2);
}

function reviewOperationTime() {
  const date = new Date();
  const pad = n => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
}

async function queueReviewOperation(q, wordId, correct) {
  if (!Number.isInteger(wordId) || !q?.mode) throw new Error("此题无法离线保存");
  const mode = q.mode === "synonym_antonym" ? "mixed"
    : (q.mode === "choice_cn2en" || q.mode === "recall_cn2en" ? "cn2en" : "en2cn");
  const operation = {
    operation_id: createOperationId(), word_id: wordId,
    meaning_id: Number.isInteger(q.meaning_id) ? q.meaning_id : null,
    rating: correct ? 5 : (q.type === "choice" ? 1 : 2), mode,
    reviewed_at: reviewOperationTime(), created_at: Date.now(), attempts: 0, last_error: "",
  };
  await reviewQueueAdd(operation);
  return operation;
}

async function drainReviewOperations() {
  if (_reviewDrainRunning || !navigator.onLine || _reviewQueueUnavailable) return;
  _reviewDrainRunning = true;
  try {
    const allOperations = await reviewQueueList(REVIEW_QUEUE_MAX_OPERATIONS);
    const operations = allOperations.filter(reviewQueueDue).slice(0, REVIEW_QUEUE_BATCH_SIZE);
    if (!operations.length) return;
    try {
      const response = await fetch(appURL("/api/review/sync"), {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ operations: operations.map(({ operation_id, word_id, meaning_id, rating, mode, reviewed_at }) => ({ operation_id, word_id, meaning_id, rating, mode, reviewed_at })) }),
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      if (!Array.isArray(data.results)) throw new Error("同步响应无效");
      const results = new Map(data.results.map(result => [result.operation_id, result]));
      let synced = 0;
      let actionRequired = 0;
      for (const operation of operations) {
        const result = results.get(operation.operation_id);
        if (result?.status === "applied" || result?.status === "duplicate") {
          await reviewQueueDelete(operation.operation_id);
          synced++;
        } else {
          const terminal = result?.status === "conflict" || result?.status === "rejected";
          reviewQueueMarkFailure(operation, result?.error || (result?.status ? `同步${result.status}` : "服务器未返回此操作结果"), terminal);
          if (operation.status === "action_required") actionRequired++;
          await reviewQueueUpdate(operation);
        }
      }
      if (synced) { toast(`已同步 ${synced} 条离线复习记录`, "success"); loadStats(); }
      if (actionRequired) toast(`${actionRequired} 条离线复习记录需要手动处理`, "error");
    } catch (error) {
      for (const operation of operations) {
        reviewQueueMarkFailure(operation, error.message || "同步失败");
        await reviewQueueUpdate(operation);
      }
    }
  } catch (error) {
    _reviewQueueUnavailable = true;
    toast(error.message || "离线复习保存不可用", "error");
  } finally {
    _reviewDrainRunning = false;
  }
}

async function showReviewQueueStatus() {
  if (_reviewQueueUnavailable) return;
  const operations = await reviewQueueList(REVIEW_QUEUE_MAX_OPERATIONS);
  const actionRequired = operations.filter(operation => operation.status === "action_required").length;
  if (actionRequired) toast(`${actionRequired} 条离线复习记录需要联网后手动处理`, "error");
}

function initReviewOperationQueue() {
  openReviewQueueDb().then(async () => {
    await showReviewQueueStatus();
    if (navigator.onLine) drainReviewOperations();
  }).catch(error => toast(error.message || "离线复习保存不可用", "error"));
}

function isNetworkJudgeFailure(error) {
  return navigator.onLine === false || error instanceof TypeError;
}

function localQuizResult(q, answer) {
  const value = String(answer || "").trim();
  const expected = String(q.answer || "").trim();
  if (!value) return { correct: false, supported: true };
  if (q.type === "choice") return { correct: value === expected, supported: true };
  if (q.type === "recall") return { correct: /^(remember|记得|yes|true|1)$/i.test(value), supported: true };
  if (q.type === "spell") {
    const lower = value.toLowerCase();
    return { correct: lower === expected.toLowerCase() || (q.accept_variants || []).some(v => lower === String(v).toLowerCase()), supported: true };
  }
  if (q.type === "contextual_recall" || q.type === "fill_blank") {
    return { correct: value.toLowerCase().split(/\s+/).join(" ") === expected.toLowerCase().split(/\s+/).join(" "), supported: true };
  }
  if (q.type === "synonym_antonym") {
    const split = text => String(text).split(/[,，;；\n]/).map(item => item.trim().toLowerCase()).filter(Boolean);
    return { correct: split(value).some(item => split(expected).includes(item)), supported: true };
  }
  return { correct: false, supported: false };
}

async function saveJudgeFallback(q, wordId, correct) {
  try {
    await queueReviewOperation(q, wordId, correct);
    toast("已离线保存，待同步", "info");
    drainReviewOperations();
    return true;
  } catch (error) {
    toast(error.message || "无法离线保存本次复习", "error");
    return false;
  }
}

// ============================================================
//  单词本
// ============================================================

async function loadStats() {
  try {
    const data = await api("/api/stats/today", { _silent: true });
    document.getElementById("stat-quota").textContent = data.daily_quota || 20;
    document.getElementById("stat-new").textContent = data.today?.new_words_learned || 0;
    document.getElementById("stat-reviewed").textContent = data.today?.words_reviewed || 0;
    document.getElementById("stat-due").textContent = data.due_count || 0;
    document.getElementById("quota-input").value = data.daily_quota || 20;
    document.getElementById("header-stats").textContent =
      `${data.overview?.total_words || 0}词 | 均熟${data.overview?.avg_proficiency || 0}`;
  } catch (e) { console.error("[loadStats] 加载失败:", e); /* 静默——stats非关键 */ }
}

async function loadCachedWords() {
  if (!_offlineCacheOwner || _offlineReadUnavailable) throw new Error("无可用离线词表缓存");
  const snapshot = await getCachedWordList();
  if (!snapshot) throw new Error("无可用离线词表缓存");
  _offlineReadOnly = true;
  STATE.words = applyOfflineWordFilters(snapshot.words || []);
  showOfflineBanner(snapshot.fetchedAt);
  return snapshot;
}
async function loadWords() {
  const keyword = document.getElementById("word-search")?.value.trim() || "";
  const tag = document.getElementById("tag-filter")?.value || "";
  let url = `/api/words?sort=${STATE.sort}`;
  if (keyword) url += `&search=${encodeURIComponent(keyword)}`;
  if (tag) url += `&tag=${encodeURIComponent(tag)}`;
  try {
    const words = await api(url);
    STATE.words = words;
    _offlineReadOnly = false;
    if (!keyword && !tag) cacheWordList(words).catch(() => {});
  } catch (e) {
    if (isNetworkFailure(e)) {
      try { await loadCachedWords(); } catch (_) { STATE.words = []; toast("离线且无可用词表缓存", "error"); }
    } else { console.error("[loadWords] 加载失败:", e); STATE.words = []; }
  }
  renderWordList();
  document.getElementById("word-count").textContent = `共 ${STATE.words.length} 词`;
}

async function searchWords() { return loadWords(); }

function setSort(value) { STATE.sort = value; loadWords(); }

let _allTags = [];
let _studyModes = {};
async function loadTags() {
  try {
    _allTags = await api("/api/tags", { _silent: true });
    const sel = document.getElementById("tag-filter");
    if (sel) {
      _allTags.forEach(t => {
        const opt = document.createElement("option");
        opt.value = t.name;
        opt.textContent = `${t.name} (${t.count})`;
        sel.appendChild(opt);
      });
    }
    const modes = await api("/api/study-modes");
    _studyModes = modes.tag_modes || {};
  } catch (e) { console.error("[loadTags] 加载失败:", e); /* 静默 */ }
}

// 获取单词的默认学习模式
function getStudyModeForWord(word) {
  const tags = word.tags || [];
  if (!tags.length) return "full";
  return _studyModes[tags[0]] || "full"; // tags[0] 是最小类
}

async function filterByTag(tag) {
  const kw = document.getElementById("word-search").value.trim();
  let url = `/api/words?sort=${STATE.sort}`;
  if (tag) url += `&tag=${encodeURIComponent(tag)}`;
  if (kw) url += `&search=${encodeURIComponent(kw)}`;
  try {
    const words = await api(url);
    STATE.words = words; _offlineReadOnly = false; cacheWordList(words).catch(() => {});
  } catch (e) {
    if (isNetworkFailure(e)) {
      try { await loadCachedWords(); } catch (_) { STATE.words = []; toast("离线且无可用词表缓存", "error"); }
    } else STATE.words = [];
  }
  renderWordList();
  document.getElementById("word-count").textContent = `共 ${STATE.words.length} 词`;
}

function renderWordList() {
  const container = document.getElementById("word-list");
  container.innerHTML = STATE.words.length === 0
    ? '<p class="placeholder">暂无单词</p>'
    : STATE.words.map(w => {
        const prof = w.proficiency || 0;
        const color = prof >= 80 ? "#38a169" : prof >= 50 ? "#3182ce" : prof >= 25 ? "#dd6b20" : "#e53e3e";
        const tags = (w.tags || []).slice(0, 3).map(t => `<span class="wi-tag">${esc(t)}</span>`).join("");
        return `<div class="word-item${STATE.selectedWordId === w.id ? ' selected' : ''}" onclick="selectWord(${w.id})">
          <span class="wi-word">${esc(w.word)}</span>
          <span class="wi-meaning">${esc(formatMeanings(w.chinese_meaning).replace(/\n/g,' ').substring(0,60))}</span>
          ${tags ? `<span class="wi-tags">${tags}</span>` : ''}
          <span class="wi-prof" style="background:${color}">${prof}%</span>
        </div>`;
      }).join("");
}

async function selectWord(id) {
  STATE.selectedWordId = id;
  renderWordList();
  try {
    const w = await api(`/api/words/${id}`);
    _offlineReadOnly = false;
    cacheWordDetail(w).catch(() => {});
    renderSelectedWord(w, false);
  } catch (e) {
    if (isNetworkFailure(e)) {
      try {
        const snapshot = _offlineCacheOwner && !_offlineReadUnavailable ? await getCachedWordDetail(id) : null;
        const fallback = snapshot?.word || STATE.words.find(word => word.id === id);
        if (!fallback) throw e;
        _offlineReadOnly = true;
        renderSelectedWord(fallback, true, snapshot?.fetchedAt);
        showOfflineBanner(snapshot?.fetchedAt);
      } catch (_) { toast("离线且无可用单词详情缓存", "error"); }
    } else console.error("[selectWord] 加载失败:", e);
  }
}
function renderSelectedWord(w, offlineReadOnly, fetchedAt) {
  if (isMobile()) {
    const pane = document.querySelector('.word-detail-pane');
    pane.classList.add('mobile-overlay'); STATE.mobileDetailOpen = true; pane.scrollTop = 0;
  }
  renderWordDetail(w, offlineReadOnly, fetchedAt);
}

function renderWordDetail(w, offlineReadOnly = false, fetchedAt) {
  const prof = w.proficiency || 0;
  const profColor = prof >= 80 ? "#38a169" : prof >= 50 ? "#3182ce" : prof >= 25 ? "#dd6b20" : "#e53e3e";
  const mobile = isMobile();
  const backBtn = mobile ? `<div class="mobile-back-btn" onclick="closeMobileDetail()">单词列表</div>` : '';
  document.getElementById("word-detail").innerHTML = `
    ${backBtn}
    <h2>${esc(w.word)} <small style="color:var(--text3);font-size:.9rem">${esc(w.phonetic||'')}</small></h2>
    <div class="wd-pos">${esc(w.part_of_speech || '—')}</div>
    ${offlineReadOnly ? `<p class="offline-detail-note">离线只读 · 缓存于 ${esc(offlineTime(fetchedAt))}${fetchedAt ? '' : ' · 缓存基础信息，完整详情未缓存'}</p>` : ''}
    ${(w.tags||[]).length ? `<div style="display:flex;gap:4px;flex-wrap:wrap;margin-bottom:10px;align-items:center"><span style="font-size:.75rem;color:var(--text3);margin-right:4px">🏷️</span>${w.tags.map(t => `<span class="wd-tag"${offlineReadOnly ? '' : ' style="cursor:pointer" title="点击移除"'} data-action="${offlineReadOnly ? '' : 'remove-tag'}" data-word-id="${w.id}" data-tag="${encodeURIComponent(t)}">${esc(t)}${offlineReadOnly ? '' : ' ×'}</span>`).join('')}</div>` : ''}
    ${offlineReadOnly ? '' : `<div style="display:flex;gap:6px;align-items:center;margin-bottom:8px;flex-wrap:wrap">
      <select id="tag-preset-${w.id}" style="font-size:.72rem;padding:2px 6px;border-radius:6px;border:1px solid var(--border);max-width:120px">
        <option value="">+ 标签</option>
        ${_allTags.map(t => `<option value="${esc(t.name)}">${esc(t.name)}</option>`).join('')}
        <option value="__custom__">✏️ 自定义...</option>
      </select>
      <button class="btn btn-sm btn-outline" onclick="addTag(${w.id})" style="font-size:.7rem">添加</button>
      ${(!w.tags||!w.tags.length) ? `<button class="btn btn-sm btn-outline" data-action="ai-classify" data-word-id="${w.id}" data-word="${encodeURIComponent(w.word)}" style="font-size:.7rem">自动分类</button>` : ''}
    </div>`}
    <div class="prof-bar"><div class="prof-bar-fill" style="width:${prof}%;background:${profColor}"></div></div>
    <p style="font-size:.8rem;color:var(--text2);margin-top:2px">熟练度 ${prof}/100 | 阶段 ${w.review_stage||0}/7 | 复习 ${w.review_count||0}次 | ${w.next_review_at ? '下次:'+w.next_review_at.substring(0,10) : ''}</p>
    ${w.chinese_meaning ? `<div class="wd-section"><div class="wd-label">📖 释义</div><div class="wd-content">${esc(formatMeanings(w.chinese_meaning))}</div></div>` : ''}
    ${w.example_sentence ? `<div class="wd-section"><div class="wd-label">💬 例句</div><div class="wd-content">${esc(w.example_sentence)}</div></div>` : ''}
    ${w.example_translation ? `<div class="wd-section"><div class="wd-label">🔤 翻译</div><div class="wd-content">${esc(w.example_translation)}</div></div>` : ''}
    ${w.notes ? `<div class="wd-notes">📝 ${esc(w.notes)}</div>` : ''}
    ${offlineReadOnly ? '' : `<div class="wd-actions">
      <button class="btn btn-primary btn-sm" onclick="openEditWord(${w.id})">✏️ 编辑</button>
      <button class="btn btn-danger btn-sm" onclick="deleteWord(${w.id})">🗑️ 删除</button>
    </div>`}`;

  const detail = document.getElementById("word-detail");
  detail.onclick = event => {
    const actionEl = event.target.closest("[data-action]");
    if (!actionEl) return;
    const wordId = Number(actionEl.dataset.wordId);
    if (actionEl.dataset.action === "remove-tag") {
      removeTag(wordId, decodeURIComponent(actionEl.dataset.tag));
    } else if (actionEl.dataset.action === "ai-classify") {
      aiClassify(decodeURIComponent(actionEl.dataset.word), wordId);
    }
  };
}

// ======= 录入/编辑单词 =======
function openAddWord() { openWordModal(null); }
function openEditWord(id) { openWordModal(STATE.words.find(w => w.id === id)); }

function openWordModal(word) {
  const isEdit = !!word;
  const wordText = word?.word || '';
  const isPhrase = wordText.includes(' ');
  document.getElementById("modal-overlay").classList.remove("hidden");
  document.getElementById("modal-content").innerHTML = `
    <h3>${isEdit ? '✏️ 编辑' : '➕ 录入'}${isPhrase ? '短语' : '单词'}</h3>
    <div class="form-group">
      <label>英文${isPhrase ? '短语' : '单词'}</label>
      <div style="display:flex;gap:8px">
        <input type="text" id="mf-word" value="${esc(wordText)}" placeholder="输入英文" style="flex:1">
        <button class="btn btn-outline btn-sm" onclick="lookupWord()">🔍 本地查词</button>
      </div>
    </div>
    <div class="form-group"><label>音标 ${isPhrase ? '<small class="setting-help">(短语无需)</small>' : ''}</label><input type="text" id="mf-phonetic" value="${esc(word?.phonetic||'')}" ${isPhrase ? 'disabled placeholder="短语无需音标"' : ''}></div>
    <div class="form-group"><label>词性</label><input type="text" id="mf-pos" value="${esc(word?.part_of_speech||'')}"></div>
    <div class="form-group"><label>中文释义</label><textarea id="mf-meaning">${esc(word?.chinese_meaning||'')}</textarea></div>
    <div class="form-group"><label>英文例句</label><textarea id="mf-example">${esc(word?.example_sentence||'')}</textarea></div>
    <div class="form-group"><label>例句翻译</label><textarea id="mf-trans">${esc(word?.example_translation||'')}</textarea></div>
    <div class="form-group"><label>📝 笔记（搭配/近反义词等）</label><textarea id="mf-notes">${esc(word?.notes||'')}</textarea></div>
    <div class="setting-help" style="font-size:12px;margin-bottom:8px">来源：<span id="mf-source-label">${word?.source || '—'}</span><input type="hidden" id="mf-source" value="${word?.source||'manual'}"></div>
    <div class="modal-actions">
      <button class="btn" onclick="closeModal()">取消</button>
      <button class="btn btn-primary" onclick="saveWord(${word?.id||'null'})">${isEdit ? '💾 保存' : '➕ 录入'}</button>
    </div>`;
  document.getElementById("mf-word").focus();
}

async function lookupWord() {
  if (!ensureOnlineForWrite()) return;
  const word = document.getElementById("mf-word").value.trim();
  if (!word) return;
  try {
    const data = await api("/api/words/lookup", {
      method: "POST", body: JSON.stringify({ word }),
    });
    if (data.found) {
      const d = data.data;
      document.getElementById("mf-phonetic").value = d.phonetic || "";
      document.getElementById("mf-pos").value = d.part_of_speech || "";
      document.getElementById("mf-meaning").value = d.chinese_meaning || "";
      document.getElementById("mf-example").value = d.example_sentence || "";
      document.getElementById("mf-trans").value = d.example_translation || "";
      document.getElementById("mf-notes").value = d.notes || "";
      document.getElementById("mf-source").value = data.source || d.source || "manual";
      document.getElementById("mf-source-label").textContent = data.source || d.source || "manual";
      toast(`✅ 查词成功 (来源: ${data.source})`, "success");
    } else if (data.typo && data.suggestions?.length) {
      // 拼写错误：显示建议列表，可点击或强制录入
      const sugs = data.suggestions;
      document.getElementById("mf-notes").value = "";
      toast("", "info"); // 清除旧 toast
      const spellFix = document.createElement("div");
      spellFix.id = "spell-fix";
      spellFix.style.cssText = "margin-top:8px;padding:8px;background:#fff3cd;border-radius:6px";
      const prompt = document.createElement("p");
      prompt.style.cssText = "margin:0 0 6px";
      prompt.textContent = "⚠️ 拼写可能有误，是否想查：";
      spellFix.appendChild(prompt);
      sugs.forEach(suggestion => {
        const button = document.createElement("button");
        button.className = "choice-btn";
        button.style.cssText = "display:inline-block;margin:4px";
        button.textContent = suggestion;
        button.addEventListener("click", () => {
          document.getElementById("mf-word").value = suggestion;
          lookupWord();
        });
        spellFix.appendChild(button);
      });
      const manual = document.createElement("p");
      manual.style.cssText = "margin:8px 0 0";
      const manualLink = document.createElement("a");
      manualLink.href = "#";
      manualLink.style.cssText = "color:#e53e3e;font-size:12px";
      manualLink.textContent = `坚持录入「${word}」`;
      manualLink.addEventListener("click", event => {
        event.preventDefault();
        spellFix.remove();
        toast("请手动填写释义后保存", "info");
      });
      manual.appendChild(manualLink);
      spellFix.appendChild(manual);
      document.getElementById("modal-content").appendChild(spellFix);
    } else {
      const sugs = data.suggestions || [];
      const msg = data.message || (sugs.length ? `未找到，相似词: ${sugs.join(', ')}` : "未找到该单词");
      toast(msg, sugs.length ? "info" : "error");
      if (sugs.length) {
        console.log("[查词] 相似词建议:", sugs.join(", "));
      }
    }
  } catch (e) { /* toast already shown */ }
}

async function saveWord(id) {
  const body = {
    word: document.getElementById("mf-word").value.trim(),
    phonetic: document.getElementById("mf-phonetic").value.trim(),
    part_of_speech: document.getElementById("mf-pos").value.trim(),
    chinese_meaning: document.getElementById("mf-meaning").value.trim(),
    example_sentence: document.getElementById("mf-example").value.trim(),
    example_translation: document.getElementById("mf-trans").value.trim(),
    notes: document.getElementById("mf-notes").value.trim(),
    source: document.getElementById("mf-source").value || "manual",
  };
  if (!body.word) { toast("单词不能为空", "error"); return; }

  try {
    if (id) {
      await api(`/api/words/${id}`, { method: "PUT", body: JSON.stringify(body) });
      toast("单词已更新", "success");
    } else {
      const resp = await fetch(appURL("/api/words"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const result = await resp.json();
      if (!resp.ok) {
        toast(result.error || "录入失败", "error");
        return;
      }
      toast(result.updated ? "单词内容已更新（学习进度保留）" : "单词已添加", "success");
    }
    closeModal();
    if (isMobile()) closeMobileDetail();
    loadWords();
    loadStats();
  } catch (e) { /* handled */ }
}

async function deleteWord(id) {
  if (!confirm("确定删除这个单词吗？")) return;
  try {
    await api(`/api/words/${id}`, { method: "DELETE" });
    STATE.selectedWordId = null;
    closeMobileDetail();
    loadWords();
    loadStats();
    toast("已删除", "info");
  } catch (e) { /* handled */ }
}

// ============================================================
//  学习 & 测验
// ============================================================

async function learnNewWords() {
  try {
    const btn = document.querySelector('#study-status .btn-primary');
    if (btn) { btn.disabled = true; btn.textContent = '⏳ 准备中...'; }
    const words = await api("/api/words/learn-new", { method: "POST", body: JSON.stringify({ count: 10 }) });
    if (btn) { btn.disabled = false; btn.textContent = '📥 学习新词'; }
    if (words.length === 0) {
      toast("当前无可学习的新词，请先录入或导入词书", "info");
      return;
    }
    toast(`已准备 ${words.length} 个新词`, "success");
    loadStats();
    loadWords();
    setTimeout(() => startReview(), 500);
  } catch (e) {
    const btn = document.querySelector('#study-status .btn-primary');
    if (btn) { btn.disabled = false; btn.textContent = '📥 学习新词'; }
  }
}

async function startReview(trainingMode = "review") {
  if (!ensureOnlineForWrite()) return;
  const btn = document.getElementById("btn-start-review");
  try {
    btn.disabled = true;
    btn.textContent = '⏳ 加载中...';
    const resp = await api("/api/quiz/sessions", { method: "POST", body: JSON.stringify({ training_mode: trainingMode }) });
    const words = resp.words || [];
    if ((resp.total === 0) || words.length === 0) {
      toast(resp.message || "暂无待复习单词，请先录入或点击「学习新词」", "info");
      return;
    }
    STATE.quiz = { sessionId: resp.session_id, words, index: 0, question: null, results: [], preparationPolling: null, deletingSession: false, trainingMode };
    document.getElementById("study-status").classList.add("hidden");
    document.getElementById("quiz-panel").classList.add("hidden");
    document.getElementById("quiz-preparing").classList.remove("hidden");
    renderQuizPreparation(resp);
    pollQuizPreparation();
    loadQuizQuestion();
  } finally {
    btn.disabled = false;
    btn.textContent = '🔄 开始复习测验';
  }
}

function quizProgressValue(value, fallback = 0) {
  return typeof value === "number" && Number.isFinite(value) ? Math.max(0, value) : fallback;
}

function renderQuizPreparation(status) {
  const legacy = status.ai_target && typeof status.ai_target === "object" ? status.ai_target : {};
  const target = quizProgressValue(status.ai_target, quizProgressValue(legacy.items));
  const completed = quizProgressValue(status.ai_completed, quizProgressValue(legacy.enhanced));
  const failed = quizProgressValue(status.ai_failed, quizProgressValue(legacy.failed));
  const progress = document.getElementById("quiz-prep-progress");
  progress.max = Math.max(1, target, completed + failed);
  progress.value = Math.min(progress.max, completed + failed);
  const details = [];
  if (target) details.push(`AI 已增强 ${completed}/${target} 道选择题`);
  if (failed) details.push("部分题目已使用本地干扰项");
  if (status.message) details.push(status.message);
  if (status.fallback && !target) details.push("已使用基础题目");
  document.getElementById("quiz-prep-message").textContent = status.status === "enhancing"
    ? "正在优化 AI 选择题..."
    : failed ? "部分题目已使用本地干扰项"
    : target ? `AI 已增强 ${completed}/${target} 道选择题` : "基础题目已准备完成";
  document.getElementById("quiz-prep-detail").textContent = details.join(" · ");
}

function stopQuizPreparationPolling() {
  if (STATE.quiz.preparationPolling) clearInterval(STATE.quiz.preparationPolling);
  STATE.quiz.preparationPolling = null;
}

async function pollQuizPreparation() {
  const sessionId = STATE.quiz.sessionId;
  if (!sessionId) return;
  let shouldPoll = true;
  const check = async () => {
    try {
      const status = await api(`/api/quiz/sessions/${sessionId}`, { _silent: true });
      if (STATE.quiz.sessionId !== sessionId) return;
      renderQuizPreparation(status);
      if (status.status !== "enhancing") {
        shouldPoll = false;
        stopQuizPreparationPolling();
      }
    } catch (e) {
      shouldPoll = false;
      stopQuizPreparationPolling();
      if (STATE.quiz.sessionId === sessionId) {
        document.getElementById("quiz-preparing").classList.add("hidden");
        document.getElementById("quiz-panel").classList.add("hidden");
        document.getElementById("study-status").classList.remove("hidden");
        toast("测验会话已失效，请重新开始", "error");
      }
    }
  };
  stopQuizPreparationPolling();
  await check();
  if (shouldPoll && STATE.quiz.sessionId === sessionId && !STATE.quiz.preparationPolling) {
    STATE.quiz.preparationPolling = setInterval(check, 1200);
  }
}

async function loadQuizQuestion() {
  const qz = STATE.quiz;
  if (qz.index >= qz.words.length) return finishQuiz();
  const requestedIndex = qz.index;
  document.getElementById("quiz-panel").classList.add("hidden");
  document.getElementById("quiz-preparing").classList.remove("hidden");
  document.getElementById("quiz-prep-message").textContent = qz.questionSource === 'ai' ? 'AI 正在生成语境和选项，请稍候…' : '正在准备本地题目…';
  document.getElementById("quiz-prep-detail").textContent = '';
  try {
    const q = await api(`/api/quiz/sessions/${qz.sessionId}/question/${requestedIndex}`, { _silent: true });
    if (qz.sessionId !== STATE.quiz.sessionId || requestedIndex !== STATE.quiz.index) return;
    STATE.quiz.question = q;
    document.getElementById("quiz-preparing").classList.add("hidden");
    document.getElementById("quiz-panel").classList.remove("hidden");
    renderQuiz(q, qz.words[qz.index]);
  } catch (e) {
    if (qz.sessionId !== STATE.quiz.sessionId || requestedIndex !== STATE.quiz.index) return;
    stopQuizPreparationPolling();
    if(e.status!==404){
      document.getElementById('quiz-prep-message').textContent=e.message||'暂时无法读取题目，学习进度仍已保留';
      const detail=document.getElementById('quiz-prep-detail');detail.replaceChildren();
      const retry=document.createElement('button');retry.className='btn btn-primary';retry.textContent='重试读取题目';retry.onclick=()=>loadQuizQuestion();detail.append(retry);
      return;
    }
    document.getElementById("quiz-preparing").classList.add("hidden");
    document.getElementById("quiz-panel").classList.add("hidden");
    document.getElementById("study-status").classList.remove("hidden");
    toast("测验会话已失效，请重新开始", "error");
  }
}

function renderQuiz(q, word) {
  const prof = word.proficiency || 0;
  const profColor = prof >= 80 ? "#38a169" : prof >= 50 ? "#3182ce" : prof >= 25 ? "#dd6b20" : "#e53e3e";

  document.getElementById("quiz-mode").textContent = `${q.generation_source === "ai" ? "AI 情境题 · " : "本地 · "}${q.mode || "quiz"}`;
  document.getElementById("quiz-progress").textContent = `${STATE.quiz.index + 1} / ${STATE.quiz.words.length}`;
  document.getElementById("quiz-prof").innerHTML = `熟练度 <b style="color:${profColor}">${prof}</b>`;
  document.getElementById("quiz-prompt").textContent = q.prompt || "";
  document.getElementById("quiz-hint").textContent = q.hint || "";
  document.getElementById("quiz-extra").textContent = [q.extra, q.generation_warning].filter(Boolean).join("\n");
  document.getElementById("quiz-feedback").classList.add("hidden");

  const dyn = document.getElementById("quiz-dynamic");
  dyn.innerHTML = "";

  if (q.type === "choice") {
    (q.options || []).forEach(opt => {
      const btn = document.createElement("button");
      btn.className = "choice-btn";
      btn.textContent = opt;
      btn.onclick = () => onChoice(q, opt, btn);
      dyn.appendChild(btn);
    });
  } else if (q.type === "recall") {
    // 回忆模式：先隐藏答案
    const revealBtn = document.createElement("button");
    revealBtn.className = "btn btn-accent";
    revealBtn.textContent = "👁 点击查看答案";
    revealBtn.onclick = () => {
      dyn.innerHTML = `
        <div style="font-size:1.2rem;font-weight:700;margin-bottom:12px">📖 ${esc(formatMeanings(q.answer))}</div>
        <p style="margin-bottom:8px">你记住了吗？</p>
        <button class="btn btn-accent" style="margin-right:8px" id="btn-remember">✅ 记得</button>
        <button class="btn btn-outline" id="btn-forgot">❌ 忘了</button>`;
      document.getElementById("btn-remember").onclick = () => onRecall(true);
      document.getElementById("btn-forgot").onclick = () => onRecall(false);
    };
    dyn.appendChild(revealBtn);
  } else {
    // 输入模式
    const input = document.createElement("input");
    input.type = "text";
    input.className = "quiz-input";
    input.placeholder = q.type === "spell" ? "输入英文单词..." : "输入答案...";
    dyn.appendChild(input);

    const submit = document.createElement("button");
    submit.className = "btn btn-primary";
    submit.textContent = "✅ 提交";
    submit.style.marginTop = "10px";
    submit.onclick = () => onSubmitInput(q, word.id, input.value);
    dyn.appendChild(submit);

    setTimeout(() => input.focus(), 100);

    // 回车提交
    input.addEventListener("keydown", e => { if (e.key === "Enter") submit.click(); });
  }
}

// 防重复提交
let _quizSubmitting = false;

async function onChoice(q, selected, btnEl) {
  if (_quizSubmitting) return; _quizSubmitting = true;
  const correct = selected === q.answer;
  // 高亮所有按钮
  document.querySelectorAll(".choice-btn").forEach(b => {
    if (b.textContent === q.answer) b.classList.add("correct");
    else if (b === btnEl && !correct) b.classList.add("wrong");
    b.style.pointerEvents = "none";
  });
  // 提交到后端更新熟练度
  const wordId = wordIdFromQuiz();
  try {
    const result = await api(`/api/quiz/sessions/${STATE.quiz.sessionId}/judge`, {
      method: "POST",
      body: JSON.stringify({ index: STATE.quiz.index, answer: selected }),
      _silent: true,
    });
    showQuizFeedback(result.correct, result.feedback || (correct ? "✅ 正确！" : `❌ 正确答案：${q.answer}`), q, wordId, result);
  } catch (e) {
    if(e.status===409){ toast(e.message,"info"); await finishQuiz(); return; }
    if (isNetworkJudgeFailure(e)) {
      const local = localQuizResult(q, selected);
      if (local.supported && await saveJudgeFallback(q, wordId, local.correct)) {
        showQuizFeedback(local.correct, `${local.correct ? "✅ 正确！" : `❌ 正确答案：${q.answer}`}（已离线保存，待同步）`, q, wordId, { rating: local.correct ? 5 : 1 });
      } else {
        showQuizFeedback(correct, `${correct ? "✅ 正确！" : `❌ 正确答案：${q.answer}`}（无法离线保存）`, q, wordId);
      }
    } else {
      toast(e.message || "评分失败", "error");
      showQuizFeedback(correct, `${correct ? "✅ 正确！" : `❌ 正确答案：${q.answer}`}（评分失败）`, q, wordId);
    }
  } finally { _quizSubmitting = false; }
}

async function onRecall(remembered) {
  if (_quizSubmitting) return; _quizSubmitting = true;
  document.querySelectorAll('#quiz-dynamic button').forEach(b => b.disabled = true);
  const wordId = wordIdFromQuiz();
  const q = STATE.quiz.question;
  try {
    const result = await api(`/api/quiz/sessions/${STATE.quiz.sessionId}/judge`, {
      method: "POST",
      body: JSON.stringify({ index: STATE.quiz.index, answer: remembered ? "remember" : "forgot" }),
      _silent: true,
    });
    showQuizFeedback(
      result.correct,
      result.feedback || (remembered ? "✅ 已记住" : "📖 继续加油"),
      q, wordId, result
    );
  } catch (e) {
    if(e.status===409){ toast(e.message,"info"); await finishQuiz(); return; }
    if (isNetworkJudgeFailure(e)) {
      const local = localQuizResult(q, remembered ? "remember" : "forgot");
      if (local.supported && await saveJudgeFallback(q, wordId, local.correct)) {
        showQuizFeedback(local.correct, `${local.correct ? "✅ 记得" : "📖 继续加油"}（已离线保存，待同步）`, q, wordId, { rating: local.correct ? 5 : 2 });
      } else {
        showQuizFeedback(remembered, `${remembered ? "✅ 记得" : "📖 继续加油"}（无法离线保存）`, q, wordId);
      }
    } else {
      toast(e.message || "评分失败", "error");
      showQuizFeedback(remembered, `${remembered ? "✅ 记得" : "📖 继续加油"}（评分失败）`, q, wordId);
    }
  } finally { _quizSubmitting = false; }
}

async function onSubmitInput(q, wordId, answer) {
  if (_quizSubmitting) return; _quizSubmitting = true;
  const dyn = document.getElementById("quiz-dynamic");
  dyn.querySelectorAll("button").forEach(b => b.disabled = true);
  const inp = dyn.querySelector("input");
  if (inp) inp.disabled = true;

  try {
    const result = await api(`/api/quiz/sessions/${STATE.quiz.sessionId}/judge`, {
      method: "POST",
      body: JSON.stringify({ index: STATE.quiz.index, answer }),
      _silent: true,
    });
    showQuizFeedback(result.correct, result.feedback || (result.correct ? "✅ 正确" : "❌ 错误"), q, wordId, result);
  } catch (e) {
    if(e.status===409){ toast(e.message,"info"); await finishQuiz(); return; }
    const local = localQuizResult(q, answer);
    if (isNetworkJudgeFailure(e) && local.supported && await saveJudgeFallback(q, wordId, local.correct)) {
      showQuizFeedback(local.correct, `${local.correct ? "✅ 正确" : "❌ 错误"}（已离线保存，待同步）`, q, wordId, { rating: local.correct ? 5 : 2 });
    } else if (isNetworkJudgeFailure(e) && !local.supported) {
      toast("此题需要在线评分，无法离线保存", "error");
      showQuizFeedback(false, "此题需要在线评分，未保存", q, wordId);
    } else if (isNetworkJudgeFailure(e)) {
      showQuizFeedback(local.correct, `${local.correct ? "✅ 正确" : "❌ 错误"}（无法离线保存）`, q, wordId);
    } else {
      toast(e.message || "评分失败", "error");
      showQuizFeedback(local.correct, `${local.correct ? "✅ 正确" : "❌ 错误"}（评分失败）`, q, wordId);
    }
  } finally { _quizSubmitting = false; }
}

function showQuizFeedback(correct, msg, q, wordId, result = null) {
  if (STATE.quiz.results.length > STATE.quiz.index) return;
  const fb = document.getElementById("quiz-feedback");
  fb.classList.remove("hidden", "correct", "wrong");
  fb.classList.add(correct ? "correct" : "wrong");
  fb.textContent = msg;
  if (q.explanation) {
    const explanation = document.createElement("p");
    explanation.className = "quiz-explanation";
    explanation.textContent = "AI 解析：" + q.explanation;
    fb.appendChild(explanation);
  }
  if (result?.diagnosis?.label) {
    const diagnosis = document.createElement("small");
    diagnosis.style.display = "block";
    diagnosis.style.marginTop = "6px";
    diagnosis.style.opacity = "0.82";
    diagnosis.textContent = `学习诊断：${result.diagnosis.label} · ${result.diagnosis.detail || ''}`;
    fb.appendChild(diagnosis);
  }
  if (!correct && q.answer) {
    const ref = document.createElement("br");
    const small = document.createElement("small");
    small.style.opacity = "0.7";
    small.textContent = `参考答案：${(q.reference||q.answer||'').substring(0,150)}`;
    fb.appendChild(ref);
    fb.appendChild(small);
  }
  STATE.quiz.results.push({ wordId, correct, rating: result?.rating || (correct ? 5 : 2) });

  // 显示下一题按钮
  const dyn = document.getElementById("quiz-dynamic");
  const next = document.createElement("button");
  next.className = "btn btn-primary";
  next.textContent = "▶ 下一题";
  next.style.marginTop = "10px";
  next.onclick = nextQuizQuestion;
  dyn.appendChild(next);
}

function nextQuizQuestion() {
  // 如果当前题目未作答（没提交评分），记录为跳过
  const answeredThisQ = STATE.quiz.results.length > STATE.quiz.index;
  if (!answeredThisQ) {
    STATE.quiz.results.push({ wordId: wordIdFromQuiz(), correct: false, rating: 0, skipped: true });
  }
  STATE.quiz.index++;
  document.getElementById("quiz-feedback").classList.add("hidden");
  _quizSubmitting = false;
  if (STATE.quiz.index >= STATE.quiz.words.length) {
    finishQuiz();
  } else {
    loadQuizQuestion();
  }
}

function releaseQuizSession(useKeepalive = false) {
  const qz = STATE.quiz;
  const sessionId = qz.sessionId;
  if (!sessionId || qz.deletingSession) return;
  qz.deletingSession = true;
  qz.sessionId = null;
  const url = `/api/quiz/sessions/${sessionId}`;
  if (useKeepalive && typeof fetch === "function") {
    fetch(appURL(url), { method: "DELETE", keepalive: true, headers: { "Content-Type": "application/json" } }).catch(() => {});
  } else {
    api(url, { method: "DELETE", _silent: true }).catch(() => {});
  }
}

function finishQuiz() {
  stopQuizPreparationPolling();
  releaseQuizSession();
  // 排除跳过的题目
  const answered = STATE.quiz.results.filter(r => !r.skipped);
  const total = answered.length;
  const skipped = STATE.quiz.results.length - total;
  const correct = answered.filter(r => r.correct).length;
  const avgRating = total ? (answered.reduce((s, r) => s + (r.rating || 0), 0) / total).toFixed(1) : 0;

  document.getElementById("quiz-preparing").classList.add("hidden");
  document.getElementById("quiz-panel").classList.add("hidden");
  document.getElementById("study-status").classList.remove("hidden");

  let msg = `🎉 测验完成！正确 ${correct}/${total} (${total ? Math.round(correct/total*100) : 0}%)  均分 ${avgRating}/5`;
  if (skipped > 0) msg += `\n跳过了 ${skipped} 题`;
  toast(msg, "success");
  loadStats();
  loadWords();

  api("/api/session/end", { method: "POST", _silent: true }).catch(() => {});

  if (answered.length > 0 && confirm(msg + "\n\n是否生成今日学习报告？")) {
    generateReport();
  }
}

// Learning sessions persist across reloads; only an explicit finish deletes them.

async function updateQuota() {
  const val = parseInt(document.getElementById("quota-input").value) || 20;
  try {
    await api("/api/settings", { method: "PUT", body: JSON.stringify({ daily_quota: val }) });
    document.getElementById("stat-quota").textContent = val;
    toast("配额已更新", "success");
  } catch (e) { /* handled */ }
}

function wordIdFromQuiz() {
  const qz = STATE.quiz;
  return qz.words[qz.index]?.id;
}

// ============================================================
//  标签编辑
// ============================================================

async function addTag(wordId) {
  const sel = document.getElementById(`tag-preset-${wordId}`);
  if (!sel) return;
  let tag = sel.value;
  if (!tag) return;
  if (tag === '__custom__') {
    tag = prompt('输入自定义标签：');
    if (!tag || !tag.trim()) return;
    tag = tag.trim();
  }
  try {
    const resp = await api(`/api/words/${wordId}/tags`, {
      method: "PUT", body: JSON.stringify({ action: "add", tag }),
    });
    if (resp.ok) { selectWord(wordId); toast(`已添加标签: ${tag}`, "success"); }
  } catch (e) { /* handled */ }
}

async function removeTag(wordId, tag) {
  try {
    const resp = await api(`/api/words/${wordId}/tags`, {
      method: "PUT", body: JSON.stringify({ action: "remove", tag }),
    });
    if (resp.ok) { selectWord(wordId); }
  } catch (e) { /* handled */ }
}

async function aiClassify(word, wordId) {
  if (!ensureOnlineForWrite()) return;
  toast("正在分类（本地优先）...", "info");
  try {
    const resp = await api("/api/words/classify", {
      method: "POST", body: JSON.stringify({ word }),
    });
    if (resp.tags && resp.tags.length) {
      await loadTags();
      selectWord(wordId);
      toast(`分类: ${resp.tags.join(', ')}`, "success");
    } else {
      toast("暂无可靠的分类结果", "info");
    }
  } catch (e) { /* handled */ }
}
// ============================================================

async function loadReports() {
  try {
    const reports = await api("/api/reports");
    const list = document.getElementById("report-list");
    list.innerHTML = reports.length === 0
      ? '<p class="placeholder">暂无报告</p>'
      : reports.map(r => `
        <div class="report-item" onclick="loadReportDetail('${r.date}')">
          <div class="rp-date">📅 ${r.date}</div>
          <div class="rp-summary">${esc(r.summary||'(无摘要)')}</div>
        </div>`).join("");
  } catch (e) { /* handled */ }
}

async function loadReportDetail(date) {
  try {
    if (isMobile()) {
      const pane = document.querySelector('.report-detail-pane');
      pane.classList.add('mobile-overlay');
      STATE.mobileDetailOpen = true;
      pane.scrollTop = 0;
    }
    const r = await api(`/api/reports/${date}`);
    const el = document.getElementById("report-detail");
    const mobile = isMobile();
    const backBtn = mobile ? `<div class="mobile-back-btn" onclick="closeMobileDetail()">报告列表</div>` : '';
    el.innerHTML = backBtn;
    if (r.full_report) {
      r.full_report.split("\n").forEach(line => {
        el.appendChild(document.createTextNode(line));
        el.appendChild(document.createElement("br"));
      });
    } else if (r.summary) {
      el.appendChild(document.createTextNode(r.summary));
    }
  } catch (e) { /* handled */ }
}

async function generateReport() {
  try {
    document.getElementById("report-detail").innerHTML = '<p class="placeholder">⏳ 正在生成报告...</p>';
    const r = await api("/api/reports/generate", { method: "POST" });
    toast("报告已生成", "success");
    loadReports();
    if (isMobile()) {
      const pane = document.querySelector('.report-detail-pane');
      pane.classList.add('mobile-overlay');
      STATE.mobileDetailOpen = true;
      pane.scrollTop = 0;
    }
    const el = document.getElementById("report-detail");
    const mobile = isMobile();
    const backBtn = mobile ? `<div class="mobile-back-btn" onclick="closeMobileDetail()">报告列表</div>` : '';
    el.innerHTML = backBtn;
    (r.full_report || r.summary || "").split("\n").forEach(line => {
      el.appendChild(document.createTextNode(line));
      el.appendChild(document.createElement("br"));
    });
  } catch (e) { /* handled */ }
}

// ============================================================
//  词书
// ============================================================

function openWordBook() {
  document.getElementById("modal-overlay").classList.remove("hidden");
  document.getElementById("modal-content").innerHTML = `
    <h3>📚 词书管理</h3>
    <p class="modal-intro">导入 CSV 词书，集中管理已导入的单词内容。</p>
    <div id="wb-list" class="wordbook-list"><p>加载中...</p></div>
    <div class="setting-section setting-section--actions">
      <input type="file" id="wb-file" class="visually-hidden" accept=".csv" onchange="importWordBook()">
      <button class="btn btn-primary" onclick="document.getElementById('wb-file').click()">📥 导入 CSV 词书</button>
    </div>
    <div class="modal-actions"><button class="btn" onclick="closeModal()">关闭</button></div>`;
  loadWordBooks();
}

async function loadWordBooks() {
  try {
    const books = await api("/api/wordbooks");
    document.getElementById("wb-list").innerHTML = books.length === 0
      ? '<p class="placeholder">暂无词书，请导入 CSV 文件</p>'
      : books.map(b => `
        <div class="wordbook-row">
          <div><b>${esc(b.name)}</b><br><small class="setting-help">${b.imported_count}/${b.total_words} 已导入</small></div>
          <button class="btn btn-danger btn-sm" onclick="deleteWordBook(${b.id})">删除</button>
        </div>`).join("");
  } catch (e) { /* handled */ }
}

async function importWordBook() {
  if (!ensureOnlineForWrite()) return;
  const file = document.getElementById("wb-file").files[0];
  if (!file) return;
  const form = new FormData();
  form.append("file", file);
  try {
    const res = await fetch(appURL("/api/wordbooks/import"), { method: "POST", body: form });
    const data = await res.json();
    if (data.ok) {
      toast(`词书「${data.name}」导入成功`, "success");
      loadWordBooks();
    } else {
      toast(data.error || "导入失败", "error");
    }
  } catch (e) { toast("导入失败", "error"); }
}

async function deleteWordBook(id) {
  if (!confirm("确定删除词书？")) return;
  try { await api(`/api/wordbooks/${id}`, { method: "DELETE" }); loadWordBooks(); } catch (e) { /* handled */ }
}

// ============================================================
//  设置
// ============================================================

function openSettings() {
  api("/api/settings").then(s => {
    document.getElementById("modal-overlay").classList.remove("hidden");
    document.getElementById("modal-content").innerHTML = `
      <h3>⚙️ 设置</h3>
      <div class="form-group"><label>API 地址</label><input type="text" id="set-api-base" value="${esc(s.api_base||'')}"></div>
      <div class="form-group"><label>API Key</label><input type="password" id="set-api-key" placeholder="${s.has_key ? '••••••••  (已设置，留空不修改)' : '请输入 API Key'}" autocomplete="off"></div>
      <div class="form-group"><label>模型名称</label><input type="text" id="set-model" value="${esc(s.model||'')}"></div>
      <div class="form-group"><label>每日新词配额</label><input type="number" id="set-quota" value="${s.daily_quota||20}" min="1" max="200"></div>
      <div class="form-group">
        <label>默认复习模式</label>
        <select id="set-review-mode">
          <option value="en2cn" ${s.review_mode==='en2cn'?'selected':''}>英→中</option>
          <option value="cn2en" ${s.review_mode==='cn2en'?'selected':''}>中→英</option>
          <option value="mixed" ${s.review_mode==='mixed'?'selected':''}>混合模式</option>
        </select>
      </div>
      <div class="form-group">
        <label>调度算法</label>
        <select id="set-scheduling-mode" onchange="document.getElementById('fsrs-opts').classList.toggle('is-hidden', this.value !== 'fsrs')">
          <option value="ebbinghaus" ${(s.scheduling_mode||'ebbinghaus')==='ebbinghaus'?'selected':''}>📅 艾宾浩斯（固定间隔）</option>
          <option value="fsrs" ${s.scheduling_mode==='fsrs'?'selected':''}>🧠 FSRS（自适应间隔）</option>
        </select>
      </div>
      <div class="form-group ${s.scheduling_mode==='fsrs' ? '' : 'is-hidden'}" id="fsrs-opts">
        <label>FSRS 目标可回收率 R</label>
        <input type="number" id="set-fsrs-target-r" value="${(s.fsrs||{}).target_R||0.9}" min="0.7" max="0.99" step="0.05">
        <span class="setting-help">越高 → 复习越频繁，越低 → 间隔越长（推荐 0.85-0.95）</span>
      </div>
      <div class="form-group setting-row setting-row--spaced">
        <label>自动衰减</label>
        <input type="checkbox" id="set-auto-decay" ${s.auto_decay?'checked':''}>
        <span class="setting-help">过期未复习自动降低熟练度</span>
      </div>
      <hr>
      <h4>� 访问密码</h4>
      ${s.has_password ? `
        <div class="form-group"><label>原密码</label><input type="password" id="set-old-pwd" placeholder="输入当前密码"></div>
        <div class="form-group"><label>新密码</label><input type="password" id="set-new-pwd" placeholder="留空不修改"></div>
      ` : `
        <div class="form-group"><label>设置密码</label><input type="password" id="set-new-pwd" placeholder="设置访问密码（至少4位）"></div>
      `}
      <hr><h4>🖼️ 自定义背景</h4>
      <div class="setting-section setting-section--actions">
        <label class="btn btn-outline btn-sm file-action">
          📤 上传图片
          <input type="file" class="visually-hidden" accept="image/*" onchange="uploadBackground(this)">
        </label>
        ${(s.appearance||{}).background_type==='custom' ? `<button class="btn btn-danger btn-sm" onclick="resetBackground()">↩ 恢复默认</button>` : ''}
      </div>
      <div class="form-group"><label>模糊度 <small>(${((s.appearance||{}).background_blur||15)}px)</small></label><input type="range" id="set-bg-blur" min="0" max="30" value="${(s.appearance||{}).background_blur||15}" oninput="updateBgStyle(this.value, document.getElementById('set-bg-brightness').value)"></div>
      <div class="form-group"><label>亮度 <small>(${((s.appearance||{}).background_brightness||60)}%)</small></label><input type="range" id="set-bg-brightness" min="20" max="100" value="${(s.appearance||{}).background_brightness||60}" oninput="updateBgStyle(document.getElementById('set-bg-blur').value, this.value)"></div>
      <div class="form-group"><label>卡片透明度 <small>(${((s.appearance||{}).card_opacity!=null?(s.appearance||{}).card_opacity:100)}%)</small></label><input type="range" id="set-card-opacity" min="15" max="100" value="${(s.appearance||{}).card_opacity!=null?(s.appearance||{}).card_opacity:100}" oninput="applyCardOpacity(this.value)"></div>
      <hr>
      <h4>📝 标签学习模式</h4>
      <p class="modal-note">每个标签单独设置，学习时自动匹配词的首标签</p>
      <div id="tag-mode-list" class="tag-mode-list">
        ${_allTags.map(t => `<div class="tag-mode-row"><span>🏷️ ${esc(t.name)}</span><select class="tag-mode-sel" data-tag="${esc(t.name)}"><option value="full" ${(_studyModes[t.name]||'full')==='full'?'selected':''}>📝 全部</option><option value="meaning_only" ${_studyModes[t.name]==='meaning_only'?'selected':''}>📖 仅释义</option><option value="choice_only" ${_studyModes[t.name]==='choice_only'?'selected':''}>🅰️ 仅选择</option></select></div>`).join('')}
      </div>
      <hr>
      <h4>🔗 Chrome 扩展</h4>
      <p class="modal-note">安装扩展后填入以下 Token 即可划词查词</p>
      <div class="token-field">
        <input id="ext-token" readonly value="加载中...">
        <button class="btn btn-sm btn-outline" onclick="navigator.clipboard.writeText(document.getElementById('ext-token').value);toast('已复制','success')">📋</button>
      </div>
      <p class="token-server">服务器: <span id="ext-server"></span></p>
      <hr><h4>💾 备份与还原</h4>
      <div class="setting-section setting-section--actions">
        <button class="btn btn-outline" onclick="exportWords()">📥 导出备份</button>
        <label class="btn btn-outline file-action">
          📤 导入备份
          <input type="file" id="import-file" class="visually-hidden" accept=".json" onchange="importWords(this)">
        </label>
      </div>
      <div class="setting-section">
        <label class="setting-help checkbox-label">
          <input type="checkbox" id="import-overwrite"> 覆盖已有单词
        </label>
      </div>
      <div class="modal-actions">
        <button class="btn" onclick="closeModal()">取消</button>
        <button class="btn btn-primary" onclick="saveSettings()">💾 保存</button>
      </div>`;
    // DOM 创建完后再加载 Token
    fetch(appURL("/api/extension/token-info")).then(r => r.json()).then(d => {
      if (d.token) {
        const tokEl = document.getElementById("ext-token");
        const srvEl = document.getElementById("ext-server");
        if (tokEl) tokEl.value = d.token;
        if (srvEl) srvEl.textContent = d.server || location.origin;
      }
    }).catch(() => {});
  }).catch(() => {});
}

async function saveSettings() {
  const apiKey = document.getElementById("set-api-key").value.trim();
  const body = {
    api_base: document.getElementById("set-api-base").value.trim(),
    model: document.getElementById("set-model").value.trim(),
    daily_quota: parseInt(document.getElementById("set-quota").value) || 20,
    review_mode: document.getElementById("set-review-mode").value,
    auto_decay: document.getElementById("set-auto-decay").checked,
    scheduling_mode: document.getElementById("set-scheduling-mode")?.value || "ebbinghaus",
  };
  if (apiKey) body.api_key = apiKey;

  // FSRS 参数
  const schedSel = document.getElementById("set-scheduling-mode");
  if (schedSel) {
    body.scheduling_mode = schedSel.value;
    if (schedSel.value === "fsrs") {
      const targetR = document.getElementById("set-fsrs-target-r");
      if (targetR) {
        body.fsrs = { target_R: parseFloat(targetR.value) || 0.9 };
      }
    }
  }

  // [BUG-FIX] 外观参数：必须带上 background_type/background_image_path
  // 否则前端只传 blur/brightness，服务端无法感知是否有自定义背景
  const blurEl = document.getElementById("set-bg-blur");
  const brightEl = document.getElementById("set-bg-brightness");
  if (blurEl && brightEl) {
    const opacityEl = document.getElementById("set-card-opacity");
    // 从当前已渲染的背景图来推断 background_type（如已设置则保留）
    const bgImg = document.getElementById("app-bg-image");
    const hasCustomBg = bgImg && bgImg.style.display !== "none" && bgImg.src && !bgImg.src.endsWith("/");
    body.appearance = {
      background_blur: parseInt(blurEl.value) || 15,
      background_brightness: parseInt(brightEl.value) || 60,
      card_opacity: opacityEl ? parseInt(opacityEl.value) : 100,
      // 只在有自定义背景时才传 background_type，避免误覆盖
      ...(hasCustomBg ? {} : { background_type: "default", background_image_path: "" }),
    };
  }

  // [BUG-FIX] 标签学习模式：合并到同一次请求体，避免并发覆盖 settings.json
  const tagModes = {};
  document.querySelectorAll(".tag-mode-sel").forEach(sel => {
    const tag = sel.dataset.tag;
    if (tag) tagModes[tag] = sel.value;
  });
  if (Object.keys(tagModes).length > 0) {
    body.study_modes = tagModes;
  }

  try {
    const resp = await api("/api/settings", { method: "PUT", body: JSON.stringify(body) });
    if (!resp || !resp.ok) {
      toast("❌ 配置保存失败：服务器返回异常", "error");
      return;
    }

    // 更新本地 _studyModes 缓存
    Object.assign(_studyModes, tagModes);

    // 验证返回的保存值与发送值一致
    const saved = resp.saved || {};
    if (saved.scheduling_mode && saved.scheduling_mode !== body.scheduling_mode) {
      console.warn("[Settings] scheduling_mode 保存不一致:", saved.scheduling_mode, body.scheduling_mode);
    }
    if (body.appearance) {
      updateBgStyle(body.appearance.background_blur, body.appearance.background_brightness);
    }

    // 密码修改（主设置保存成功后再处理）
    const newPwd = document.getElementById("set-new-pwd");
    if (newPwd && newPwd.value.trim()) {
      const oldPwd = document.getElementById("set-old-pwd");
      const pwdBody = {
        new_password: newPwd.value.trim(),
        old_password: oldPwd ? oldPwd.value.trim() : "",
      };
      const pwdResp = await fetch(appURL("/api/auth/change-password"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(pwdBody),
      });
      if (!pwdResp.ok) {
        const err = await pwdResp.json();
        toast(err.error || "密码修改失败", "error");
        return;
      }
    }

    toast("✅ 设置已保存", "success");
    closeModal();
    loadStats();
  } catch (e) { /* handled */ }
}

// ============================================================
//  导入导出
// ============================================================

function exportWords() {
  fetch(appURL("/api/words/export"))
    .then(r => r.json())
    .then(data => {
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      const now = new Date().toISOString().slice(0, 10);
      a.href = url;
      a.download = `word-backup-${now}.json`;
      a.click();
      URL.revokeObjectURL(url);
      toast(`已导出 ${data.word_count} 个单词`, "success");
    })
    .catch(() => toast("导出失败", "error"));
}

function importWords(input) {
  if (!ensureOnlineForWrite()) { input.value = ""; return; }
  const file = input.files[0];
  if (!file) return;
  const overwrite = document.getElementById("import-overwrite")?.checked || false;
  const formData = new FormData();
  formData.append("file", file);
  formData.append("mode", overwrite ? "overwrite" : "merge");

  fetch(appURL("/api/words/import"), { method: "POST", body: formData })
    .then(r => r.json())
    .then(data => {
      if (data.error) { toast(data.error, "error"); return; }
      const parts = [];
      if (data.imported) parts.push(`新增 ${data.imported} 个`);
      if (data.overwritten) parts.push(`覆盖 ${data.overwritten} 个`);
      if (data.skipped) parts.push(`跳过 ${data.skipped} 个`);
      toast(`导入完成: ${parts.join("，")}`, "success");
      closeModal();
      loadWords();
      loadStats();
    })
    .catch(() => toast("导入失败", "error"));
  input.value = "";
}

// ============================================================
//  输出与阅读练习
// ============================================================
function openPracticeHub() {
  const options = STATE.words.map(w => `<option value="${w.id}">${esc(w.word)} — ${esc(w.chinese_meaning || '未填写释义')}</option>`).join('');
  document.getElementById("modal-overlay").classList.remove("hidden");
  document.getElementById("modal-content").innerHTML = `
    <h3>✍️ 输出与阅读练习</h3>
    <div class="form-group"><label>目标词</label><select id="practice-word">${options}</select></div>
    <div class="form-group"><label>用目标词写一句英文</label><textarea id="practice-sentence" placeholder="例如：I was reluctant to leave the familiar place."></textarea></div>
    <div class="modal-actions"><button class="btn btn-primary" onclick="submitWritingPractice()">🤖 批改句子</button><button class="btn btn-outline" onclick="generateScenarioPractice()">🎭 生成情境任务</button></div>
    <hr style="margin:18px 0;border:0;border-top:1px solid var(--border)">
    <div class="form-group"><label>粘贴英文阅读材料</label><textarea id="reading-text" placeholder="粘贴一段英文，系统会标出已收录词与未收录词。"></textarea></div>
    <div class="modal-actions"><button class="btn btn-outline" onclick="analyzeReadingPractice()">📖 分析词汇</button><button class="btn" onclick="closeModal()">关闭</button></div>
    <div id="practice-result" style="margin-top:14px"></div>`;
}

async function submitWritingPractice() {
  const wordId = Number(document.getElementById("practice-word").value);
  const sentence = document.getElementById("practice-sentence").value.trim();
  const result = await api("/api/practice/writing", { method: "POST", body: JSON.stringify({ word_id: wordId, sentence }) });
  document.getElementById("practice-result").innerHTML = `<div class="quiz-feedback ${result.correct ? 'correct' : 'wrong'}"><b>${result.correct ? '使用正确' : '继续调整'}</b><br>${esc(result.feedback)}<br><small>建议改写：${esc(result.rewrite)}</small></div>`;
}

async function generateScenarioPractice() {
  const wordId = Number(document.getElementById("practice-word").value);
  const result = await api("/api/practice/scenario", { method: "POST", body: JSON.stringify({ word_ids: [wordId], scene: "日常交流" }) });
  document.getElementById("practice-result").innerHTML = `<div class="wd-section"><div class="wd-label">🎭 情境任务</div><div class="wd-content">${esc(result.prompt)}</div></div>`;
}

async function analyzeReadingPractice() {
  const text = document.getElementById("reading-text").value.trim();
  const result = await api("/api/practice/reading", { method: "POST", body: JSON.stringify({ text }) });
  const known = result.known.map(item => `<span class="wd-tag">${esc(item.word)}</span>`).join(' ') || '无';
  const unknown = result.unknown.map(item => `<span class="wd-tag" style="background:var(--warning-light);color:var(--warning)">${esc(item.word)}</span>`).join(' ') || '无';
  document.getElementById("practice-result").innerHTML = `<div class="wd-section"><div class="wd-label">覆盖率 ${result.coverage}% · 共 ${result.tokens} 个词</div><p>已收录：${known}</p><p style="margin-top:8px">未收录：${unknown}</p></div>`;
}

// ============================================================
//  PWA 离线提示
// ============================================================

window.addEventListener("online", async () => {
  await initOfflineReadCache();
  await drainReviewOperations();
  loadStats();
  loadWords();
  const banner = document.getElementById("offline-banner");
  if (banner) banner.remove();
  toast("🌐 网络已恢复", "success");
});

function showOfflineBanner(fetchedAt) {
  let banner = document.getElementById("offline-banner");
  if (!banner) {
    banner = document.createElement("div");
    banner.id = "offline-banner";
    banner.style.cssText = "position:fixed;bottom:0;left:0;right:0;background:#e04650;color:#fff;text-align:center;padding:8px;z-index:9999;font-size:13px;";
    document.body.appendChild(banner);
  }
  const cacheText = fetchedAt ? `（缓存于 ${offlineTime(fetchedAt)}）` : "";
  banner.textContent = _reviewQueueUnavailable
    ? `离线只读${cacheText} — 词表只能浏览；此浏览器不能离线保存复习结果`
    : `离线只读${cacheText} — 可浏览缓存词表；可继续完成已经加载的测验，评分会待同步`;
}

window.addEventListener("offline", showOfflineBanner);

// ============================================================
//  工具函数
// ============================================================

function closeModal(e) {
  if (e && e.target !== document.getElementById("modal-overlay")) return;
  document.getElementById("modal-overlay").classList.add("hidden");
}

function esc(str) {
  if (!str) return "";
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}
