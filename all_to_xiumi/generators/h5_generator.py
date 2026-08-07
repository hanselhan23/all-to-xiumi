import html
import os
import re
import shutil
from typing import Dict, List, Tuple

from .. import config
from ..image_paths import clean_markdown_image_target, is_remote_or_data_image, resolve_existing_image_path


THEME_SOURCE_DIR = os.path.normpath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "output",
        "万有预报 _ 2025-2026学年春季学期SRT学生报名即将截止_files",
    )
)
THEME_ASSET_SPECS = {
    "badge": ("0(1)", "badge.png"),
    "badge_mini": ("300", "badge-mini.png"),
}
THEME_DIR_NAME = "_theme"
THEME_BADGE_ALT = "物理系风格标识"
THEME_BADGE_MINI_ALT = "物理系风格标识-页尾"
HEADER_TITLE_LINE = "**万有预报**"
HEADER_SUBTITLE_LINE = "*清华大学物理系校园信息整理*"
FOOTER_LINE = "*万有预报，下期再见。*"
SECTION_LEADS = {
    "教务通知": "这周和课程、选课、学业节奏直接相关的更新，先看这里。",
    "家园网信息": "生活层面的提醒和安排放在这一栏，方便课间快速扫一眼。",
    "图书馆信息": "图书馆的新讲座、资源和训练营，适合顺手加入本周计划。",
    "新清华学堂": "这一周值得出门听一场、看一场的内容，集中放在这里。",
    "物理系学术报告": "楼里的报告会是这一期的重头戏，尽量把关键信息和气质都保留下来。",
    "学生会信息": "和校园活动、同学权益更贴近的消息，统一收在这一栏。",
    "青年科协信息": "如果你关心科创、沙龙和项目机会，这一栏通常最有料。",
    "学生社团信息": "社团活动和招新动向，适合按兴趣挑着看。",
    "学生公益信息": "和志愿服务、公益行动相关的消息，整理在这里。",
    "其他公众号信息": "其他重点公众号里的校园动态，也顺手汇总在这里。",
}
META_LABELS = {
    "日期",
    "时间",
    "地点",
    "票价",
    "发布日期",
    "报告时间",
    "报告地点",
    "报告人",
    "来源公众号",
    "作者",
    "链接",
    "摘要",
    "报告摘要",
}


def _score_text(text: str) -> tuple[int, int]:
    cjk = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    latin1_noise = sum(1 for ch in text if "\u00c0" <= ch <= "\u00ff")
    return cjk, -latin1_noise



def _maybe_fix_mojibake(text: str) -> str:
    cleaned = (text or "").replace("\ufeff", "").strip()
    try:
        repaired = cleaned.encode("latin1").decode("utf-8")
    except Exception:
        return cleaned
    if _score_text(repaired) > _score_text(cleaned):
        return repaired
    return cleaned



def _safe_title(title: str) -> str:
    candidate = _maybe_fix_mojibake(title or getattr(config, "H5_TITLE", "万有预报"))
    if not candidate:
        return "万有预报"
    cjk, latin_penalty = _score_text(candidate)
    if cjk == 0 and -latin_penalty >= 3:
        return "万有预报"
    return candidate



def _theme_asset_output_dir(target_path: str) -> str:
    return os.path.join(os.path.dirname(target_path), THEME_DIR_NAME)



def ensure_theme_assets(target_path: str) -> Dict[str, str]:
    output_dir = _theme_asset_output_dir(target_path)
    os.makedirs(output_dir, exist_ok=True)
    copied = {}
    for name, (source_name, target_name) in THEME_ASSET_SPECS.items():
        source_path = os.path.join(THEME_SOURCE_DIR, source_name)
        if not os.path.exists(source_path):
            continue
        target_file = os.path.join(output_dir, target_name)
        if not os.path.exists(target_file):
            shutil.copyfile(source_path, target_file)
        copied[name] = target_file
    return copied



def _strip_previous_theme_markers(text: str) -> str:
    cleaned = re.sub(r"^!\[[^\]]*\]\(_theme/(?:cover\.jpg|divider\.png|badge\.png|badge-mini\.png)\)\s*$", "", text, flags=re.M)
    for marker in (HEADER_TITLE_LINE, HEADER_SUBTITLE_LINE, FOOTER_LINE):
        cleaned = re.sub(r"^" + re.escape(marker) + r"\s*$", "", cleaned, flags=re.M)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()



