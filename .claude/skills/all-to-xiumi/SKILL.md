---
name: all-to-xiumi
description: Turn a local HTML / Markdown / PDF file into a saved Xiumi 秀米 editor draft. Use when finished content (a designed HTML page, or a Markdown/PDF document) needs to become a Xiumi draft — HTML input can preserve the source design's inline styles (backgrounds, gradients, borders, fonts) via --preserve-styles; Markdown/PDF input is converted through a template system (generic/wanyou/red) then published. Focuses on the single publish step; does not crawl or generate content.
---

# all-to-xiumi

## Purpose

One CLI + Python API that turns a local file into a saved Xiumi (秀米) draft:

| Input | Path |
|---|---|
| `.html` | Passed straight to the publish core. Default paste path; `--preserve-styles` keeps the design's inline styles. |
| `.md` | Converted by `markdown_to_html` (template system) → HTML file → publish core. |
| `.pdf` | Text extracted (pdfplumber) → treated as Markdown source → same as `.md`. |

## Commands

### Publish an HTML file (paste path)

```powershell
$env:WANYOU_SELENIUM_BROWSER='chrome'; $env:PYTHONIOENCODING='utf-8'
all-to-xiumi path/to/your.html --title "推送标题" --author "作者"
```

When a sibling `.md` exists it is auto-detected as the image base + title/digest source.

### Publish a Markdown file (template conversion)

```powershell
all-to-xiumi path/to/your.md --template generic --title "推送标题" --author "作者"
```

Templates: `generic` (default), `wanyou` (清华物理系风格), `red` (理论学习/党建), or `auto` (keyword detection). The converted HTML is written to `output/<stem>.html`.

### Publish a PDF

```powershell
all-to-xiumi path/to/your.pdf --title "推送标题"
```

Requires pdfplumber (`pip install all-to-xiumi[pdf]`; auto-installed on first PDF run).

### Preserve a design HTML's styles (model-build path)

```powershell
all-to-xiumi path/to/your.html --title "推送标题" --preserve-styles --no-base-format
```

