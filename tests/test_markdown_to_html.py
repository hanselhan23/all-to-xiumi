"""
测试 markdown_to_html 转换器。
"""

import pytest

from all_to_xiumi.markdown_to_html import (
    _is_ordered_list_item,
    _is_table_row,
    _is_table_separator,
    _render_inline_markdown,
    _split_label_value,
    _split_table_row,
    markdown_to_html,
)


class TestSplitLabelValue:
    def test_with_colon(self):
        assert _split_label_value("日期: 2024-01-01") == ("日期", "2024-01-01")

    def test_with_chinese_colon(self):
        assert _split_label_value("地点：理科楼") == ("地点", "理科楼")

    def test_no_label(self):
        assert _split_label_value("普通文本") == ("", "普通文本")

    def test_empty(self):
        assert _split_label_value("") == ("", "")


class TestRenderInlineMarkdown:
    def test_bold(self):
        result = _render_inline_markdown("这是 **粗体** 文本")
        assert "<strong" in result
        assert "粗体" in result

    def test_italic(self):
        result = _render_inline_markdown("这是 *斜体* 文本")
        assert "<em" in result

    def test_link(self):
        result = _render_inline_markdown("[点击](https://example.com)")
        assert "href" in result
        assert "https://example.com" in result

    def test_inline_code(self):
        result = _render_inline_markdown("使用 `code` 标签")
        assert "<code" in result

    def test_plain_text(self):
        result = _render_inline_markdown("普通文本")
        assert result == "普通文本"


class TestTableDetection:
    def test_table_row(self):
        assert _is_table_row("| A | B | C |")

    def test_not_table_row(self):
        assert not _is_table_row("普通文本")

    def test_table_separator(self):
        assert _is_table_separator("|---|---|")

    def test_not_table_separator(self):
        assert not _is_table_separator("| A | B |")

    def test_split_table_row(self):
        assert _split_table_row("| A | B | C |") == ["A", "B", "C"]


class TestOrderedList:
    def test_ordered_list_item(self):
        assert _is_ordered_list_item("1. 第一项")

    def test_not_ordered_list_item(self):
        assert not _is_ordered_list_item("- 无序列表")

    def test_two_digit(self):
        assert _is_ordered_list_item("12. 第十二项")


class TestMarkdownToHtml:
    def test_basic_heading(self):
        html = markdown_to_html("# 标题\n\n内容段落")
        assert "<h1" in html
        assert "标题" in html
        assert "内容段落" in html

    def test_h2_section(self):
        html = markdown_to_html("## 栏目一\n\n卡片内容")
        assert "栏目一" in html

    def test_h3_card(self):
        html = markdown_to_html("## 栏目\n\n### 卡片标题\n\n卡片内容")
        assert "卡片标题" in html

    def test_unordered_list(self):
        html = markdown_to_html("## 列表\n\n- 项目一\n- 项目二")
        assert "项目一" in html
        assert "项目二" in html

    def test_ordered_list(self):
        html = markdown_to_html("## 步骤\n\n1. 第一步\n2. 第二步")
        assert "第一步" in html
        assert "第二步" in html

    def test_table(self):
        md = "## 表格\n\n| 名称 | 值 |\n|---|---|\n| A | 1 |\n| B | 2 |"
        html = markdown_to_html(md)
        assert "<table" in html
        assert "名称" in html
        assert "A" in html

    def test_image(self):
        html = markdown_to_html("![配图](https://example.com/img.png)")
        assert "<img" in html
        assert "example.com/img.png" in html

    def test_meta_label(self):
        html = markdown_to_html("日期: 2024-01-01")
        assert "日期" in html
        assert "2024-01-01" in html

    def test_code_block(self):
        md = "```python\nprint('hello')\n```"
        html = markdown_to_html(md)
        assert "<pre" in html
        assert "print" in html

    def test_blockquote(self):
        html = markdown_to_html("> 这是一段引用")
        assert "<blockquote" in html
        assert "这是一段引用" in html

    def test_empty_markdown(self):
        html = markdown_to_html("")
        assert "<section" in html  # page wrapper still renders

    def test_template_selection(self):
        html = markdown_to_html("# 标题", template="generic")
        assert html  # should not error

        html_wanyou = markdown_to_html("# 标题", template="wanyou")
        assert html_wanyou  # should not error
        assert "清物语" in html_wanyou

    def test_bold_inline(self):
        html = markdown_to_html("这是 **粗体** 文本")
        assert "<strong" in html

    def test_link_inline(self):
        html = markdown_to_html("访问 [GitHub](https://github.com)")
        assert "href" in html
        assert "github.com" in html

    def test_custom_title(self):
        html = markdown_to_html("## 章节\n内容", title="自定义标题")
        assert "自定义标题" in html