def decorate_markdown_with_theme(markdown_text: str, markdown_path: str) -> str:
    text = _strip_previous_theme_markers(markdown_text or "")
    if not text:
        return markdown_text

    assets = ensure_theme_assets(markdown_path)
    badge = assets.get("badge")
    badge_mini = assets.get("badge_mini")
    parts: List[str] = []

    if badge:
        badge_rel = os.path.relpath(badge, start=os.path.dirname(markdown_path)).replace("\\", "/")
        parts.append(f"![{THEME_BADGE_ALT}]({badge_rel})")
        parts.append("")

    parts.append(HEADER_TITLE_LINE)
    parts.append(HEADER_SUBTITLE_LINE)
    parts.append("")
    parts.append(text)
    parts.append("")

    if badge_mini:
        badge_mini_rel = os.path.relpath(badge_mini, start=os.path.dirname(markdown_path)).replace("\\", "/")
        parts.append(f"![{THEME_BADGE_MINI_ALT}]({badge_mini_rel})")
    parts.append(FOOTER_LINE)
    return "\n".join(part for part in parts if part is not None).strip() + "\n"



def _resolve_image_src(src: str, markdown_path: str, output_path: str) -> str:
    cleaned = src.strip().strip("<>").strip('"').strip("'")
    if not cleaned:
        return cleaned
    if is_remote_or_data_image(cleaned):
        return cleaned

    markdown_dir = os.path.dirname(markdown_path)
    resolved_path = resolve_existing_image_path(cleaned, base_dir=markdown_dir)
    if resolved_path is not None:
        resolved = str(resolved_path)
    else:
        resolved = os.path.normpath(os.path.join(markdown_dir, clean_markdown_image_target(cleaned)))
    relative = os.path.relpath(resolved, start=os.path.dirname(output_path))
    return relative.replace("\\", "/")



