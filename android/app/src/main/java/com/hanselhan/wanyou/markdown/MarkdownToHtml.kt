package com.hanselhan.wanyou.markdown

import java.io.File

/**
 * 通用 Markdown → 富文本 HTML 转换器 —— `all_to_xiumi/markdown_to_html.py` 的移植。
 *
 * 与 Python 逐字节一致（金标测试比对），包括几处「怪癖」：
 * - 链接 URL 经两次转义（全文先 quote=False 转义，URL 再 quote=True 转义）；
 * - H5/H6 样式由 para/strong 样式字符串拼接而成；
 * - Hero 标题不转义、隐式 section、`\n`.join(blocks) 结尾无换行。
 */
object MarkdownToHtml {

    // ── 时间类标签（值会用强调色渲染） ──
    val TIME_LABELS = setOf(
        "日期", "时间", "发布日期", "报告时间", "截止时间",
        "活动时间", "演出时间", "开票时间", "开始时间", "结束时间",
    )

    // ── 标准元信息标签（key: value 模式会被渲染为样式化行） ──
    val META_LABELS = setOf(
        "日期", "时间", "地点", "票价", "发布日期", "报告时间",
        "报告地点", "报告人", "来源公众号", "作者", "链接",
        "摘要", "报告摘要", "截止时间", "活动时间", "开始时间",
        "结束时间", "主办方", "报名方式", "联系方式", "备注",
    )

    private val LABEL_VALUE_RE = Regex("^([^:：]{1,16})[:：]\\s*(.+)$")
    private val BOLD_RE = Regex("\\*\\*(.+?)\\*\\*")
    private val EM_RE = Regex("(?<!\\*)\\*(?!\\*)(.+?)(?<!\\*)\\*(?!\\*)")
    private val INLINE_CODE_RE = Regex("`([^`]+)`")
    private val LINK_RE = Regex("\\[([^\\]]+)\\]\\(([^)]+)\\)")
    private val TABLE_SEPARATOR_RE =
        Regex("^\\|?\\s*:?-{3,}:?\\s*(?:\\|\\s*:?-{3,}:?\\s*)+\\|?\\s*$")
    private val TABLE_SPLIT_RE = Regex("(?<!\\\\)\\|")
    private val ORDERED_ITEM_RE = Regex("^(\\d+)\\.\\s+(.+)")
    private val BULLET_RE = Regex("^[-*]\\s+\\S")
    private val BULLET_ITEM_RE = Regex("^[-*]\\s+(.+)")
    private val HR_RE = Regex("^[-*_]{3,}\\s*$")
    private val IMAGE_RE = Regex("!\\[([^\\]]*)\\]\\(([^)]+)\\)")
    private val HX_STRIP_RE = Regex("^#+\\s*")
    private val HTTPS_RE = Regex("^https?://")
    private val PARA_COLOR_RE = Regex("color:(#[0-9a-fA-F]{6})")
    private val BORDER_COLOR_RE = Regex("border:1px\\s+solid\\s+(#[0-9a-fA-F]{6})")
    private val CODE_BG_RE = Regex("background:(#[0-9a-fA-F]{6})")

    private const val DEFAULT_STRONG = "color:#1a344c;font-weight:700;"
    private const val DEFAULT_EM = "color:#5c7d99;font-style:italic;"
    private const val DEFAULT_LINK = "color:#2f6f9f;text-decoration:underline;word-break:break-all;"
    private const val DEFAULT_PARA_COLOR = "#3a4a5c"
    private const val DEFAULT_BORDER_COLOR = "#c8ddf0"
    private const val DEFAULT_CODE_BG = "#d8ecf8"

    // ── 基础工具 ──

    /** 拆分 '标签: 值' 格式的文本。 */
    fun splitLabelValue(text: String): Pair<String, String> {
        val m = LABEL_VALUE_RE.find(text)?.takeIf { it.range.first == 0 } ?: return "" to text
        return m.groupValues[1].trim() to m.groupValues[2].trim()
    }

