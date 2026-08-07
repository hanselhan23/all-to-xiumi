import argparse
import base64
import json
import mimetypes
import os
import pathlib
import re
import shutil
import sys
import tempfile
import time
import traceback

from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from . import config
from .browser import browser_supports_profile_dir, get_selenium_browser_name, make_browser_options, make_webdriver
from .image_paths import clean_markdown_image_target, resolve_existing_image_path

_XIUMI_DEBUG_LOG_PATH = None


def _configure_console():
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def _xiumi_debug_log_path() -> pathlib.Path:
    global _XIUMI_DEBUG_LOG_PATH
    if _XIUMI_DEBUG_LOG_PATH is None:
        log_dir = ROOT / "output" / "xiumi_debug"
        log_dir.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d_%H%M%S")
        _XIUMI_DEBUG_LOG_PATH = log_dir / f"xiumi_upload_{stamp}.jsonl"
    return _XIUMI_DEBUG_LOG_PATH


def _log_xiumi_debug(event: str, **data):
    try:
        payload = {
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "event": event,
            **data,
        }
        path = _xiumi_debug_log_path()
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")
    except Exception:
        pass


def _print_xiumi_image_progress(message: str):
    print(f"秀米：正文图片{message}", flush=True)


def _extract_main_html(html_text: str) -> str:
    match = re.search(r"<main[^>]*class=[\"'][^\"']*page[^\"']*[\"'][^>]*>([\s\S]*?)</main>", html_text or "", flags=re.I)
    if match:
        return match.group(1).strip()
    match = re.search(r"<body[^>]*>([\s\S]*?)</body>", html_text or "", flags=re.I)
    if match:
        return match.group(1).strip()
    return (html_text or "").strip()


def _resolve_content_paths(html_path: pathlib.Path, markdown_override: str = "") -> tuple[str, pathlib.Path]:
    """Extract content HTML from the html file; use a sibling/override markdown file only
    as the image base path (so relative local images resolve). Markdown→HTML conversion
    happens upstream (markdown_to_html); this publish core is HTML-driven.
    """
    markdown_path = pathlib.Path(markdown_override).resolve() if markdown_override else html_path.with_suffix(".md")
    html_text = html_path.read_text(encoding="utf-8")
    content_html = _extract_main_html(html_text)
    if markdown_path.exists():
        _log_xiumi_debug("xiumi_source_markdown", path=str(markdown_path))
        return content_html, markdown_path
    _log_xiumi_debug("xiumi_source_html", path=str(html_path))
    return content_html, html_path


def _guess_mime_type(path: pathlib.Path) -> str:
    return mimetypes.guess_type(str(path))[0] or "application/octet-stream"


def _image_file_to_data_url(path: pathlib.Path) -> str:
    mime_type = _guess_mime_type(path)
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{data}"


def _apply_xiumi_base_format(html_text: str) -> str:
    """Post-process Xiumi content HTML to align with the base format defined in format.md.

    format.md specifies:
      - title:  h1 tag, font-size 18px
      - paragraph: font-size 14px, line-height 1.6, letter-spacing 0,
                   margin-left 0, margin-right 0
    """

    def _fix_h1_style(match):
        before_attrs = match.group(1)
        style = match.group(2)
        after_attrs = match.group(3)
        style = re.sub(r"font-size:\s*\d+px", "font-size:18px", style)
        return f"<h1{before_attrs}style=\"{style}\"{after_attrs}>"

    def _fix_p_style(match):
        before_attrs = match.group(1)
        style = match.group(2)
        after_attrs = match.group(3)

        # Split into individual CSS declarations and process each
        raw_decls = [d.strip() for d in style.split(";") if d.strip()]
        new_decls = []
        margin_top = margin_bottom = None
        seen_font_size = seen_line_height = seen_letter_spacing = False

        for decl in raw_decls:
            if ":" not in decl:
                new_decls.append(decl)
                continue
            name, value = decl.split(":", 1)
            name = name.strip()
            value = value.strip()

            if name == "font-size":
                value = "14px"
                seen_font_size = True
            elif name == "line-height":
                value = "1.6"
                seen_line_height = True
            elif name == "letter-spacing":
                value = "0px"
                seen_letter_spacing = True
            elif name == "margin-left":
                value = "0px"
            elif name == "margin-right":
                value = "0px"
            elif name == "margin":
                parts = value.split()
                n = len(parts)
                if n == 1:
                    margin_top = margin_bottom = parts[0]
                elif n == 2:
                    margin_top = margin_bottom = parts[0]
                elif n == 3:
                    margin_top = parts[0]
                    margin_bottom = parts[2]
                elif n >= 4:
                    margin_top = parts[0]
                    margin_bottom = parts[2]
                # Decompose shorthand → explicit longhands so we can
                # enforce margin-left/right = 0 while preserving top/bottom.
                continue  # skip the shorthand itself

            new_decls.append(f"{name}:{value}")

        # Always emit the base-format paragraph properties
        if not seen_font_size:
            new_decls.append("font-size:14px")
        if not seen_line_height:
            new_decls.append("line-height:1.6")
        if not seen_letter_spacing:
            new_decls.append("letter-spacing:0px")
        if margin_top is not None:
            new_decls.append(f"margin-top:{margin_top}")
            new_decls.append(f"margin-bottom:{margin_bottom or margin_top}")
        new_decls.append("margin-left:0px")
        new_decls.append("margin-right:0px")

        new_style = ";".join(new_decls)
        return f"<p{before_attrs}style=\"{new_style}\"{after_attrs}>"

    html_text = re.sub(
        r"<h1\b([^>]*?)style=\"([^\"]*)\"([^>]*)>",
        _fix_h1_style,
        html_text,
    )
    html_text = re.sub(
        r"<p\b([^>]*?)style=\"([^\"]*)\"([^>]*)>",
        _fix_p_style,
        html_text,
    )
    return html_text


def _inline_local_images(html_text: str, asset_base_path: pathlib.Path) -> str:
    def repl(match):
        quote = match.group(1)
        src = (match.group(2) or "").strip()
        if not src or re.match(r"^(?:https?:)?//|^data:", src, flags=re.I):
            return match.group(0)
        cleaned = src.split("?", 1)[0].strip().strip("'").strip('"')
        candidate = pathlib.Path(cleaned)
        if not candidate.is_absolute():
            candidate = (asset_base_path.parent / candidate).resolve()
        if not candidate.exists():
            return match.group(0)
        data_url = _image_file_to_data_url(candidate)
        return f'src={quote}{data_url}{quote}'

    return re.sub(r"src=(['\"])(.*?)\1", repl, html_text or "", flags=re.I)


def _is_remote_image_src(src: str) -> bool:
    return bool(re.match(r"^(?:https?:)?//", str(src or ""), flags=re.I))


def _is_data_image_src(src: str) -> bool:
    return str(src or "").startswith("data:")


def _image_payload_stats(html_text: str) -> dict:
    srcs = re.findall(r"<img\b[^>]*\bsrc=(['\"])(.*?)\1", html_text or "", flags=re.I)
    data_urls = [src for _quote, src in srcs if _is_data_image_src(src)]
    local_urls = [
        src
        for _quote, src in srcs
        if src and not _is_data_image_src(src) and not _is_remote_image_src(src)
    ]
    return {
        "html_chars": len(html_text or ""),
        "image_count": len(srcs),
        "data_image_count": len(data_urls),
        "local_image_count": len(local_urls),
        "data_image_chars": sum(len(src) for src in data_urls),
    }


def _local_image_sources(html_text: str) -> list[str]:
    srcs = re.findall(r"<img\b[^>]*\bsrc=(['\"])(.*?)\1", html_text or "", flags=re.I)
    return [
        src
        for _quote, src in srcs
        if src and not _is_data_image_src(src) and not _is_remote_image_src(src)
    ]


def _remove_images_for_xiumi(html_text: str) -> str:
    removed = 0

    def repl(match):
        nonlocal removed
        removed += 1
        return "<p style=\"margin:8px 0;color:#8a7c58;font-size:14px;\">[配图已保留在本地 HTML，秀米草稿中未自动内联]</p>"

    cleaned = re.sub(r"<img\b[^>]*>", repl, html_text or "", flags=re.I)
    cleaned = re.sub(r"<section\b([^>]*)>\s*(?:<p[^>]*>\[配图已保留在本地 HTML，秀米草稿中未自动内联\]</p>\s*)+</section>", "", cleaned, flags=re.I)
    _log_xiumi_debug("xiumi_image_mode_omit_count", removed=removed)
    return cleaned


def _remove_unuploaded_images_for_xiumi(html_text: str) -> str:
    removed = 0

    def repl(match):
        nonlocal removed
        tag = match.group(0)
        src_match = re.search(r"\bsrc=(['\"])(.*?)\1", tag, flags=re.I)
        src = (src_match.group(2) if src_match else "").strip()
        if src and _is_remote_image_src(src):
            return tag
        removed += 1
        return "<p style=\"margin:8px 0;color:#8a7c58;font-size:14px;\">[配图上传未完成，请在秀米图库中手动补充]</p>"

    cleaned = re.sub(r"<img\b[^>]*>", repl, html_text or "", flags=re.I)
    _log_xiumi_debug("xiumi_unuploaded_image_omit_count", removed=removed)
    return cleaned


def _replace_images_with_placeholders_for_xiumi(html_text: str) -> str:
    mode = str(getattr(config, "XIUMI_IMAGE_MODE", "upload") or "upload").strip().lower()
    if mode != "upload":
        return html_text

    index = 0

    def repl(match):
        nonlocal index
        index += 1
        return (
            "<p "
            f"data-wanyou-image-placeholder=\"{index}\" "
            "style=\"margin:8px 0;color:#8a7c58;font-size:14px;\">"
            "[配图上传中]"
            "</p>"
        )

    prepared = re.sub(r"<img\b[^>]*>", repl, html_text or "", flags=re.I)
    if index:
        _log_xiumi_debug("text_first_image_placeholders", count=index)
    return prepared


def _prepare_xiumi_images(html_text: str, asset_base_path: pathlib.Path) -> str:
    mode = str(getattr(config, "XIUMI_IMAGE_MODE", "upload") or "upload").strip().lower()
    if mode not in {"upload", "auto", "inline", "omit"}:
        mode = "upload"

    before = _image_payload_stats(html_text)
    _log_xiumi_debug("xiumi_image_payload_before", **before)

    if mode == "omit":
        _log_xiumi_debug("xiumi_image_mode", mode="omit")
        return _remove_images_for_xiumi(html_text)

    if mode == "upload":
        local_images = _local_image_sources(html_text)
        data_images = before["data_image_count"]
        if local_images or data_images:
            _log_xiumi_debug("xiumi_image_mode", mode="upload_pending", local_images=len(local_images), data_images=data_images)
            return html_text
        _log_xiumi_debug("xiumi_image_mode", mode="upload_no_images")
        return html_text

    inlined = _inline_local_images(html_text, asset_base_path)
    after = _image_payload_stats(inlined)
    _log_xiumi_debug("xiumi_image_payload_after_inline", **after)

    max_chars = int(getattr(config, "XIUMI_MAX_INLINE_IMAGE_HTML_CHARS", 900000) or 0)
    if mode == "auto" and max_chars and after["html_chars"] > max_chars:
        _log_xiumi_debug("xiumi_image_mode", mode="auto_omit", html_chars=after["html_chars"], max_chars=max_chars)
        return _remove_images_for_xiumi(html_text)

    _log_xiumi_debug("xiumi_image_mode", mode=f"{mode}_inline")
    return inlined


