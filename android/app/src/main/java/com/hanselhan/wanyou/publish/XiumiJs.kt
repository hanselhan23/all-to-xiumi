package com.hanselhan.wanyou.publish

/**
 * 秀米编辑器自动化所需的全部 JS 片段 —— `all_to_xiumi/xiumi_publish.py` 的移植。
 *
 * 与 Python 版的差异（WebView 适配）：
 * - 需要传参的片段改为 `function(a, b) {...}` 形式，经 [JsBridge.withArgs]
 *   以 base64 JSON 注入；原 Python 版里作为 `arguments[i]` 传递的 WebElement
 *   一律改为 `input[type="file"]` 的 DOM 序号（index）。
 * - CDP 能力（剪贴板、鼠标事件、DOM.setFileInputFiles）在 WebView 不可用：
 *   粘贴改用 `document.execCommand`，文件由 `onShowFileChooser` 桥接供给。
 * - 普通按钮/链接的 `.click()` 在 WebView 中无用户手势限制，保留原样。
 *
 * 注意：Kotlin raw string 中 `$` 会触发插值，JS 里的 `$apply`/`$parent`
 * 需写成 `${'$'}apply`/`${'$'}parent`。
 */
object XiumiJs {

    // ── 简单状态查询 ──

    /** document.readyState（"complete" 视为就绪）。 */
    const val READY_STATE = "document.readyState"

    /** 保存按钮存在（`_wait_editor_ready` 条件之一）。 */
    const val HAS_SAVE_BUTTON = "document.querySelectorAll('button.btn-img.op-btn.save').length > 0"

    /** contenteditable 存在（`_wait_editor_ready` 条件之二）。 */
    const val HAS_EDITABLE = "document.querySelectorAll('[contenteditable=\"true\"]').length > 0"

    /** 页面正文文本（`_page_excerpt` / `_save_diagnostics`）。 */
    const val BODY_TEXT = "document.body ? document.body.innerText : ''"

    /** 当前 URL（hash 路由的编辑器地址）。 */
    const val CURRENT_URL = "location.href"

    /** file input 数量（`_file_input_count`）。 */
    const val FILE_INPUT_COUNT = "document.querySelectorAll('input[type=\"file\"]').length"

    /** 上传观察器记录的事件（`_xiumi_observed_upload_assets` / `_xiumi_upload_event_count`）。 */
    const val UPLOAD_EVENTS = "window.__wanyouXiumiUploadEvents || []"

    // ── 登录检测 ──

    /** `_visible_header_login_links`：视口右上角的登录/登陆入口。 */
    val VISIBLE_HEADER_LOGIN_LINKS = """
const out = [];
const viewportH = window.innerHeight || document.documentElement.clientHeight || 900;
const viewportW = window.innerWidth || document.documentElement.clientWidth || 1200;
for (const el of Array.from(document.querySelectorAll('a,button,[role="button"]'))) {
  const text = String(el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim();
  if (!/(登录|登陆)/.test(text)) continue;
  const style = window.getComputedStyle(el);
  const rect = el.getBoundingClientRect();
  const visible = style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
  if (!visible) continue;
  const inHeader = rect.top >= 0 && rect.top <= Math.max(120, viewportH * 0.18);
  const nearRight = rect.left >= viewportW * 0.55;
  if (inHeader && nearRight) {
    out.push({ text, top: Math.round(rect.top), left: Math.round(rect.left), width: Math.round(rect.width), height: Math.round(rect.height) });
  }
}
out;
""".trimIndent()

    /** `_visible_login_controls`：页面上可见的登录/注册入口（排除“登录中”态）。 */
    val VISIBLE_LOGIN_CONTROLS = """
const out = [];
for (const el of Array.from(document.querySelectorAll('a,button,[role="button"],.usr-sign-in'))) {
  const text = String(el.innerText || el.textContent || el.getAttribute('aria-label') || el.getAttribute('title') || '').replace(/\s+/g, ' ').trim();
  if (!/(登录|登陆|注册)/.test(text)) continue;
  if (/(登录中|正在登录|退出登录|退出登陆)/.test(text)) continue;
  const style = window.getComputedStyle(el);
  const rect = el.getBoundingClientRect();
  const visible = style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
  if (!visible) continue;
  out.push({ text, top: Math.round(rect.top), left: Math.round(rect.left), width: Math.round(rect.width), height: Math.round(rect.height) });
}
out;
""".trimIndent()