    /** 去除 Markdown 强调标记，返回纯文本。 */
    fun stripMarkdownEmphasis(text: String): String {
        var result = BOLD_RE.replace(text, "$1")
        result = EM_RE.replace(result, "$1")
        return result
    }

    /** 从 Markdown 图片语法提取 alt 文本。 */
    fun extractAltText(text: String): String {
        val m = IMAGE_RE.find(text)?.takeIf { it.range.first == 0 } ?: return ""
        return m.groupValues[1].trim()
    }

    /** 解析图片路径，优先使用本地文件。 */
    fun resolveImageSrc(src: String, markdownPath: String = ""): String {
        val cleaned = src.trim().trim('<', '>').trim('"').trim('\'')
        if (cleaned.isEmpty() || ImagePaths.isRemoteOrDataImage(cleaned)) return cleaned

        val markdownDir = if (markdownPath.isNotEmpty()) {
            File(markdownPath).parentFile ?: File(System.getProperty("user.dir") ?: ".")
        } else {
            File(System.getProperty("user.dir") ?: ".")
        }
        val resolved = ImagePaths.resolveExistingImagePath(cleaned, baseDir = markdownDir)
        val result = if (resolved != null) {
            resolved.path
        } else {
            // os.path.normpath(os.path.join(...)) → 组件归一化
            File(markdownDir, ImagePaths.cleanMarkdownImageTarget(cleaned))
                .toPath().normalize().toString()
        }
        return result.replace("\\", "/")
    }

    /** 从模板的 para_style 中提取文字颜色。 */
    fun extractParaColor(tpl: Template): String =
        PARA_COLOR_RE.find(tpl.paraStyle)?.groupValues?.get(1) ?: DEFAULT_PARA_COLOR

    /** 从模板的 card_style 中提取边框颜色。 */
    fun extractBorderColor(tpl: Template): String =
        BORDER_COLOR_RE.find(tpl.cardStyle)?.groupValues?.get(1) ?: DEFAULT_BORDER_COLOR

    /** 将行内 Markdown 格式转换为 HTML。 */
    fun renderInlineMarkdown(text: String, tpl: Template? = null): String {
        var result = Html.escape(text, quote = false)

        // 使用模板样式或默认值
        val strongS = tpl?.strongStyle ?: DEFAULT_STRONG
        val emS = tpl?.emStyle ?: DEFAULT_EM
        val linkS = tpl?.linkStyle ?: DEFAULT_LINK

        // 行内代码背景色从模板提取或默认
        var codeBg = DEFAULT_CODE_BG
        if (tpl != null) {
            val m = CODE_BG_RE.find(tpl.thStyle)
            if (m != null) codeBg = m.groupValues[1]
        }

        // 粗体 **text**
        result = BOLD_RE.replace(result) { m ->
            "<strong style=\"$strongS\">${m.groupValues[1]}</strong>"
        }
        // 斜体 *text*
        result = EM_RE.replace(result) { m ->
            "<em style=\"$emS\">${m.groupValues[1]}</em>"
        }
        // 行内代码 `code`
        result = INLINE_CODE_RE.replace(result) { m ->
            "<code style=\"background:$codeBg;padding:1px 5px;" +
                "border-radius:3px;font-size:0.9em;\">${m.groupValues[1]}</code>"
        }
        // 链接 [text](url) —— 注意 URL 会被二次转义（先 quote=False 后 quote=True）
        result = LINK_RE.replace(result) { m ->
            "<a href=\"${Html.escape(m.groupValues[2], quote = true)}\" " +
                "style=\"$linkS\">${m.groupValues[1]}</a>"
        }

        return result
    }

    // ── 表格解析 ──

    fun isTableRow(text: String): Boolean {
        val stripped = text.trim()
        return stripped.startsWith("|") && stripped.count { it == '|' } >= 2
    }

    fun isTableSeparator(text: String): Boolean =
        TABLE_SEPARATOR_RE.matches(text.trim())

    fun splitTableRow(text: String): List<String> {
        val stripped = text.trim().trim('|')
        return TABLE_SPLIT_RE.split(stripped).map { cell ->
            cell.replace("\\|", "|").trim()
        }
    }

