"""
all-to-xiumi Skill Pipeline — HTML / Markdown / PDF → 富文本 → 秀米草稿的一键生成。

统一入口：html 直接进入发布核心；md / pdf 先用模板系统转成富文本 HTML，
再把 HTML 文件交给发布核心（图片基路径仍指向原 markdown 目录，保证相对图片可解析）。
"""

import pathlib
import subprocess
import sys

from .markdown_to_html import markdown_to_html
from .templates import list_templates
from .xiumi_publish import publish_xiumi_draft


def _extract_pdf_text(pdf_path: pathlib.Path) -> str:
    """用 pdfplumber 提取 PDF 文本。"""
    try:
        import pdfplumber
    except ImportError:
        print("正在安装 pdfplumber...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pdfplumber", "-q"])
        import pdfplumber

    with pdfplumber.open(str(pdf_path)) as pdf:
        texts = []
        for page in pdf.pages:
            t = page.extract_text()
            if t:
                texts.append(t)
    return "\n\n".join(texts)


def _detect_content_type(text: str) -> str:
    """根据文本内容自动检测推送类型和推荐模板。"""
    keywords_red = [
        "社会主义", "共产主义", "马克思主义", "列宁", "毛泽东", "邓小平",
        "习近平", "革命", "阶级", "帝国主义", "党的领导", "理论", "思想",
        "党的建设", "党性", "群众路线", "唯物", "辩证法", "历史唯物",
    ]
    keywords_science = [
        "物理", "数学", "计算", "实验", "科学", "量子", "相对论",
        "学术", "研究", "论文", "证明", "定理", "公式",
    ]
    score_red = sum(1 for kw in keywords_red if kw in text)
    score_sci = sum(1 for kw in keywords_science if kw in text)

    if score_red > score_sci and score_red >= 3:
        return "red"
    return "generic"


def _detect_structure(text: str) -> dict:
    """分析文本结构：识别标题层级、表格、列表、引用等。"""
    lines = text.strip().splitlines()
    structure = {
        "h1_count": 0,
        "h2_count": 0,
        "h3_count": 0,
        "has_table": False,
        "has_quote": False,
        "has_list": False,
        "has_link": False,
        "total_lines": len(lines),
        "sections": [],
    }
    current_section = None
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("# ") and not stripped.startswith("## "):
            structure["h1_count"] += 1
            current_section = stripped[2:].strip()
        elif stripped.startswith("## ") and not stripped.startswith("### "):
            structure["h2_count"] += 1
            title = stripped[3:].strip()
            current_section = title
            structure["sections"].append({"level": 2, "title": title})
        elif stripped.startswith("### "):
            structure["h3_count"] += 1
            title = stripped[4:].strip()
            structure["sections"].append({"level": 3, "title": title, "parent": current_section})
        elif stripped.startswith("|") and "|" in stripped[1:]:
            structure["has_table"] = True
        elif stripped.startswith("> "):
            structure["has_quote"] = True
        elif stripped.startswith("- ") or stripped.startswith("* "):
            structure["has_list"] = True
        elif "http" in stripped:
            structure["has_link"] = True
    return structure