    /** `_visible_login_links`：a.usr-sign-in 与文本含 登录/登陆 的可点击元素。 */
    val VISIBLE_LOGIN_LINKS = """
const out = [];
const selector = 'a.usr-sign-in, a, button';
for (const el of Array.from(document.querySelectorAll(selector))) {
  const text = String(el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim();
  const isUsrSignIn = el.matches('a.usr-sign-in');
  if (!isUsrSignIn && !/(登录|登陆)/.test(text)) continue;
  const style = window.getComputedStyle(el);
  const rect = el.getBoundingClientRect();
  const visible = style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
  if (!visible) continue;
  out.push({ text, top: Math.round(rect.top), left: Math.round(rect.left), width: Math.round(rect.width), height: Math.round(rect.height) });
}
out;
""".trimIndent()

    /** 点击第一个可见登录入口（Android 上用户也可直接在 WebView 中手动登录）。 */
    const val CLICK_FIRST_LOGIN_LINK = """
const els = Array.from(document.querySelectorAll('a.usr-sign-in, a, button')).filter(el => {
  const text = String(el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim();
  if (!el.matches('a.usr-sign-in') && !/(登录|登陆)/.test(text)) return false;
  const style = window.getComputedStyle(el);
  const rect = el.getBoundingClientRect();
  return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
});
if (!els.length) return { clicked: false };
try { els[0].click(); return { clicked: true, text: String(els[0].innerText || '').trim().slice(0, 60) }; }
catch (e) { return { clicked: false, error: String(e) }; }
"""

    // ── 对话框 / 字段 ──

    /** `_dismiss_xiumi_recover_dialog`：点掉“上次没有保存到服务器”恢复弹窗。 */
    val DISMISS_RECOVER_DIALOG = """
function exactBtn(text) {
  const els = Array.from(document.querySelectorAll('button, [ng-click], a, [class*="btn"]'));
  return els.find(e => (e.textContent || '').trim() === text && e.offsetWidth > 0 && e.offsetHeight > 0) || null;
}
for (const t of ['取消', '确定']) {
  const b = exactBtn(t);
  if (b) {
    const r = b.getBoundingClientRect();
    b.click();
    return { text: t, x: Math.round(r.x + r.width / 2), y: Math.round(r.y + r.height / 2) };
  }
}
return { text: null };
""".trimIndent()

    /** `_set_input_value`：设值并派发 input/change 事件（Angular 表单感知）。 */
    val SET_INPUT_VALUE_FN = """
function(selector, value) {
  const el = document.querySelector(selector);
  if (!el) return false;
  el.value = value;
  el.dispatchEvent(new Event('input', { bubbles: true }));
  el.dispatchEvent(new Event('change', { bubbles: true }));
  return true;
}
"""

    /** 点击保存按钮（`_click_save`）。 */
    val CLICK_SAVE = """
(() => {
  const btn = document.querySelector('button.btn-img.op-btn.save');
  if (!btn) return false;
  btn.click();
  return true;
})();
"""

    // ── 正文注入（WebView 版 _paste_xiumi_html：execCommand 替代 CDP 剪贴板） ──

    /** 聚焦第一个可见 contenteditable，并全选其内容（供后续 delete/insertHTML）。 */
    val FOCUS_EDITOR_SELECT_ALL = """
(() => {
  const editable = Array.from(document.querySelectorAll('[contenteditable="true"]')).find(e => e.offsetWidth > 0);
  if (!editable) return false;
  editable.scrollIntoView({ block: 'center' });
  editable.focus();
  const range = document.createRange();
  range.selectNodeContents(editable);
  const sel = window.getSelection();
  sel.removeAllRanges();
  sel.addRange(range);
  return true;
})();
"""

