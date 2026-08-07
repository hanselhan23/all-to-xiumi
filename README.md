# all-to-xiumi

把本地 **HTML / Markdown / PDF** 一键发布为**秀米（Xiumi）草稿**。

合并自两个仓库：

- **[html-to-xiumi](https://github.com/hanselhan23/html-to-xiumi)** — 秀米保存 / 编辑核心（采用更新版本）
- **[xiumi_publisher](https://github.com/hanselhan23/xiumi_publisher)** — Markdown/PDF → 模板富文本的转换与流水线

## 功能

| 输入 | 处理方式 |
|---|---|
| `.html` | 直接进入秀米发布核心。默认粘贴路径；`--preserve-styles` 可在模型级保留设计稿内联样式（背景 / 渐变 / 边框 / 字体）。 |
| `.md` | 用模板系统（`generic` / `wanyou` / `red`）转成富文本 HTML，再发布。 |
| `.pdf` | 提取文本（pdfplumber）后按 Markdown 源处理，走与 `.md` 相同流程。 |

发布核心完全沿用 html-to-xiumi 的秀米交互（登录、填充、图片上传、保存、恢复对话框处理），并沉淀了经真实草稿验证的编辑器陷阱（见 [SKILL.md](.claude/skills/all-to-xiumi/SKILL.md)）。

## 安装

```powershell
cd all-to-xiumi
pip install -r requirements.txt        # 基础（selenium）
pip install -e .                       # 安装为包，获得 all-to-xiumi 命令
pip install -e ".[pdf]"                # 若需要 PDF 输入
```

## 快速开始

Windows PowerShell 每次命令都需设置浏览器与编码：

```powershell
$env:WANYOU_SELENIUM_BROWSER='chrome'; $env:PYTHONIOENCODING='utf-8'
```

发布 HTML（保留设计稿样式）：

```powershell
all-to-xiumi path/to/your.html --title "推送标题" --author "作者" --preserve-styles --no-base-format
```

发布 Markdown：

```powershell
all-to-xiumi path/to/your.md --template generic --title "推送标题" --author "作者"
```

发布 PDF：

```powershell
all-to-xiumi path/to/your.pdf --title "推送标题"
```

只生成富文本 HTML（不打开浏览器）：

```powershell
all-to-xiumi path/to/your.md --template generic --html-only
```

不点击保存的试运行：

```powershell
all-to-xiumi path/to/your.html --title "推送标题" --dry-run
```

> 发布完成后浏览器保持打开，方便人工检查 / 微调；回到命令行按 **Enter** 关闭。

## Claude Code Skill

仓库自带 Claude Code skill（`.claude/skills/all-to-xiumi/SKILL.md`）。在 `all-to-xiumi` 目录内使用时自动生效，可直接对 Claude Code 说「把 `file.md` 发成秀米草稿」或 `/all-to-xiumi`，由 Claude 调用本仓库的发布功能。skill 内沉淀了经真实草稿验证的编辑器陷阱（innerHTML 不渲染、paste 剥样式、data: URL 保存后被剥离、CDN 内联、`--preserve-styles` 模型 schema 等）。

若希望在任何项目里全局可用，把 skill 复制到本地技能目录：

```powershell
$local = Join-Path $HOME ".claude\skills\all-to-xiumi"
Copy-Item -Recurse .claude\skills\all-to-xiumi $local
```

之后修改仓库里的 `SKILL.md` 时，重新执行上面的 `Copy-Item`（或把 `$local` 建成仓库目录的符号链接）以同步本地副本。

## 主要选项

| 选项 | 说明 |
|---|---|
| `--template {auto,generic,wanyou,red}` | md/pdf 模板；`auto` 按关键词自动检测（默认） |
| `--title` / `--subtitle` / `--author` / `--digest` / `--source-url` | 草稿字段 |
| `--preserve-styles` | 模型级保留源设计样式（适合设计稿 HTML） |
| `--no-base-format` / `--base-format` | 秀米 base 格式归一化（h1 18px / p 14px）。默认：html 输入应用，md/pdf 输入不应用（保留模板排版） |
| `--html-only` | 只生成 HTML，不打开浏览器 |
| `--dry-run` | 打开并填充编辑器，不点击保存 |
| `--image-mode {upload,auto,inline,omit}` | 图片处理模式（默认取 `XIUMI_IMAGE_MODE`） |
| `--profile-dir` | 浏览器 profile 目录（保留登录态） |
| `--home-url` | 秀米首页 URL |
| `--login-timeout` / `--save-timeout` | 超时秒数 |
| `--upload-probe` | 上传前先测试图片上传链路 |

## 配置

`.env.example` → 复制为 `.env` 并按需填写。项目启动时自动加载（Windows / macOS 无需 shell export）。

```dotenv
WANYOU_SELENIUM_BROWSER=chrome
XIUMI_HOME_URL=https://xiumi.us/studio/v5?lang=zh_CN#/
XIUMI_PROFILE_DIR=./output/selenium_cache/xiumi-profile
XIUMI_IMAGE_MODE=upload
```

完整配置项见 [all_to_xiumi/config.py](all_to_xiumi/config.py)。

## Python API

```python
from all_to_xiumi import run_skill

result = run_skill("input.md", template="generic", title="标题", author="作者")
# result: {html_content, html_path, markdown_text, template, structure, draft_url, editor_url, status}
```

其他导出：`markdown_to_html`、`publish_xiumi_draft`、`get_template` / `list_templates` / `register_template`、`Template`。

## 目录结构

```
all-to-xiumi/
├── .claude/skills/all-to-xiumi/SKILL.md   # Claude Code skill（含编辑器陷阱）
├── all_to_xiumi/
│   ├── cli.py                 # 统一命令行入口
│   ├── skill_pipeline.py      # run_skill：输入分发 + md/pdf 转换 + 发布
│   ├── xiumi_publish.py       # 秀米发布核心（HTML 驱动）
│   ├── markdown_to_html.py    # Markdown → 模板富文本
│   ├── templates/             # generic / wanyou / red
│   ├── browser.py / image_paths.py / env_loader.py / config.py
│   └── generators/h5_generator.py   # H5 导出（保留，不在发布主链路）
├── examples/                  # 验证 / 诊断脚本
├── tests/                     # markdown_to_html 单测
└── format.md                  # 秀米 base 格式说明
```

## 测试

```powershell
pip install pytest
python -m pytest tests/ -q
```

## 与两个源仓库的差异

- 统一入口 `all-to-xiumi <html|md|pdf>`；旧 `publish_xiumi_draft.py` 脚本入口保留在 `all_to_xiumi/xiumi_publish.py`（`python -m all_to_xiumi.xiumi_publish`）。
- 秀米交互只用 html-to-xiumi 的新实现；xiumi_publisher 的旧 `publish.py`（与 `wechat_inline` 转换器）未合并。
- Markdown 转换统一走模板系统 `markdown_to_html`；`_resolve_content_paths` 改为 HTML 驱动，markdown 仅作图片基路径与标题 / 摘要来源。
