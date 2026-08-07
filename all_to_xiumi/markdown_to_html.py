"""
通用 Markdown → 富文本 HTML 转换器。

忠实地将任意 Markdown 结构映射为排版精美的内联 HTML，
适用于秀米、微信公众号等富文本编辑器。

映射规则:
  # H1       → 页面 Hero 标题
  ## H2      → Section 区块标题
  ### H3     → Card 卡片标题
  #### H4    → 卡片内子标题
  段落       → 样式化 <p>
  - 列表     → 无序列表
  1. 列表    → 有序列表
  **粗体**   → <strong>
  *斜体*     → <em>
  ![]()      → 响应式图片
  []()       → 超链接
  ``` 代码   → <pre> 代码块
  > 引用     → <blockquote>
  | 表格     → 样式化 <table>
  key: value → 元信息行
"""

import html
import os
import re
from pathlib import Path
from typing import List, Tuple

from .image_paths import (
    clean_markdown_image_target,
    is_remote_or_data_image,
    resolve_existing_image_path,
)
from .templates import Template, get_template

# ── 时间类标签（值会用强调色渲染） ──
TIME_LABELS = {
    "日期", "时间", "发布日期", "报告时间", "截止时间",
    "活动时间", "演出时间", "开票时间", "开始时间", "结束时间",
}

# ── 标准元信息标签（key: value 模式会被渲染为样式化行） ──
META_LABELS = {
    "日期", "时间", "地点", "票价", "发布日期", "报告时间",
    "报告地点", "报告人", "来源公众号", "作者", "链接",
    "摘要", "报告摘要", "截止时间", "活动时间", "开始时间",
    "结束时间", "主办方", "报名方式", "联系方式", "备注",
}


def _split_label_value(text: str) -> Tuple[str, str]:
    """拆分 '标签: 值' 格式的文本。"""
    match = re.match(r"^([^:：]{1,16})[:：]\s*(.+)$", text)
    if not match:
        return "", text
    return match.group(1).strip(), match.group(2).strip()


def _strip_markdown_emphasis(text: str) -> str:
    """去除 Markdown 强调标记，返回纯文本。"""
    # **bold**
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    # *italic*
    text = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"\1", text)
    return text


def _extract_alt_text(text: str) -> str:
    """从 Markdown 图片语法提取 alt 文本。"""
    match = re.match(r"!\[([^\]]*)\]\(([^)]+)\)", text)
    if match:
        return match.group(1).strip()
    return ""


def _resolve_image_src(src: str, markdown_path: str = "") -> str:
    """解析图片路径，优先使用本地文件。"""
    cleaned = src.strip().strip("<>").strip('"').strip("'")
    if not cleaned or is_remote_or_data_image(cleaned):
        return cleaned

    markdown_dir = os.path.dirname(markdown_path) if markdown_path else os.getcwd()
    resolved = resolve_existing_image_path(cleaned, base_dir=markdown_dir)
    if resolved is not None:
        result = str(resolved)
    else:
        result = os.path.normpath(
            os.path.join(markdown_dir, clean_markdown_image_target(cleaned))
        )
    return result.replace("\\", "/")


def _extract_para_color(tpl) -> str:
    """从模板的 para_style 中提取文字颜色。"""
    ps = getattr(tpl, "para_style", "")
    m = re.search(r"color:(#[0-9a-fA-F]{6})", ps)
    return m.group(1) if m else "#3a4a5c"


def _extract_border_color(tpl) -> str:
    """从模板的 card_style 中提取边框颜色。"""
    card = getattr(tpl, "card_style", "")
    m = re.search(r"border:1px\s+solid\s+(#[0-9a-fA-F]{6})", card)
    return m.group(1) if m else "#c8ddf0"