def _should_skip_line(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return True
    if stripped.startswith("[English]("):
        return True
    if stripped.startswith("* [") and "](" in stripped:
        return True
    return False



def _split_label_value(text: str) -> Tuple[str, str]:
    match = re.match(r"^([^:：]{1,12})[:：]\s*(.+)$", text)
    if not match:
        return "", text
    return match.group(1).strip(), match.group(2).strip()



def _strip_markdown_emphasis(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("**") and stripped.endswith("**") and len(stripped) > 4:
        return stripped[2:-2].strip()
    if stripped.startswith("*") and stripped.endswith("*") and len(stripped) > 2:
        return stripped[1:-1].strip()
    return stripped


def _is_table_row(text: str) -> bool:
    stripped = text.strip()
    return stripped.startswith("|") and stripped.endswith("|") and stripped.count("|") >= 2


def _is_table_separator(text: str) -> bool:
    return bool(re.match(r"^\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$", text.strip()))


def _split_table_row(text: str) -> List[str]:
    stripped = text.strip().strip("|")
    cells = re.split(r"(?<!\\)\|", stripped)
    return [cell.replace(r"\|", "|").strip() for cell in cells]


def _render_markdown_table(table_lines: List[str]) -> str:
    rows = [line for line in table_lines if _is_table_row(line) and not _is_table_separator(line)]
    if not rows:
        return ""
    parsed = [_split_table_row(line) for line in rows]
    max_cols = max(len(row) for row in parsed)
    for row in parsed:
        row.extend([""] * (max_cols - len(row)))
    header = parsed[0]
    body = parsed[1:]
    head_html = "".join(f"<th>{html.escape(cell)}</th>" for cell in header)
    body_html = "\n".join(
        "<tr>" + "".join(f"<td>{html.escape(cell)}</td>" for cell in row) + "</tr>"
        for row in body
    )
    return (
        "<div class='table-wrap'><table class='info-table'>"
        f"<thead><tr>{head_html}</tr></thead>"
        f"<tbody>{body_html}</tbody>"
        "</table></div>"
    )


def _is_time_like_label(label: str) -> bool:
    return label in {
        "日期",
        "时间",
        "发布日期",
        "报告时间",
        "截止时间",
        "截止日期",
        "活动时间",
        "演出时间",
        "开票时间",
    }


def _highlight_time_text(text: str) -> str:
    escaped = html.escape(text or "")
    patterns = [
        r"20\d{2}[\u5e74\-/.]\d{1,2}[\u6708\-/.]\d{1,2}(?:\u65e5)?",
        r"\d{1,2}\u6708\d{1,2}\u65e5(?:\s*[\uff08(][^\uff09)]*[\uff09)])?(?:\s*(?:\u5468|\u661f\u671f)[\u4e00\u4e8c\u4e09\u56db\u4e94\u516d\u65e5\u5929])?",
        r"(?:\u5468|\u661f\u671f)[\u4e00\u4e8c\u4e09\u56db\u4e94\u516d\u65e5\u5929]",
        r"\d{1,2}[:\uff1a]\d{2}(?:\s*[-~\u81f3\u5230]\s*\d{1,2}[:\uff1a]\d{2})?",
        r"(?:\u4eca\u5929|\u660e\u5929|\u540e\u5929|\u4eca\u665a|\u4eca\u65e9|\u4eca\u6668|\u672c\u5468|\u672c\u5468\u5185|\u4e0b\u5468|\u8fd1\u671f|\u5373\u65e5\u8d77)",
        r"\u622a\u6b62\u81f3?\s*\d{1,2}\u6708\d{1,2}\u65e5",
    ]
    combined = re.compile("(" + "|".join(patterns) + ")")
    return combined.sub(r"<span class='time-highlight'>\1</span>", escaped)


def markdown_to_h5_html(markdown_text: str, markdown_path: str, output_path: str, title: str = "") -> str:
    page_title = _safe_title(title)
    theme_assets = ensure_theme_assets(output_path)
    badge_rel = ""
    badge_mini_rel = ""
    if theme_assets.get("badge"):
        badge_rel = os.path.relpath(theme_assets["badge"], start=os.path.dirname(output_path)).replace("\\", "/")
    if theme_assets.get("badge_mini"):
        badge_mini_rel = os.path.relpath(theme_assets["badge_mini"], start=os.path.dirname(output_path)).replace("\\", "/")

    blocks: List[str] = []
    article_open = False
    section_open = False

    def close_article():
        nonlocal article_open
        if article_open:
            blocks.append("</article>")
            article_open = False

    def close_section():
        nonlocal section_open
        if section_open:
            close_article()
            blocks.append("</section>")
            section_open = False

    lines = markdown_text.splitlines()
    index = 0
    while index < len(lines):
        raw_line = lines[index]
        stripped = _maybe_fix_mojibake(raw_line)
        if _is_table_row(stripped) and index + 1 < len(lines) and _is_table_separator(_maybe_fix_mojibake(lines[index + 1])):
            table_lines = [stripped, _maybe_fix_mojibake(lines[index + 1])]
            index += 2
            while index < len(lines) and _is_table_row(_maybe_fix_mojibake(lines[index])):
                table_lines.append(_maybe_fix_mojibake(lines[index]))
                index += 1
            rendered_table = _render_markdown_table(table_lines)
            if rendered_table:
                blocks.append(rendered_table)
            continue
        if _is_table_row(stripped):
            lookahead = index + 1
            while lookahead < len(lines) and not _maybe_fix_mojibake(lines[lookahead]).strip():
                lookahead += 1
            if lookahead < len(lines) and _is_table_separator(_maybe_fix_mojibake(lines[lookahead])):
                table_lines = [stripped, _maybe_fix_mojibake(lines[lookahead])]
                index = lookahead + 1
                while index < len(lines):
                    candidate = _maybe_fix_mojibake(lines[index])
                    if not candidate.strip():
                        index += 1
                        continue
                    if not _is_table_row(candidate):
                        break
                    table_lines.append(candidate)
                    index += 1
                rendered_table = _render_markdown_table(table_lines)
                if rendered_table:
                    blocks.append(rendered_table)
                continue
        index += 1
        if _should_skip_line(stripped):
            continue

        image_match = re.match(r"!\[([^\]]*)\]\(([^)]+)\)", stripped)
        if image_match:
            alt = _maybe_fix_mojibake(image_match.group(1).strip())
            src = html.escape(_resolve_image_src(image_match.group(2), markdown_path, output_path))
            if alt in {THEME_BADGE_ALT, THEME_BADGE_MINI_ALT}:
                continue
            blocks.append(f"<figure class='figure'><img src='{src}' alt='{html.escape(alt or '配图')}' loading='lazy' /></figure>")
            continue

        if stripped in {HEADER_TITLE_LINE, HEADER_SUBTITLE_LINE, FOOTER_LINE}:
            continue

        if stripped.startswith("# "):
            close_section()
            current_section = stripped[2:].strip()
            lead = SECTION_LEADS.get(current_section, "把这部分内容整理成更接近人工编辑版公众号的阅读卡片。")
            blocks.append("<section class='section'>")
            blocks.append("<div class='section-head'>")
            blocks.append("<span class='section-kicker'>本期栏目</span>")
            blocks.append(f"<h2>{html.escape(current_section)}</h2>")
            blocks.append(f"<p class='section-lead'>{html.escape(lead)}</p>")
            blocks.append("</div>")
            section_open = True
            continue

        if stripped.startswith("## "):
            close_article()
            blocks.append("<article class='card'>")
            blocks.append("<div class='card-notch'></div>")
            blocks.append(f"<h3>{html.escape(stripped[3:].strip())}</h3>")
            article_open = True
            continue

        if stripped.startswith("### "):
            blocks.append(f"<h4 class='subhead'>{html.escape(stripped[4:].strip())}</h4>")
            continue

        label, value = _split_label_value(stripped)
        if label == "要点透视":
            blocks.append(
                "<div class='lede-box'>"
                "<div class='lede-tag'>要点透视</div>"
                f"<p>{_highlight_time_text(value)}</p>"
                "</div>"
            )
            continue
        if label in META_LABELS:
            rendered_value = _highlight_time_text(value) if _is_time_like_label(label) else html.escape(value)
            if label == "链接" and re.match(r"^https?://", value):
                rendered_value = f"<a href='{html.escape(value)}'>{html.escape(value)}</a>"
            value_class = "meta-value"
            if label in {"日期", "时间", "发布日期", "报告时间"}:
                value_class += " is-highlight"
            blocks.append(
                f"<p class='meta-row'><span class='meta-label'>{html.escape(label)}</span><span class='{value_class}'>{rendered_value}</span></p>"
            )
            continue

        if re.match(r"^https?://", stripped):
            url = html.escape(stripped)
            blocks.append(f"<p class='link-row'><a href='{url}'>{url}</a></p>")
            continue

        if stripped.startswith(("- ", "• ")):
            bullet_text = stripped[2:].strip()
            blocks.append(f"<p class='bullet'>{html.escape(bullet_text)}</p>")
            continue

        emphasis_text = _strip_markdown_emphasis(stripped)
        if emphasis_text != stripped:
            blocks.append(f"<p class='note'><strong>{html.escape(emphasis_text)}</strong></p>")
            continue

        if stripped.startswith("*"):
            blocks.append(f"<p class='note'>{html.escape(stripped.lstrip('*').strip())}</p>")
            continue

        blocks.append(f"<p>{html.escape(stripped)}</p>")

    close_section()
    body_html = "\n".join(blocks)

    hero_badge = ""
    if badge_rel:
        hero_badge = f"<img class='hero-badge' src='{html.escape(badge_rel)}' alt='物理系风格标识' loading='lazy' />"
    footer_badge = ""
    if badge_mini_rel:
        footer_badge = f"<img class='footer-badge' src='{html.escape(badge_mini_rel)}' alt='物理系风格标识' loading='lazy' />"

    return f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{html.escape(page_title)}</title>
  <style>
    :root {{
      --accent: #f5c833;
      --accent-deep: #d5a51c;
      --accent-soft: rgba(245, 200, 51, 0.16);
      --accent-ink: #8f6a00;
      --paper: #ffffff;
      --paper-soft: #faf7ef;
      --ink: #3e3e3e;
      --muted: #70695d;
      --line: rgba(213, 165, 28, 0.55);
      --bg: #f6f2e8;
      --shadow: 0 22px 50px rgba(92, 74, 16, 0.08);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background:
        radial-gradient(circle at top right, rgba(245, 200, 51, 0.12), transparent 24%),
        radial-gradient(circle at left 20%, rgba(171, 211, 224, 0.18), transparent 18%),
        var(--bg);
      color: var(--ink);
      font-family: "Source Han Serif SC", "Noto Serif SC", "Songti SC", serif;
    }}
    .page {{
      width: min(760px, calc(100vw - 24px));
      margin: 0 auto;
      padding: 22px 0 46px;
    }}
    .hero {{
      position: relative;
      overflow: hidden;
      background: linear-gradient(180deg, rgba(255,255,255,0.98), rgba(250,247,239,0.96));
      border: 1px solid var(--line);
      border-radius: 26px;
      padding: 22px 20px 20px;
      box-shadow: var(--shadow);
    }}
    .hero::before {{
      content: "";
      position: absolute;
      left: 20px;
      right: 20px;
      top: 0;
      height: 5px;
      border-radius: 999px;
      background: var(--accent);
    }}
    .hero-top {{ display: flex; align-items: center; gap: 14px; margin-bottom: 12px; }}
    .hero-badge {{ width: 68px; height: 68px; border-radius: 50%; flex: 0 0 auto; box-shadow: 0 10px 24px rgba(143, 106, 0, 0.12); background: #fff; }}
    .hero-mark {{ display: inline-flex; align-items: center; gap: 8px; padding: 5px 10px; border-radius: 999px; background: var(--accent-soft); color: var(--accent-ink); font-size: 12px; letter-spacing: 0.08em; }}
    .hero h1 {{ margin: 8px 0 0; font-size: 34px; line-height: 1.15; letter-spacing: 0.03em; }}
    .hero p {{ margin: 10px 0 0; color: var(--muted); line-height: 1.85; font-size: 15px; }}
    .hero-note {{ margin-top: 16px; border-top: 4px solid var(--accent); background: #efefef; padding: 12px 14px; font-size: 14px; line-height: 1.8; border-radius: 0 0 16px 16px; }}
    .section {{ margin-top: 24px; }}
    .section-head {{ margin-bottom: 10px; }}
    .section-kicker {{ display: inline-block; margin-bottom: 8px; padding: 0.45em 0.8em; background: rgba(245, 200, 51, 0.7); color: #fff; font-size: 16px; letter-spacing: 0.08em; border-radius: 4px 0 0 4px; position: relative; }}
    .section-kicker::after {{ content: ""; position: absolute; top: 0; right: -18px; border-left: 18px solid rgba(245, 200, 51, 0.7); border-top: 16px solid transparent; border-bottom: 16px solid transparent; }}
    .section h2 {{ margin: 4px 0 0; font-size: 28px; line-height: 1.2; }}
    .section-lead {{ margin: 8px 0 0; color: var(--muted); font-size: 15px; line-height: 1.8; }}
    .card {{ position: relative; margin: 14px 0 0; padding: 16px 16px 14px; background: var(--paper); border: 1px solid var(--line); box-shadow: 0 10px 24px rgba(92, 74, 16, 0.05); }}
    .card + .card {{ margin-top: 12px; }}
    .card-notch {{ position: absolute; right: -1px; bottom: -1px; width: 22px; height: 22px; border-right: 1px solid var(--line); border-bottom: 1px solid var(--line); transform: rotate(-45deg) translate(9px, 9px); background: var(--paper); transform-origin: center; }}
    .card h3 {{ margin: 0 0 10px; font-size: 22px; line-height: 1.5; }}
    .subhead {{ margin: 14px 0 6px; font-size: 16px; color: var(--accent-ink); border-left: 4px solid rgba(171, 211, 224, 0.95); padding-left: 8px; }}
    p {{ margin: 8px 0; line-height: 1.9; font-size: 15px; word-break: break-word; }}
    .lede-box {{ margin: 10px 0 14px; border-top: 5px solid var(--accent); border-right: 5px solid var(--accent); background: rgba(245, 200, 51, 0.16); padding: 10px 12px 10px 14px; }}
    .lede-tag {{ display: inline-block; margin-bottom: 6px; padding: 3px 9px; background: rgba(245, 200, 51, 0.75); color: #fff; font-size: 14px; letter-spacing: 0.08em; }}
    .lede-box p {{ margin: 0; }}
    .meta-row {{ display: flex; gap: 10px; align-items: baseline; margin: 7px 0; }}
    .meta-label {{ flex: 0 0 auto; min-width: 78px; color: var(--muted); font-size: 13px; letter-spacing: 0.04em; }}
    .meta-value {{ flex: 1 1 auto; }}
    .meta-value.is-highlight, .time-highlight {{ color: #f96e57; font-weight: 700; }}
    .note {{ color: var(--ink); font-size: 14px; }}
    .bullet {{ position: relative; padding-left: 1.1em; }}
    .bullet::before {{ content: "•"; position: absolute; left: 0; color: var(--accent-ink); }}
    .table-wrap {{ margin: 12px 0; overflow-x: auto; border: 1px solid rgba(213, 165, 28, 0.45); border-radius: 8px; background: #fffdf6; }}
    .info-table {{ width: 100%; border-collapse: collapse; min-width: 420px; font-size: 14px; line-height: 1.65; }}
    .info-table th, .info-table td {{ padding: 8px 10px; border-bottom: 1px solid rgba(213, 165, 28, 0.26); border-right: 1px solid rgba(213, 165, 28, 0.18); text-align: left; vertical-align: top; }}
    .info-table th {{ background: rgba(245, 200, 51, 0.18); color: var(--accent-ink); font-weight: 700; }}
    .info-table tr:last-child td {{ border-bottom: 0; }}
    .info-table th:last-child, .info-table td:last-child {{ border-right: 0; }}
    a {{ color: #8b5600; text-decoration: none; border-bottom: 1px solid rgba(139, 86, 0, 0.24); }}
    .figure {{ margin: 12px 0 4px; text-align: center; }}
    .figure img {{ display: inline-block; max-width: 100%; border-radius: 10px; border: 1px solid rgba(62, 62, 62, 0.08); }}
    .page-footer {{ margin-top: 28px; padding: 16px 14px 0; text-align: center; }}
    .footer-note {{ margin-top: 12px; border-top: 4px solid var(--accent); background: #efefef; padding: 12px 14px; border-radius: 0 0 16px 16px; font-size: 14px; color: var(--muted); line-height: 1.8; }}
    .footer-badge {{ width: 54px; height: 54px; border-radius: 50%; box-shadow: 0 10px 20px rgba(143, 106, 0, 0.10); background: #fff; }}
    @media (max-width: 640px) {{
      .page {{ width: min(100vw - 16px, 760px); padding-top: 14px; }}
      .hero {{ padding: 18px 14px 16px; border-radius: 22px; }}
      .hero-top {{ gap: 10px; }}
      .hero-badge {{ width: 56px; height: 56px; }}
      .hero h1 {{ font-size: 28px; }}
      .section-kicker {{ font-size: 14px; }}
      .section-kicker::after {{ right: -16px; border-left-width: 16px; border-top-width: 15px; border-bottom-width: 15px; }}
      .section h2 {{ font-size: 24px; }}
      .card h3 {{ font-size: 19px; }}
      .meta-row {{ display: block; }}
      .meta-label {{ display: block; min-width: 0; margin-bottom: 2px; }}
    }}
  </style>
</head>
<body>
  <main class="page">
    <header class="hero">
      <div class="hero-top">
        {hero_badge}
        <div>
          <span class="hero-mark">清物语 · 物理系风格</span>
          <h1>{html.escape(page_title)}</h1>
        </div>
      </div>
      <p>参考人工编辑版万有预报的公众号排版节奏，保留物理系熟悉的暖黄色标签、纸片感信息卡和系内识别贴图，让自动生成的版本也尽量像一篇认真整理过的推送。</p>
      <div class="hero-note">天气渐暖，大家注意增减衣物。以下内容按栏目整理，方便直接转成物理系风格的万有预报。</div>
    </header>
    {body_html}
    <footer class="page-footer">
      {footer_badge}
      <div class="footer-note">本期万有预报到这里就结束了。<br />万有预报，下期再见。</div>
    </footer>
  </main>
</body>
</html>
'''



def export_h5(markdown_path: str, output_path: str, title: str = "") -> str:
    with open(markdown_path, "r", encoding="utf-8") as f:
        markdown_text = f.read()

    html_text = markdown_to_h5_html(markdown_text, markdown_path=markdown_path, output_path=output_path, title=title)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_text)
    return output_path