    /**
     * `_paste_xiumi_html` 的 WebView 实现：
     * 清空 → `execCommand('insertHTML')` 插入片段。
     * 秀米真实粘贴入口（Ctrl+V）会把内容构建成可渲染 comp；直接 innerHTML
     * 会落进 _qiBlock 且保存后不渲染。这里先尝试 execCommand 走浏览器
     * 插入管线，失败后由 Kotlin 侧用系统剪贴板 + KEYCODE_PASTE 兜底。
     */
    val SEED_PASTE_HTML_FN = """
function(htmlText) {
  const editable = Array.from(document.querySelectorAll('[contenteditable="true"]')).find(e => e.offsetWidth > 0);
  if (!editable) return { ok: false, err: 'no editable' };
  editable.scrollIntoView({ block: 'center' });
  editable.focus();
  const range = document.createRange();
  range.selectNodeContents(editable);
  const sel = window.getSelection();
  sel.removeAllRanges();
  sel.addRange(range);
  let cleared = false;
  try { cleared = document.execCommand('delete'); } catch (e) {}
  let inserted = false;
  try { inserted = document.execCommand('insertHTML', false, htmlText); } catch (e) {
    return { ok: false, err: 'insertHTML:' + e };
  }
  return { ok: inserted, cleared, htmlChars: htmlText.length };
}
"""

    // ── 上传观察器（_install_xiumi_upload_observer） ──

    val UPLOAD_OBSERVER_INSTALL = """
if (!window.__wanyouXiumiUploadObserverInstalled) {
  window.__wanyouXiumiUploadObserverInstalled = true;
  window.__wanyouXiumiUploadEvents = [];
  const fileNamesFromBody = (body) => {
    const names = [];
    try {
      if (body && typeof body.forEach === 'function') {
        body.forEach((value) => {
          if (value && typeof value === 'object' && 'name' in value) names.push(String(value.name || ''));
        });
      }
    } catch (e) {}
    return names.filter(Boolean);
  };
  const record = (kind, url, status, body, files) => {
    try {
      const text = String(body || '');
      if (/上传|upload|img\.xiumi\.us|\/xmi\/ua\//i.test(String(url || '') + ' ' + text)) {
        window.__wanyouXiumiUploadEvents.push({
          time: Date.now(),
          kind,
          url: String(url || ''),
          status: status || 0,
          files: files || [],
          body: text.slice(0, 200000)
        });
        if (window.__wanyouXiumiUploadEvents.length > 120) {
          window.__wanyouXiumiUploadEvents = window.__wanyouXiumiUploadEvents.slice(-120);
        }
      }
    } catch (e) {}
  };
  if (window.fetch) {
    const originalFetch = window.fetch;
    window.fetch = function() {
      const requestUrl = arguments[0] && (arguments[0].url || arguments[0]);
      const requestFiles = arguments[1] ? fileNamesFromBody(arguments[1].body) : [];
      return originalFetch.apply(this, arguments).then(resp => {
        try {
          const clone = resp.clone();
          clone.text().then(text => record('fetch', requestUrl, resp.status, text, requestFiles)).catch(() => {});
        } catch (e) {}
        return resp;
      });
    };
  }
  if (window.XMLHttpRequest) {
    const OriginalXHR = window.XMLHttpRequest;
    window.XMLHttpRequest = function() {
      const xhr = new OriginalXHR();
      let requestUrl = '';
      const open = xhr.open;
      xhr.open = function(method, url) {
        requestUrl = url;
        return open.apply(xhr, arguments);
      };
      xhr.addEventListener('loadend', function() {
        try { record('xhr', requestUrl, xhr.status, xhr.responseText || '', xhr.__wanyouUploadFiles || []); } catch (e) {}
      });
      const send = xhr.send;
      xhr.send = function(body) {
        try { xhr.__wanyouUploadFiles = fileNamesFromBody(body); } catch (e) {}
        return send.apply(xhr, arguments);
      };
      return xhr;
    };
  }
}
true;
""".trimIndent()

    // ── 图库资产（_xiumi_gallery_assets） ──

