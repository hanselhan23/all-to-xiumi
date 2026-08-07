"""
all-to-xiumi — HTML / Markdown / PDF → 秀米草稿一键生成。

CLI 用法:
    all-to-xiumi input.html --title "标题" --author "作者"
    all-to-xiumi input.md   --template generic --title "标题"
    all-to-xiumi input.pdf  --title "标题"

Python API 用法:
    from all_to_xiumi import run_skill
    result = run_skill("input.md", title="标题", author="作者")
"""

from .markdown_to_html import markdown_to_html, markdown_to_wechat_html
from .skill_pipeline import run_skill
from .templates import Template, get_template, list_templates, register_template
from .xiumi_publish import publish_xiumi_draft

__version__ = "0.1.0"

__all__ = [
    "run_skill",
    "markdown_to_html",
    "markdown_to_wechat_html",
    "publish_xiumi_draft",
    "get_template",
    "list_templates",
    "register_template",
    "Template",
]
