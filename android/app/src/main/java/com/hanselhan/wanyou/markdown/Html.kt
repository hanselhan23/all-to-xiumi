package com.hanselhan.wanyou.markdown

/**
 * HTML 转义工具，行为与 Python `html.escape` / `html.unescape` 对齐。
 *
 * Python 版在渲染行内 Markdown 时用 quote=False（只转 & < >），
 * 代码块 / 表格单元格用 quote=True（额外转 " '）——移植必须逐字节一致。
 */
object Html {

    /** 与 Python `html.escape(text, quote=True)` 默认值一致。 */
    fun escape(text: String, quote: Boolean = true): String {
        val sb = StringBuilder(text.length + 16)
        for (ch in text) {
            when (ch) {
                '&' -> sb.append("&amp;")
                '<' -> sb.append("&lt;")
                '>' -> sb.append("&gt;")
                '"' -> if (quote) sb.append("&quot;") else sb.append(ch)
                '\'' -> if (quote) sb.append("&#x27;") else sb.append(ch)
                else -> sb.append(ch)
            }
        }
        return sb.toString()
    }

    /**
     * 最小 unescape，覆盖 HTML 常见命名实体与数字实体。
     * （Python `html.unescape` 支持全量实体表；图片路径场景只需常见子集。）
     */
    fun unescape(text: String): String {
        return NAMED_RE.replace(text) { m ->
            when (m.value.lowercase()) {
                "&amp;" -> "&"
                "&lt;" -> "<"
                "&gt;" -> ">"
                "&quot;" -> "\""
                "&apos;", "&#39;" -> "'"
                "&nbsp;" -> " "
                else -> {
                    val digits = NUM_RE.find(m.value)?.groupValues?.get(1) ?: return@replace m.value
                    val code = if (m.value.startsWith("&#x", ignoreCase = true) || m.value.startsWith("&#X"))
                        digits.toIntOrNull(16) else digits.toIntOrNull(10)
                    if (code != null && code in 0..0x10FFFF) String(Character.toChars(code)) else m.value
                }
            }
        }
    }

    private val NAMED_RE = Regex("&(?:amp|lt|gt|quot|apos|nbsp);|&#(?:x?[0-9a-fA-F]+);")
    private val NUM_RE = Regex("^&#x?([0-9a-fA-F]+);$", RegexOption.IGNORE_CASE)
}

/** `re.match` 语义（仅锚定字符串开头）。 */
internal fun Regex.matchAtStart(input: String): Boolean =
    find(input)?.range?.first == 0