def run_skill(
    file_path: str,
    *,
    template: str = "auto",
    to_xiumi: bool = True,
    title: str = "",
    author: str = "",
    subtitle: str = "",
    digest: str = "",
    source_url: str = "",
    html_only: bool = False,
    dry_run: bool = False,
    upload_probe: bool = False,
    preserve_styles: bool = False,
    apply_base_format: bool | None = None,
    profile_dir: str = "",
    home_url: str = "",
    login_timeout: int = 0,
    save_timeout: int = 0,
    output_dir: str = "output",
) -> dict:
    """
    统一主流程：识别输入类型 → （md/pdf 生成富文本） → 发布到秀米草稿。

    Args:
        file_path: HTML / Markdown / PDF 文件路径。
        template: 模板名称 ("auto" 自动检测 / generic / wanyou / red)，仅 md/pdf 使用。
        to_xiumi: 是否发布到秀米草稿。
        title: 草稿标题（默认取 Markdown 第一个 H1）。
        author: 作者名。
        subtitle: 页面副标题（md/pdf 使用）。
        digest: 摘要。
        source_url: 原文链接。
        html_only: 只生成富文本 HTML，不打开浏览器。
        dry_run: 仅填充编辑器不保存。
        upload_probe: 上传前先测试图片上传链路。
        preserve_styles: 模型级保留设计样式。
        apply_base_format: base 格式归一化；None 时按输入类型取默认
                           （html=True，md/pdf=False 保留模板排版）。
        profile_dir: 浏览器 profile 目录。
        home_url: 秀米首页 URL。
        login_timeout: 登录超时秒数。
        save_timeout: 保存超时秒数。
        output_dir: md/pdf 生成 HTML 的输出目录。

    Returns:
        dict: 包含 html_content, html_path, markdown_text, template, draft_url 等字段。
    """
    path = pathlib.Path(file_path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"文件不存在: {path}")

    ext = path.suffix.lower()
    print(f"\n📄 读取文件: {path.name}")

    # ── Step 1: 输入识别 ──
    if ext == ".html":
        source_kind = "html"
        html_source_path = path
    elif ext == ".md":
        source_kind = "markdown"
        raw_text = path.read_text(encoding="utf-8")
    elif ext == ".pdf":
        print("   → 检测到 PDF，正在提取文本...")
        source_kind = "markdown"
        raw_text = _extract_pdf_text(path)
    else:
        raise ValueError(f"不支持的文件格式: {ext}，请使用 HTML / Markdown / PDF")

    structure = {}
    if source_kind == "markdown":
        # ── Step 2: 结构分析 ──
        structure = _detect_structure(raw_text)
        print(f"🔍 文档结构: H1={structure['h1_count']}  H2={structure['h2_count']}  "
              f"H3={structure['h3_count']}  表格={'✓' if structure['has_table'] else '✗'}  "
              f"引用={'✓' if structure['has_quote'] else '✗'}")

        # ── Step 3: 模板选择 ──
        if template == "auto":
            template = _detect_content_type(raw_text)
        else:
            template = template.strip().lower()
            if template not in list_templates():
                print(f"⚠️  未知模板 '{template}'，回退到 generic")
                template = "generic"
        print(f"🎨 模板: {template}")

        # ── Step 4: 生成富文本 HTML ──
        html_content = markdown_to_html(
            raw_text,
            template=template,
            title=title,
            subtitle=subtitle,
            markdown_path=str(path.parent),
        )
        out_dir = pathlib.Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        html_path = out_dir / f"{path.stem}.html"
        html_path.write_text(html_content, encoding="utf-8")
        print(f"✅ 富文本已保存: {html_path} ({html_path.stat().st_size:,} bytes)")

        publish_html_path = html_path
        publish_markdown = str(path)
    else:
        html_content = path.read_text(encoding="utf-8")
        html_path = path
        publish_html_path = path
        sibling_md = path.with_suffix(".md")
        publish_markdown = str(sibling_md) if sibling_md.exists() else ""

    if apply_base_format is None:
        apply_base_format = source_kind == "html"

    result = {
        "html_content": html_content,
        "html_path": str(html_path),
        "markdown_text": raw_text if source_kind == "markdown" else "",
        "template": template if source_kind == "markdown" else "",
        "structure": structure,
        "draft_url": "",
        "status": "html_only" if html_only else "unknown",
    }

    if html_only or not to_xiumi:
        return result

    # ── Step 5: 发布到秀米 ──
    print("\n🚀 发布到秀米草稿...")
    try:
        xiumi_result = publish_xiumi_draft(
            str(publish_html_path),
            markdown=publish_markdown,
            title=title,
            author=author,
            digest=digest,
            source_url=source_url,
            profile_dir=profile_dir,
            home_url=home_url,
            login_timeout=login_timeout,
            save_timeout=save_timeout,
            dry_run=dry_run,
            upload_probe=upload_probe,
            apply_base_format=apply_base_format,
            preserve_styles=preserve_styles,
        )
        result["draft_url"] = xiumi_result.get("draft_url", "")
        result["editor_url"] = xiumi_result.get("editor_url", "")
        result["status"] = xiumi_result.get("status", "unknown")
        print(f"  状态: {result['status']}")
        if result["draft_url"]:
            print(f"  草稿: {result['draft_url']}")
    except Exception as exc:
        print(f"❌ 秀米发布失败: {exc}")
        result["status"] = "xiumi_failed"
        result["error"] = str(exc)

    return result


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="推送生成器 — HTML/Markdown/PDF → 富文本 → 秀米草稿")
    parser.add_argument("file", help="HTML / Markdown / PDF 文件路径")
    parser.add_argument("--template", default="auto", help="模板名称 (auto/generic/red/wanyou)")
    parser.add_argument("--to-xiumi", action="store_true", help="同步发布到秀米草稿")
    parser.add_argument("--title", default="", help="草稿标题")
    parser.add_argument("--author", default="", help="作者")
    args = parser.parse_args()

    run_skill(
        args.file,
        template=args.template,
        to_xiumi=args.to_xiumi,
        title=args.title,
        author=args.author,
    )