def _render_inline_markdown(text: str, tpl=None) -> str:
    """将行内 Markdown 格式转换为 HTML。"""
    result = html.escape(text, quote=False)

    # 使用模板样式或默认值
    strong_s = getattr(tpl, "strong_style", "color:#1a344c;font-weight:700;") if tpl else "color:#1a344c;font-weight:700;"
    em_s = getattr(tpl, "em_style", "color:#5c7d99;font-style:italic;") if tpl else "color:#5c7d99;font-style:italic;"
    link_s = getattr(tpl, "link_style", "color:#2f6f9f;text-decoration:underline;word-break:break-all;") if tpl else "color:#2f6f9f;text-decoration:underline;word-break:break-all;"

    # 行内代码背景色从模板提取或默认
    code_bg = "#d8ecf8"
    if tpl:
        _th = getattr(tpl, "th_style", "")
        import re as _re
        _m = _re.search(r"background:(#[0-9a-fA-F]{6})", _th)
        if _m:
            code_bg = _m.group(1)

    # 粗体 **text**
    result = re.sub(
        r"\*\*(.+?)\*\*",
        lambda m: (
            f"<strong style=\"{strong_s}\">"
            f"{m.group(1)}</strong>"
        ),
        result,
    )
    # 斜体 *text*
    result = re.sub(
        r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)",
        lambda m: (
            f"<em style=\"{em_s}\">"
            f"{m.group(1)}</em>"
        ),
        result,
    )
    # 行内代码 `code`
    result = re.sub(
        r"`([^`]+)`",
        lambda m: (
            f"<code style=\"background:{code_bg};padding:1px 5px;"
            f"border-radius:3px;font-size:0.9em;\">{m.group(1)}</code>"
        ),
        result,
    )
    # 链接 [text](url)
    result = re.sub(
        r"\[([^\]]+)\]\(([^)]+)\)",
        lambda m: (
            f"<a href=\"{html.escape(m.group(2), quote=True)}\" "
            f"style=\"{link_s}\">{m.group(1)}</a>"
        ),
        result,
    )

    return result


# ── 表格解析 ──

def _is_table_row(text: str) -> bool:
    stripped = text.strip()
    return stripped.startswith("|") and stripped.count("|") >= 2


def _is_table_separator(text: str) -> bool:
    return bool(
        re.match(
            r"^\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$",
            text.strip(),
        )
    )


def _split_table_row(text: str) -> List[str]:
    stripped = text.strip().strip("|")
    return [
        cell.replace(r"\|", "|").strip()
        for cell in re.split(r"(?<!\\)\|", stripped)
    ]


def _consume_table(
    lines: List[str], start_index: int
) -> Tuple[List[str], int]:
    """消费从 start_index 开始的表格行，返回 (rows, next_index)。"""
    table_lines = []
    index = start_index

    # 第一行必须是表格行
    if index < len(lines) and _is_table_row(lines[index]):
        table_lines.append(lines[index])
        index += 1
    else:
        return [], start_index

    # 跳过空行
    while index < len(lines) and not lines[index].strip():
        index += 1

    # 分隔行
    if index < len(lines) and _is_table_separator(lines[index]):
        table_lines.append(lines[index])
        index += 1
    else:
        return [], start_index

    # 剩余行
    while index < len(lines):
        stripped = lines[index].strip()
        if not stripped:
            index += 1
            continue
        if _is_table_row(stripped):
            table_lines.append(stripped)
            index += 1
        else:
            break

    return table_lines, index


# ── 有序列表解析 ──

def _is_ordered_list_item(text: str) -> bool:
    return bool(re.match(r"^\d+\.\s+\S", text.strip()))


# ── 主转换函数 ──

