#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成 Android Kotlin 移植的金标测试文件。

用本仓库 Python 参考实现生成期望输出，写入
android/app/src/test/resources/golden/，供 Kotlin 单元测试逐字节比对。

用法（仓库根目录）：
    python android/tools/gen_golden_tests.py
"""

import json
import pathlib
import sys
import tempfile
import importlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

# 注意：all_to_xiumi/__init__.py 会 re-export 同名函数，遮蔽模块名，故用 importlib 取模块。
m2h = importlib.import_module("all_to_xiumi.markdown_to_html")
image_paths = importlib.import_module("all_to_xiumi.image_paths")
xp = importlib.import_module("all_to_xiumi.xiumi_publish")

OUT = ROOT / "android" / "app" / "src" / "test" / "resources" / "golden"
FIXTURES = ROOT / "android" / "app" / "src" / "test" / "resources" / "fixtures"


def main() -> None:
    (OUT / "markdown").mkdir(parents=True, exist_ok=True)

    manifest = {}

    # ── 1. markdown_to_html 金标：每模板 × 每 fixture ──
    for fixture_name in ("sample.md", "extended.md"):
        text = (FIXTURES / fixture_name).read_text(encoding="utf-8")
        for template in ("generic", "wanyou", "red"):
            html_out = m2h.markdown_to_html(text, template=template)
            rel = f"markdown/{fixture_name.removesuffix('.md')}_{template}.html"
            (OUT / rel).write_text(html_out, encoding="utf-8")
            manifest[rel] = {"input": fixture_name, "template": template}

    # ── 2. 纯函数测试向量（JSON） ──
    vectors = {}

    # 2.0 输入快照（供 Kotlin 测试读取，避免输入在两侧漂移）
    vectors["inputs"] = {
        "render_inline_markdown": [
            "**粗体**与*斜体*和`代码`及[链接](https://a.b/c?x=1&y=2)",
            "普通文本 <b>&</b> 转义",
            "**链接内的粗体** http://直接地址",
        ],
        "render_inline_markdown_red": "**红**模板*内联*`code`",
        "split_label_value": [
            "日期: 2024-01-15",
            "地点：清华大学 礼堂",
            "没有冒号的行",
            "太长太长太长太长太长太长太长太长太长太长太长: 值",
        ],
        "is_table_row": ["| a | b |", "| a |", "普通行"],
        "is_table_separator": ["|---|---|", "|:---|:---:|", "|---|--|"],
        "split_table_row": "| a | b\\|c | d |",
        "is_ordered_list_item": ["1. 第一", "12. 十二", "1. 无空格后文本"],
        "is_remote_or_data": [
            "https://a.b/c.png", "//cdn.a.b/x.png", "data:image/png;base64,xx",
            "images/a.png", "C:/Users/a.png", "ftp://a.b/x", "mailto:a@b.c", "",
        ],
        "clean_target": [
            "images\\wanyou20260531_1131\\1.jpg", "images/wanyou_20260531_1131/2.jpg",
            "\"images/quoted.png\"", "<images/angle.png>", "images\\a_b.png",
            "images/x.png?w=1", "https://a.b/c.png?x=1", "data:image/png;base64,zzz",
            "C:\\Users\\a\\b.png", "images/inline/wanyou20260531_1131_0.jpg",
        ],
        "iter_candidates": [
            "images/wanyou20260531_1131/1.jpg",
            "output/20260428/1030/images/inline/wanyou20260428_1030_0.jpg",
        ],
        "resolve_existing": ["images/wanyou20260531_1131/1.jpg", "images/nope.jpg"],
        "sample_html": (
            '<main class="page hero-v2">'
            '<section style="margin:0 auto;background:#f5f8fc;"><h1 style="font-size:38px;color:#1a344c;">大标题</h1></section>'
            '<section style="background:#e3eff9;">'
            '<p style="font-size:16px;line-height:2;margin:0 8px;letter-spacing:1px;">正文段落一</p>'
            '<p style="color:#3a4a5c;">正文段落二</p>'
            '<img src="images/a.png" alt="配图一" style="width:100%;" />'
            '<img src="https://cdn.example.com/b.png" alt="远程图" />'
            '</section></main>'
        ),
        "extract_main_html_body": "<html><body><p>x</p></body></html>",
        "extract_main_html_raw": "<div>无main</div>",
        "camelize_css": "margin:0 auto; Background-Color:#fff;box-sizing:border-box;font-Size:14px;-webkit-x:1;broken",
        "flatten_inner_html": (
            '<!-- 注释 --><section style="margin:0"><span>chip</span><p>正文</p><p></p></section>'
            '<div class="x">  多  空格  </div>'
        ),
        "first_heading": "# 标题\n正文",
        "first_summary_line": "\n## 节\n![图](x.png)\n这是摘要第一行。\n",
        "image_urls_from_text": (
            'a //img.xiumi.us/xmi/ua/abc/123.png b https://statics.xiumi.us/stc/1.png '
            'c "https://a.b/xmi/ua/2.jpg" d'
        ),
        "normalize_urls": ["//img.xiumi.us/x/1.png", "\\/\\/img.xiumi.us/x/2.png", "https://a.b/c"],
        "looks_like_user_image": [
            "https://img.xiumi.us/xmi/ua/1/1.png", "https://statics.xiumi.us/stc/x.png",
            "https://a.b/xmi/ua/2.jpg", "",
        ],
        "upload_name_variants_path": "images/My Photo.PNG",
        "upload_image_key_path": "a/b/My-Photo_2.jpg",
        "upload_image_key_source": "images/wanyou_20260531_1131/1.jpg",
        "asset_matches_asset": {"files": ["my-photo_2.JPG"], "text": "我的图库"},
        "asset_matches_path": "a/b/My-Photo_2.jpg",
    }

    # 2.1 行内渲染 / 标签拆分
    tpl = m2h.get_template("generic")
    vectors["render_inline_markdown"] = [
        {"in": "**粗体**与*斜体*和`代码`及[链接](https://a.b/c?x=1&y=2)",
         "out": m2h._render_inline_markdown("**粗体**与*斜体*和`代码`及[链接](https://a.b/c?x=1&y=2)", tpl)},
        {"in": "普通文本 <b>&</b> 转义",
         "out": m2h._render_inline_markdown("普通文本 <b>&</b> 转义", tpl)},
        {"in": "**链接内的粗体** http://直接地址",
         "out": m2h._render_inline_markdown("**链接内的粗体** http://直接地址", tpl)},
    ]
    vectors["split_label_value"] = [
        {"in": "日期: 2024-01-15", "out": list(m2h._split_label_value("日期: 2024-01-15"))},
        {"in": "地点：清华大学 礼堂", "out": list(m2h._split_label_value("地点：清华大学 礼堂"))},
        {"in": "没有冒号的行", "out": list(m2h._split_label_value("没有冒号的行"))},
        {"in": "太长太长太长太长太长太长太长太长太长太长太长: 值", "out": list(m2h._split_label_value("太长太长太长太长太长太长太长太长太长太长太长: 值"))},
    ]
    red_tpl = m2h.get_template("red")
    vectors["render_inline_markdown_red"] = [
        {"in": "**红**模板*内联*`code`",
         "out": m2h._render_inline_markdown("**红**模板*内联*`code`", red_tpl)},
    ]
    vectors["table_helpers"] = {
        "is_table_row": [m2h._is_table_row("| a | b |"), m2h._is_table_row("| a |"), m2h._is_table_row("普通行")],
        "is_table_separator": [m2h._is_table_separator("|---|---|"), m2h._is_table_separator("|:---|:---:|"), m2h._is_table_separator("|---|--|")],
        "split_table_row": m2h._split_table_row("| a | b\\|c | d |"),
        "is_ordered_list_item": [m2h._is_ordered_list_item("1. 第一"), m2h._is_ordered_list_item("12. 十二"), m2h._is_ordered_list_item("1. 无空格后文本")],
    }

    # 2.2 image_paths
    vectors["image_paths"] = {
        "is_remote_or_data": [image_paths.is_remote_or_data_image(s) for s in [
            "https://a.b/c.png", "//cdn.a.b/x.png", "data:image/png;base64,xx",
            "images/a.png", "C:/Users/a.png", "ftp://a.b/x", "mailto:a@b.c", ""]],
        "clean_target": [image_paths.clean_markdown_image_target(s) for s in [
            "images\\wanyou20260531_1131\\1.jpg", "images/wanyou_20260531_1131/2.jpg",
            "\"images/quoted.png\"", "<images/angle.png>", "images\\a_b.png",
            "images/x.png?w=1", "https://a.b/c.png?x=1", "data:image/png;base64,zzz",
            "C:\\Users\\a\\b.png", "images/inline/wanyou20260531_1131_0.jpg"]],
    }
    with tempfile.TemporaryDirectory() as tmp:
        base = pathlib.Path(tmp)
        # 文件名用无下划线形式 wanyou<时间戳>，正好命中 variants[0]（原始名）
        (base / "images" / "wanyou20260531_1131").mkdir(parents=True)
        (base / "images" / "wanyou20260531_1131" / "1.jpg").write_bytes(b"x")

        def mask(value: str) -> str:
            # 临时目录与仓库根目录的绝对路径不可复现，替换为占位符
            return value.replace(str(base.resolve()), "<TMP>").replace(str(ROOT.resolve()), "<ROOT>")

        vectors["image_paths"]["iter_candidates"] = [
            [mask(str(p)) for p in image_paths.iter_image_path_candidates(
                "images/wanyou20260531_1131/1.jpg", base_dir=base)],
            [mask(str(p)) for p in image_paths.iter_image_path_candidates(
                "output/20260428/1030/images/inline/wanyou20260428_1030_0.jpg", base_dir=base)],
        ]
        vectors["image_paths"]["resolve_existing"] = [
            mask(str(image_paths.resolve_existing_image_path("images/wanyou20260531_1131/1.jpg", base_dir=base) or "")),
            mask(str(image_paths.resolve_existing_image_path("images/nope.jpg", base_dir=base) or "")),
        ]

    # 2.3 xiumi_publish 纯 HTML 预处理
    sample_html = (
        '<main class="page hero-v2">'
        '<section style="margin:0 auto;background:#f5f8fc;"><h1 style="font-size:38px;color:#1a344c;">大标题</h1></section>'
        '<section style="background:#e3eff9;">'
        '<p style="font-size:16px;line-height:2;margin:0 8px;letter-spacing:1px;">正文段落一</p>'
        '<p style="color:#3a4a5c;">正文段落二</p>'
        '<img src="images/a.png" alt="配图一" style="width:100%;" />'
        '<img src="https://cdn.example.com/b.png" alt="远程图" />'
        '</section></main>'
    )
    vectors["xiumi_pure"] = {
        "extract_main_html": xp._extract_main_html(sample_html),
        "extract_main_html_body": xp._extract_main_html("<html><body><p>x</p></body></html>"),
        "extract_main_html_raw": xp._extract_main_html("<div>无main</div>"),
        "apply_base_format": xp._apply_xiumi_base_format(sample_html),
        "promote_headings": xp._promote_headings_for_xiumi(sample_html),
        "camelize_css": xp._xiumi_camelize_css(
            "margin:0 auto; Background-Color:#fff;box-sizing:border-box;font-Size:14px;-webkit-x:1;broken"),
        "flatten_inner_html": xp._xiumi_flatten_inner_html(
            '<!-- 注释 --><section style="margin:0"><span>chip</span><p>正文</p><p></p></section>'
            '<div class="x">  多  空格  </div>'),
        "blocks": xp._xiumi_html_to_blocks(sample_html),
        "first_heading": xp._first_heading("# 标题\n正文"),
        "first_summary_line": xp._first_summary_line("\n## 节\n![图](x.png)\n这是摘要第一行。\n"),
        "image_urls_from_text": xp._xiumi_image_urls_from_text(
            'a //img.xiumi.us/xmi/ua/abc/123.png b https://statics.xiumi.us/stc/1.png c "https://a.b/xmi/ua/2.jpg" d'),
        "normalize_urls": [xp._normalize_xiumi_image_url(u) for u in ["//img.xiumi.us/x/1.png", "\\/\\/img.xiumi.us/x/2.png", "https://a.b/c"]],
        "looks_like_user_image": [xp._looks_like_user_xiumi_image(u) for u in [
            "https://img.xiumi.us/xmi/ua/1/1.png", "https://statics.xiumi.us/stc/x.png", "https://a.b/xmi/ua/2.jpg", ""]],
        "upload_name_variants": sorted(xp._upload_name_variants(pathlib.Path("images/My Photo.PNG"))),
        "upload_image_key": [xp._upload_image_key(pathlib.Path("a/b/My-Photo_2.jpg")), xp._upload_image_key(None, "images/wanyou_20260531_1131/1.jpg")],
        "asset_matches": [xp._asset_matches_upload_path(
            {"files": ["my-photo_2.JPG"], "text": "我的图库"}, pathlib.Path("a/b/My-Photo_2.jpg"))],
    }

    (OUT / "pure_vectors.json").write_text(
        json.dumps(vectors, ensure_ascii=False, indent=2), encoding="utf-8")

    # ── 3. 清单 ──
    (OUT / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"golden 已生成：{OUT}")


if __name__ == "__main__":
    main()
