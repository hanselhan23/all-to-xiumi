package com.hanselhan.wanyou.markdown

/**
 * 模板系统 —— `all_to_xiumi/templates/`（base / generic / wanyou / red）的移植。
 *
 * 样式常量与渲染输出必须与 Python 逐字节一致（金标测试比对）。
 * 注意 Python 的 `render_header` 不对 title/subtitle 转义，这里同样保留。
 */
open class Template {
    // ── 页面级样式 ──
    open val pageStyle: String =
        "margin:0 auto;padding:0 0 8px;background:#f5f8fc;color:#2c3440;" +
            "font-family:-apple-system,BlinkMacSystemFont,'Helvetica Neue'," +
            "'PingFang SC','Microsoft YaHei',sans-serif;line-height:1.75;font-size:15px;"
    open val heroStyle: String =
        "margin:0 0 18px;padding:22px 18px 20px;" +
            "border:1px solid #b8d0e8;background:#e3eff9;border-radius:12px;"
    open val heroMarkStyle: String =
        "display:inline-block;margin-bottom:8px;padding:3px 8px;" +
            "color:#fff;border-radius:999px;font-size:12px;letter-spacing:.08em;"
    open val heroTitleStyle: String =
        "margin:0;color:#1a344c;font-size:26px;font-weight:800;line-height:1.25;"
    open val heroSubtitleStyle: String =
        "margin:8px 0 0;color:#5c7d99;font-size:14px;"

    open val sectionStyle: String =
        "margin:20px 0 0;padding:18px 16px;background:#f6f9fc;" +
            "border:1px solid #c8ddf0;border-radius:12px;" +
            "box-shadow:0 3px 12px rgba(40,80,120,.05);"
    open val sectionTitleStyle: String =
        "margin:0 0 10px;color:#1a344c;font-size:20px;font-weight:800;" +
            "line-height:1.35;padding-bottom:6px;border-bottom:2px solid #5ca4d4;"
    open val sectionLeadStyle: String =
        "margin:8px 0 10px;color:#5c7d99;font-size:14px;line-height:1.7;"

    open val cardStyle: String =
        "margin:10px 0 0;padding:12px 12px;background:#eef4fa;" +
            "border:1px solid #d4e4f2;border-radius:8px;"
    open val cardTitleStyle: String =
        "margin:0 0 8px;color:#1a344c;font-size:16px;font-weight:700;line-height:1.4;"

    open val paraStyle: String =
        "margin:8px 0;color:#3a4a5c;font-size:14px;line-height:1.6;" +
            "letter-spacing:0;text-indent:2em;"
    open val strongStyle: String = "color:#1a344c;font-weight:700;"
    open val emStyle: String = "color:#5c7d99;font-style:italic;"

    open val bulletStyle: String =
        "margin:6px 0 6px 1em;color:#3a4a5c;font-size:14px;line-height:1.6;"

    open val imageStyle: String =
        "display:block;width:100%;max-width:100%;height:auto;" +
            "margin:10px auto;border-radius:8px;"

    open val linkStyle: String = "color:#3b8cc7;text-decoration:underline;word-break:break-all;"

    open val quoteStyle: String =
        "margin:10px 0;padding:10px 12px;background:#eaf2fa;" +
            "border-left:4px solid #5ca4d4;border-radius:6px;color:#3d5268;"

    open val codeBlockStyle: String =
        "margin:10px 0;padding:12px 14px;background:#2d2d2d;color:#c5d4e0;" +
            "border-radius:8px;font-family:'SF Mono','Fira Code','Consolas',monospace;" +
            "font-size:13px;line-height:1.6;overflow-x:auto;white-space:pre-wrap;"

    // ── 元信息行样式 (key: value 模式) ──
    open val metaRowStyle: String =
        "margin:5px 0;color:#3a4a5c;font-size:14px;line-height:1.65;"
    open val metaLabelStyle: String =
        "display:inline-block;margin-right:6px;color:#5c7d99;font-weight:700;"
    open val metaTimeValueStyle: String = "color:#3b8cc7;font-weight:700;"

    // ── 表格样式 ──
    open val tableWrapStyle: String =
        "margin:10px 0;overflow-x:auto;border:1px solid #c8ddf0;" +
            "border-radius:8px;background:#f6f9fc;"
    open val tableStyle: String =
        "width:100%;border-collapse:collapse;font-size:14px;line-height:1.6;"
    open val thStyle: String =
        "padding:7px 8px;border:1px solid #c8ddf0;background:#d8ecf8;" +
            "color:#1a4a6c;font-weight:700;text-align:left;vertical-align:top;"
    open val tdStyle: String =
        "padding:7px 8px;border:1px solid #c8ddf0;color:#3a4a5c;" +
            "text-align:left;vertical-align:top;"

    open val footerStyle: String =
        "margin:24px 0 0;padding:14px 10px;text-align:center;" +
            "color:#6c8da8;font-size:14px;"