def _promote_headings_for_xiumi(html_text: str) -> str:
    """Turn large-font paragraphs into h1/h2/h3 so Xiumi keeps heading hierarchy.

    Xiumi's paste handler strips inline font-size but maps h1/h2/h3 to
    semantic font-size (180%/140%/120%). Without this, a 38px <p> title would
    collapse to the default 16px after paste.
    """

    def repl(match):
        before_attrs = match.group(1)
        style = match.group(2)
        after_attrs = match.group(3)
        content = match.group(4)
        size_m = re.search(r"font-size:\s*(\d+)px", style)
        size = int(size_m.group(1)) if size_m else 0
        align_m = re.search(r"text-align:\s*(center|left|right)", style)
        align = align_m.group(1) if align_m else None
        weight_m = re.search(r"font-weight:\s*(700|800|bold)", style)
        bold = bool(weight_m)
        if size >= 34:
            tag = "h1"
        elif size >= 20:
            tag = "h2"
        elif size >= 17 and bold:
            tag = "h3"
        else:
            return match.group(0)
        decls = []
        if align:
            decls.append("text-align:%s" % align)
        if tag in ("h1", "h2"):
            decls.append("letter-spacing:2px")
        new_style = ";".join(decls)
        return "<%s style=\"%s\"%s>%s</%s>" % (tag, new_style, after_attrs, content, tag)

    return re.sub(
        r"<p\b([^>]*?)style=\"([^\"]*)\"([^>]*)>([\s\S]*?)</p>",
        repl,
        html_text,
        flags=re.I,
    )


_XIUMI_WS = re.compile(r"\s+")


def _xiumi_camelize_css(css_text: str) -> dict:
    out = {}
    for decl in (css_text or "").split(";"):
        decl = decl.strip()
        if not decl or ":" not in decl:
            continue
        prop, _, val = decl.partition(":")
        prop = prop.strip().lower()
        val = val.strip()
        if not prop or not val or prop == "box-sizing":
            continue
        parts = prop.split("-")
        camel = parts[0] + "".join(p.capitalize() for p in parts[1:])
        out[camel] = val
    return out


def _xiumi_flatten_inner_html(inner: str) -> str:
    """把嵌套 section/div 转成 <p>（保留其 style），只留 p/span/br/strong 与文本。

    浏览器 HTML 解析器会自行闭合嵌套的 <p>（section 里既有 span 又有 p 的
    结构转 p 后正好被自动纠正成 <p><span>chip</span></p><p>正文</p>）。
    转换产生的空 <p></p> 会被清掉，避免卡片顶部多空行。
    """

    def _tag(tag):
        def repl(match):
            attrs = match.group(1).strip()
            return "<%s%s>" % (tag, (" " + attrs) if attrs else "")

        return repl

    html = re.sub(r"<!--[\s\S]*?-->", "", inner or "")
    html = re.sub(r"<section\b([^>]*)>", _tag("p"), html, flags=re.I)
    html = re.sub(r"</section>", "</p>", html, flags=re.I)
    html = re.sub(r"<div\b([^>]*)>", _tag("p"), html, flags=re.I)
    html = re.sub(r"</div>", "</p>", html, flags=re.I)
    html = _XIUMI_WS.sub(" ", html)
    html = re.sub(r"<p>\s*</p>", "", html)
    return html.strip()


def _xiumi_html_to_blocks(html_text: str) -> list[dict]:
    """把设计稿 HTML 拆成 {style, text} 块：每个顶层 <section> 对应一个块。

    Xiumi 的粘贴处理器会剥掉颜色/背景/边框等行内样式；直接往模型的
    comps.items[].txt1.style（camelCase CSS）和 txt1.text（带行内样式的
    HTML）写这些样式，渲染层和保存都会原样保留（已验证）。
    """
    m = re.search(r"<main[^>]*class=[\"']page[\"'][^>]*>([\s\S]*?)</main>", html_text, flags=re.I)
    frag = m.group(1) if m else html_text

    tag_re = re.compile(r"<(/?)section\b[^>]*>", flags=re.I)
    depth = 0
    cur_start = None
    cur_attrs = ""
    blocks = []
    for tm in tag_re.finditer(frag):
        if not tm.group(1):  # opening
            if depth == 0:
                cur_start = tm.end()
                attrs_m = re.search(r"style=[\"']([^\"']*)[\"']", tm.group(0), flags=re.I)
                cur_attrs = attrs_m.group(1) if attrs_m else ""
            depth += 1
        else:  # closing
            depth -= 1
            if depth == 0 and cur_start is not None:
                inner = frag[cur_start:tm.start()]
                text = _xiumi_flatten_inner_html(inner)
                if not text:
                    text = "<p><br></p>"
                blocks.append({"style": _xiumi_camelize_css(cur_attrs), "text": text})
                cur_start = None
    return blocks


def _first_heading(markdown_text: str) -> str:
    for line in (markdown_text or "").splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
    return ""


def _first_summary_line(markdown_text: str) -> str:
    for line in (markdown_text or "").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            continue
        if stripped.startswith("!"):
            continue
        stripped = re.sub(r"\s+", " ", stripped)
        return stripped[:120]
    return ""


def _make_xiumi_browser(profile_dir: pathlib.Path):
    os.makedirs(config.SELENIUM_CACHE_DIR, exist_ok=True)
    os.environ.setdefault("SE_CACHE_PATH", os.path.abspath(config.SELENIUM_CACHE_DIR))

    browser_name = get_selenium_browser_name()
    if browser_supports_profile_dir(browser_name):
        profile_dir.mkdir(parents=True, exist_ok=True)
    options = make_browser_options(browser_name, str(profile_dir), headless=False, detach=False)
    browser = make_webdriver(browser_name, options)
    browser._wanyou_browser_name = browser_name
    if getattr(config, "PAGE_LOAD_TIMEOUT", 0):
        browser.set_page_load_timeout(config.PAGE_LOAD_TIMEOUT)
    return browser


def _cleanup_profile_dir(profile_dir: pathlib.Path, retries: int = 5, delay_seconds: float = 1.0) -> bool:
    if not profile_dir.exists():
        return True
    for _ in range(max(1, retries)):
        try:
            shutil.rmtree(profile_dir)
            return True
        except Exception:
            time.sleep(delay_seconds)
    return not profile_dir.exists()


def _wait_for_user_before_closing_browser():
    if not getattr(sys.stdin, "isatty", lambda: False)():
        print("秀米：当前不是交互式命令行，跳过编辑等待并关闭浏览器。")
        return
    print("秀米：浏览器将保持打开，方便你继续检查或微调。确认已在秀米保存后，回到命令行按回车关闭浏览器并结束程序。")
    try:
        input()
    except EOFError:
        print("秀米：命令行输入已关闭，继续关闭浏览器。")


def _wait_editor_ready(browser, timeout: int):
    WebDriverWait(browser, timeout).until(lambda d: d.execute_script("return document.readyState") == "complete")
    WebDriverWait(browser, timeout).until(lambda d: len(d.find_elements(By.CSS_SELECTOR, "button.btn-img.op-btn.save")) > 0)
    WebDriverWait(browser, timeout).until(lambda d: len(d.find_elements(By.XPATH, '//*[@contenteditable="true"]')) > 0)


def _visible_login_links(browser):
    links = []
    selectors = [
        (By.CSS_SELECTOR, "a.usr-sign-in"),
        (By.XPATH, "//*[self::a or self::button][contains(normalize-space(.), '登录') or contains(normalize-space(.), '登陆')]"),
    ]
    for by, value in selectors:
        for el in browser.find_elements(by, value):
            try:
                if el.is_displayed() and el not in links:
                    links.append(el)
            except Exception:
                continue
    return links


def _visible_header_login_links(browser):
    script = """
const out = [];
const viewportH = window.innerHeight || document.documentElement.clientHeight || 900;
const viewportW = window.innerWidth || document.documentElement.clientWidth || 1200;
for (const el of Array.from(document.querySelectorAll('a,button,[role="button"]'))) {
  const text = String(el.innerText || el.textContent || '').replace(/\\s+/g, ' ').trim();
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
return out;
"""
    try:
        return browser.execute_script(script) or []
    except Exception:
        return []


def _visible_login_controls(browser):
    script = """
const out = [];
for (const el of Array.from(document.querySelectorAll('a,button,[role="button"],.usr-sign-in'))) {
  const text = String(el.innerText || el.textContent || el.getAttribute('aria-label') || el.getAttribute('title') || '').replace(/\\s+/g, ' ').trim();
  if (!/(登录|登陆|注册)/.test(text)) continue;
  if (/(登录中|正在登录|退出登录|退出登陆)/.test(text)) continue;
  const style = window.getComputedStyle(el);
  const rect = el.getBoundingClientRect();
  const visible = style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
  if (!visible) continue;
  out.push({ text, top: Math.round(rect.top), left: Math.round(rect.left), width: Math.round(rect.width), height: Math.round(rect.height) });
}
return out;
"""
    try:
        return browser.execute_script(script) or []
    except Exception:
        return []


def _xiumi_login_state(browser) -> dict:
    controls = _visible_login_controls(browser)
    header_controls = _visible_header_login_links(browser)
    excerpt = _page_excerpt(browser, 500)
    if not controls and re.search(r"(?<!退出)(登录|登陆|注册)", excerpt) and not re.search(r"(登录中|正在登录|退出登录|退出登陆)", excerpt):
        controls = [{"text": "登录", "source": "body_excerpt"}]
    has_paper_entry = _xiumi_home_has_paper_entry(browser)
    settling = _xiumi_login_is_settling(browser)
    try:
        has_editor = (
            len(browser.find_elements(By.CSS_SELECTOR, "button.btn-img.op-btn.save")) > 0
            and len(browser.find_elements(By.XPATH, '//*[@contenteditable="true"]')) > 0
        )
    except Exception:
        has_editor = False
    authenticated = (has_paper_entry or has_editor) and not controls and not header_controls and not settling
    return {
        "authenticated": authenticated,
        "has_paper_entry": has_paper_entry,
        "has_editor": has_editor,
        "settling": settling,
        "login_controls": controls,
        "header_login_controls": header_controls,
        "url": getattr(browser, "current_url", ""),
        "excerpt": excerpt,
    }


def _wait_for_manual_login(browser, timeout: int):
    links = _visible_login_links(browser)
    if links:
        try:
            links[0].click()
        except Exception:
            pass

    is_interactive = getattr(sys.stdin, "isatty", lambda: False)()

    if is_interactive:
        try:
            browser.execute_script("window.focus();")
        except Exception:
            pass
        print("秀米：浏览器已打开登录页面，请在浏览器中完成登录。")
        print("秀米：登录完成后回到终端按回车继续 —— 程序会验证登录状态后自动执行后续步骤。")
        try:
            input()
        except EOFError:
            pass
        state = _xiumi_login_state(browser)
        if state.get("authenticated"):
            _log_xiumi_debug("xiumi_manual_login_confirmed", state=state)
            return True
        print("秀米：未检测到登录状态，继续等待自动检测...")

    print("秀米：正在自动检测登录状态，请在浏览器中完成登录。")
    deadline = time.time() + timeout
    while time.time() < deadline:
        state = _xiumi_login_state(browser)
        if state.get("authenticated"):
            _log_xiumi_debug("xiumi_manual_login_confirmed", state=state)
            return True
        time.sleep(1)
    _log_xiumi_debug("xiumi_manual_login_timeout", state=_xiumi_login_state(browser))
    return False