    /** 消费从 startIndex 开始的表格行，返回 (rows, next_index)。 */
    fun consumeTable(lines: List<String>, startIndex: Int): Pair<List<String>, Int> {
        val tableLines = mutableListOf<String>()
        var index = startIndex

        // 第一行必须是表格行（保留原文，Python 同）
        if (index < lines.size && isTableRow(lines[index])) {
            tableLines.add(lines[index])
            index += 1
        } else {
            return emptyList<String>() to startIndex
        }

        // 跳过空行
        while (index < lines.size && lines[index].trim().isEmpty()) {
            index += 1
        }

        // 分隔行
        if (index < lines.size && isTableSeparator(lines[index])) {
            tableLines.add(lines[index])
            index += 1
        } else {
            return emptyList<String>() to startIndex
        }

        // 剩余行
        while (index < lines.size) {
            val stripped = lines[index].trim()
            if (stripped.isEmpty()) {
                index += 1
                continue
            }
            if (isTableRow(stripped)) {
                tableLines.add(stripped)
                index += 1
            } else {
                break
            }
        }

        return tableLines.toList() to index
    }

    // ── 有序列表解析 ──

    fun isOrderedListItem(text: String): Boolean =
        Regex("^\\d+\\.\\s+\\S").matchAtStart(text.trim())

    // ── 主转换函数 ──

