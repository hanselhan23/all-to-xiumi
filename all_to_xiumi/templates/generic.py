"""
通用模板 — 干净简洁，适用于任意 Markdown 内容的发布。
"""

from .base import Template


class GenericTemplate(Template):
    """通用模板，无色块品牌标识，适合发布任意类型的内容。"""

    name = "generic"
    hero_mark_text = ""

    # 通用模板使用更中性的 Hero 配色
    hero_style: str = (
        "margin:0 0 18px;padding:22px 18px 20px;"
        "border:1px solid #c5d4e0;background:#e6f0f8;border-radius:12px;"
    )
    hero_mark_style: str = (
        "display:inline-block;margin-bottom:8px;padding:3px 8px;"
        "background:#5a8da8;color:#fff;border-radius:999px;"
        "font-size:12px;letter-spacing:.08em;"
    )
    hero_title_style: str = (
        "margin:0;color:#1a2a38;font-size:26px;font-weight:800;line-height:1.25;"
    )
    hero_subtitle_style: str = (
        "margin:8px 0 0;color:#5c7c94;font-size:14px;"
    )