    // ── 模板元信息 ──
    open val name: String = "base"
    open val heroMarkText: String = ""

    fun renderHeader(title: String = "", subtitle: String = ""): String {
        val parts = mutableListOf("<section style=\"$heroStyle\">")
        if (heroMarkText.isNotEmpty()) {
            parts.add("<span style=\"$heroMarkStyle\">$heroMarkText</span>")
        }
        if (title.isNotEmpty()) {
            parts.add("<h1 style=\"$heroTitleStyle\">$title</h1>")
        }
        if (subtitle.isNotEmpty()) {
            parts.add("<p style=\"$heroSubtitleStyle\">$subtitle</p>")
        }
        parts.add("</section>")
        return parts.joinToString("\n")
    }

    fun renderFooter(text: String = ""): String =
        "<section style=\"$footerStyle\">${text.ifEmpty { "—" }}</section>"

    fun renderSectionStart(title: String): String =
        "<section style=\"$sectionStyle\"><h2 style=\"$sectionTitleStyle\">$title</h2>"

    fun renderSectionEnd(): String = "</section>"

    fun renderCardStart(title: String): String =
        "<section style=\"$cardStyle\"><h3 style=\"$cardTitleStyle\">$title</h3>"

    fun renderCardEnd(): String = "</section>"

    fun renderParagraph(text: String): String =
        "<p style=\"$paraStyle\">$text</p>"

    fun renderMetaRow(label: String, value: String, isTimeLabel: Boolean = false): String {
        val valueStyle = if (isTimeLabel) metaTimeValueStyle else "color:#3a4a5c;"
        return "<p style=\"$metaRowStyle\">" +
            "<span style=\"$metaLabelStyle\">$label</span>" +
            "<span style=\"$valueStyle\">$value</span></p>"
    }

    fun renderImage(src: String, alt: String = ""): String =
        "<img src=\"$src\" alt=\"${alt.ifEmpty { "配图" }}\" style=\"$imageStyle\" />"

    fun renderLink(url: String, text: String = ""): String {
        val display = text.ifEmpty { url }
        return "<a href=\"$url\" style=\"$linkStyle\">$display</a>"
    }

    fun renderBullet(text: String): String =
        "<p style=\"$bulletStyle\">• $text</p>"

    fun renderOrderedItem(number: Int, text: String): String =
        "<p style=\"$bulletStyle\">$number. $text</p>"

    fun renderQuote(text: String): String =
        "<blockquote style=\"$quoteStyle\">$text</blockquote>"

    fun renderCodeBlock(code: String): String =
        "<pre style=\"$codeBlockStyle\">$code</pre>"

    fun renderTable(headers: List<String>, rows: List<List<String>>): String {
        val head = headers.joinToString("") { "<th style=\"$thStyle\">$it</th>" }
        val body = rows.joinToString("") { row ->
            "<tr>" + row.joinToString("") { "<td style=\"$tdStyle\">$it</td>" } + "</tr>"
        }
        return "<section style=\"$tableWrapStyle\">" +
            "<table style=\"$tableStyle\">" +
            "<thead><tr>$head</tr></thead>" +
            "<tbody>$body</tbody>" +
            "</table></section>"
    }

    open fun renderH4(text: String): String =
        "<p style=\"${paraStyle}font-weight:700;" +
            "color:#3a6d94;font-size:16px;\">$text</p>"
}

/** 通用模板 —— 更中性的 Hero 配色。 */
open class GenericTemplate : Template() {
    override val name: String = "generic"
    override val heroMarkText: String = ""

    override val heroStyle: String =
        "margin:0 0 18px;padding:22px 18px 20px;" +
            "border:1px solid #c5d4e0;background:#e6f0f8;border-radius:12px;"
    override val heroMarkStyle: String =
        "display:inline-block;margin-bottom:8px;padding:3px 8px;" +
            "background:#5a8da8;color:#fff;border-radius:999px;" +
            "font-size:12px;letter-spacing:.08em;"
    override val heroTitleStyle: String =
        "margin:0;color:#1a2a38;font-size:26px;font-weight:800;line-height:1.25;"
    override val heroSubtitleStyle: String =
        "margin:8px 0 0;color:#5c7c94;font-size:14px;"
}

/** 万有预报模板 —— 清华物理系风格（仅品牌标识差异）。 */
class WanyouTemplate : Template() {
    override val name: String = "wanyou"
    override val heroMarkText: String = "清物语 · 物理系风格"
}

/** 红色主题模板 —— 理论学习 / 党建类推送。 */
class RedTemplate : Template() {
    override val name: String = "red"
    override val heroMarkText: String = "理论学习"

