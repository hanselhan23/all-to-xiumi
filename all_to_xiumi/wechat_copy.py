"""Build a self-contained, inline-styled article with a rich-text copy button.

This prepares the clipboard artifact; it does not log in to WeChat or save a draft.
"""

import base64
import hashlib
import html
import io
import logging
import re
from pathlib import Path
from urllib.parse import unquote, urlparse
from urllib.request import Request, urlopen


_URL = re.compile(r"url\(\s*(['\"]?)(.*?)\1\s*\)", re.I)
_BLOCKED = {"script", "iframe", "video", "audio", "canvas", "object", "embed", "svg", "picture"}


def _dependencies():
    try:
        from lxml import html as lhtml
        from PIL import Image
        from premailer import Premailer
        import cssutils
    except ImportError as exc:
        raise RuntimeError('公众号直接复制需要可选依赖：在仓库中执行 pip install -e ".[wechat]"') from exc
    return lhtml, Image, Premailer, cssutils


def _image_data(src, base_dir, Image):
    """Validate image bytes and preserve them exactly, including animated GIFs."""
    src = html.unescape(src).strip()
    if src.lower().startswith("data:"):
        header, sep, payload = src.partition(",")
        if not sep or not header.lower().startswith("data:image/"):
            raise ValueError("图片必须使用有效的 image data URL")
        try:
            data = base64.b64decode(payload, validate=True) if ";base64" in header.lower() else unquote(payload).encode("utf-8")
        except ValueError as exc:
            raise ValueError("图片 data URL 的编码无效") from exc
    elif src.startswith(("http://", "https://", "//")):
        address = "https:" + src if src.startswith("//") else src
        with urlopen(Request(address, headers={"User-Agent": "all-to-xiumi/0.1"}), timeout=30) as response:
            data = response.read()
    else:
        parsed = urlparse(src)
        if parsed.scheme == "file":
            name = unquote(parsed.path)
            if re.match(r"^/[A-Za-z]:/", name):
                name = name[1:]
            path = Path(name)
        else:
            path = Path(unquote(src.split("?", 1)[0].split("#", 1)[0]))
            if not path.is_absolute():
                path = Path(base_dir) / path
        data = path.read_bytes()
    try:
        with Image.open(io.BytesIO(data)) as image:
            mime = Image.MIME.get(image.format)
            size = image.size
            frames = getattr(image, "n_frames", 1)
            image.verify()
    except Exception as exc:
        raise ValueError("图片无法解码；SVG 或其他非位图素材需另行验证，不能声明复制无损") from exc
    if mime not in {"image/png", "image/jpeg", "image/gif", "image/webp"}:
        raise ValueError(f"未支持的公众号图片格式：{mime}")
    url = f"data:{mime};base64," + base64.b64encode(data).decode("ascii")
    return url, {"sha256": hashlib.sha256(data).hexdigest(), "mime": mime,
                 "width": size[0], "height": size[1], "frames": frames, "bytes": len(data)}


def _content_node(document):
    for selector in ("#gzh-content", "#wechat-content", "article", "body"):
        matches = document.cssselect(selector)
        if matches:
            return matches[0]
    raise ValueError("找不到正文区域")


def _check_css(document, content, cssutils):
    """Do not silently discard media-dependent or generated article content."""
    parser = cssutils.CSSParser(loglevel=logging.CRITICAL, fetcher=lambda _: (None, None))
    for sheet_node in document.cssselect("style"):
        sheet = parser.parseString(sheet_node.text or "")
        for rule in sheet.cssRules:
            if rule.type in (rule.IMPORT_RULE, rule.FONT_FACE_RULE):
                raise ValueError("正文样式含 @import 或 @font-face；请先验证并准备不依赖外部字体/样式的兼容稿")
            if rule.type not in (rule.MEDIA_RULE, rule.STYLE_RULE):
                continue
            rules = rule.cssRules if rule.type == rule.MEDIA_RULE else [rule]
            for child in rules:
                if child.type != child.STYLE_RULE:
                    continue
                for selector in child.selectorList:
                    text = selector.selectorText
                    plain = re.sub(r"::?(before|after)$", "", text)
                    try:
                        applies = any(node is content or content in node.iterancestors() or node in content.iterancestors()
                                      for node in document.cssselect(plain))
                    except Exception:
                        raise ValueError(f"无法验证正文 CSS 选择器：{text}")
                    if applies and (rule.type == rule.MEDIA_RULE or plain != text):
                        raise ValueError("正文依赖媒体查询或伪元素；请先提供等价的行内响应式布局，再生成直复制样本")