    val GALLERY_ASSETS = """
const results = [];
const seen = new Set();
const urlRe = /(https?:)?\/\/[^"'\s<>）)]*(?:img\.xiumi\.us|\/xmi\/ua\/)[^"'\s<>）)]*/ig;
function cleanUrl(value) {
  if (!value) return '';
  let text = String(value).replace(/\\\//g, '/');
  const match = text.match(urlRe);
  if (!match || !match.length) return '';
  let url = match[0];
  if (url.startsWith('//')) url = 'https:' + url;
  return url;
}
function add(url, text, source) {
  url = cleanUrl(url);
  if (!url || seen.has(url)) return;
  seen.add(url);
  results.push({ url, text: String(text || '').replace(/\s+/g, ' ').slice(0, 500), source });
}
for (const img of Array.from(document.querySelectorAll('img'))) {
  const text = [
    img.alt, img.title, img.getAttribute('data-name'), img.getAttribute('data-title'),
    img.closest('li,div,section,figure') && img.closest('li,div,section,figure').innerText
  ].join(' ');
  add(img.getAttribute('src') || img.getAttribute('data-src') || '', text, 'img');
}
for (const el of Array.from(document.querySelectorAll('*'))) {
  const text = [
    el.innerText, el.textContent, el.title, el.getAttribute('alt'),
    el.getAttribute('data-name'), el.getAttribute('data-title'), el.getAttribute('data-src')
  ].join(' ');
  add(text, text, 'text');
  try {
    const bg = window.getComputedStyle(el).backgroundImage || '';
    add(bg, text, 'background');
  } catch (e) {}
}
if (window.angular) {
  const seenObjects = new Set();
  function walk(obj, depth, label) {
    if (!obj || depth > 5) return;
    if (typeof obj === 'string') {
      add(obj, label, 'angular');
      return;
    }
    if (typeof obj !== 'object') return;
    if (seenObjects.has(obj)) return;
    seenObjects.add(obj);
    const values = [];
    for (const [key, value] of Object.entries(obj)) {
      if (/name|file|title|text|url|src|image|img|pic|path/i.test(key)) {
        values.push(String(value || ''));
      }
    }
    const joined = values.join(' ');
    add(joined, joined || label, 'angular');
    for (const [key, value] of Object.entries(obj).slice(0, 80)) {
      if (/^\$/.test(key)) continue;
      if (/image|img|pic|upload|gallery|material|file|list|data|items/i.test(key)) walk(value, depth + 1, joined || label);
    }
  }
  for (const el of Array.from(document.querySelectorAll('[ng-controller], [ng-repeat], .ng-scope, .ng-isolate-scope')).slice(0, 120)) {
    try { walk(window.angular.element(el).scope(), 0, el.innerText || ''); } catch (e) {}
    try { walk(window.angular.element(el).isolateScope(), 0, el.innerText || ''); } catch (e) {}
  }
}
results.slice(-300);
""".trimIndent()

    // ── 文件输入 ──

    /** `_file_input_diagnostics`：全部 file input 的元信息。 */
    val FILE_INPUT_DIAGNOSTICS = """
Array.from(document.querySelectorAll('input[type="file"]')).map((el, index) => {
  const style = window.getComputedStyle(el);
  const rect = el.getBoundingClientRect();
  const parent = el.parentElement;
  return {
    index,
    accept: el.getAttribute('accept') || '',
    multiple: !!el.multiple,
    disabled: !!el.disabled,
    visible: style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0,
    width: Math.round(rect.width),
    height: Math.round(rect.height),
    id: el.id || '',
    name: el.name || '',
    className: String(el.className || ''),
    parentClass: parent ? String(parent.className || '') : '',
    parentText: parent ? String(parent.innerText || '').replace(/\s+/g, ' ').slice(0, 80) : ''
  };
});
""".trimIndent()