def markdown_to_html(
    markdown_text: str,
    *,
    template: str | Template = "generic",
    title: str = "",
    subtitle: str = "",
    markdown_path: str = "",
) -> str:
    """
    将 Markdown 文本转换为排版精美的内联 HTML。

    Args:
        markdown_text: Markdown 源文本。
        template: 模板名称 ("generic" | "wanyou") 或 Template 实例。
        title: 页面标题（覆盖 Markdown 中的 H1）。
        subtitle: 页面副标题。
        markdown_path: Markdown 文件路径，用于解析相对路径图片。

    Returns:
        内联样式的 HTML 字符串。
    """
    if isinstance(template, str):
        tpl = get_template(template)
    else:
        tpl = template

    blocks: List[str] = [f"<section style=\"{tpl.page_style}\">"]
    section_open = False
    card_open = False
    in_code_block = False
    code_lines: List[str] = []
    in_ordered_list = False

    def close_card():
        nonlocal card_open
        if card_open:
            blocks.append(tpl.render_card_end())
            card_open = False

    def close_section():
        nonlocal section_open
        close_card()
        if section_open:
            blocks.append(tpl.render_section_end())
            section_open = False

    def close_all():
        close_section()

    # ── 确定标题 ──
    hero_title = title
    hero_subtitle = subtitle
    content_start = 0

    lines = (markdown_text or "").splitlines()

    # 如果未指定标题，从第一个 H1 提取
    if not hero_title:
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("# ") and not stripped.startswith("## "):
                hero_title = stripped[2:].strip()
                content_start = i + 1
                break

    # 渲染 Hero 区
    blocks.append(tpl.render_header(hero_title, hero_subtitle))

    # ── 逐行解析 ──
    index = content_start
    while index < len(lines):
        raw_line = lines[index]
        stripped = raw_line.strip()

        # ── 代码块 ──
        if stripped.startswith("```"):
            if in_code_block:
                # 结束代码块
                code_text = "\n".join(code_lines)
                blocks.append(tpl.render_code_block(html.escape(code_text)))
                code_lines = []
                in_code_block = False
            else:
                # 开始代码块
                close_card()
                in_code_block = True
            index += 1
            continue

        if in_code_block:
            code_lines.append(raw_line)
            index += 1
            continue

        # ── 空行 ──
        if not stripped:
            if in_ordered_list:
                in_ordered_list = False
            index += 1
            continue

        # ── H1 (第二个及以后的 H1 作为 section) ──
        if stripped.startswith("# ") and not stripped.startswith("## "):
            close_section()
            h1_title = stripped[2:].strip()
            blocks.append(
                f"<section style=\"{tpl.section_style}\">"
                f"<h2 style=\"{tpl.section_title_style}\">{html.escape(h1_title)}</h2>"
            )
            section_open = True
            index += 1
            continue

        # ── H2 → Section ──
        if stripped.startswith("## ") and not stripped.startswith("### "):
            close_section()
            h2_title = stripped[3:].strip()
            blocks.append(tpl.render_section_start(html.escape(h2_title)))
            section_open = True
            index += 1
            continue

        # ── H3 → Card ──
        if stripped.startswith("### ") and not stripped.startswith("#### "):
            if not section_open:
                # 隐式 section
                blocks.append(tpl.render_section_start(""))
                section_open = True
            close_card()
            h3_title = stripped[4:].strip()
            blocks.append(tpl.render_card_start(html.escape(h3_title)))
            card_open = True
            index += 1
            continue

        # ── H4 → 子标题 ──
        if stripped.startswith("#### "):
            h4_title = stripped[5:].strip()
            if not card_open and not section_open:
                blocks.append(tpl.render_section_start(""))
                section_open = True
            blocks.append(tpl.render_h4(html.escape(h4_title)))
            index += 1
            continue

        # ── H5/H6 → 更小子标题 ──
        if stripped.startswith("##### ") or stripped.startswith("###### "):
            hx_title = re.sub(r"^#+\s*", "", stripped).strip()
            blocks.append(
                f"<p style=\"{tpl.para_style}text-indent:0;font-weight:600;"
                f"{tpl.strong_style.replace('font-weight:700;','').strip().rstrip(';')};"
                f"font-size:15px;\">"
                f"{html.escape(hx_title)}</p>"
            )
            index += 1
            continue

        # ── 水平分隔线 ──
        if re.match(r"^[-*_]{3,}\s*$", stripped):
            hr_color = _extract_border_color(tpl)
            blocks.append(
                "<hr style=\"margin:16px 0;border:none;"
                f"border-top:1px solid {hr_color};\" />"
            )
            index += 1
            continue

        # ── 图片 ![]() ──
        image_match = re.match(r"!\[([^\]]*)\]\(([^)]+)\)", stripped)
        if image_match:
            alt = image_match.group(1).strip()
            src = _resolve_image_src(image_match.group(2), markdown_path)
            escaped_src = html.escape(src, quote=True)
            blocks.append(
                f"<img src=\"{escaped_src}\" "
                f"alt=\"{html.escape(alt or '配图')}\" "
                f"style=\"{tpl.image_style}\" />"
            )
            index += 1
            continue

        # ── 表格 ──
        if _is_table_row(stripped):
            table_rows, next_index = _consume_table(lines, index)
            if len(table_rows) >= 2:
                parsed = [
                    _split_table_row(row)
                    for row in table_rows
                    if not _is_table_separator(row)
                ]
                if parsed:
                    max_cols = max(len(row) for row in parsed)
                    for row in parsed:
                        row.extend([""] * (max_cols - len(row)))
                    headers = [html.escape(cell) for cell in parsed[0]]
                    body = [
                        [html.escape(cell) for cell in row]
                        for row in parsed[1:]
                    ]
                    blocks.append(tpl.render_table(headers, body))
                    index = next_index
                    continue
            # 不是有效表格，按段落处理
            index += 1
            continue

        # ── 引用块 > ──
        if stripped.startswith("> "):
            quote_text = stripped[2:].strip()
            # 收集连续引用行
            quote_lines = [quote_text]
            index += 1
            while index < len(lines) and lines[index].strip().startswith("> "):
                quote_lines.append(lines[index].strip()[2:].strip())
                index += 1
            combined = "<br>".join(
                _render_inline_markdown(line, tpl) for line in quote_lines
            )
            blocks.append(
                f"<blockquote style=\"{tpl.quote_style}\">{combined}</blockquote>"
            )
            continue

        # ── 有序列表 1. ──
        if _is_ordered_list_item(stripped):
            if not in_ordered_list:
                in_ordered_list = True
                list_counter = 1
            item_match = re.match(r"^(\d+)\.\s+(.+)", stripped)
            if item_match:
                number = int(item_match.group(1))
                item_text = item_match.group(2)
                blocks.append(
                    tpl.render_ordered_item(
                        number, _render_inline_markdown(item_text, tpl)
                    )
                )
                list_counter = number + 1
            index += 1
            continue

        # ── 无序列表 - / * ──
        if re.match(r"^[-*]\s+\S", stripped):
            item_match = re.match(r"^[-*]\s+(.+)", stripped)
            if item_match:
                item_text = item_match.group(1)
                blocks.append(
                    tpl.render_bullet(_render_inline_markdown(item_text, tpl))
                )
            index += 1
            continue

        # ── key: value 元信息 ──
        label, value = _split_label_value(stripped)
        if label in META_LABELS:
            is_time = label in TIME_LABELS
            escaped_label = html.escape(label)
            if label == "链接" and re.match(r"^https?://", value):
                escaped_value = (
                    f"<a href=\"{html.escape(value, quote=True)}\" "
                    f"style=\"color:#2f6f9f;text-decoration:underline;"
                    f"word-break:break-all;\">{html.escape(value)}</a>"
                )
            else:
                value_color = (
                    tpl.meta_time_value_style if is_time else f"color:{_extract_para_color(tpl)};"
                )
                escaped_value = (
                    f"<span style=\"{value_color}\">"
                    f"{_render_inline_markdown(value, tpl)}</span>"
                )
            blocks.append(
                f"<p style=\"{tpl.meta_row_style}\">"
                f"<span style=\"{tpl.meta_label_style}\">{escaped_label}</span>"
                f"{escaped_value}</p>"
            )
            index += 1
            continue

        # ── 原始 HTML ──
        if stripped.startswith("@html "):
            raw_html = stripped[6:].strip()
            blocks.append(raw_html)
            index += 1
            continue

        # ── 普通段落 ──
        if not card_open and not section_open:
            # 没有 section 时创建隐式 section
            blocks.append(tpl.render_section_start(""))
            section_open = True

        blocks.append(
            f"<p style=\"{tpl.para_style}\">"
            f"{_render_inline_markdown(stripped, tpl)}</p>"
        )
        index += 1

    # ── 收尾 ──
    close_all()

    # Footer
    blocks.append(tpl.render_footer())

    # 关闭页面
    blocks.append("</section>")

    return "\n".join(blocks)


# ── 便捷别名 ──
def markdown_to_wechat_html(
    markdown_text: str,
    *,
    template: str | Template = "generic",
    title: str = "",
    subtitle: str = "",
    markdown_path: str = "",
) -> str:
    """与 markdown_to_html 相同，为兼容 Wanyou 命名的别名。"""
    return markdown_to_html(
        markdown_text,
        template=template,
        title=title,
        subtitle=subtitle,
        markdown_path=markdown_path,
    )
