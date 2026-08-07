"""
模板基类 — 定义页面级结构和各区域的 HTML 渲染接口。
"""

from typing import ClassVar


class Template:
    """抽象模板基类。子类覆盖样式常量和渲染方法来定制外观。"""

    # ── 页面级样式 ──
    page_style: str = (
        "margin:0 auto;padding:0 0 8px;background:#f5f8fc;color:#2c3440;"
        "font-family:-apple-system,BlinkMacSystemFont,'Helvetica Neue',"
        "'PingFang SC','Microsoft YaHei',sans-serif;line-height:1.75;font-size:15px;"
    )
    hero_style: str = (
        "margin:0 0 18px;padding:22px 18px 20px;"
        "border:1px solid #b8d0e8;background:#e3eff9;border-radius:12px;"
    )
    hero_mark_style: str = (
        "display:inline-block;margin-bottom:8px;padding:3px 8px;"
        "color:#fff;border-radius:999px;font-size:12px;letter-spacing:.08em;"
    )
    hero_title_style: str = (
        "margin:0;color:#1a344c;font-size:26px;font-weight:800;line-height:1.25;"
    )
    hero_subtitle_style: str = (
        "margin:8px 0 0;color:#5c7d99;font-size:14px;"
    )

    section_style: str = (
        "margin:20px 0 0;padding:18px 16px;background:#f6f9fc;"
        "border:1px solid #c8ddf0;border-radius:12px;"
        "box-shadow:0 3px 12px rgba(40,80,120,.05);"
    )
    section_title_style: str = (
        "margin:0 0 10px;color:#1a344c;font-size:20px;font-weight:800;"
        "line-height:1.35;padding-bottom:6px;border-bottom:2px solid #5ca4d4;"
    )
    section_lead_style: str = (
        "margin:8px 0 10px;color:#5c7d99;font-size:14px;line-height:1.7;"
    )

    card_style: str = (
        "margin:10px 0 0;padding:12px 12px;background:#eef4fa;"
        "border:1px solid #d4e4f2;border-radius:8px;"
    )
    card_title_style: str = (
        "margin:0 0 8px;color:#1a344c;font-size:16px;font-weight:700;line-height:1.4;"
    )

    para_style: str = (
        "margin:8px 0;color:#3a4a5c;font-size:14px;line-height:1.6;"
        "letter-spacing:0;text-indent:2em;"
    )
    strong_style: str = "color:#1a344c;font-weight:700;"
    em_style: str = "color:#5c7d99;font-style:italic;"

    bullet_style: str = (
        "margin:6px 0 6px 1em;color:#3a4a5c;font-size:14px;line-height:1.6;"
    )

    image_style: str = (
        "display:block;width:100%;max-width:100%;height:auto;"
        "margin:10px auto;border-radius:8px;"
    )

    link_style: str = "color:#3b8cc7;text-decoration:underline;word-break:break-all;"

    quote_style: str = (
        "margin:10px 0;padding:10px 12px;background:#eaf2fa;"
        "border-left:4px solid #5ca4d4;border-radius:6px;color:#3d5268;"
    )

    code_block_style: str = (
        "margin:10px 0;padding:12px 14px;background:#2d2d2d;color:#c5d4e0;"
        "border-radius:8px;font-family:'SF Mono','Fira Code','Consolas',monospace;"
        "font-size:13px;line-height:1.6;overflow-x:auto;white-space:pre-wrap;"
    )

    # ── 元信息行样式 (key: value 模式) ──
    meta_row_style: str = (
        "margin:5px 0;color:#3a4a5c;font-size:14px;line-height:1.65;"
    )
    meta_label_style: str = (
        "display:inline-block;margin-right:6px;color:#5c7d99;font-weight:700;"
    )
    meta_time_value_style: str = "color:#3b8cc7;font-weight:700;"

    # ── 表格样式 ──
    table_wrap_style: str = (
        "margin:10px 0;overflow-x:auto;border:1px solid #c8ddf0;"
        "border-radius:8px;background:#f6f9fc;"
    )
    table_style: str = (
        "width:100%;border-collapse:collapse;font-size:14px;line-height:1.6;"
    )
    th_style: str = (
        "padding:7px 8px;border:1px solid #c8ddf0;background:#d8ecf8;"
        "color:#1a4a6c;font-weight:700;text-align:left;vertical-align:top;"
    )
    td_style: str = (
        "padding:7px 8px;border:1px solid #c8ddf0;color:#3a4a5c;"
        "text-align:left;vertical-align:top;"
    )

    footer_style: str = (
        "margin:24px 0 0;padding:14px 10px;text-align:center;"
        "color:#6c8da8;font-size:14px;"
    )

    # ── 模板元信息 ──
    name: ClassVar[str] = "base"
    hero_mark_text: ClassVar[str] = ""

    def render_header(self, title: str = "", subtitle: str = "") -> str:
        """渲染页面头部 Hero 区域。"""
        parts = [f"<section style=\"{self.hero_style}\">"]
        if self.hero_mark_text:
            parts.append(
                f"<span style=\"{self.hero_mark_style}\">"
                f"{self.hero_mark_text}</span>"
            )
        if title:
            parts.append(
                f"<h1 style=\"{self.hero_title_style}\">{title}</h1>"
            )
        if subtitle:
            parts.append(
                f"<p style=\"{self.hero_subtitle_style}\">{subtitle}</p>"
            )
        parts.append("</section>")
        return "\n".join(parts)

    def render_footer(self, text: str = "") -> str:
        """渲染页面底部 Footer 区域。"""
        return f"<section style=\"{self.footer_style}\">{text or '—'}</section>"

    def render_section_start(self, title: str) -> str:
        """渲染 Section 开始标签和标题。"""
        return (
            f"<section style=\"{self.section_style}\">"
            f"<h2 style=\"{self.section_title_style}\">{title}</h2>"
        )

    def render_section_end(self) -> str:
        """渲染 Section 结束标签。"""
        return "</section>"

    def render_card_start(self, title: str) -> str:
        """渲染 Card 开始标签和标题。"""
        return (
            f"<section style=\"{self.card_style}\">"
            f"<h3 style=\"{self.card_title_style}\">{title}</h3>"
        )

    def render_card_end(self) -> str:
        """渲染 Card 结束标签。"""
        return "</section>"

    def render_paragraph(self, text: str) -> str:
        """渲染段落。"""
        return f"<p style=\"{self.para_style}\">{text}</p>"

    def render_meta_row(
        self, label: str, value: str, is_time_label: bool = False
    ) -> str:
        """渲染 key: value 元信息行。"""
        value_style = (
            self.meta_time_value_style if is_time_label else "color:#3a4a5c;"
        )
        return (
            f"<p style=\"{self.meta_row_style}\">"
            f"<span style=\"{self.meta_label_style}\">{label}</span>"
            f"<span style=\"{value_style}\">{value}</span>"
            f"</p>"
        )

    def render_image(self, src: str, alt: str = "") -> str:
        """渲染图片。"""
        return (
            f"<img src=\"{src}\" alt=\"{alt or '配图'}\" "
            f"style=\"{self.image_style}\" />"
        )

    def render_link(self, url: str, text: str = "") -> str:
        """渲染超链接。"""
        display = text or url
        return f"<a href=\"{url}\" style=\"{self.link_style}\">{display}</a>"

    def render_bullet(self, text: str) -> str:
        """渲染列表项。"""
        return f"<p style=\"{self.bullet_style}\">• {text}</p>"

    def render_ordered_item(self, number: int, text: str) -> str:
        """渲染有序列表项。"""
        return f"<p style=\"{self.bullet_style}\">{number}. {text}</p>"

    def render_quote(self, text: str) -> str:
        """渲染引用块。"""
        return f"<blockquote style=\"{self.quote_style}\">{text}</blockquote>"

    def render_code_block(self, code: str) -> str:
        """渲染代码块。"""
        return f"<pre style=\"{self.code_block_style}\">{code}</pre>"

    def render_table(self, headers: list[str], rows: list[list[str]]) -> str:
        """渲染表格。"""
        head = "".join(
            f"<th style=\"{self.th_style}\">{h}</th>" for h in headers
        )
        body = "".join(
            "<tr>"
            + "".join(
                f"<td style=\"{self.td_style}\">{cell}</td>" for cell in row
            )
            + "</tr>"
            for row in rows
        )
        return (
            f"<section style=\"{self.table_wrap_style}\">"
            f"<table style=\"{self.table_style}\">"
            f"<thead><tr>{head}</tr></thead>"
            f"<tbody>{body}</tbody>"
            f"</table></section>"
        )

    def render_h4(self, text: str) -> str:
        """渲染四级标题（卡片内子标题）。"""
        return (
            f"<p style=\"{self.para_style}font-weight:700;"
            f"color:#3a6d94;font-size:16px;\">{text}</p>"
        )