- `--preserve-styles` keeps the source design's inline styles by building `comps.items` in the model directly.
- `--no-base-format` avoids the default 14px/18px normalization that squashes custom large typography (for `.md`/`.pdf` input the template's own typography is kept by default).
- In this mode local images are pasted to trigger Xiumi's own upload, then inlined as **CDN URLs** (`img.xiumi.us/...`) inside the text comp — these persist through save, unlike `data:` URLs (see Pitfalls).

### HTML only / dry run

```powershell
all-to-xiumi path/to/your.md --template generic --html-only      # 只生成 HTML，不打开浏览器
all-to-xiumi path/to/your.html --title "标题" --dry-run           # 打开并填充编辑器，不点击保存
```

### Browser / profile options

```powershell
all-to-xiumi path/to/your.html --title "标题" --profile-dir output/selenium_cache/my-xiumi-profile --home-url "https://xiumi.us/studio/v5?lang=zh_CN#/"
```

- `--profile-dir` keeps the login session across runs. Without it, the browser profile is cleaned up after the browser closes.
- The script keeps the browser open after save for manual verification; press Enter in the terminal to close it.
- All CLI flags map to `run_skill(...)` / `publish_xiumi_draft(...)` in `all_to_xiumi/`.

## Python API

```python
from all_to_xiumi import run_skill

result = run_skill("input.md", template="generic", title="标题", author="作者")
# → {html_content, html_path, markdown_text, template, draft_url, status, ...}
```

## Environment

Windows PowerShell does not inherit bash env vars — set these on every command:

```powershell
$env:WANYOU_SELENIUM_BROWSER='chrome'; $env:PYTHONIOENCODING='utf-8'
```

Config lives in `all_to_xiumi/config.py`, loaded from `.env` (see `.env.example`). Image handling is controlled by `XIUMI_IMAGE_MODE`:

| `XIUMI_IMAGE_MODE` | Behavior |
|---|---|
| `upload` (default) | Upload local images to the Xiumi gallery, rewrite URLs, then apply layout. |
| `inline` | Convert local images to base64 data URLs inline. Larger HTML but no upload step. |
| `auto` | Try inline; fall back to omit if HTML exceeds `XIUMI_MAX_INLINE_IMAGE_HTML_CHARS`. |
| `omit` | Remove all images and leave placeholders. |

## Xiumi Editor Publish Pitfalls (verified against real drafts)

Read before touching editor-write logic in `all_to_xiumi/xiumi_publish.py`.

### Direct innerHTML injection saves but never renders → empty draft

The Xiumi editor is an Angular app. The rendering layer is `comps.items`; content injected via `innerHTML=` or `scope.cell.text=` lands in `_qiBlock.items` (frozen layer — it saves but never renders). Symptom: save reports success but the body opens empty.

**Fix: trusted paste.** `navigator.clipboard.write([new ClipboardItem({'text/html': blob, 'text/plain': blob})])` → focus `[contenteditable]` → CDP `Input.dispatchKeyEvent` Ctrl+V (`modifiers:2, key:"v", code:"KeyV", windowsVirtualKeyCode:86`). This makes Xiumi's own paste handler build rendering-layer components under `comps.items`.

### Paste handler strips all inline styles

Only `text-align:justify` survives; `<h1>/<h2>/<h3>` map to semantic font-size 180%/140%/120%; adjacent blocks merge into ONE text component. Paste cannot preserve colors/backgrounds/borders. To keep the full source design, use `--preserve-styles` above.

### data: image URLs get stripped after save; CDN URLs persist

A `data:image/...` URL written into a text comp's model renders in the editor but its `src` is stripped on save (reopening shows `<img src>` empty). Workaround: paste a fragment containing the data URL so Xiumi's own paste handler uploads it, read back the resulting `//img.xiumi.us/xmi/ua/...` URL from the generated image comp, then inline that **CDN URL** into the text comp. CDN URLs persist through save and reopen.

### Clear-then-paste is idempotent, but re-pasting identical content clears the draft

Clear = Ctrl+A + Delete, then re-paste; only the last content survives. Gotcha: when the HTML has no images, `final_html == text_first_html`, so the second clear+paste wipes the already-rendered content → empty draft. `_fill_xiumi_body_then_images` guards with `if final_html != text_first_html:` to skip the second paste.

### Preserve-styles comp schema

Each TOP-LEVEL `<section>` of the source becomes one block:

- The section's inline CSS (camelCased) → `comps.items[].txt1.style`
- The inner HTML (paragraphs/spans with their inline styles) → `txt1.text`
- Convert nested `<section>`/`<div>` to `<p>` (keep their style; the browser's HTML parser auto-closes nested `<p>`), drop empty `<p></p>` artifacts.

Comp schema:

```python
{
  "_comp": {
    "constraint": {"opMenu": {"text-merged": True}, "pose": {"resize": "h"}},
    "pose": {"position": "static", "width": None, "height": None},
    "style": {},
    "tplId": "paper-cp:header/1-txt-normal",
    "_$uuid": "comp-xxx",
  },
  "txt1": {"type": "text", "text": "<p style=...>...</p>", "style": {"camelCase CSS"}},
}
```

Reach the model:

```javascript
window.angular.element(contenteditable).scope()._$.pages[0].layers[0].comps.items
```

### Image components need a full `_comp`

Text comps need a complete `_comp` (`tplId: paper-cp:header/1-txt-normal`); image comps need `tplId: paper-cp:image/img-autowidth` + pose/constraint/style/uuid — otherwise they don't render. After a model edit, always `scope.$apply()` then **save and reload** to verify render (in-session rebuilds don't reconstruct rendered tracks like sliders).

### Xiumi rewrites `<img src>` on render

The renderer appends `?x-oss-process=style/xmwebp` to img src. Verify image presence by normalized src (strip scheme/query), not exact match.

### Persistent-profile recover dialog blocks the editor

The editor may pop a "上次没有保存到服务器，是否恢复?" dialog that blocks editing. It must be dismissed (click 取消/确定). Handled automatically by `_dismiss_xiumi_recover_dialog`.

## Debug Rules

- If login fails or is not detected, look for `output/xiumi_debug/*.jsonl` for login/upload diagnostics. The browser is kept open on error — check the browser window directly.
- If the editor enters but text is not applied, the `contenteditable` / Angular scope detection may need updating — check `xiumi_body_text_model_applied` in the debug log.
- If image upload fails for all images (consecutive failures >= `XIUMI_IMAGE_UPLOAD_MAX_FAILURES`), the script aborts image upload and leaves placeholders.
- If individual images fail to upload, they are skipped and replaced with a "[配图上传未完成]" placeholder rather than blocking the whole draft.
- If the editor save state is "uncertain", the draft may still have been saved — check the editor URL in the browser. The browser window stays open after save for manual verification.
- Use `--dry-run` to test without saving, avoiding orphan drafts in Xiumi.
- `output/xiumi_debug/*.jsonl` is the primary diagnostics target. Look there before changing `all_to_xiumi/xiumi_publish.py`.
- Never touch a live draft's uncommitted manual edits; only mutate the model for the specific region being changed.

## Repository Layout

- `all_to_xiumi/xiumi_publish.py` — Xiumi publish core (HTML-driven; markdown param is only the image base + title/digest source).
- `all_to_xiumi/markdown_to_html.py` — Markdown → styled inline HTML converter (template-based).
- `all_to_xiumi/templates/` — template system (generic / wanyou / red); `register_template` for custom ones.
- `all_to_xiumi/skill_pipeline.py` — `run_skill`: input dispatch + md/pdf conversion + publish.
- `all_to_xiumi/browser.py` / `image_paths.py` / `env_loader.py` / `config.py` — browser & config support.
- `all_to_xiumi/generators/h5_generator.py` — H5 export generator (kept; not on the publish path).
- `examples/` — verification/diagnostic scripts.