    /** `_file_input_state`：单个 input（按 index 定位）的运行时状态。 */
    val FILE_INPUT_STATE_FN = """
function(index) {
  const el = document.querySelectorAll('input[type="file"]')[index];
  if (!el) return null;
  const style = window.getComputedStyle(el);
  const rect = el.getBoundingClientRect();
  return {
    value: el.value || '',
    filesLength: el.files ? el.files.length : null,
    accept: el.getAttribute('accept') || '',
    multiple: !!el.multiple,
    disabled: !!el.disabled,
    visible: style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0,
    width: Math.round(rect.width),
    height: Math.round(rect.height),
    id: el.id || '',
    className: String(el.className || '')
  };
}
"""

    /** `_prepare_file_input_for_upload`：把隐藏的 file input 强制置为可见可点。 */
    val PREPARE_FILE_INPUT_FN = """
function(index) {
  const el = document.querySelectorAll('input[type="file"]')[index];
  if (!el) return false;
  let current = el;
  for (let depth = 0; current && depth < 5; depth += 1, current = current.parentElement) {
    current.removeAttribute('hidden');
    current.classList.remove('ng-hide', 'hide', 'hidden');
    current.style.display = 'block';
    current.style.visibility = 'visible';
    current.style.opacity = 1;
  }
  el.removeAttribute('disabled');
  el.style.position = 'fixed';
  el.style.left = '8px';
  el.style.top = '8px';
  el.style.width = '240px';
  el.style.height = '32px';
  el.style.zIndex = 2147483647;
  return true;
}
"""

    /** `_activate_file_upload_control`：点击包裹控件触发文件选择。 */
    val ACTIVATE_FILE_UPLOAD_CONTROL_FN = """
function(index) {
  const el = document.querySelectorAll('input[type="file"]')[index];
  if (!el) return { clicked: false, reason: 'input_missing' };
  const control =
    el.closest('label,button,a,[role="button"],.btn,.btn-upload,.tn-image-uploader') ||
    el.parentElement;
  if (!control) return { clicked: false, reason: 'parent_missing' };
  const text = String(control.innerText || control.textContent || '').replace(/\s+/g, ' ').trim();
  try {
    control.scrollIntoView({ block: 'center', inline: 'center' });
    control.click();
    return { clicked: true, text, tag: control.tagName, className: String(control.className || '') };
  } catch (e) {
    return { clicked: false, text, error: String(e) };
  }
}
"""

    /** `_dispatch_file_input_events`：文件到账后派发 input/change 并触发 Angular 摘要。 */
    val DISPATCH_FILE_INPUT_EVENTS_FN = """
function(index) {
  const el = document.querySelectorAll('input[type="file"]')[index];
  if (!el) return false;
  for (const name of ['input', 'change']) {
    try {
      el.dispatchEvent(new Event(name, { bubbles: true }));
    } catch (e) {}
  }
  if (window.angular) {
    try {
      const scope = window.angular.element(el).scope();
      if (scope && scope.${'$'}applyAsync) scope.${'$'}applyAsync();
      else if (scope && scope.${'$'}apply) scope.${'$'}apply();
    } catch (e) {}
  }
  return true;
}
"""

    // ── UI 候选点击（_click_xiumi_ui_candidates） ──

    val CLICK_UI_CANDIDATES_FN = """
function(includeTerms, excludeTerms, limit) {
  const include = (includeTerms || []).map(t => String(t).toLowerCase());
  const exclude = (excludeTerms || []).map(t => String(t).toLowerCase());
  function visible(el) {
    const style = window.getComputedStyle(el);
    const rect = el.getBoundingClientRect();
    return style && style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
  }
  function haystack(el) {
    return [
      el.innerText, el.textContent, el.title, el.alt, el.getAttribute('aria-label'),
      el.id, el.className, el.getAttribute('data-title'), el.getAttribute('data-name')
    ].join(' ').toLowerCase();
  }
  const selector = [
    'button', 'a', 'label', 'li', 'span', 'i', 'em',
    '[role="button"]', '[title]', '[aria-label]', '[class*="image"]',
    '[class*="img"]', '[class*="pic"]', '[class*="upload"]'
  ].join(',');
  const candidates = Array.from(document.querySelectorAll(selector))
    .filter(el => visible(el))
    .map(el => {
      const text = haystack(el);
      let score = 0;
      let matched = false;
      for (const term of include) {
        if (!term) continue;
        if (text === term) {
          score += 20;
          matched = true;
        } else if (text.includes(term)) {
          score += 8;
          matched = true;
        }
      }
      if (!matched) return { el, score: -999, text };
      for (const term of exclude) {
        if (term && text.includes(term)) score -= 30;
      }
      const tag = el.tagName.toLowerCase();
      if (tag === 'button' || tag === 'label' || el.getAttribute('role') === 'button') score += 3;
      return { el, score, text };
    })
    .filter(item => item.score > 0)
    .sort((a, b) => b.score - a.score);
  const clickedItems = [];
  for (const item of candidates.slice(0, limit)) {
    try {
      item.el.scrollIntoView({ block: 'center', inline: 'center' });
      item.el.click();
      clickedItems.push({ score: item.score, text: item.text.slice(0, 160) });
    } catch (e) {}
  }
  return { clicked: clickedItems.length, candidates: candidates.length, items: clickedItems };
}
"""