def _ensure_xiumi_logged_in_before_edit(browser, context: str):
    state = _xiumi_login_state(browser)
    _log_xiumi_debug("xiumi_login_guard", context=context, state=state)
    if state.get("authenticated"):
        return
    controls = state.get("login_controls") or state.get("header_login_controls") or []
    if controls:
        raise RuntimeError(f"秀米尚未登录，页面仍显示登录入口，已停止自动编辑。context={context}")
    raise RuntimeError(f"秀米登录状态未确认，已停止自动编辑。context={context}")


def _page_excerpt(browser, limit: int = 300) -> str:
    try:
        text = browser.execute_script("return document.body ? document.body.innerText : '';") or ""
    except Exception:
        return ""
    return re.sub(r"\s+", " ", str(text)).strip()[:limit]


def _xiumi_login_is_settling(browser) -> bool:
    excerpt = _page_excerpt(browser, 500)
    settling_terms = ["正在登录", "登录中"]
    return any(term in excerpt for term in settling_terms)


def _xiumi_home_has_paper_entry(browser) -> bool:
    try:
        text = browser.execute_script("return document.body ? document.body.innerText : '';") or ""
    except Exception:
        return False
    normalized = re.sub(r"\s+", " ", str(text))
    return "我的秀米" in normalized and "图文排版" in normalized


def _wait_until_xiumi_home_settled(browser, timeout: int) -> bool:
    deadline = time.time() + max(5, timeout)
    while time.time() < deadline:
        state = _xiumi_login_state(browser)
        if state.get("authenticated"):
            _log_xiumi_debug("xiumi_home_settled", state=state)
            return True
        time.sleep(1)
    _log_xiumi_debug("xiumi_home_not_settled", state=_xiumi_login_state(browser))
    return False


def _is_xiumi_editor_url(url: str) -> bool:
    return bool(url and re.search(r"#/paper/", url or ""))


def _wait_for_editor_loaded(browser, timeout: int) -> bool:
    """等编辑器真正就绪：出现保存按钮与 contenteditable。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            has_save = len(browser.find_elements(By.CSS_SELECTOR, "button.btn-img.op-btn.save")) > 0
            has_edit = len(browser.find_elements(By.CSS_SELECTOR, "[contenteditable=\"true\"]")) > 0
            if has_save and has_edit:
                return True
        except Exception:
            pass
        time.sleep(1)
    return False


def _wait_for_xiumi_login_on_home(browser, home_url: str, login_timeout: int, wait_timeout: int):
    print("秀米：正在打开图文编辑器并确认登录状态")
    browser.get(home_url)
    WebDriverWait(browser, wait_timeout).until(lambda d: d.execute_script("return document.readyState") in ("interactive", "complete"))

    if _is_xiumi_editor_url(home_url):
        # 直连编辑器 URL：登录态由持久化 profile 的 cookie 承载，
        # 首页登录检测在编辑器渲染完成前会误判为未登录并误点“登录”链接。
        # 直接等编辑器就绪即可。
        _log_xiumi_debug("xiumi_direct_editor_url", url=browser.current_url)
        if _wait_for_editor_loaded(browser, login_timeout):
            print("秀米：已进入图文编辑器")
            return
        raise RuntimeError("未能进入图文编辑器（可能未登录）。")

    initial_state = _xiumi_login_state(browser)
    _log_xiumi_debug("xiumi_login_initial_state", state=initial_state)
    if not initial_state.get("authenticated"):
        logged_in = _wait_for_manual_login(browser, login_timeout)
        if not logged_in:
            raise RuntimeError("秀米登录未完成，已超过等待时间。")
        browser.get(home_url)
        WebDriverWait(browser, wait_timeout).until(lambda d: d.execute_script("return document.readyState") in ("interactive", "complete"))

    if not _wait_until_xiumi_home_settled(browser, min(login_timeout, max(20, wait_timeout * 2))):
        _log_xiumi_debug("xiumi_login_not_settled", url=browser.current_url, excerpt=_page_excerpt(browser))
        raise RuntimeError("秀米登录态仍在初始化，未确认进入“我的秀米”。")
    _log_xiumi_debug("xiumi_login_confirmed", url=browser.current_url, excerpt=_page_excerpt(browser))
    print("秀米：已确认登录状态")


def _open_xiumi_editor_from_my_xiumi(browser, home_url: str, login_timeout: int, wait_timeout: int):
    _wait_for_xiumi_login_on_home(browser, home_url, login_timeout, wait_timeout)

    paper_state = _click_xiumi_ui_candidates(browser, ["图文排版"], exclude_terms=["选择编辑器", "模板", "教程"])
    _log_xiumi_debug("xiumi_paper_entry_click", state=paper_state, url=browser.current_url)
    if paper_state.get("clicked"):
        print("秀米：已进入图文排版")
        time.sleep(2)
        _dismiss_xiumi_recover_dialog(browser)
        try:
            _wait_editor_ready(browser, 3)
            return
        except Exception:
            pass

    try:
        _wait_editor_ready(browser, 2)
        return
    except Exception:
        pass

    create_steps = [
        ["新建图文", "创建图文", "新建空白图文", "空白图文"],
        ["新建", "空白"],
    ]
    exclude = ["保存", "预览", "删除", "导出", "登录", "注册", "会员", "教程", "模板", "选择编辑器", "图文排版"]
    last_state = {}
    for terms in create_steps:
        state = _click_xiumi_ui_candidates(browser, terms, exclude_terms=exclude)
        last_state = state
        _log_xiumi_debug("xiumi_create_click", terms=terms, state=state, url=browser.current_url)
        if state.get("clicked"):
            print("秀米：已新建图文")
            time.sleep(1)

            type_state = _click_xiumi_ui_candidates(
                browser,
                ["图文排版", "图文", "公众号图文"],
                exclude_terms=["H5", "设计", "文档", "模板", "教程", "返回", "取消"],
            )
            _log_xiumi_debug("xiumi_create_type_click", state=type_state, url=browser.current_url)
            if type_state.get("clicked"):
                print("秀米：已选择图文类型")

            deadline = time.time() + wait_timeout
            while time.time() < deadline:
                try:
                    _wait_editor_ready(browser, 2)
                    return
                except Exception:
                    time.sleep(1)

    _log_xiumi_debug("xiumi_create_failed", last_state=last_state, url=browser.current_url, excerpt=_page_excerpt(browser))
    raise RuntimeError("未能在“我的秀米”页面找到可用的新建图文入口，请检查页面状态或更新 XIUMI_HOME_URL。")


def _open_xiumi_editor(browser, home_url: str, login_timeout: int, wait_timeout: int):
    _open_xiumi_editor_from_my_xiumi(browser, home_url, login_timeout, wait_timeout)
    _wait_editor_ready(browser, wait_timeout)
    _ensure_xiumi_logged_in_before_edit(browser, "editor_ready")


def _set_input_value(browser, css_selector: str, value: str):
    if value is None:
        value = ""
    elements = browser.find_elements(By.CSS_SELECTOR, css_selector)
    if not elements:
        return
    browser.execute_script(
        """
const el = arguments[0];
const value = arguments[1];
el.value = value;
el.dispatchEvent(new Event('input', { bubbles: true }));
el.dispatchEvent(new Event('change', { bubbles: true }));
""",
        elements[0],
        value,
    )


def _xiumi_cdp_key_combo(browser, modifiers: int, key: str, code: str, vk: int):
    browser.execute_cdp_cmd(
        "Input.dispatchKeyEvent",
        {"type": "keyDown", "modifiers": modifiers, "key": key, "code": code, "windowsVirtualKeyCode": vk},
    )
    browser.execute_cdp_cmd(
        "Input.dispatchKeyEvent",
        {"type": "keyUp", "modifiers": modifiers, "key": key, "code": code, "windowsVirtualKeyCode": vk},
    )


def _setup_xiumi_clipboard_cdp(browser):
    """Grant clipboard + focus emulation so Ctrl+V via CDP performs a trusted paste.

    Xiumi's real paste handler (Ctrl+V with a text/html clipboard) creates
    rendering-layer components under comps.items; direct innerHTML injection
    lands in _qiBlock and never renders after save.
    """
    try:
        browser.execute_cdp_cmd(
            "Browser.grantPermissions",
            {"permissions": ["clipboardReadWrite", "clipboardSanitizedWrite"], "origin": "https://xiumi.us"},
        )
        browser.execute_cdp_cmd("Emulation.setFocusEmulationEnabled", {"enabled": True})
        return True
    except Exception as exc:
        _log_xiumi_debug("xiumi_clipboard_cdp", error=str(exc))
        return False


def _dismiss_xiumi_recover_dialog(browser):
    """Close the '上次没有保存到服务器，是否恢复？' dialog that a persistent profile may show."""
    time.sleep(1.5)
    dismiss = browser.execute_script(
        """
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
"""
    )
    if not dismiss or not dismiss.get("text"):
        return dismiss
    time.sleep(1.5)
    still = browser.execute_script("return (document.body.innerText || '').includes('上次没有保存');")
    if still and dismiss.get("x"):
        browser.execute_cdp_cmd("Input.dispatchMouseEvent", {"type": "mousePressed", "x": dismiss["x"], "y": dismiss["y"], "button": "left", "clickCount": 1})
        browser.execute_cdp_cmd("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": dismiss["x"], "y": dismiss["y"], "button": "left", "clickCount": 1})
        time.sleep(1.5)
    return dismiss


def _focus_xiumi_editor(browser):
    editables = browser.find_elements(By.CSS_SELECTOR, "[contenteditable]")
    for el in editables:
        try:
            if el.is_displayed():
                browser.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
                time.sleep(0.3)
                ActionChains(browser).move_to_element(el).click().perform()
                return el
        except Exception:
            continue
    return editables[0] if editables else None


def _paste_xiumi_html(browser, html_text: str) -> bool:
    """Replace editor content by trusted paste: clear, write clipboard, Ctrl+V.

    The clipboard must carry both text/html and text/plain so Xiumi's paste
    handler builds renderable components rather than the frozen _qiBlock.
    """
    _setup_xiumi_clipboard_cdp(browser)
    _dismiss_xiumi_recover_dialog(browser)

    plain = re.sub(r"\n+", "\n", re.sub(r"<[^>]+>", "\n", html_text)).strip()
    write_result = browser.execute_async_script(
        """
