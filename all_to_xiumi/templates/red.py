"""
红色主题模板 — 适用于理论学习、党建等红色主题推送。
"""

from .base import Template


class RedTemplate(Template):
    """红色主题模板，以革命红为主色调，适合理论学习类内容。"""

    name = "red"
    hero_mark_text = "理论学习"

    # ── 页面级样式 ──
    page_style: str = (
        "margin:0 auto;padding:0 0 8px;background:#fdf8f8;color:#2c2020;"
        "font-family:-apple-system,BlinkMacSystemFont,'Helvetica Neue',"
        "'PingFang SC','Microsoft YaHei',sans-serif;line-height:1.75;font-size:15px;"
    )
    hero_style: str = (
        "margin:0 0 18px;padding:22px 18px 20px;"
        "border:1px solid #d4b8b8;background:#fdf2f2;border-radius:12px;"
    )
    hero_mark_style: str = (
        "display:inline-block;margin-bottom:8px;padding:3px 10px;"
        "background:#c0392b;color:#fff;border-radius:999px;font-size:12px;letter-spacing:.08em;"
    )
    hero_title_style: str = (
        "margin:0;color:#8b1a1a;font-size:26px;font-weight:800;line-height:1.25;"
    )
    hero_subtitle_style: str = (
        "margin:8px 0 0;color:#8b5a5a;font-size:14px;"
    )

    section_style: str = (
        "margin:20px 0 0;padding:18px 16px;background:#fdf6f6;"
        "border:1px solid #e8cccc;border-radius:12px;"
        "box-shadow:0 3px 12px rgba(120,20,20,.05);"
    )
    section_title_style: str = (
        "margin:0 0 10px;color:#8b1a1a;font-size:20px;font-weight:800;"
        "line-height:1.35;padding-bottom:6px;border-bottom:2px solid #c0392b;"
    )
    section_lead_style: str = (
        "margin:8px 0 10px;color:#8b5a5a;font-size:14px;line-height:1.7;"
    )

    card_style: str = (
        "margin:10px 0 0;padding:14px 14px;background:#fdf2f2;"
        "border:1px solid #e8d0d0;border-radius:8px;"
    )
    card_title_style: str = (
        "margin:0 0 8px;color:#8b1a1a;font-size:16px;font-weight:700;line-height:1.4;"
    )

    para_style: str = (
        "margin:8px 0;color:#4a3030;font-size:14px;line-height:1.6;"
        "letter-spacing:0;text-indent:2em;"
    )
    strong_style: str = "color:#a82020;font-weight:700;"
    em_style: str = "color:#8b5a5a;font-style:italic;"

    bullet_style: str = (
        "margin:6px 0 6px 1em;color:#4a3030;font-size:14px;line-height:1.6;"
    )

    image_style: str = (
        "display:block;width:100%;max-width:100%;height:auto;"
        "margin:10px auto;border-radius:8px;"
    )

    link_style: str = "color:#c0392b;text-decoration:underline;word-break:break-all;"

    quote_style: str = (
        "margin:10px 0;padding:10px 14px;background:#fdf2f2;"
        "border-left:4px solid #c0392b;border-radius:6px;color:#5a3838;"
    )

    code_block_style: str = (
        "margin:10px 0;padding:12px 14px;background:#2d2d2d;color:#e0d0d0;"
        "border-radius:8px;font-family:'SF Mono','Fira Code','Consolas',monospace;"
        "font-size:13px;line-height:1.6;overflow-x:auto;white-space:pre-wrap;"
    )

    # ── 元信息行样式 ──
    meta_row_style: str = (
        "margin:5px 0;color:#4a3030;font-size:14px;line-height:1.65;"
    )
    meta_label_style: str = (
        "display:inline-block;margin-right:6px;color:#8b5a5a;font-weight:700;"
    )
    meta_time_value_style: str = "color:#c0392b;font-weight:700;"

    # ── 表格样式 ──
    table_wrap_style: str = (
        "margin:10px 0;overflow-x:auto;border:1px solid #e8cccc;"
        "border-radius:8px;background:#fdf6f6;"
    )
    table_style: str = (
        "width:100%;border-collapse:collapse;font-size:14px;line-height:1.6;"
    )
    th_style: str = (
        "padding:7px 8px;border:1px solid #e8cccc;background:#f8e0e0;"
        "color:#6b1a1a;font-weight:700;text-align:left;vertical-align:top;"
    )
    td_style: str = (
        "padding:7px 8px;border:1px solid #e8cccc;color:#4a3030;"
        "text-align:left;vertical-align:top;"
    )

    footer_style: str = (
        "margin:24px 0 0;padding:14px 10px;text-align:center;"
        "color:#8b5a5a;font-size:14px;"
    )

    # ── 预置分隔符 ──
    def render_h4(self, text: str) -> str:
        """渲染四级标题（卡片内子标题）。"""
        return (
            f"<p style=\"{self.para_style}text-indent:0;font-weight:700;"
            f"color:#a82020;font-size:15px;\">{text}</p>"
        )