    // ── 上传状态 ──

    /** `_xiumi_upload_messages`：页面上可见的上传相关提示。 */
    val UPLOAD_MESSAGES = """
const parts = [];
const selector = [
  '.toast', '.toast-message', '.alert', '.modal', '.tips', '.notify', '.notification',
  '[class*="toast"]', '[class*="alert"]', '[class*="message"]', '[class*="error"]',
  '[class*="notify"]', '[class*="upload"]', '[role="alert"]'
].join(',');
for (const el of Array.from(document.querySelectorAll(selector))) {
  const style = window.getComputedStyle(el);
  const rect = el.getBoundingClientRect();
  if (!style || style.display === 'none' || style.visibility === 'hidden' || rect.width <= 0 || rect.height <= 0) continue;
  const text = String(el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim();
  if (text && /上传|失败|成功|错误|cos|COS|图片|图库|稍后|超过|太大|超出|大小|尺寸|MB|不支持/.test(text)) parts.push(text.slice(0, 500));
}
if (!parts.length && document.body) {
  const body = String(document.body.innerText || document.body.textContent || '').replace(/\s+/g, ' ');
  const patterns = ['图片正在上传，请稍后再试', '上传成功', '上传失败', '上传完成', '超过', '太大', '不支持', '失败'];
  for (const pattern of patterns) {
    const index = body.indexOf(pattern);
    if (index >= 0) parts.push(body.slice(Math.max(0, index - 80), index + pattern.length + 80));
  }
}
Array.from(new Set(parts)).slice(0, 8);
""".trimIndent()

    /** `_remote_image_sources_ordered`：页面中所有远程图片 src（含 CSS 背景）。 */
    val REMOTE_IMAGE_SOURCES = """
const values = [];
for (const img of Array.from(document.querySelectorAll('img'))) {
  values.push(img.getAttribute('src') || '');
}
for (const el of Array.from(document.querySelectorAll('*'))) {
  const bg = window.getComputedStyle(el).backgroundImage || '';
  const match = bg.match(/url\(["']?([^"')]+)["']?\)/i);
  if (match) values.push(match[1]);
}
values.filter(src => new RegExp('^(https?:)?//', 'i').test(src));
""".trimIndent()

    // ── 模型构建 / 脏标记 ──

    /** `_build_xiumi_comps_from_blocks`：在模型层直接构建 comps.items（样式全保留）。 */
    val BUILD_COMPS_FROM_BLOCKS_FN = """
function(BLOCKS) {
  const editable = Array.from(document.querySelectorAll('[contenteditable="true"]')).find(e => e.offsetWidth > 0);
  if (!editable) return { ok: false, err: 'no editable' };
  let scope = null;
  let node = editable;
  while (node) {
    try { const s = window.angular.element(node).scope(); if (s && s.cell) { scope = s; break; } } catch(e) {}
    node = node.parentElement;
  }
  if (!scope) return { ok: false, err: 'no scope' };
  const ds = scope._$;
  const layer = ds.pages[0].layers[0];
  const newComps = BLOCKS.map((b, i) => ({
    _comp: {
      constraint: { opMenu: { "text-merged": true }, pose: { resize: "h" } },
      pose: { position: "static", width: null, height: null },
      style: {},
      tplId: "paper-cp:header/1-txt-normal",
      _${'$'}uuid: "comp-" + Date.now().toString(36) + i,    },
    txt1: { type: "text", text: b.text, style: b.style },
  }));
  const run = function () {
    layer.comps = { type: "group", constraint: { childLayout: "static" }, items: newComps };
    if (layer._qiBlock) layer._qiBlock.items = [];
  };
  if (scope.${'$'}apply) { scope.${'$'}apply(run); }
  else { run(); }
  return { ok: true, compCount: newComps.length };
}
"""