const fragment = arguments[0];
const plain = arguments[1];
const done = arguments[2];
const item = new ClipboardItem({
  'text/html': new Blob([fragment], {type: 'text/html'}),
  'text/plain': new Blob([plain], {type: 'text/plain'})
});
navigator.clipboard.write([item]).then(
  () => done('ok'),
  e => done('err:' + (e && e.message))
);
""",
        html_text,
        plain,
    )
    if write_result != "ok":
        _log_xiumi_debug("xiumi_clipboard_write", result=write_result)
        return False

    el = _focus_xiumi_editor(browser)
    if el is None:
        return False
    time.sleep(0.4)

    # 清空既有内容（第一次调用时文档为空，无害）
    _xiumi_cdp_key_combo(browser, 2, "a", "KeyA", 65)
    time.sleep(0.3)
    _xiumi_cdp_key_combo(browser, 0, "Delete", "Delete", 46)
    time.sleep(0.6)

    _focus_xiumi_editor(browser)
    time.sleep(0.4)
    _xiumi_cdp_key_combo(browser, 2, "v", "KeyV", 86)
    time.sleep(5)
    return True


def _set_editor_html(browser, html_text: str):
    return _paste_xiumi_html(browser, html_text)


def _data_url_to_temp_image(src: str, temp_dir: pathlib.Path, index: int) -> pathlib.Path | None:
    match = re.match(r"^data:([^;,]+);base64,(.+)$", src or "", flags=re.I | re.S)
    if not match:
        return None
    mime_type = match.group(1).strip().lower()
    ext = mimetypes.guess_extension(mime_type) or ".png"
    if ext == ".jpe":
        ext = ".jpg"
    try:
        data = base64.b64decode(match.group(2), validate=False)
    except Exception:
        return None
    path = temp_dir / f"xiumi_inline_{index:04d}{ext}"
    path.write_bytes(data)
    return path


def _resolve_upload_image_path(src: str, asset_base_path: pathlib.Path, temp_dir: pathlib.Path, index: int) -> pathlib.Path | None:
    if _is_data_image_src(src):
        return _data_url_to_temp_image(src, temp_dir, index)
    if not src or _is_remote_image_src(src):
        return None
    resolved = resolve_existing_image_path(src, base_dir=asset_base_path.parent, extra_roots=(ROOT,))
    if resolved is not None:
        return resolved
    cleaned = clean_markdown_image_target(src)
    path = pathlib.Path(cleaned)
    if not path.is_absolute():
        path = (asset_base_path.parent / path).resolve()
    return path if path.exists() else None


def _image_entries_for_upload(html_text: str, asset_base_path: pathlib.Path, temp_dir: pathlib.Path) -> list[dict]:
    result = []
    seen = set()
    for index, src in enumerate(re.findall(r"<img\b[^>]*\bsrc=(?:['\"])(.*?)(?:['\"])", html_text or "", flags=re.I), start=1):
        if not src or _is_remote_image_src(src) or src in seen:
            continue
        path = _resolve_upload_image_path(src, asset_base_path, temp_dir, index)
        if path and path.exists():
            result.append(
                {
                    "index": index,
                    "source": src,
                    "path": path,
                    "is_data": _is_data_image_src(src),
                    "key": _upload_image_key(path, src),
                }
            )
            seen.add(src)
    return result


def _upload_entries_in_safe_order(entries: list[dict]) -> list[dict]:
    # Upload normal local assets before data URLs; Xiumi's COS endpoint is less
    # tolerant of converted inline images. Final body order is restored later.
    return sorted(entries, key=lambda item: (bool(item.get("is_data")), int(item.get("index") or 0)))


def _image_entry_for_log(entry: dict, remote_url: str = "") -> dict:
    path = entry.get("path")
    source = str(entry.get("source", ""))
    if _is_data_image_src(source):
        source = source.split(";", 1)[0] + ";base64,..."
    return {
        "index": entry.get("index"),
        "image": path.name if isinstance(path, pathlib.Path) else "",
        "key": entry.get("key", ""),
        "source": _short_url(source),
        "remote_url": _short_url(remote_url),
        "uploaded": bool(remote_url),
    }


def _html_image_order_for_log(html_text: str) -> list[dict]:
    order = []
    for index, src in enumerate(re.findall(r"<img\b[^>]*\bsrc=(?:['\"])(.*?)(?:['\"])", html_text or "", flags=re.I), start=1):
        normalized = _normalize_xiumi_image_url(src)
        logged_src = normalized
        if _is_data_image_src(logged_src):
            logged_src = logged_src.split(";", 1)[0] + ";base64,..."
        order.append(
            {
                "index": index,
                "key": _upload_image_key(None, src),
                "src": _short_url(logged_src),
                "is_xiumi": _looks_like_user_xiumi_image(normalized),
            }
        )
    return order


def _html_image_sources(html_text: str) -> list[str]:
    return [
        _normalize_xiumi_image_url(src)
        for src in re.findall(r"<img\b[^>]*\bsrc=(?:['\"])(.*?)(?:['\"])", html_text or "", flags=re.I)
        if src
    ]


def _rewrite_images_by_html_order(
    html_text: str,
    url_by_source: dict[str, str],
    url_by_key: dict[str, str],
) -> str:
    replaced = 0

    def repl(match):
        nonlocal replaced
        tag = match.group(0)
        quote = match.group(1)
        src = (match.group(2) or "").strip()
        if not src or _is_remote_image_src(src):
            return tag
        remote_url = url_by_source.get(src, "")
        if not remote_url:
            key = _upload_image_key(None, src)
            remote_url = url_by_key.get(key, "")
        if not remote_url:
            return tag
        replaced += 1
        return re.sub(r"\bsrc=(['\"])(.*?)\1", f"src={quote}{remote_url}{quote}", tag, count=1, flags=re.I)

    rewritten = re.sub(r"<img\b[^>]*\bsrc=(['\"])(.*?)\1[^>]*>", repl, html_text or "", flags=re.I)
    _log_xiumi_debug(
        "xiumi_html_order_image_rewrite",
        replaced=replaced,
        source_mappings=len(url_by_source),
        key_mappings=len(url_by_key),
    )
    return rewritten


def _remote_image_sources_ordered(browser) -> list[str]:
    try:
        values = browser.execute_script(
            """
const values = [];
for (const img of Array.from(document.querySelectorAll('img'))) {
  values.push(img.getAttribute('src') || '');
}
for (const el of Array.from(document.querySelectorAll('*'))) {
  const bg = window.getComputedStyle(el).backgroundImage || '';
  const match = bg.match(/url\\(["']?([^"')]+)["']?\\)/i);
  if (match) values.push(match[1]);
}
return values.filter(src => new RegExp('^(https?:)?//', 'i').test(src));
"""
        )
    except Exception:
        return []
    result = []
    seen = set()
    for value in values:
        text = str(value or "")
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _remote_image_sources(browser) -> set[str]:
    return set(_remote_image_sources_ordered(browser))


def _install_xiumi_upload_observer(browser):
    script = r"""
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
return true;
"""
    try:
        browser.execute_script(script)
    except Exception as exc:
        _log_xiumi_debug("upload_observer_install_failed", error=str(exc))


def _xiumi_observed_upload_assets(browser, since: int = 0) -> list[dict]:
    try:
        events = browser.execute_script("return window.__wanyouXiumiUploadEvents || [];") or []
    except Exception:
        return []
    if not isinstance(events, list):
        return []
    assets = []
    seen = set()
    for event in events[max(0, since):]:
        if not isinstance(event, dict):
            continue
        files = [str(name or "") for name in (event.get("files") or []) if str(name or "")]
        for value in (event.get("url", ""), event.get("body", "")):
            for url in _xiumi_image_urls_from_text(value):
                key = (url, tuple(files))
                if key in seen:
                    continue
                seen.add(key)
                assets.append({"url": url, "text": " ".join(files), "files": files, "source": "observer"})
    return assets


def _xiumi_upload_event_count(browser) -> int:
    try:
        events = browser.execute_script("return window.__wanyouXiumiUploadEvents || [];") or []
    except Exception:
        return 0
    return len(events) if isinstance(events, list) else 0


def _xiumi_gallery_assets(browser) -> list[dict]:
    script = r"""
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
return results.slice(-300);
"""
    try:
        values = browser.execute_script(script) or []
    except Exception as exc:
        _log_xiumi_debug("gallery_assets_failed", error=str(exc))
        return []
    assets = [item for item in values if isinstance(item, dict) and _looks_like_user_xiumi_image(item.get("url", ""))]
    return assets


def _upload_name_variants(path: pathlib.Path) -> set[str]:
    name = path.name.lower()
    stem = path.stem.lower()
    variants = {name}
    if stem:
        variants.add(stem)
        for ext in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
            variants.add(stem + ext)
    return {variant for variant in variants if variant}


def _upload_image_key(path: pathlib.Path | None, source: str = "") -> str:
    if path:
        stem = path.stem.lower().strip()
        if stem:
            return stem
    cleaned = str(source or "").split("?", 1)[0].strip().strip("'").strip('"')
    name = pathlib.Path(cleaned).name.lower()
    return pathlib.Path(name).stem if name else ""


def _asset_matches_upload_path(asset: dict, path: pathlib.Path) -> tuple[bool, int]:
    files = [str(name or "").lower() for name in (asset.get("files") or []) if str(name or "")]
    text = str(asset.get("text", "") or "").lower()
    haystack = " ".join(files + [text])
    variants = _upload_name_variants(path)
    exact_name = path.name.lower()
    if exact_name and any(exact_name == pathlib.Path(name).name.lower() for name in files):
        return True, 100
    for name in files:
        basename = pathlib.Path(name).name.lower()
        if basename in variants:
            return True, 90
    for variant in variants:
        if variant and variant in haystack:
            return True, 60 if "." in variant else 30
    return False, 0


def _xiumi_uploaded_urls_for_paths(browser, image_paths: list[pathlib.Path], before: set[str], observed_since: int = 0) -> list[str]:
    assets = _xiumi_observed_upload_assets(browser, observed_since) + _xiumi_gallery_assets(browser)
    matched: dict[int, str] = {}
    for asset in assets:
        url = _normalize_xiumi_image_url(asset.get("url", ""))
        if not url:
            continue
        best_index = -1
        best_score = 0
        for index, path in enumerate(image_paths):
            if index in matched:
                continue
            matched_path, score = _asset_matches_upload_path(asset, path)
            if matched_path and score > best_score:
                best_index = index
                best_score = score
        if best_index >= 0:
            matched[best_index] = url

    ordered_by_index = [""] * len(image_paths)
    for index, path in enumerate(image_paths):
        url = matched.get(index, "")
        if url:
            ordered_by_index[index] = url
    if all(ordered_by_index):
        return ordered_by_index

    ordered = [url for url in ordered_by_index if url]
    return ordered


def _short_url(value: str) -> str:
    text = str(value or "")
    return text if len(text) <= 180 else text[:177] + "..."


def _normalize_xiumi_image_url(value: str) -> str:
    text = str(value or "").strip()
    text = text.replace("\\/", "/")
    if text.startswith("//"):
        return "https:" + text
    return text


def _xiumi_image_urls_from_text(text: str) -> list[str]:
    normalized = str(text or "").replace("\\/", "/")
    urls = []
    for match in re.finditer(r"(?:(?:https?:)?//)?img\.xiumi\.us/[^\s\"'<>）)]+|(?:https?:)?//[^\s\"'<>）)]*/xmi/ua/[^\s\"'<>）)]+", normalized, flags=re.I):
        url = match.group(0)
        if url.startswith("img.xiumi.us/"):
            url = "https://" + url
        url = _normalize_xiumi_image_url(url)
        if _looks_like_user_xiumi_image(url) and url not in urls:
            urls.append(url)
    return urls


def _looks_like_user_xiumi_image(value: str) -> bool:
    text = str(value or "").lower()
    if not text:
        return False
    if "statics.xiumi.us" in text or "/stc/" in text or "templates-assets" in text:
        return False
    return "img.xiumi.us" in text or "/xmi/ua/" in text


def _file_input_count(browser) -> int:
    try:
        return len(browser.find_elements(By.CSS_SELECTOR, "input[type='file']"))
    except Exception:
        return 0


def _file_input_diagnostics(browser) -> list[dict]:
    script = """
