---
name: all-to-xiumi
description: 将本地 HTML、Markdown 或 PDF 文件转换并保存为秀米编辑器草稿。适用于把已经完成的设计稿或文档发布到秀米：HTML 可通过 --preserve-styles 保留行内背景、渐变、边框和字体等样式；Markdown/PDF 则先经过 generic、wanyou 或 red 模板转换再发布。本技能只负责单次发布，不负责抓取或生成内容。
---

# all-to-xiumi

[English version](SKILL.en.md)

## 用途

通过一个命令行工具和一套 Python API，将本地文件转换并保存为秀米草稿：

| 输入 | 处理路径 |
|---|---|
| `.html` | 直接交给发布核心。默认使用粘贴路径；`--preserve-styles` 可保留设计稿的行内样式。 |
| `.md` | 通过 `markdown_to_html` 的模板系统转换为 HTML，再交给发布核心。 |
| `.pdf` | 使用 pdfplumber 提取文字，作为 Markdown 源处理，后续流程与 `.md` 相同。 |

## 命令

### 发布 HTML 文件（粘贴路径）

```powershell
$env:WANYOU_SELENIUM_BROWSER='chrome'; $env:PYTHONIOENCODING='utf-8'
all-to-xiumi path/to/your.html --title "推送标题" --author "作者"
```

若同目录存在同名 `.md` 文件，程序会自动将它作为图片基准路径以及标题、摘要来源。

### 发布 Markdown 文件（模板转换）

```powershell
all-to-xiumi path/to/your.md --template generic --title "推送标题" --author "作者"
```

可用模板：`generic`（默认）、`wanyou`（清华物理系风格）、`red`（理论学习/党建）和 `auto`（按关键词自动识别）。转换后的 HTML 写入 `output/<stem>.html`。

### 发布 PDF 文件

```powershell
all-to-xiumi path/to/your.pdf --title "推送标题"
```

需要 pdfplumber：可执行 `pip install all-to-xiumi[pdf]` 安装；首次处理 PDF 时也会自动安装。

### 保留设计型 HTML 的样式（模型构建路径）

```powershell
all-to-xiumi path/to/your.html --title "推送标题" --preserve-styles --no-base-format
```

- `--preserve-styles`：直接构建模型中的 `comps.items`，保留源文件的行内样式。
- `--no-base-format`：避免默认的 14px/18px 规范化压缩大型标题。`.md` 和 `.pdf` 输入默认保留模板自身的排版。
- 此模式会通过秀米自身的上传机制处理本地图片，再将得到的 **CDN URL**（`img.xiumi.us/...`）写入文本组件。CDN URL 能在保存后持续有效，而 `data:` URL 会被秀米清除，详见“秀米发布陷阱”。

### 仅生成 HTML / 试运行

```powershell
all-to-xiumi path/to/your.md --template generic --html-only      # 只生成 HTML，不打开浏览器
all-to-xiumi path/to/your.html --title "标题" --dry-run           # 打开并填充编辑器，不点击保存
```

### 浏览器与用户配置目录

```powershell
all-to-xiumi path/to/your.html --title "标题" --profile-dir output/selenium_cache/my-xiumi-profile --home-url "https://xiumi.us/studio/v5?lang=zh_CN#/"
```

- `--profile-dir` 用于跨运行保留登录状态；未指定时，浏览器关闭后会清理临时配置目录。
- 正常发布（非 `--dry-run`）必须实际点击秀米编辑器中可见的“保存”按钮。检测到保存成功后，还必须重新载入草稿并确认内容仍可正确渲染；不得只依赖模型写入、自动保存状态或按钮的 JavaScript 回调。
- 保存后保持浏览器窗口打开，供人工复核；在终端按 Enter 后关闭。
- 所有命令行参数都映射到 `all_to_xiumi/` 中的 `run_skill(...)` 或 `publish_xiumi_draft(...)`。

## Python 接口

```python
from all_to_xiumi import run_skill

result = run_skill("input.md", template="generic", title="标题", author="作者")
# → {html_content, html_path, markdown_text, template, draft_url, status, ...}
```

## 环境配置

Windows PowerShell 不会继承 Bash 环境变量，每次运行都应显式设置：

```powershell
$env:WANYOU_SELENIUM_BROWSER='chrome'; $env:PYTHONIOENCODING='utf-8'
```

配置位于 `all_to_xiumi/config.py`，从 `.env` 加载，示例见 `.env.example`。图片处理方式由 `XIUMI_IMAGE_MODE` 控制：

| `XIUMI_IMAGE_MODE` | 行为 |
|---|---|
| `upload`（默认） | 将本地图片上传到秀米图库，改写 URL，再应用版式。 |
| `inline` | 将本地图片转换成 base64 data URL。HTML 会更大，但无需上传步骤。 |
| `auto` | 优先尝试内嵌；HTML 超过 `XIUMI_MAX_INLINE_IMAGE_HTML_CHARS` 时回退为省略图片。 |
| `omit` | 移除所有图片并保留占位符。 |

## 秀米发布陷阱

以下结论均经过真实草稿验证。修改 `all_to_xiumi/xiumi_publish.py` 的编辑器写入逻辑前应先阅读本节。

### 直接注入 innerHTML 可以保存，但不会渲染

秀米编辑器是 Angular 应用。真正的渲染层是 `comps.items`；通过 `innerHTML=` 或 `scope.cell.text=` 注入的内容会落入 `_qiBlock.items` 冻结层。表现为保存提示成功，但重新打开后正文为空。

