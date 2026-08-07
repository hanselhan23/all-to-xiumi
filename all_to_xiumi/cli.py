"""
all-to-xiumi 统一命令行入口。

输入可以是 .html / .md / .pdf：
  - .html 直接进入发布核心（可选 --preserve-styles 保留设计稿样式）。
  - .md / .pdf 先用模板系统转成富文本 HTML，再发布。
"""

import argparse
import os
import sys

from .skill_pipeline import run_skill


def _configure_console():
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def main(argv=None):
    _configure_console()

    parser = argparse.ArgumentParser(
        prog="all-to-xiumi",
        description="HTML / Markdown / PDF → 秀米草稿一键发布。",
    )
    parser.add_argument("input", help="输入文件：.html / .md / .pdf")
    parser.add_argument(
        "--template",
        default="auto",
        choices=["auto", "generic", "wanyou", "red"],
        help="Markdown/PDF 模板（默认 auto 自动检测；仅 md/pdf 使用）",
    )
    parser.add_argument("--title", default="", help="草稿标题（默认取 Markdown 第一个 H1）")
    parser.add_argument("--subtitle", default="", help="页面副标题（md/pdf 使用）")
    parser.add_argument("--author", default="", help="作者")
    parser.add_argument("--digest", default="", help="摘要/导语")
    parser.add_argument("--source-url", default="", help="原文链接")
    parser.add_argument(
        "--image-mode",
        default=None,
        choices=["upload", "auto", "inline", "omit"],
        help="图片处理模式（默认取 XIUMI_IMAGE_MODE）",
    )
    parser.add_argument("--html-only", action="store_true", help="只生成富文本 HTML，不打开浏览器")
    parser.add_argument("--dry-run", action="store_true", help="打开并填充编辑器，但不点击保存")
    parser.add_argument("--upload-probe", action="store_true", help="上传前先测试图片上传链路")
    parser.add_argument(
        "--preserve-styles",
        action="store_true",
        help="模型级保留源设计样式（背景/渐变/边框/字体），适合设计稿 HTML",
    )
    parser.add_argument("--no-base-format", action="store_true", help="跳过秀米 base 格式归一化")
    parser.add_argument("--base-format", action="store_true", help="强制应用秀米 base 格式归一化")
    parser.add_argument(
        "--profile-dir",
        default="",
        help="浏览器 profile 目录（保留登录态；不传则用配置目录并在关闭后清理）",
    )
    parser.add_argument("--home-url", default="", help="秀米首页 URL")
    parser.add_argument("--login-timeout", type=int, default=0, help="登录超时秒数")
    parser.add_argument("--save-timeout", type=int, default=0, help="保存超时秒数")
    parser.add_argument("--output-dir", default="output", help="md/pdf 生成 HTML 的输出目录")

    args = parser.parse_args(argv)

    if args.base_format and args.no_base_format:
        parser.error("--base-format 与 --no-base-format 不能同时使用")

    apply_base_format = None
    if args.base_format:
        apply_base_format = True
    elif args.no_base_format:
        apply_base_format = False

    if args.image_mode:
        os.environ["XIUMI_IMAGE_MODE"] = args.image_mode

    result = run_skill(
        args.input,
        template=args.template,
        to_xiumi=not args.html_only,
        title=args.title,
        subtitle=args.subtitle,
        author=args.author,
        digest=args.digest,
        source_url=args.source_url,
        html_only=args.html_only,
        dry_run=args.dry_run,
        upload_probe=args.upload_probe,
        preserve_styles=args.preserve_styles,
        apply_base_format=apply_base_format,
        profile_dir=args.profile_dir,
        home_url=args.home_url,
        login_timeout=args.login_timeout,
        save_timeout=args.save_timeout,
        output_dir=args.output_dir,
    )

    if result.get("draft_url"):
        print(f"秀米草稿: {result['draft_url']}")
    return 0 if result.get("status") in ("saved", "dry_run", "html_only") else 1


if __name__ == "__main__":
    sys.exit(main())