    override val pageStyle: String =
        "margin:0 auto;padding:0 0 8px;background:#fdf8f8;color:#2c2020;" +
            "font-family:-apple-system,BlinkMacSystemFont,'Helvetica Neue'," +
            "'PingFang SC','Microsoft YaHei',sans-serif;line-height:1.75;font-size:15px;"
    override val heroStyle: String =
        "margin:0 0 18px;padding:22px 18px 20px;" +
            "border:1px solid #d4b8b8;background:#fdf2f2;border-radius:12px;"
    override val heroMarkStyle: String =
        "display:inline-block;margin-bottom:8px;padding:3px 10px;" +
            "background:#c0392b;color:#fff;border-radius:999px;font-size:12px;letter-spacing:.08em;"
    override val heroTitleStyle: String =
        "margin:0;color:#8b1a1a;font-size:26px;font-weight:800;line-height:1.25;"
    override val heroSubtitleStyle: String =
        "margin:8px 0 0;color:#8b5a5a;font-size:14px;"

    override val sectionStyle: String =
        "margin:20px 0 0;padding:18px 16px;background:#fdf6f6;" +
            "border:1px solid #e8cccc;border-radius:12px;" +
            "box-shadow:0 3px 12px rgba(120,20,20,.05);"
    override val sectionTitleStyle: String =
        "margin:0 0 10px;color:#8b1a1a;font-size:20px;font-weight:800;" +
            "line-height:1.35;padding-bottom:6px;border-bottom:2px solid #c0392b;"
    override val sectionLeadStyle: String =
        "margin:8px 0 10px;color:#8b5a5a;font-size:14px;line-height:1.7;"

    override val cardStyle: String =
        "margin:10px 0 0;padding:14px 14px;background:#fdf2f2;" +
            "border:1px solid #e8d0d0;border-radius:8px;"
    override val cardTitleStyle: String =
        "margin:0 0 8px;color:#8b1a1a;font-size:16px;font-weight:700;line-height:1.4;"

    override val paraStyle: String =
        "margin:8px 0;color:#4a3030;font-size:14px;line-height:1.6;" +
            "letter-spacing:0;text-indent:2em;"
    override val strongStyle: String = "color:#a82020;font-weight:700;"
    override val emStyle: String = "color:#8b5a5a;font-style:italic;"

    override val bulletStyle: String =
        "margin:6px 0 6px 1em;color:#4a3030;font-size:14px;line-height:1.6;"

    override val imageStyle: String =
        "display:block;width:100%;max-width:100%;height:auto;" +
            "margin:10px auto;border-radius:8px;"

    override val linkStyle: String = "color:#c0392b;text-decoration:underline;word-break:break-all;"

    override val quoteStyle: String =
        "margin:10px 0;padding:10px 14px;background:#fdf2f2;" +
            "border-left:4px solid #c0392b;border-radius:6px;color:#5a3838;"

    override val codeBlockStyle: String =
        "margin:10px 0;padding:12px 14px;background:#2d2d2d;color:#e0d0d0;" +
            "border-radius:8px;font-family:'SF Mono','Fira Code','Consolas',monospace;" +
            "font-size:13px;line-height:1.6;overflow-x:auto;white-space:pre-wrap;"

    override val metaRowStyle: String =
        "margin:5px 0;color:#4a3030;font-size:14px;line-height:1.65;"
    override val metaLabelStyle: String =
        "display:inline-block;margin-right:6px;color:#8b5a5a;font-weight:700;"
    override val metaTimeValueStyle: String = "color:#c0392b;font-weight:700;"

    override val tableWrapStyle: String =
        "margin:10px 0;overflow-x:auto;border:1px solid #e8cccc;" +
            "border-radius:8px;background:#fdf6f6;"
    override val tableStyle: String =
        "width:100%;border-collapse:collapse;font-size:14px;line-height:1.6;"
    override val thStyle: String =
        "padding:7px 8px;border:1px solid #e8cccc;background:#f8e0e0;" +
            "color:#6b1a1a;font-weight:700;text-align:left;vertical-align:top;"
    override val tdStyle: String =
        "padding:7px 8px;border:1px solid #e8cccc;color:#4a3030;" +
            "text-align:left;vertical-align:top;"

    override val footerStyle: String =
        "margin:24px 0 0;padding:14px 10px;text-align:center;" +
            "color:#8b5a5a;font-size:14px;"

    override fun renderH4(text: String): String =
        "<p style=\"${paraStyle}text-indent:0;font-weight:700;" +
            "color:#a82020;font-size:15px;\">$text</p>"
}

/** 模板注册与查找 —— `templates/__init__.py` 的移植。 */
object TemplateRegistry {
    private val builtin = linkedMapOf<String, () -> Template>(
        "generic" to { GenericTemplate() },
        "wanyou" to { WanyouTemplate() },
        "red" to { RedTemplate() },
    )

    fun getTemplate(name: String = "generic"): Template {
        val key = name.trim().lowercase()
        return (builtin[key] ?: builtin.getValue("generic")).invoke()
    }

    fun listTemplates(): List<String> = builtin.keys.toList()

    fun registerTemplate(name: String, factory: () -> Template) {
        builtin[name.trim().lowercase()] = factory
    }
}