    /** `_mark_xiumi_document_dirty`：标记文档有改动，确保保存按钮可用。 */
    val MARK_DOCUMENT_DIRTY = """
(() => {
  function findSaveScope() {
    var btn = document.querySelector('button.btn-img.op-btn.save');
    if (!btn || !window.angular) return null;
    var s = window.angular.element(btn).scope();
    while (s && typeof s.onBtnClickSave !== 'function') s = s.${'$'}parent;
    return s || null;
  }
  var scope = findSaveScope();
  var out = { applied: false, dirty: null, canUndo: null, empty: null };
  if (!scope) return out;
  try {
    if (scope.${'$'}apply) {
      scope.${'$'}apply(function () {
        if (scope.undoStatus) {
          scope.undoStatus.isDirty = true;
          scope.undoStatus.canUndo = true;
        }
        if (scope.status && scope.status.show) {
          scope.status.show.empty = false;
        }
      });
    } else {
      if (scope.undoStatus) {
        scope.undoStatus.isDirty = true;
        scope.undoStatus.canUndo = true;
      }
      if (scope.status && scope.status.show) {
        scope.status.show.empty = false;
      }
    }
    out.applied = true;
  } catch (e) {
    out.error = String(e);
  }
  out.dirty = scope.undoStatus ? scope.undoStatus.isDirty : null;
  out.canUndo = scope.undoStatus ? scope.undoStatus.canUndo : null;
  out.empty = scope.status && scope.status.show ? scope.status.show.empty : null;
  return out;
})();
"""

    /** `_read_xiumi_comp_image_srcs`：模型 comps 中已渲染图片的 src。 */
    val READ_COMP_IMAGE_SRCS = """
(() => {
  const out = [];
  const editable = Array.from(document.querySelectorAll('[contenteditable="true"]')).find(e => e.offsetWidth > 0);
  if (!editable) return out;
  let node = editable, scope = null;
  while (node) {
    try { const s = window.angular.element(node).scope(); if (s && s.cell) { scope = s; break; } } catch(e) {}
    node = node.parentElement;
  }
  if (scope) {
    const items = (scope._$.pages[0].layers[0].comps.items) || [];
    for (const c of items) {
      if (c.img1) {
        const src = c.img1.src || c.img1.url || '';
        if (src) out.push(src);
      }
    }
  }
  return out;
})();
"""

    /** `_log_xiumi_editor_image_order` 的查询部分：各 editable 内图片与期望 URL 的匹配。 */
    val EDITOR_IMAGE_ORDER_FN = """
function(expected) {
  const editables = Array.from(document.querySelectorAll('[contenteditable="true"]'));
  function srcsFor(el) {
    return Array.from(el.querySelectorAll('img')).map(img => img.getAttribute('src') || '').filter(Boolean);
  }
  return editables.map((el, index) => {
    const rect = el.getBoundingClientRect();
    const srcs = srcsFor(el);
    const matches = srcs.filter(src => expected.includes(src)).length;
    return {
      index,
      width: Math.round(rect.width),
      height: Math.round(rect.height),
      image_count: srcs.length,
      expected_matches: matches,
      text: String(el.innerText || el.textContent || '').replace(/\s+/g, ' ').slice(0, 120),
      srcs: srcs.map(src => src.length > 180 ? src.slice(0, 177) + '...' : src)
    };
  });
}
"""
}
