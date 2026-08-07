import json
import pathlib
import sys
import time

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from all_to_xiumi.browser import get_selenium_browser_name, make_browser_options, make_webdriver

PROFILE = str(REPO_ROOT / "output/selenium_cache/xiumi-profile-persist")
DRAFT = sys.argv[1] if len(sys.argv) > 1 else ""

name = get_selenium_browser_name()
opts = make_browser_options(name, PROFILE, headless=True)
browser = make_webdriver(name, opts)
try:
    browser.get(DRAFT)
    time.sleep(10)
    d = browser.execute_script(
        """
const out = { url: location.href, renderImgs: [] };
const editable = Array.from(document.querySelectorAll('[contenteditable="true"]')).find(e => e.offsetWidth > 0);
if (editable) {
  out.renderImgs = Array.from(editable.querySelectorAll('img')).map(i => {
    const r = i.getBoundingClientRect();
    return { src: (i.getAttribute('src')||'').slice(0,70), w: Math.round(r.width), h: Math.round(r.height) };
  });
}
return out;
"""
    )
    print("STATE=" + json.dumps(d, ensure_ascii=False, indent=1), flush=True)
finally:
    try:
        browser.quit()
    except Exception:
        pass
