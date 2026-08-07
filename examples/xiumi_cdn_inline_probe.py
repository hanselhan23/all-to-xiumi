import json
import pathlib
import sys
import time

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from all_to_xiumi import xiumi_publish as mod
from all_to_xiumi.browser import get_selenium_browser_name, make_browser_options, make_webdriver

PROFILE = str(REPO_ROOT / "output/selenium_cache/xiumi-profile-persist")
EDITOR = "https://xiumi.us/studio/v5?lang=zh_CN#/paper/for/new/cube/0"
LOGO = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else REPO_ROOT / "examples/example_logo.png"
mod._wait_for_user_before_closing_browser = lambda: None


def read_model(browser):
    return browser.execute_script(
        """
const out = { comps: [] };
const editable = Array.from(document.querySelectorAll('[contenteditable="true"]')).find(e => e.offsetWidth > 0);
if (!editable) return out;
let node = editable, scope = null;
while (node) {
  try { const s = window.angular.element(node).scope(); if (s && s.cell) { scope = s; break; } } catch(e) {}
  node = node.parentElement;
}
if (scope) {
  const items = (scope._$.pages[0].layers[0].comps.items) || [];
  out.comps = items.map(c => ({
    tplId: c._comp ? c._comp.tplId : '',
    txt: c.txt1 ? (c.txt1.text || '').slice(0, 90) : null,
    imgSrc: c.img1 ? (c.img1.src || c.img1.url || '') : null,
  }));
}
return out;
"""
    )


def read_render_imgs(browser):
    return browser.execute_script(
        """
const out = { imgs: [] };
const editable = Array.from(document.querySelectorAll('[contenteditable="true"]')).find(e => e.offsetWidth > 0);
if (editable) {
  out.imgs = Array.from(editable.querySelectorAll('img')).map(i => {
    const r = i.getBoundingClientRect();
    return { src: (i.getAttribute('src')||'').slice(0,70), w: Math.round(r.width), h: Math.round(r.height) };
  });
}
return out;
"""
    )


name = get_selenium_browser_name()
opts = make_browser_options(name, PROFILE, headless=True)
browser = make_webdriver(name, opts)
try:
    data_url = mod._image_file_to_data_url(LOGO)
    browser.get(EDITOR)
    time.sleep(6)
    mod._paste_xiumi_html(
        browser,
        '<section><p>logo</p><img src="%s" style="width:140px;"><p>end</p></section>' % data_url,
    )
    print("PASTE_OK", flush=True)
    time.sleep(6)
    print("AFTER_PASTE=" + json.dumps(read_model(browser), ensure_ascii=False), flush=True)

    # 从 image comp 拿 CDN URL
    cdn = None
    model = read_model(browser)
    for c in model.get("comps", []):
        if c.get("imgSrc"):
            cdn = c["imgSrc"]
    print("CDN_URL=" + (cdn or "NONE"), flush=True)
    if not cdn:
        sys.exit(3)

    # 用 CDN URL 构建含 img 的 text block
    mod._paste_xiumi_html(browser, "<section><p>seed</p></section>")
    time.sleep(2)
    block = {
        "style": {"background": "linear-gradient(90deg,#F3CD7C,#E3A524,#BE8413)", "borderRadius": "6px", "textAlign": "center", "padding": "30px 18px"},
        "text": (
            '<p style="margin:0 0 12px;text-align:center;"><img src="__SRC__" alt="物理系" '
            'style="width:200px;height:auto;display:inline-block;vertical-align:middle;max-width:100%;"></p>'
            '<p style="font-size:38px;color:#FFFFFF;font-weight:800;margin:0;">物理迎新志愿者招募</p>'
        ).replace("__SRC__", cdn),
    }
    ok = mod._build_xiumi_comps_from_blocks(browser, [block])
    print("BUILD_OK=" + json.dumps(ok), flush=True)
    time.sleep(3)
    print("RENDER_BEFORE_SAVE=" + json.dumps(read_render_imgs(browser), ensure_ascii=False), flush=True)

    mod._mark_xiumi_document_dirty(browser)
    browser.execute_script("document.querySelector('button.btn-img.op-btn.save').click();")
    print("SAVE_CLICKED", flush=True)
    time.sleep(8)
    saved_url = browser.current_url
    print("SAVED_URL=" + saved_url, flush=True)
finally:
    try:
        browser.quit()
    except Exception:
        pass