def prepare_wechat_copy(source, *, base_dir, title="公众号推送"):
    """Return (complete HTML, media audit), without contacting Xiumi."""
    lhtml, Image, Premailer, cssutils = _dependencies()
    document = lhtml.document_fromstring(source)
    content = _content_node(document)
    _check_css(document, content, cssutils)
    for node in content.iter():
        if not isinstance(node.tag, str):
            continue
        tag = node.tag.lower()
        if tag in _BLOCKED:
            raise ValueError(f"正文含 {tag}：需公众号原生组件或专门的兼容验证，不能静默删除后声明复制无损")
        if node.get("srcset"):
            raise ValueError("正文含 srcset；请先确定并验证公众号要使用的图片版本")
        if any(key.lower().startswith("on") for key in node.attrib):
            raise ValueError("正文依赖事件脚本，不能通过富文本剪贴板保留")
    # Network access is restricted to explicitly referenced image resources below.
    if document.cssselect("link[rel='stylesheet']"):
        raise ValueError("请先将外部样式表放入 HTML；直接复制不依赖外部 CSS")
    inlined = Premailer(lhtml.tostring(document, encoding="unicode"),
                       allow_network=False, remove_classes=False,
                       keep_style_tags=False, disable_validation=True,
                       cssutils_logging_level=logging.CRITICAL).transform()
    document = lhtml.document_fromstring(inlined)
    content = _content_node(document)
    assets = {}

    def embed(src):
        if src not in assets:
            assets[src] = _image_data(src, base_dir, Image)
        return assets[src][0]

    for node in content.iter():
        if not isinstance(node.tag, str):
            continue
        style = node.get("style", "")
        if "var(" in style or re.search(r"(?:^|;)\s*(animation|transition)(?:-|\s*:)", style):
            raise ValueError("正文样式依赖 CSS 变量或动画，需要先完成公众号兼容验证")
        if style:
            node.set("style", _URL.sub(lambda match: 'url("' + embed(match.group(2)) + '")', style))
        if node.tag.lower() == "img":
            if not node.get("src"):
                raise ValueError("正文有缺少 src 的图片")
            node.set("src", embed(node.get("src")))
        if node.tag.lower() == "a":
            href = node.get("href", "")
            if href.lower().startswith("javascript:"):
                raise ValueError("正文链接依赖脚本")
    # Keep the content container itself: its inline style may carry inheritance.
    content.tag = "section"
    content.set("id", "wechat-article")
    article = lhtml.tostring(content, encoding="unicode", with_tail=False)
    audit = {"images": len(content.cssselect("img")), "assets": [item[1] for item in assets.values()],
             "all_images_embedded": True, "external_stylesheets": 0,
             "clipboard_validation": "pending", "wechat_save_validation": "pending"}
    return _page(article, title), audit


def _page(article, title):
    # Only toolbar CSS lives in <head>; everything in the copied article is inline.
    return """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>""" + html.escape(title) + """</title><style>
body{margin:0;background:#eef0f2;font-family:Arial,'Microsoft YaHei',sans-serif}
.gzh-toolbar{position:fixed;inset:0 0 auto;height:54px;background:white;display:flex;align-items:center;justify-content:space-between;padding:0 16px;z-index:99;box-shadow:0 1px 10px #0001}
.gzh-hint{font-size:13px;color:#6b7280}.gzh-copy{background:#059669;color:white;border:0;border-radius:9px;padding:10px 20px;font-size:14px;font-weight:700;cursor:pointer}
.gzh-stage{max-width:700px;margin:78px auto 64px;padding:0 8px}
.gzh-toast{position:fixed;top:64px;left:50%;transform:translateX(-50%);background:#111827;color:white;padding:10px 16px;border-radius:9px;font-size:14px;z-index:100;max-width:85vw;display:none}
@media(max-width:520px){.gzh-hint{max-width:150px}}
</style></head><body>
<div class="gzh-toolbar"><span class="gzh-hint">正文和图片已内嵌 · 复制后到公众号正文区粘贴</span><button class="gzh-copy" id="gzhCopyBtn" type="button">复制到公众号</button></div>
<div class="gzh-toast" id="gzhToast" role="status"></div><main class="gzh-stage"><div id="gzh-content">
""" + article + """
</div></main><script>
function gzhShowToast(message){const el=document.getElementById('gzhToast');el.textContent=message;el.style.display='block';clearTimeout(el.timer);el.timer=setTimeout(()=>el.style.display='none',3500);}
async function gzhCopy(){
  const root=document.getElementById('gzh-content');
  if([...root.querySelectorAll('img')].some(img=>!img.complete||!img.naturalWidth)){gzhShowToast('图片尚未加载完成，请稍后重试；不要复制缺图的正文。');return;}
  const rich=root.innerHTML,plain=root.innerText;
  const selection=window.getSelection(),range=document.createRange();range.selectNodeContents(root);selection.removeAllRanges();selection.addRange(range);
  const handler=event=>{event.clipboardData.setData('text/html',rich);event.clipboardData.setData('text/plain',plain);event.preventDefault();};
  document.addEventListener('copy',handler);let copied=false;
  try{copied=document.execCommand('copy');}catch(error){}finally{document.removeEventListener('copy',handler);}
  if(!copied&&navigator.clipboard&&window.ClipboardItem){try{await navigator.clipboard.write([new ClipboardItem({'text/html':new Blob([rich],{type:'text/html'}),'text/plain':new Blob([plain],{type:'text/plain'})})]);copied=true;}catch(error){}}
  if(copied){selection.removeAllRanges();gzhShowToast('已复制正文、样式和图片；到公众号正文区按 Ctrl/⌘+V，检查后保存。');}else{gzhShowToast('自动复制失败：正文已选中，请按 Ctrl/⌘+C 复制。');}
}
document.getElementById('gzhCopyBtn').addEventListener('click',gzhCopy);
</script></body></html>
"""