**处理方式：可信粘贴。** 先执行 `navigator.clipboard.write([new ClipboardItem({'text/html': blob, 'text/plain': blob})])`，聚焦 `[contenteditable]`，再通过 CDP `Input.dispatchKeyEvent` 发送 Ctrl+V（`modifiers:2, key:"v", code:"KeyV", windowsVirtualKeyCode:86`）。这样会由秀米自身的粘贴处理器在 `comps.items` 中建立渲染组件。

### 粘贴处理器会清除行内样式

普通粘贴后仅 `text-align:justify` 会保留；`<h1>/<h2>/<h3>` 分别映射为 180%/140%/120% 的语义字号；相邻区块会合并为一个文本组件。颜色、背景、边框等样式无法通过普通粘贴保留。需要完整保存源设计时使用 `--preserve-styles`。

### data: 图片地址保存后会被清除，CDN 地址可保留

写入文本组件的 `data:image/...` 地址在当前编辑器中能够显示，但保存并重新打开后其 `src` 会变为空。处理方式是：粘贴包含 data URL 的片段，让秀米自身的粘贴处理器完成上传；读取新建图片组件中的 `//img.xiumi.us/xmi/ua/...` 地址；再把该 **CDN URL** 写入文本组件。CDN URL 能在保存和重载后保留。

### 清空后粘贴可保持幂等，但重复粘贴相同内容会清空草稿

清空操作是 Ctrl+A 后按 Delete，再粘贴，因此只保留最后一次内容。若 HTML 不含图片，`final_html == text_first_html`；此时第二次“清空并粘贴”会抹掉已经渲染的正文，造成空白草稿。`_fill_xiumi_body_then_images` 通过 `if final_html != text_first_html:` 跳过无意义的第二次粘贴。

### preserve-styles 的组件结构

源文件中的每个顶层 `<section>` 对应一个区块：

- `<section>` 的行内 CSS 转换为 camelCase 后写入 `comps.items[].txt1.style`。
- 内部 HTML（带行内样式的段落和 span）写入 `txt1.text`。
- 嵌套的 `<section>`/`<div>` 转换为 `<p>` 并保留样式；浏览器解析器会自动闭合嵌套的 `<p>`；删除空的 `<p></p>` 残片。

组件结构：

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

模型入口：

```javascript
window.angular.element(contenteditable).scope()._$.pages[0].layers[0].comps.items
```

### 图片组件需要完整的 `_comp`

文本组件需要完整 `_comp`，其 `tplId` 为 `paper-cp:header/1-txt-normal`；图片组件需要 `tplId: paper-cp:image/img-autowidth`，并同时包含 pose、constraint、style 和 uuid，否则不会渲染。修改模型后必须调用 `scope.$apply()`，再点击保存并重新载入验证；只在当前会话中重建无法恢复轮播等渲染轨道。

### 秀米渲染时会改写 `<img src>`

渲染器会在图片地址后追加 `?x-oss-process=style/xmwebp`。验证图片时应对 `src` 做规范化处理，去掉协议和查询参数后再比较，不要要求完整字符串完全相等。

### 持久化配置目录中的恢复对话框会阻塞编辑器

编辑器可能弹出“上次没有保存到服务器，是否恢复?”，从而阻塞后续操作。必须点击“取消”或“确定”关闭它；该逻辑由 `_dismiss_xiumi_recover_dialog` 自动处理。

## 调试规则

- 登录失败或无法识别登录状态时，先查看 `output/xiumi_debug/*.jsonl` 中的登录和上传诊断。发生错误时浏览器会保持打开，应直接检查窗口中的实际状态。
- 已进入编辑器但正文没有应用时，可能需要更新 `contenteditable` 或 Angular scope 的检测逻辑；检查调试日志中的 `xiumi_body_text_model_applied`。
- 若所有图片均上传失败，且连续失败次数达到 `XIUMI_IMAGE_UPLOAD_MAX_FAILURES`，应中止图片上传并保留占位符。
- 个别图片上传失败时跳过该图片，并替换成“[配图上传未完成]”占位符，不阻塞整篇草稿。
- 保存状态为 `uncertain` 时，草稿可能已经保存，应检查浏览器中的编辑器 URL。保存后浏览器窗口保持打开，供人工复核。
- 使用 `--dry-run` 测试而不保存，避免在秀米中产生孤立草稿。
- `output/xiumi_debug/*.jsonl` 是主要诊断目标；修改 `all_to_xiumi/xiumi_publish.py` 前先检查这些日志。
- 不得覆盖在线草稿中尚未提交的人工修改；只修改当前任务明确涉及的区域。

## 仓库结构

- `all_to_xiumi/xiumi_publish.py`：秀米发布核心。以 HTML 为主；Markdown 参数只用于图片基准路径以及标题、摘要来源。
- `all_to_xiumi/markdown_to_html.py`：基于模板的 Markdown → 行内样式 HTML 转换器。
- `all_to_xiumi/templates/`：模板系统（generic / wanyou / red）；通过 `register_template` 注册自定义模板。
- `all_to_xiumi/skill_pipeline.py`：`run_skill`，负责输入分发、Markdown/PDF 转换和发布。
- `all_to_xiumi/browser.py`、`image_paths.py`、`env_loader.py`、`config.py`：浏览器及配置支持。
- `all_to_xiumi/generators/h5_generator.py`：H5 导出生成器，继续保留，但不参与发布路径。
- `examples/`：验证和诊断脚本。