return Array.from(document.querySelectorAll('input[type="file"]')).map((el, index) => {
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
    parentText: parent ? String(parent.innerText || '').replace(/\\s+/g, ' ').slice(0, 80) : ''
  };
});
"""
    try:
        values = browser.execute_script(script) or []
    except Exception:
        return []
    diagnostics = [value for value in values if isinstance(value, dict)]
    return diagnostics


def _click_xiumi_ui_candidates(browser, include_terms: list[str], *, exclude_terms: list[str] | None = None, limit: int = 1) -> dict:
    script = """
const includeTerms = arguments[0].map(t => String(t).toLowerCase());
const excludeTerms = arguments[1].map(t => String(t).toLowerCase());
const limit = arguments[2];
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
    for (const term of includeTerms) {
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
    for (const term of excludeTerms) {
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
"""
    try:
        value = browser.execute_script(script, include_terms, exclude_terms or [], limit) or {}
        if isinstance(value, dict):
            return value
        return {"clicked": int(value or 0), "candidates": 0, "items": []}
    except Exception:
        return {"clicked": 0, "candidates": 0, "items": []}


def _open_xiumi_image_library(browser) -> dict:
    state = {"gallery": 0, "upload_button": 0, "file_inputs_before": _file_input_count(browser)}

    exclude = ["保存", "预览", "导出", "关闭", "删除", "推送", "上传推送", "打开", "save", "preview", "export", "close", "delete"]
    steps = [
        ("gallery", ["我的图库", "图库", "图片库"], exclude),
        ("upload_button", ["上传图片", "无水印", "图片上传"], exclude),
    ]
    for key, terms, blocked in steps:
        click_state = _click_xiumi_ui_candidates(browser, terms, exclude_terms=blocked, limit=1)
        clicked = int(click_state.get("clicked", 0) or 0)
        state[key] = state.get(key, 0) + clicked
        if clicked:
            time.sleep(0.8)
    state["file_inputs_after"] = _file_input_count(browser)
    return state


def _find_image_file_input(browser):
    library_state = _open_xiumi_image_library(browser)
    inputs = browser.find_elements(By.CSS_SELECTOR, "input[type='file']")
    diagnostics = _file_input_diagnostics(browser)
    input_meta = {int(item.get("index", -1)): item for item in diagnostics}

    ranked = []
    for index, element in enumerate(inputs):
        meta = input_meta.get(index, {})
        accept = str(meta.get("accept", ""))
        text = " ".join(
            str(meta.get(key, ""))
            for key in ("id", "name", "className", "parentClass", "parentText")
        ).lower()
        is_image_input = bool(re.search(r"(?:image|\.png|\.jpe?g|\.gif)", accept, flags=re.I))
        if not is_image_input:
            continue

        score = index
        input_id = str(meta.get("id", ""))
        score += 100
        if input_id == "imageFileUploadInput":
            score += 80
        if input_id == "teamImageFileUploadInput":
            score -= 60
        if not meta.get("disabled"):
            score += 20
        if meta.get("visible"):
            score += 40
        if meta.get("multiple"):
            score += 15
        if "无水印" in str(meta.get("parentText", "")):
            score += 40
        if any(term in text for term in ("上传", "图片", "图库", "image", "img", "pic", "upload", "gallery")):
            score += 30
        if any(term in text for term in ("team", "团队", "cover", "封面", "video", "audio", "file-attachment", "附件")):
            score -= 80
        ranked.append((score, index, element, meta))

    ranked.sort(key=lambda item: item[0], reverse=True)
    chosen = ranked[0] if ranked else None
    if chosen:
        score, index, element, meta = chosen
        return element, len(inputs), library_state
    _log_xiumi_debug("file_input_missing", total=0, library_state=library_state)
    return None, len(inputs), library_state


def _prepare_file_input_for_upload(browser, file_input):
    try:
        state = _file_input_state(browser, file_input)
        if state.get("visible") and int(state.get("width") or 0) > 0 and int(state.get("height") or 0) > 0:
            return
        browser.execute_script(
            """
const el = arguments[0];
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
""",
            file_input,
        )
    except Exception:
        pass


def _activate_file_upload_control(browser, file_input) -> dict:
    script = """
const el = arguments[0];
const control =
  el.closest('label,button,a,[role="button"],.btn,.btn-upload,.tn-image-uploader') ||
  el.parentElement;
if (!control) return { clicked: false, reason: 'parent_missing' };
const text = String(control.innerText || control.textContent || '').replace(/\\s+/g, ' ').trim();
try {
  control.scrollIntoView({ block: 'center', inline: 'center' });
  control.click();
  return { clicked: true, text, tag: control.tagName, className: String(control.className || '') };
} catch (e) {
  return { clicked: false, text, error: String(e) };
}
"""
    try:
        state = browser.execute_script(script, file_input) or {}
    except Exception as exc:
        state = {"clicked": False, "error": str(exc)}
    return state


def _file_input_cdp_selector(browser, file_input) -> str:
    try:
        state = _file_input_state(browser, file_input)
        input_id = str(state.get("id", "") or "").strip()
        if input_id:
            return f"#{input_id}"
        index = browser.execute_script(
            """
const target = arguments[0];
return Array.from(document.querySelectorAll('input[type="file"]')).indexOf(target);
""",
            file_input,
        )
        if isinstance(index, int) and index >= 0:
            return f'input[type="file"]:nth-of-type({index + 1})'
    except Exception:
        pass
    return ""


def _attach_files_with_cdp(browser, file_input, image_paths: list[pathlib.Path]) -> dict:
    if not hasattr(browser, "execute_cdp_cmd"):
        return {"applied": False, "reason": "cdp_unavailable"}
    selector = _file_input_cdp_selector(browser, file_input)
    if not selector:
        return {"applied": False, "reason": "selector_unavailable"}
    try:
        root = browser.execute_cdp_cmd("DOM.getDocument", {})
        node = browser.execute_cdp_cmd(
            "DOM.querySelector",
            {"nodeId": root["root"]["nodeId"], "selector": selector},
        )
        node_id = node.get("nodeId")
        if not node_id:
            return {"applied": False, "selector": selector, "reason": "node_not_found"}
        browser.execute_cdp_cmd(
            "DOM.setFileInputFiles",
            {"nodeId": node_id, "files": [str(path) for path in image_paths]},
        )
        return {"applied": True, "selector": selector}
    except Exception as exc:
        return {"applied": False, "selector": selector, "reason": str(exc)}


def _attach_files_to_input(browser, file_input, image_paths: list[pathlib.Path]) -> tuple[dict, dict]:
    before_state = _file_input_state(browser, file_input)
    _activate_file_upload_control(browser, file_input)
    joined_paths = "\n".join(str(path) for path in image_paths)
    try:
        file_input.send_keys(joined_paths)
    except Exception as exc:
        _log_xiumi_debug(
            "batch_send_keys_exception",
            images=[path.name for path in image_paths],
            error=str(exc),
            state=before_state,
        )

    after_send_keys_state = _file_input_state(browser, file_input)
    expected = len(image_paths)
    if int(after_send_keys_state.get("filesLength") or 0) < expected:
        cdp_state = _attach_files_with_cdp(browser, file_input, image_paths)
        if not cdp_state.get("applied"):
            _log_xiumi_debug("batch_cdp_file_attach_failed", images=[path.name for path in image_paths], state=cdp_state)
        after_send_keys_state = _file_input_state(browser, file_input)

    _dispatch_file_input_events(browser, file_input)
    after_dispatch_state = _file_input_state(browser, file_input)
    return after_send_keys_state, after_dispatch_state


def _file_input_state(browser, file_input) -> dict:
    script = """
const el = arguments[0];
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
"""
    try:
        return browser.execute_script(script, file_input) or {}
    except Exception as exc:
        return {"error": str(exc)}


def _dispatch_file_input_events(browser, file_input):
    script = """
const el = arguments[0];
for (const name of ['input', 'change']) {
  try {
    el.dispatchEvent(new Event(name, { bubbles: true }));
  } catch (e) {}
}
if (window.angular) {
  try {
    const scope = window.angular.element(el).scope();
    if (scope && scope.$applyAsync) scope.$applyAsync();
    else if (scope && scope.$apply) scope.$apply();
  } catch (e) {}
}
"""
    try:
        browser.execute_script(script, file_input)
    except Exception:
        pass


def _xiumi_upload_messages(browser) -> list[str]:
    script = """
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
  const text = String(el.innerText || el.textContent || '').replace(/\\s+/g, ' ').trim();
  if (text && /上传|失败|成功|错误|cos|COS|图片|图库|稍后|超过|太大|超出|大小|尺寸|MB|不支持/.test(text)) parts.push(text.slice(0, 500));
}
if (!parts.length && document.body) {
  const body = String(document.body.innerText || document.body.textContent || '').replace(/\\s+/g, ' ');
  const patterns = ['图片正在上传，请稍后再试', '上传成功', '上传失败', '上传完成', '超过', '太大', '不支持', '失败'];
  for (const pattern of patterns) {
    const index = body.indexOf(pattern);
    if (index >= 0) parts.push(body.slice(Math.max(0, index - 80), index + pattern.length + 80));
  }
}
return Array.from(new Set(parts)).slice(0, 8);
"""
    try:
        values = browser.execute_script(script) or []
    except Exception:
        return []
    return [str(value) for value in values if value]


def _xiumi_upload_state(browser) -> dict:
    messages = _xiumi_upload_messages(browser)
    text = "\n".join(messages)
    busy = bool(re.search(r"(正在上传|上传中|请稍后再试|稍后再试)", text, flags=re.I))
    failed = bool(re.search(r"(上传失败|失败|错误|超过|太大|超出|大小限制|不支持|MB)", text, flags=re.I))
    success_counts = [int(value) for value in re.findall(r"(\d+)\s*张(?:图片)?上传成功", text)]
    success = bool(success_counts or re.search(r"(上传成功|上传完成|已上传)", text, flags=re.I))
    return {
        "busy": busy,
        "failed": failed,
        "success": success,
        "success_count": max(success_counts) if success_counts else 0,
        "messages": messages,
    }


def _wait_xiumi_upload_idle(browser, *, context: str = "") -> dict:
    stall_seconds = max(30, int(getattr(config, "XIUMI_IMAGE_UPLOAD_STALL_SECONDS", 180) or 180))
    last_busy = time.time()
    announced = False
    while True:
        state = _xiumi_upload_state(browser)
        if not state.get("busy"):
            return state
        if not announced:
            _print_xiumi_image_progress("：秀米仍在处理上一批上传，等待完成")
            announced = True
        if time.time() - last_busy > stall_seconds:
            _log_xiumi_debug("upload_idle_wait_stalled", context=context, state=state, stall_seconds=stall_seconds)
            return state
        time.sleep(0.6)


def _wait_for_xiumi_uploaded_sources(
    browser,
    before: set[str],
    expected: int,
    *,
    context: str,
    image_paths: list[pathlib.Path] | None = None,
    observed_since: int = 0,
) -> list[str]:
    stall_seconds = max(30, int(getattr(config, "XIUMI_IMAGE_UPLOAD_STALL_SECONDS", 180) or 180))
    last_progress = time.time()
    last_count = -1
    last_state_key = None
    announced_busy = False
    last_resolve_at = 0.0
    last_named_sources = []

    while True:
        after_ordered = _remote_image_sources_ordered(browser)
        new_sources = [src for src in after_ordered if src and src not in before and not src.startswith("data:")]
        user_sources = [_normalize_xiumi_image_url(src) for src in new_sources if _looks_like_user_xiumi_image(src)]
        state = _xiumi_upload_state(browser)
        named_sources = []
        should_resolve_assets = (
            bool(image_paths)
            and (
                len(user_sources) >= expected
                or state.get("success")
                or int(state.get("success_count") or 0) > 0
                or bool(new_sources)
                or time.time() - last_resolve_at > 5
            )
        )
        if should_resolve_assets:
            last_resolve_at = time.time()
            named_sources = _xiumi_uploaded_urls_for_paths(browser, image_paths, before, observed_since=observed_since)
            if named_sources:
                last_named_sources = named_sources
            for url in named_sources:
                if url not in user_sources:
                    user_sources.append(url)

        state_key = (len(new_sources), len(user_sources), bool(state.get("busy")), bool(state.get("success")), bool(state.get("failed")), int(state.get("success_count") or 0))
        if state.get("busy") and not announced_busy:
            _print_xiumi_image_progress("：等待秀米完成当前上传")
            announced_busy = True

        if len(user_sources) != last_count or state_key != last_state_key:
            last_progress = time.time()
            last_count = len(user_sources)
            last_state_key = state_key

        if state.get("failed"):
            return named_sources if image_paths else user_sources

        # When Xiumi is idle and reports partial completion (some images failed
        # e.g. due to file size), return what we have instead of waiting for the
        # full stall timeout.
        settled_count = int(state.get("success_count") or 0)
        if settled_count > 0 and not state.get("busy"):
            sources_to_return = named_sources if image_paths else user_sources
            if sources_to_return:
                _log_xiumi_debug(
                    "upload_settled_partial",
                    context=context,
                    expected=expected,
                    success_count=settled_count,
                    matched_sources=len(sources_to_return),
                )
                return sources_to_return

        if len(named_sources) >= expected and not state.get("busy"):
            return named_sources[-expected:]

        if image_paths and len(user_sources) >= expected and not state.get("busy") and not named_sources:
            _log_xiumi_debug(
                "upload_urls_unmatched_by_name",
                context=context,
                expected=expected,
                user_sources=len(user_sources),
                images=[path.name for path in image_paths],
            )
            return []

        if image_paths:
            if time.time() - last_progress > stall_seconds:
                _log_xiumi_debug(
                    "upload_wait_stalled",
                    context=context,
                    expected=expected,
                    matched_sources=len(last_named_sources),
                    state=state,
                    stall_seconds=stall_seconds,
                )
                return last_named_sources
            time.sleep(0.6)
            continue

        if len(user_sources) >= expected and not state.get("busy"):
            return user_sources[-expected:]

        success_count = int(state.get("success_count") or 0)
        generic_single_success = expected == 1 and state.get("success") and not state.get("busy")
        if (success_count >= expected or generic_single_success) and not state.get("busy"):
            named_sources = _xiumi_uploaded_urls_for_paths(browser, image_paths or [], before, observed_since=observed_since)
            if len(named_sources) >= expected:
                return named_sources[-expected:]
            _log_xiumi_debug(
                "upload_success_count_without_urls",
                context=context,
                expected=expected,
                success_count=success_count,
                named_sources=len(named_sources),
                messages=state.get("messages"),
            )
            return named_sources

        if time.time() - last_progress > stall_seconds:
            _log_xiumi_debug(
                "upload_wait_stalled",
                context=context,
                expected=expected,
                user_sources=len(user_sources),
                state=state,
                stall_seconds=stall_seconds,
            )
            return user_sources

        time.sleep(0.6)


def _write_probe_image(temp_dir: pathlib.Path) -> pathlib.Path:
    data = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAEAAAAAwCAIAAABOyVRHAAAAPElEQVR4nO3PQQ0AIBDAMMC/5+ONAvZoFSzZnYFn"
        "NzMAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAADg1wGfXgAB3WQj8QAAAABJRU5ErkJggg=="
    )
    path = temp_dir / "wanyou_xiumi_upload_probe.png"
    path.write_bytes(data)
    return path


def _probe_xiumi_image_upload(browser) -> dict:
    with tempfile.TemporaryDirectory(prefix="wanyou_xiumi_probe_") as temp:
        image_path = _write_probe_image(pathlib.Path(temp))
        print("秀米：正在检查图片上传链路")
        _install_xiumi_upload_observer(browser)
        remote_url = _upload_one_xiumi_image(browser, image_path)
    status = "ok" if remote_url else "failed"
    _log_xiumi_debug("upload_probe", status=status, remote_url=_short_url(remote_url))
    return {"status": status, "remote_url": remote_url}


def _upload_one_xiumi_image(browser, image_path: pathlib.Path) -> str:
    _wait_xiumi_upload_idle(browser, context=f"before_single:{image_path.name}")
    file_input, input_count, library_state = _find_image_file_input(browser)
    if file_input is None:
        _log_xiumi_debug("upload_unavailable", image=image_path.name, input_count=input_count, library_state=library_state)
        return ""

    # Open the library first, then take the baseline. Otherwise existing gallery
    # and template thumbnails are misidentified as images uploaded by this run.
    before = _remote_image_sources(browser)
    observed_since = _xiumi_upload_event_count(browser)
    try:
        _prepare_file_input_for_upload(browser, file_input)
        _attach_files_to_input(browser, file_input, [image_path])
    except Exception as exc:
        _log_xiumi_debug("send_keys_failed", image=image_path.name, error=str(exc))
        return ""

    user_sources = _wait_for_xiumi_uploaded_sources(
        browser,
        before,
        1,
        context=f"single:{image_path.name}",
        image_paths=[image_path],
        observed_since=observed_since,
    )
    if user_sources:
        return _normalize_xiumi_image_url(user_sources[-1])
    state = _xiumi_upload_state(browser)
    _log_xiumi_debug(
        "upload_incomplete",
        image=image_path.name,
        gallery_new_sources=len(_remote_image_sources(browser) - before),
        user_gallery_sources=len([src for src in _remote_image_sources(browser) - before if _looks_like_user_xiumi_image(src)]),
        state=state,
    )
    return ""


def _upload_xiumi_image_batch(browser, image_paths: list[pathlib.Path]) -> list[str]:
    if not image_paths:
        return []

    _wait_xiumi_upload_idle(browser, context=f"before_batch:{','.join(path.name for path in image_paths)}")
    file_input, input_count, library_state = _find_image_file_input(browser)
    if file_input is None:
        _log_xiumi_debug(
            "batch_upload_unavailable",
            images=[path.name for path in image_paths],
            input_count=input_count,
            library_state=library_state,
        )
        return []

    before = set(_remote_image_sources_ordered(browser))
    observed_since = _xiumi_upload_event_count(browser)
    try:
        _prepare_file_input_for_upload(browser, file_input)
        _attach_files_to_input(browser, file_input, image_paths)
    except Exception as exc:
        _log_xiumi_debug("batch_send_keys_failed", images=[path.name for path in image_paths], error=str(exc))
        return []

    user_sources = _wait_for_xiumi_uploaded_sources(
        browser,
        before,
        len(image_paths),
        context=f"batch:{','.join(path.name for path in image_paths)}",
        image_paths=image_paths,
        observed_since=observed_since,
    )
    if len(user_sources) >= len(image_paths):
        return user_sources[-len(image_paths):]
    after = set(_remote_image_sources_ordered(browser))
    state = _xiumi_upload_state(browser)
    _log_xiumi_debug(
        "batch_upload_incomplete_wait",
        images=[path.name for path in image_paths],
        gallery_new_sources=len(after - before),
        user_gallery_sources=len(user_sources),
        state=state,
    )
    return user_sources


def _chunks(values: list, size: int):
    for index in range(0, len(values), max(1, size)):
        yield values[index:index + max(1, size)]


def _upload_xiumi_images_and_rewrite(browser, html_text: str, asset_base_path: pathlib.Path) -> tuple[str, dict]:
    mode = str(getattr(config, "XIUMI_IMAGE_MODE", "upload") or "upload").strip().lower()
    if mode != "upload":
        return html_text, {"status": "skipped", "uploaded": 0, "total": 0}

    with tempfile.TemporaryDirectory(prefix="wanyou_xiumi_images_") as temp:
        temp_dir = pathlib.Path(temp)
        html_order_entries = _image_entries_for_upload(html_text, asset_base_path, temp_dir)
        upload_entries = _upload_entries_in_safe_order(html_order_entries)
        _log_xiumi_debug(
            "upload_candidates",
            total=len(upload_entries),
            local_upload_html_order=[_image_entry_for_log(entry) for entry in html_order_entries],
            upload_order=[_image_entry_for_log(entry) for entry in upload_entries],
        )
        if not upload_entries:
            return html_text, {"status": "no_images", "uploaded": 0, "total": 0}
        _install_xiumi_upload_observer(browser)

        url_by_source: dict[str, str] = {}
        url_by_key: dict[str, str] = {}
        uploaded = 0
        failures = 0
        consecutive_failures = 0
        skipped_images = []
        max_failures = max(1, int(getattr(config, "XIUMI_IMAGE_UPLOAD_MAX_FAILURES", 3) or 3))
        retries = max(0, int(getattr(config, "XIUMI_IMAGE_UPLOAD_RETRIES", 2) or 0))
        batch_size = max(1, int(getattr(config, "XIUMI_IMAGE_UPLOAD_BATCH_SIZE", 6) or 1))
        total_batches = (len(upload_entries) + batch_size - 1) // batch_size
        _print_xiumi_image_progress(f"：发现 {len(upload_entries)} 张，开始上传")

        def record_upload(entry: dict, remote_url: str, mode: str):
            nonlocal uploaded, consecutive_failures
            source = str(entry.get("source") or "")
            image_path = entry["path"]
            key = str(entry.get("key") or _upload_image_key(image_path, source))
            url_by_source[source] = remote_url
            if key:
                url_by_key[key] = remote_url
            uploaded += 1
            consecutive_failures = 0

        def upload_single(image_path: pathlib.Path, entry_index: int = 0, total: int = 0) -> str:
            remote_url = ""
            for attempt in range(retries + 1):
                remote_url = _upload_one_xiumi_image(browser, image_path)
                if remote_url:
                    break
                if attempt < retries:
                    _log_xiumi_debug("upload_retry", image=image_path.name, attempt=attempt + 1, retries=retries)
                    _print_xiumi_image_progress(
                        f"：{image_path.name} 上传失败，重试 {attempt + 1}/{retries}"
                    )
                    time.sleep(1)
            if not remote_url:
                state = _xiumi_upload_state(browser)
                failure_msgs = state.get("messages") or []
                reason = "; ".join(failure_msgs[:2]) if failure_msgs else "未知错误（可能文件过大或格式不支持）"
                _print_xiumi_image_progress(
                    f"：{image_path.name} 经 {retries + 1} 次尝试后仍上传失败：{reason}"
                )
            return remote_url

        for batch_index, batch in enumerate(_chunks(upload_entries, batch_size), start=1):
            batch_urls = []
            if len(batch) > 1:
                _print_xiumi_image_progress(
                    f"：第 {batch_index}/{total_batches} 批上传中（{len(batch)} 张，已完成 {uploaded}/{len(upload_entries)}）"
                )
                batch_urls = _upload_xiumi_image_batch(browser, [entry["path"] for entry in batch])
                if len(batch_urls) == len(batch):
                    _print_xiumi_image_progress(
                        f"：第 {batch_index}/{total_batches} 批完成，累计 {uploaded + len(batch_urls)}/{len(upload_entries)}"
                    )
                else:
                    _log_xiumi_debug(
                        "batch_upload_incomplete",
                        images=[entry["path"].name for entry in batch],
                        received=len(batch_urls),
                        expected=len(batch),
                    )
                    _print_xiumi_image_progress(
                        f"：第 {batch_index}/{total_batches} 批未完整确认，改为逐张补传"
                    )
                    batch_urls = []
            else:
                _print_xiumi_image_progress(
                    f"：第 {batch_index}/{total_batches} 批逐张上传中（已完成 {uploaded}/{len(upload_entries)}）"
                )

            if batch_urls:
                for entry, remote_url in zip(batch, batch_urls):
                    record_upload(entry, remote_url, "batch")
                continue

            for entry in batch:
                image_path = entry["path"]
                remote_url = upload_single(image_path, entry.get("index", 0), len(upload_entries))
                if remote_url:
                    record_upload(entry, remote_url, "single")
                    _print_xiumi_image_progress(f"：已上传 {uploaded}/{len(upload_entries)}")
                    continue

                failures += 1
                consecutive_failures += 1
                skipped_images.append(image_path.name)
                _print_xiumi_image_progress(
                    f"：{image_path.name} 未确认上传成功，暂跳过（已上传 {uploaded}/{len(upload_entries)}，跳过 {len(skipped_images)}）"
                )
                _log_xiumi_debug(
                    "upload_failure",
                    image=image_path.name,
                    failures=failures,
                    consecutive_failures=consecutive_failures,
                    max_failures=max_failures,
                    uploaded=uploaded,
                )
                if uploaded == 0 and consecutive_failures >= max_failures:
                    _log_xiumi_debug(
                        "upload_abort",
                        reason="initial_consecutive_failures",
                        failures=failures,
                        consecutive_failures=consecutive_failures,
                        uploaded=uploaded,
                        total=len(upload_entries),
                    )
                    break
            if uploaded == 0 and consecutive_failures >= max_failures:
                break

        status = "ok" if uploaded == len(upload_entries) else "partial" if uploaded else "failed"
        if status == "ok":
            print(f"秀米：正文图片已上传完成（{uploaded}/{len(upload_entries)}）")
        elif uploaded:
            print(f"秀米：部分正文图片已上传（{uploaded}/{len(upload_entries)}），未上传图片将保留提示")
        else:
            print("秀米：正文图片未能自动上传，将在草稿中保留提示")
        _log_xiumi_debug(
            "upload_summary",
            status=status,
            uploaded=uploaded,
            failed=failures,
            skipped_images=skipped_images,
            total=len(upload_entries),
        )
        if uploaded:
            mapping_order = []
            for entry in html_order_entries:
                source = str(entry.get("source") or "")
                key = str(entry.get("key") or "")
                mapping_order.append(_image_entry_for_log(entry, url_by_source.get(source) or url_by_key.get(key) or ""))
            _log_xiumi_debug("xiumi_image_order_mapping", mapping_order=mapping_order)
            rewritten = _rewrite_images_by_html_order(html_text, url_by_source, url_by_key)
            _log_xiumi_debug("xiumi_final_html_image_order", order=_html_image_order_for_log(rewritten))
            return _remove_unuploaded_images_for_xiumi(rewritten), {"status": status, "uploaded": uploaded, "total": len(upload_entries)}
        return _remove_images_for_xiumi(html_text), {"status": status, "uploaded": 0, "total": len(upload_entries)}


def _mark_xiumi_document_dirty(browser) -> dict:
    return browser.execute_script(
        """
function findSaveScope() {
  var btn = document.querySelector('button.btn-img.op-btn.save');
  if (!btn || !window.angular) return null;
  var s = window.angular.element(btn).scope();
  while (s && typeof s.onBtnClickSave !== 'function') s = s.$parent;
  return s || null;
}
var scope = findSaveScope();
var out = { applied: false, dirty: null, canUndo: null, empty: null };
if (!scope) return out;
try {
  if (scope.$apply) {
    scope.$apply(function () {
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
""",
    ) or {}


def _log_xiumi_editor_image_order(browser, expected_html: str, stage: str):
    expected_order = _html_image_order_for_log(expected_html)
    expected_urls = _html_image_sources(expected_html)
    script = """
const expected = arguments[0];
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
    text: String(el.innerText || el.textContent || '').replace(/\\s+/g, ' ').slice(0, 120),
    srcs: srcs.map(src => src.length > 180 ? src.slice(0, 177) + '...' : src)
  };
});
"""
    try:
        editables = browser.execute_script(script, expected_urls) or []
    except Exception as exc:
        _log_xiumi_debug("xiumi_editor_image_order", stage=stage, error=str(exc), expected_order=expected_order)
        return
    best = {}
    if isinstance(editables, list) and editables:
        best = max(
            (item for item in editables if isinstance(item, dict)),
            key=lambda item: (int(item.get("expected_matches") or 0), int(item.get("image_count") or 0), int(item.get("width") or 0) * int(item.get("height") or 0)),
            default={},
        )
    actual_srcs = [_normalize_xiumi_image_url(str(src)) for src in (best.get("srcs") or [])]
    _log_xiumi_debug(
        "xiumi_editor_image_order",
        stage=stage,
        expected_count=len(expected_urls),
        actual_count=len(actual_srcs),
        exact_order_match=actual_srcs[: len(expected_urls)] == expected_urls,
        expected_order=expected_order,
        actual_order=[{"index": index, "src": _short_url(src)} for index, src in enumerate(actual_srcs, start=1)],
        best_editable=best,
        all_editables=editables,
    )


def _click_save(browser):
    save_button = browser.find_element(By.CSS_SELECTOR, "button.btn-img.op-btn.save")
    browser.execute_script("arguments[0].click();", save_button)


def _wait_for_save_result(browser, old_url: str, timeout: int) -> tuple[str, str]:
    deadline = time.time() + timeout
    while time.time() < deadline:
        current_url = browser.current_url
        if "/for/new/" not in current_url:
            return "url_changed", current_url
        if current_url != old_url and "/for/new/" not in current_url:
            return "url_changed", current_url
        if _visible_login_controls(browser) or _visible_login_links(browser):
            return "login_required", current_url
        time.sleep(1)
    return "timeout", browser.current_url


def _save_diagnostics(browser) -> dict:
    try:
        body_text = browser.execute_script("return document.body ? document.body.innerText : '';") or ""
    except Exception:
        body_text = ""
    body_text = re.sub(r"\s+", " ", str(body_text)).strip()
    return {
        "url": browser.current_url,
        "login_links": len(_visible_login_links(browser)),
        "login_controls": len(_visible_login_controls(browser)),
        "save_buttons": len(browser.find_elements(By.CSS_SELECTOR, "button.btn-img.op-btn.save")),
        "editable": len(browser.find_elements(By.XPATH, '//*[@contenteditable="true"]')),
        "body_excerpt": body_text[:240],
    }


def _fill_xiumi_fields(browser, title: str, author: str, source_url: str, digest: str):
    _set_input_value(browser, "input.title", title)
    _set_input_value(browser, "input.author", author)
    if source_url:
        _set_input_value(browser, "input.link", source_url)
    if digest:
        _set_input_value(browser, "textarea.desc", digest)


def _build_xiumi_comps_from_blocks(browser, blocks: list[dict]) -> bool:
    """直接用已知的 comp schema 在模型里构建 comps.items（样式全保留）。

    渲染层 DOM 从 comps.items[].txt1.style（camelCase CSS）和 txt1.text
    （带行内样式的 HTML）映射；scope.$apply 触发重渲染；保存时原样持久化。
    """
    result = browser.execute_script(
        """
const BLOCKS = arguments[0];
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
    _$uuid: "comp-" + Date.now().toString(36) + i,
  },
  txt1: { type: "text", text: b.text, style: b.style },
}));
const run = function () {
  layer.comps = { type: "group", constraint: { childLayout: "static" }, items: newComps };
  if (layer._qiBlock) layer._qiBlock.items = [];
};
if (scope.$apply) { scope.$apply(run); }
else { run(); }
return { ok: true, compCount: newComps.length };
""",
        blocks,
    )
    ok = bool(result and result.get("ok"))
    _log_xiumi_debug("xiumi_comps_built", ok=ok, compCount=(result or {}).get("compCount"), err=(result or {}).get("err"))
    return ok


def _fill_xiumi_body_style_aware(browser, content_html: str) -> tuple[dict, bool]:
    """按设计稿样式填充正文：seed 粘贴 + 直接构建 comps.items。"""
    print("秀米：正在按设计稿样式写入正文")
    blocks = _xiumi_html_to_blocks(content_html)
    _log_xiumi_debug("xiumi_style_aware_blocks", count=len(blocks))
    if not blocks:
        return {"status": "skipped", "uploaded": 0, "total": 0}, False

    _paste_xiumi_html(browser, "<section><p>seed</p></section>")
    time.sleep(2)
    ok = _build_xiumi_comps_from_blocks(browser, blocks)
    if not ok:
        print("秀米：按样式构建失败，退回基础粘贴流程")
        return _fill_xiumi_body_then_images(browser, content_html, pathlib.Path("."), upload_probe=False)
    dirty_state = _mark_xiumi_document_dirty(browser)
    _log_xiumi_debug("xiumi_dirty_state", **dirty_state)
    return {"status": "skipped", "uploaded": 0, "total": 0}, ok


def _read_xiumi_comp_image_srcs(browser) -> list[str]:
    values = browser.execute_script(
        """
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
"""
    )
    return [_normalize_xiumi_image_url(str(v)) for v in (values or []) if str(v or "").strip()]


def _paste_image_get_cdn_url(browser, data_url: str) -> str:
    """粘贴含 data URL 图片的片段，让秀米自动上传并返回 CDN 地址。

    data URL 直接写进文本 comp 保存后会被秀米剥离（已验证）；粘贴会触发秀米
    自己的图片上传转换，能拿到 img.xiumi.us 的持久化 URL。
    """
    probe = '<section><p>wanyou-image</p><img src="%s" style="width:60px;"><p>end</p></section>' % data_url
    _paste_xiumi_html(browser, probe)
    deadline = time.time() + 20
    while time.time() < deadline:
        for src in _read_xiumi_comp_image_srcs(browser):
            if _looks_like_user_xiumi_image(src):
                return src
        time.sleep(1)
    return ""


def _fill_xiumi_body_style_aware_with_images(browser, content_html: str, asset_base_path: pathlib.Path) -> tuple[dict, bool]:
    """样式保留模式处理图片：本地图先粘贴转 CDN，再内联进文本 comp 直接构建。"""
    for src in _local_image_sources(content_html):
        candidate = pathlib.Path(src)
        if not candidate.is_absolute():
            candidate = (asset_base_path.parent / candidate).resolve()
        if not candidate.exists():
            _log_xiumi_debug("xiumi_image_cdn_missing", src=src)
            continue
        cdn = _paste_image_get_cdn_url(browser, _image_file_to_data_url(candidate))
        if cdn:
            content_html = content_html.replace('src="%s"' % src, 'src="%s"' % cdn)
            _log_xiumi_debug("xiumi_image_cdn_inline", src=src, cdn=cdn[:90])
        else:
            _log_xiumi_debug("xiumi_image_cdn_failed", src=src)
    return _fill_xiumi_body_style_aware(browser, content_html)


def _fill_xiumi_body_then_images(browser, content_html: str, asset_base_path: pathlib.Path, *, upload_probe: bool = False, preserve_styles: bool = False) -> tuple[dict, bool]:
    if preserve_styles:
        return _fill_xiumi_body_style_aware_with_images(browser, content_html, asset_base_path)
    print("秀米：正在写入正文文字")
    text_first_html = _replace_images_with_placeholders_for_xiumi(content_html)
    model_applied = _set_editor_html(browser, text_first_html)
    _log_xiumi_debug("xiumi_body_text_model_applied", applied=bool(model_applied))
    _log_xiumi_editor_image_order(browser, text_first_html, "text_placeholders")

    upload_state = {"status": "skipped", "uploaded": 0, "total": 0}
    mode = str(getattr(config, "XIUMI_IMAGE_MODE", "upload") or "upload").strip().lower()
    if mode == "upload":
        if upload_probe:
            probe_state = _probe_xiumi_image_upload(browser)
            if probe_state.get("status") != "ok":
                print("秀米：测试图片上传失败，跳过正文图片上传。")
                upload_state = {"status": "probe_failed", "uploaded": 0, "total": _image_payload_stats(content_html)["image_count"]}
                final_html = _remove_images_for_xiumi(content_html)
                model_applied = _set_editor_html(browser, final_html)
                dirty_state = _mark_xiumi_document_dirty(browser)
                _log_xiumi_debug("xiumi_body_image_model_applied", applied=bool(model_applied))
                _log_xiumi_debug("xiumi_dirty_state", **dirty_state)
                return upload_state, model_applied

        print("秀米：正在上传正文图片")
        final_html, upload_state = _upload_xiumi_images_and_rewrite(
            browser,
            content_html,
            asset_base_path,
        )
        _log_xiumi_debug("xiumi_image_upload_state", **upload_state)
        # 无图片需要替换时 final_html 与首次粘贴内容相同，
        # 重复"清空再粘贴"会清掉已渲染内容，必须跳过。
        if final_html != text_first_html:
            print("秀米：正在应用最终排版")
            model_applied = _set_editor_html(browser, final_html)
            _log_xiumi_debug("xiumi_body_image_model_applied", applied=bool(model_applied))
            _log_xiumi_editor_image_order(browser, final_html, "final_layout")

    dirty_state = _mark_xiumi_document_dirty(browser)
    _log_xiumi_debug("xiumi_dirty_state", **dirty_state)
    return upload_state, model_applied


def publish_xiumi_draft(
    html_path: str,
    *,
    markdown: str = "",
    title: str = "",
    author: str = "物理系学生会",
    digest: str = "",
    source_url: str = "",
    profile_dir: str = "",
    home_url: str = "",
    editor_url: str = "",
    save_timeout: int = 0,
    login_timeout: int = 0,
    dry_run: bool = False,
    leave_open: bool = False,
    upload_probe: bool = False,
    apply_base_format: bool = True,
    preserve_styles: bool = False,
) -> dict:
    html_path_obj = pathlib.Path(html_path).resolve()
    if not html_path_obj.exists():
        raise FileNotFoundError(f"HTML 文件不存在: {html_path_obj}")

    content_html, asset_base_path = _resolve_content_paths(html_path_obj, markdown)
    if preserve_styles:
        # 样式保留模式走模型直接构建，基础格式/标题提升会破坏原设计稿样式。
        pass
    elif apply_base_format:
        content_html = _apply_xiumi_base_format(content_html)
    else:
        content_html = _promote_headings_for_xiumi(content_html)
    content_html = _prepare_xiumi_images(content_html, asset_base_path)

    markdown_path = pathlib.Path(markdown).resolve() if markdown else html_path_obj.with_suffix(".md")
    markdown_text = markdown_path.read_text(encoding="utf-8") if markdown_path.exists() else ""
    final_title = (title or _first_heading(markdown_text) or "万有预报").strip()
    final_digest = (digest or _first_summary_line(markdown_text) or "").strip()
    final_author = (author or "").strip()
    final_source_url = (source_url or "").strip()

    explicit_profile_dir = bool((profile_dir or "").strip())
    profile_dir_value = profile_dir or getattr(config, "XIUMI_PROFILE_DIR", "./output/selenium_cache/xiumi-profile")
    profile_dir_path = pathlib.Path(profile_dir_value).resolve()
    home_url_value = home_url or editor_url or getattr(config, "XIUMI_HOME_URL", "https://xiumi.us/studio/v5?lang=zh_CN#/")
    save_timeout_value = int(save_timeout or getattr(config, "XIUMI_SAVE_WAIT_SECONDS", 30))
    login_timeout_value = int(login_timeout or getattr(config, "XIUMI_LOGIN_WAIT_SECONDS", 600))

    _log_xiumi_debug("xiumi_profile_dir", path=str(profile_dir_path))
    browser = _make_xiumi_browser(profile_dir_path)
    result = {
        "status": "unknown",
        "editor_url": "",
        "draft_url": "",
        "title": final_title,
        "profile_dir": str(profile_dir_path),
    }
    keep_browser_open = False
    try:
        print("秀米：正在打开图文编辑器")
        _open_xiumi_editor(
            browser,
            home_url_value,
            login_timeout_value,
            max(15, getattr(config, "WAIT_TIMEOUT", 15)),
        )

        print("秀米：正在填充标题、作者和摘要")
        _fill_xiumi_fields(browser, final_title, final_author, final_source_url, final_digest)
        _fill_xiumi_body_then_images(browser, content_html, asset_base_path, upload_probe=upload_probe, preserve_styles=preserve_styles)

        result["editor_url"] = browser.current_url

        if dry_run:
            print("秀米：已完成自动填充，未点击保存")
            print(f"秀米编辑器地址：{browser.current_url}")
            result["status"] = "dry_run"
        else:
            print("秀米：正在点击保存")
            before_url = browser.current_url
            _click_save(browser)
            save_state, current_url = _wait_for_save_result(browser, before_url, save_timeout_value)
            if save_state == "login_required":
                print("秀米：保存前需要重新登录")
                logged_in = _wait_for_manual_login(browser, login_timeout_value)
                if not logged_in:
                    raise RuntimeError("秀米保存前登录未完成，已超过等待时间。")
                _open_xiumi_editor(
                    browser,
                    home_url_value,
                    login_timeout_value,
                    max(15, getattr(config, "WAIT_TIMEOUT", 15)),
                )
                _wait_editor_ready(browser, max(15, getattr(config, "WAIT_TIMEOUT", 15)))
                _fill_xiumi_fields(browser, final_title, final_author, final_source_url, final_digest)
                _fill_xiumi_body_then_images(browser, content_html, asset_base_path, upload_probe=upload_probe, preserve_styles=preserve_styles)
                before_url = browser.current_url
                print("秀米：登录完成，重新点击保存")
                _click_save(browser)
                save_state, current_url = _wait_for_save_result(browser, before_url, save_timeout_value)
            result["editor_url"] = current_url
            if save_state == "url_changed":
                print("秀米：草稿已保存")
                print(f"秀米草稿地址：{current_url}")
                result["status"] = "saved"
                result["draft_url"] = current_url
            else:
                diagnostics = _save_diagnostics(browser)
                _log_xiumi_debug("xiumi_save_diagnostics", diagnostics=diagnostics)
                print("秀米：保存状态未能自动确认，请在浏览器中检查是否已保存")
                print(f"秀米编辑器地址：{current_url}")
                result["status"] = "uncertain"

        _wait_for_user_before_closing_browser()
        return result
    except Exception as exc:
        keep_browser_open = True
        result["status"] = "error"
        result["editor_url"] = getattr(browser, "current_url", "")
        result["error"] = f"{type(exc).__name__}: {exc}"
        _log_xiumi_debug(
            "xiumi_exception",
            error=result["error"],
            traceback=traceback.format_exc(),
            url=result["editor_url"],
            excerpt=_page_excerpt(browser),
        )
        print(f"秀米：发生异常，浏览器将保留打开便于检查：{result['error']}")
        print("确认后回到命令行按回车结束程序。详细日志在 output/xiumi_debug。")
        _wait_for_user_before_closing_browser()
        return result
    finally:
        if keep_browser_open:
            _log_xiumi_debug("xiumi_browser_close", status="skipped_after_error")
        else:
            try:
                browser.quit()
            except Exception as exc:
                _log_xiumi_debug("xiumi_browser_close", status="ignored", error=str(exc))
        if (
            not keep_browser_open
            and not explicit_profile_dir
            and browser_supports_profile_dir(getattr(browser, "_wanyou_browser_name", ""))
        ):
            cleaned = _cleanup_profile_dir(profile_dir_path)
            if cleaned:
                _log_xiumi_debug("xiumi_profile_cleanup", status="removed", path=str(profile_dir_path))
            else:
                _log_xiumi_debug("xiumi_profile_cleanup", status="failed", path=str(profile_dir_path))


def main():
    _configure_console()

    parser = argparse.ArgumentParser(description="Open Xiumi paper editor, fill content, and save a draft.")
    parser.add_argument("html_path", help="Final Wanyou HTML path.")
    parser.add_argument("--markdown", default="", help="Optional Markdown path; preferred for building inline richtext.")
    parser.add_argument("--title", default="", help="Draft title to fill in Xiumi.")
    parser.add_argument("--author", default="物理系学生会", help="Author to fill in Xiumi.")
    parser.add_argument("--digest", default="", help="Digest/summary to fill in Xiumi.")
    parser.add_argument("--source-url", default="", help="Original link field to fill in Xiumi.")
    parser.add_argument(
        "--profile-dir",
        default="",
        help=(
            "Optional browser profile directory. By default the configured Xiumi profile is used and "
            "cleaned after the browser closes; explicit profile directories are preserved."
        ),
    )
    parser.add_argument("--home-url", default=getattr(config, "XIUMI_HOME_URL", "https://xiumi.us/studio/v5?lang=zh_CN#/"), help="Xiumi home/My Xiumi URL used before creating a new paper.")
    parser.add_argument("--editor-url", default="", help="Deprecated alias for --home-url; direct paper/for/new is no longer used before login.")
    parser.add_argument("--save-timeout", type=int, default=getattr(config, "XIUMI_SAVE_WAIT_SECONDS", 30))
    parser.add_argument("--login-timeout", type=int, default=getattr(config, "XIUMI_LOGIN_WAIT_SECONDS", 600))
    parser.add_argument("--dry-run", action="store_true", help="Open and fill editor, but do not click save.")
    parser.add_argument(
        "--upload-probe",
        action="store_true",
        help="Upload a generated harmless test image first; upload body images only if the probe succeeds.",
    )
    parser.add_argument(
        "--no-base-format",
        action="store_true",
        help="Skip the Xiumi base format normalization (h1 18px / p 14px). Use for content with custom large typography.",
    )
    parser.add_argument(
        "--preserve-styles",
        action="store_true",
        help="Preserve the source design's inline styles by building comps.items in the model directly (backgrounds, colors, borders, fonts survive). Local images are pasted to trigger Xiumi upload, then inlined as CDN URLs.",
    )
    parser.add_argument(
        "--leave-open",
        action="store_true",
        help="Compatibility option. The browser now stays open for editing by default until you press Enter.",
    )
    args = parser.parse_args()

    publish_xiumi_draft(
        args.html_path,
        markdown=args.markdown,
        title=args.title,
        author=args.author,
        digest=args.digest,
        source_url=args.source_url,
        profile_dir=args.profile_dir,
        home_url=args.home_url or args.editor_url,
        save_timeout=args.save_timeout,
        login_timeout=args.login_timeout,
        dry_run=args.dry_run,
        leave_open=args.leave_open,
        upload_probe=args.upload_probe,
        apply_base_format=not args.no_base_format,
        preserve_styles=args.preserve_styles,
    )


if __name__ == "__main__":
    main()