    /**
     * 将 Markdown 文本转换为排版精美的内联 HTML。
     *
     * @param template 模板名称 ("generic" | "wanyou" | "red") 或 Template 实例。
     * @param title 页面标题（覆盖 Markdown 中的 H1）。
     * @param markdownPath Markdown 文件路径，用于解析相对路径图片。
     */
    fun markdownToHtml(
        markdownText: String?,
        template: Template = TemplateRegistry.getTemplate("generic"),
        title: String = "",
        subtitle: String = "",
        markdownPath: String = "",
    ): String {
        val tpl = template

        val blocks = mutableListOf("<section style=\"${tpl.pageStyle}\">")
        var sectionOpen = false
        var cardOpen = false
        var inCodeBlock = false
        val codeLines = mutableListOf<String>()
        // in_ordered_list 仅记录状态，不影响输出（Python 同）
        var inOrderedList = false

        fun closeCard() {
            if (cardOpen) {
                blocks.add(tpl.renderCardEnd())
                cardOpen = false
            }
        }

        fun closeSection() {
            closeCard()
            if (sectionOpen) {
                blocks.add(tpl.renderSectionEnd())
                sectionOpen = false
            }
        }

        // ── 确定标题 ──
        var heroTitle = title
        val heroSubtitle = subtitle
        var contentStart = 0

        val lines = (markdownText ?: "").lines()

        // 如果未指定标题，从第一个 H1 提取（其前的行会被跳过）
        if (heroTitle.isEmpty()) {
            for (i in lines.indices) {
                val stripped = lines[i].trim()
                if (stripped.startsWith("# ") && !stripped.startsWith("## ")) {
                    heroTitle = stripped.substring(2).trim()
                    contentStart = i + 1
                    break
                }
            }
        }

        // 渲染 Hero 区（标题不转义，Python 同）
        blocks.add(tpl.renderHeader(heroTitle, heroSubtitle))

        // ── 逐行解析 ──
        var index = contentStart
        while (index < lines.size) {
            val rawLine = lines[index]
            val stripped = rawLine.trim()

            // ── 代码块 ──
            if (stripped.startsWith("```")) {
                if (inCodeBlock) {
                    // 结束代码块
                    val codeText = codeLines.joinToString("\n")
                    blocks.add(tpl.renderCodeBlock(Html.escape(codeText)))
                    codeLines.clear()
                    inCodeBlock = false
                } else {
                    // 开始代码块
                    closeCard()
                    inCodeBlock = true
                }
                index += 1
                continue
            }

            if (inCodeBlock) {
                codeLines.add(rawLine)
                index += 1
                continue
            }

            // ── 空行 ──
            if (stripped.isEmpty()) {
                if (inOrderedList) inOrderedList = false
                index += 1
                continue
            }

            // ── H1 (第二个及以后的 H1 作为 section) ──
            if (stripped.startsWith("# ") && !stripped.startsWith("## ")) {
                closeSection()
                val h1Title = stripped.substring(2).trim()
                blocks.add(
                    "<section style=\"${tpl.sectionStyle}\">" +
                        "<h2 style=\"${tpl.sectionTitleStyle}\">${Html.escape(h1Title)}</h2>"
                )
                sectionOpen = true
                index += 1
                continue
            }

            // ── H2 → Section ──
            if (stripped.startsWith("## ") && !stripped.startsWith("### ")) {
                closeSection()
                val h2Title = stripped.substring(3).trim()
                blocks.add(tpl.renderSectionStart(Html.escape(h2Title)))
                sectionOpen = true
                index += 1
                continue
            }

            // ── H3 → Card ──
            if (stripped.startsWith("### ") && !stripped.startsWith("#### ")) {
                if (!sectionOpen) {
                    // 隐式 section
                    blocks.add(tpl.renderSectionStart(""))
                    sectionOpen = true
                }
                closeCard()
                val h3Title = stripped.substring(4).trim()
                blocks.add(tpl.renderCardStart(Html.escape(h3Title)))
                cardOpen = true
                index += 1
                continue
            }

            // ── H4 → 子标题 ──
            if (stripped.startsWith("#### ")) {
                val h4Title = stripped.substring(5).trim()
                if (!cardOpen && !sectionOpen) {
                    blocks.add(tpl.renderSectionStart(""))
                    sectionOpen = true
                }
                blocks.add(tpl.renderH4(Html.escape(h4Title)))
                index += 1
                continue
            }

            // ── H5/H6 → 更小子标题（样式拼接怪癖，逐字节保留） ──
            if (stripped.startsWith("##### ") || stripped.startsWith("###### ")) {
                val hxTitle = HX_STRIP_RE.replace(stripped, "").trim()
                blocks.add(
                    "<p style=\"${tpl.paraStyle}text-indent:0;font-weight:600;" +
                        "${tpl.strongStyle.replace("font-weight:700;", "").trim().trimEnd(';')};" +
                        "font-size:15px;\">" +
                        "${Html.escape(hxTitle)}</p>"
                )
                index += 1
                continue
            }

            // ── 水平分隔线 ──
            if (HR_RE.matches(stripped)) {
                val hrColor = extractBorderColor(tpl)
                blocks.add(
                    "<hr style=\"margin:16px 0;border:none;" +
                        "border-top:1px solid $hrColor;\" />"
                )
                index += 1
                continue
            }

            // ── 图片 ![]() ──
            val imageMatch = IMAGE_RE.find(stripped)?.takeIf { it.range.first == 0 }
            if (imageMatch != null) {
                val alt = imageMatch.groupValues[1].trim()
                val src = resolveImageSrc(imageMatch.groupValues[2], markdownPath)
                val escapedSrc = Html.escape(src, quote = true)
                blocks.add(
                    "<img src=\"$escapedSrc\" " +
                        "alt=\"${Html.escape(alt.ifEmpty { "配图" })}\" " +
                        "style=\"${tpl.imageStyle}\" />"
                )
                index += 1
                continue
            }

            // ── 表格 ──
            if (isTableRow(stripped)) {
                val (tableRows, nextIndex) = consumeTable(lines, index)
                if (tableRows.size >= 2) {
                    val parsed = tableRows
                        .filterNot { isTableSeparator(it) }
                        .map { splitTableRow(it).toMutableList() }
                        .toMutableList()
                    if (parsed.isNotEmpty()) {
                        val maxCols = parsed.maxOf { it.size }
                        for (row in parsed) {
                            row.addAll(List(maxCols - row.size) { "" })
                        }
                        val headers = parsed[0].map { Html.escape(it) }
                        val body = parsed.drop(1).map { row -> row.map { Html.escape(it) } }
                        blocks.add(tpl.renderTable(headers, body))
                        index = nextIndex
                        continue
                    }
                }
                // 不是有效表格，按段落处理（消费一行）
                index += 1
                continue
            }

            // ── 引用块 > ──
            if (stripped.startsWith("> ")) {
                val quoteText = stripped.substring(2).trim()
                // 收集连续引用行
                val quoteLines = mutableListOf(quoteText)
                index += 1
                while (index < lines.size && lines[index].trim().startsWith("> ")) {
                    quoteLines.add(lines[index].trim().substring(2).trim())
                    index += 1
                }
                val combined = quoteLines.joinToString("<br>") { renderInlineMarkdown(it, tpl) }
                blocks.add("<blockquote style=\"${tpl.quoteStyle}\">$combined</blockquote>")
                continue
            }

            // ── 有序列表 1. ──
            if (isOrderedListItem(stripped)) {
                inOrderedList = true
                val itemMatch = ORDERED_ITEM_RE.find(stripped)?.takeIf { it.range.first == 0 }
                if (itemMatch != null) {
                    // Python int() 会去掉前导零；此处按数字字符串归一化（超长溢出按 0 渲染）
                    val numberText = itemMatch.groupValues[1].trimStart('0').ifEmpty { "0" }
                    val number = numberText.toIntOrNull() ?: 0
                    val itemText = itemMatch.groupValues[2]
                    blocks.add(
                        tpl.renderOrderedItem(number, renderInlineMarkdown(itemText, tpl))
                    )
                }
                index += 1
                continue
            }

            // ── 无序列表 - / * ──
            if (BULLET_RE.matchAtStart(stripped)) {
                val itemMatch = BULLET_ITEM_RE.find(stripped)?.takeIf { it.range.first == 0 }
                if (itemMatch != null) {
                    val itemText = itemMatch.groupValues[1]
                    blocks.add(tpl.renderBullet(renderInlineMarkdown(itemText, tpl)))
                }
                index += 1
                continue
            }

            // ── key: value 元信息 ──
            val (label, value) = splitLabelValue(stripped)
            if (label in META_LABELS) {
                val isTime = label in TIME_LABELS
                val escapedLabel = Html.escape(label)
                val escapedValue = if (label == "链接" && HTTPS_RE.matchAtStart(value)) {
                    "<a href=\"${Html.escape(value, quote = true)}\" " +
                        "style=\"color:#2f6f9f;text-decoration:underline;" +
                        "word-break:break-all;\">${Html.escape(value)}</a>"
                } else {
                    val valueColor = if (isTime) tpl.metaTimeValueStyle
                    else "color:${extractParaColor(tpl)};"
                    "<span style=\"$valueColor\">" +
                        "${renderInlineMarkdown(value, tpl)}</span>"
                }
                blocks.add(
                    "<p style=\"${tpl.metaRowStyle}\">" +
                        "<span style=\"${tpl.metaLabelStyle}\">$escapedLabel</span>" +
                        "$escapedValue</p>"
                )
                index += 1
                continue
            }

            // ── 原始 HTML ──
            if (stripped.startsWith("@html ")) {
                val rawHtml = stripped.substring(6).trim()
                blocks.add(rawHtml)
                index += 1
                continue
            }

            // ── 普通段落 ──
            if (!cardOpen && !sectionOpen) {
                // 没有 section 时创建隐式 section
                blocks.add(tpl.renderSectionStart(""))
                sectionOpen = true
            }

            blocks.add(
                "<p style=\"${tpl.paraStyle}\">" +
                    "${renderInlineMarkdown(stripped, tpl)}</p>"
            )
            index += 1
        }

        // ── 收尾 ──
        closeSection()

        // Footer
        blocks.add(tpl.renderFooter())

        // 关闭页面
        blocks.add("</section>")

        return blocks.joinToString("\n")
    }

    /** 与 markdownToHtml 相同，为兼容 Wanyou 命名的别名。 */
    fun markdownToWechatHtml(
        markdownText: String?,
        template: Template = TemplateRegistry.getTemplate("generic"),
        title: String = "",
        subtitle: String = "",
        markdownPath: String = "",
    ): String = markdownToHtml(markdownText, template, title, subtitle, markdownPath)
}
