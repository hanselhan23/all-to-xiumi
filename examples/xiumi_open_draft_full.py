import json
import os
import pathlib
import sys
import time

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from all_to_xiumi.browser import get_selenium_browser_name, make_browser_options, make_webdriver

PROFILE = os.environ.get("XIUMI_PROFILE_DIR") or str(REPO_ROOT / "output/selenium_cache/xiumi-profile-persist")
DRAFT_URL = sys.argv[1] if len(sys.argv) > 1 else ""

name = get_selenium_browser_name()
opts = make_browser_options(name, PROFILE, headless=True)
browser = make_webdriver(name, opts)
try:
    browser.get("https://xiumi.us/studio/v5?lang=zh_CN#/paper/for/new/cube/0")
    time.sleep(3)
    browser.execute_script(
        """
window.__respLog = [];
const origOpen = XMLHttpRequest.prototype.open;
const origSend = XMLHttpRequest.prototype.send;
XMLHttpRequest.prototype.open = function(m, u) { this.__m = m; this.__u = String(u); return origOpen.apply(this, arguments); };
XMLHttpRequest.prototype.send = function(body) {
  const xhr = this;
  const rec = { url: xhr.__u, method: xhr.__m, respLen: 0, resp: null };
  window.__respLog.push(rec);
  xhr.addEventListener('load', function() {
    try {
      rec.respLen = (xhr.responseText || '').length;
      if (xhr.__u.indexOf('data/editing') >= 0) rec.resp = xhr.responseText;
      else rec.resp = (xhr.responseText || '').slice(0, 200);
    } catch(e) {}
  });
  return origSend.apply(this, arguments);
};
return 'hooked';
"""
    )
    browser.get(DRAFT_URL)
    print("OPENED", flush=True)
    time.sleep(12)

    data = browser.execute_script(
        """
const reqs = window.__respLog || [];
const editing = reqs.filter(r => r.url.indexOf('data/editing') >= 0);
const bodyText = (document.body ? document.body.innerText : '') || '';
const cebs = Array.from(document.querySelectorAll('[contenteditable="true"]'));
return {
  url: location.href,
  bodyTextHead: bodyText.replace(/\\s+/g,' ').slice(0, 300),
  editableCount: cebs.length,
  editableTexts: cebs.map(e => (e.innerText||'').replace(/\\s+/g,' ').slice(0, 120)),
  editorContainers: Array.from(document.querySelectorAll('[class*="editor"], .tn-container, [class*="page-container"], [class*="tn-page"]'))
    .slice(0, 5).map(e => ({ cls: String(e.className).slice(0, 100), text: (e.innerText||'').replace(/\\s+/g,' ').slice(0, 60) })),
  editingRespLen: editing.length ? editing[0].respLen : null,
  editingResp: editing.length ? editing[0].resp : null,
};
"""
    )
    print("FULL=" + json.dumps(data, ensure_ascii=False, indent=1), flush=True)
    if len(sys.argv) > 2:
        out = str(REPO_ROOT / "output" / sys.argv[2])
        with open(out, "w", encoding="utf-8") as f:
            f.write(json.dumps(data, ensure_ascii=False, indent=1))
        print("WROTE=" + out, flush=True)
finally:
    try:
        browser.quit()
    except Exception:
        pass
