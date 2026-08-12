package com.hanselhan.wanyou.publish

import com.hanselhan.wanyou.markdown.ImagePaths
import com.hanselhan.wanyou.markdown.matchAtStart
import java.io.File
import java.util.Base64

/**
 * 秀米发布前的纯 HTML 预处理 —— `all_to_xiumi/xiumi_publish.py` 纯函数部分的移植。
 *
 * 不含任何浏览器/WebView 依赖，可用 JVM 单元测试逐字节比对
 * （golden/pure_vectors.json 的 xiumi_pure 向量）。
 */
object HtmlPrepare {

    // ── 基础工具 ──

    fun extractMainHtml(htmlText: String?): String {
        val text = htmlText ?: ""
        val main = Regex(
            "<main[^>]*class=[\"'][^\"']*page[^\"']*[\"'][^>]*>([\\s\\S]*?)</main>",
            RegexOption.IGNORE_CASE
        ).find(text)
        if (main != null) return main.groupValues[1].trim()
        val body = Regex("<body[^>]*>([\\s\\S]*?)</body>", RegexOption.IGNORE_CASE).find(text)
        if (body != null) return body.groupValues[1].trim()
        return text.trim()
    }

    fun guessMimeType(path: File): String {
        val ext = path.extension.lowercase()
        val known = mapOf(
            "png" to "image/png", "jpg" to "image/jpeg", "jpeg" to "image/jpeg",
            "gif" to "image/gif", "webp" to "image/webp", "bmp" to "image/bmp",
            "svg" to "image/svg+xml", "ico" to "image/x-icon", "tif" to "image/tiff",
            "tiff" to "image/tiff",
        )
        if (ext in known) return known.getValue(ext)
        return try {
            java.net.URLConnection.guessContentTypeFromName(path.name)
                ?: "application/octet-stream"
        } catch (e: Exception) {
            "application/octet-stream"
        }
    }

    /** 对应 `mimetypes.guess_extension` 的常用子集。 */
    fun guessExtension(mimeType: String): String {
        val mime = mimeType.trim().lowercase()
        val known = mapOf(
            "image/png" to ".png", "image/jpeg" to ".jpg", "image/jpg" to ".jpg",
            "image/gif" to ".gif", "image/webp" to ".webp", "image/bmp" to ".bmp",
            "image/svg+xml" to ".svg", "image/tiff" to ".tiff", "image/x-icon" to ".ico",
        )
        return known[mime] ?: ".png"
    }

    fun imageFileToDataUrl(path: File): String {
        val mimeType = guessMimeType(path)
        val data = Base64.getEncoder().encodeToString(path.readBytes())
        return "data:$mimeType;base64,$data"
    }

    // ── 秀米 base 格式归一化（h1 18px / p 14px，见 format.md） ──

    fun applyXiumiBaseFormat(htmlText: String?): String {
        var html = Regex("<h1\\b([^>]*?)style=\"([^\"]*)\"([^>]*)>").replace(htmlText ?: "") { m ->
            val beforeAttrs = m.groupValues[1]
            val style = Regex("font-size:\\s*\\d+px").replace(m.groupValues[2], "font-size:18px")
            val afterAttrs = m.groupValues[3]
            "<h1${beforeAttrs}style=\"$style\"$afterAttrs>"
        }
        html = Regex("<p\\b([^>]*?)style=\"([^\"]*)\"([^>]*)>").replace(html) { m ->
            val beforeAttrs = m.groupValues[1]
            val afterAttrs = m.groupValues[3]

            // 拆成单条 CSS 声明逐条处理
            val rawDecls = m.groupValues[2].split(";").map { it.trim() }.filter { it.isNotEmpty() }
            val newDecls = mutableListOf<String>()
            var marginTop: String? = null
            var marginBottom: String? = null
            var seenFontSize = false
            var seenLineHeight = false
            var seenLetterSpacing = false

            for (decl in rawDecls) {
                if (':' !in decl) {
                    newDecls.add(decl)
                    continue
                }
                val idx = decl.indexOf(':')
                val name = decl.substring(0, idx).trim()
                var value = decl.substring(idx + 1).trim()

                when (name) {
                    "font-size" -> {
                        value = "14px"
                        seenFontSize = true
                    }
                    "line-height" -> {
                        value = "1.6"
                        seenLineHeight = true
                    }
                    "letter-spacing" -> {
                        value = "0px"
                        seenLetterSpacing = true
                    }
                    "margin-left" -> value = "0px"
                    "margin-right" -> value = "0px"
                    "margin" -> {
                        val parts = value.split(Regex("\\s+"))
                        when (parts.size) {
                            1 -> {
                                marginTop = parts[0]
                                marginBottom = parts[0]
                            }
                            2 -> {
                                marginTop = parts[0]
                                marginBottom = parts[0]
                            }
                            3 -> {
                                marginTop = parts[0]
                                marginBottom = parts[2]
                            }
                            else -> {
                                marginTop = parts[0]
                                marginBottom = parts[2]
                            }
                        }
                        // 拆解 shorthand 为 longhand，强制 margin-left/right = 0 的同时保留上下边距
                        continue
                    }
                }

                newDecls.add("$name:$value")
            }

            // 总是补全 base 格式的段落属性
            if (!seenFontSize) newDecls.add("font-size:14px")
            if (!seenLineHeight) newDecls.add("line-height:1.6")
            if (!seenLetterSpacing) newDecls.add("letter-spacing:0px")
            if (marginTop != null) {
                newDecls.add("margin-top:$marginTop")
                newDecls.add("margin-bottom:${marginBottom ?: marginTop}")
            }
            newDecls.add("margin-left:0px")
            newDecls.add("margin-right:0px")

            "<p${beforeAttrs}style=\"${newDecls.joinToString(";")}\"$afterAttrs>"
        }
        return html
    }

    /**
     * 把大字号段落提升为 h1/h2/h3，让秀米保留标题层级。
     * （秀米粘贴会剥掉行内 font-size，但 h1/h2/h3 会映射为语义字号。）
     */
    fun promoteHeadingsForXiumi(htmlText: String?): String {
        return Regex(
            "<p\\b([^>]*?)style=\"([^\"]*)\"([^>]*)>([\\s\\S]*?)</p>",
            RegexOption.IGNORE_CASE
        ).replace(htmlText ?: "") { m ->
            val style = m.groupValues[2]
            val content = m.groupValues[4]
            val sizeM = Regex("font-size:\\s*(\\d+)px").find(style)
            val size = sizeM?.groupValues?.get(1)?.toIntOrNull() ?: 0
            val align = Regex("text-align:\\s*(center|left|right)").find(style)?.groupValues?.get(1)
            val bold = Regex("font-weight:\\s*(700|800|bold)").find(style) != null

            val tag = when {
                size >= 34 -> "h1"
                size >= 20 -> "h2"
                size >= 17 && bold -> "h3"
                else -> return@replace m.value
            }
            val decls = mutableListOf<String>()
            if (align != null) decls.add("text-align:$align")
            if (tag == "h1" || tag == "h2") decls.add("letter-spacing:2px")
            val newStyle = decls.joinToString(";")
            "<$tag style=\"$newStyle\"${m.groupValues[3]}>$content</$tag>"
        }
    }

    // ── CSS / 块解析 ──

    /** 秀米模型样式为 camelCase CSS（跳过 box-sizing）。 */
    fun camelizeCss(cssText: String?): Map<String, String> {
        val out = LinkedHashMap<String, String>()
        for (declRaw in (cssText ?: "").split(";")) {
            val decl = declRaw.trim()
            if (decl.isEmpty() || ':' !in decl) continue
            val idx = decl.indexOf(':')
            val prop = decl.substring(0, idx).trim().lowercase()
            val value = decl.substring(idx + 1).trim()
            if (prop.isEmpty() || value.isEmpty() || prop == "box-sizing") continue
            val parts = prop.split("-")
            val camel = parts[0] + parts.drop(1).joinToString("") {
                it.replaceFirstChar { c -> c.uppercase() }
            }
            out[camel] = value
        }
        return out
    }

    /**
     * 把嵌套 section/div 转成 <p>（保留其 style），只留 p/span/br/strong 与文本。
     * 浏览器 HTML 解析器会自行闭合嵌套的 <p>；产生的空 <p></p> 会被清掉。
     */
    fun flattenInnerHtml(inner: String?): String {
        var html = Regex("<!--[\\s\\S]*?-->").replace(inner ?: "", "")
        html = Regex("<section\\b([^>]*)>", RegexOption.IGNORE_CASE).replace(html) { m ->
            val attrs = m.groupValues[1].trim()
            "<p${if (attrs.isNotEmpty()) " $attrs" else ""}>"
        }
        html = Regex("</section>", RegexOption.IGNORE_CASE).replace(html, "</p>")
        html = Regex("<div\\b([^>]*)>", RegexOption.IGNORE_CASE).replace(html) { m ->
            val attrs = m.groupValues[1].trim()
            "<p${if (attrs.isNotEmpty()) " $attrs" else ""}>"
        }
        html = Regex("</div>", RegexOption.IGNORE_CASE).replace(html, "</p>")
        html = Regex("\\s+").replace(html, " ")
        html = Regex("<p>\\s*</p>").replace(html, "")
        return html.trim()
    }

    /** 设计稿 HTML 块：每个顶层 <section> 对应一个 {style, text} 块。 */
    data class Block(val style: Map<String, String>, val text: String)

    fun htmlToBlocks(htmlText: String?): List<Block> {
        val m = Regex(
            "<main[^>]*class=[\"']page[\"'][^>]*>([\\s\\S]*?)</main>",
            RegexOption.IGNORE_CASE
        ).find(htmlText ?: "")
        val frag = m?.groupValues?.get(1) ?: (htmlText ?: "")

        val tagRe = Regex("<(/?)section\\b[^>]*>", RegexOption.IGNORE_CASE)
        var depth = 0
        var curStart: Int? = null
        var curAttrs = ""
        val blocks = mutableListOf<Block>()
        for (tm in tagRe.findAll(frag)) {
            if (tm.groupValues[1].isEmpty()) { // opening
                if (depth == 0) {
                    curStart = tm.range.last + 1
                    val attrsM = Regex("style=[\"']([^\"']*)[\"']", RegexOption.IGNORE_CASE).find(tm.value)
                    curAttrs = attrsM?.groupValues?.get(1) ?: ""
                }
                depth += 1
            } else { // closing
                depth -= 1
                if (depth == 0 && curStart != null) {
                    val inner = frag.substring(curStart, tm.range.first)
                    val text = flattenInnerHtml(inner).ifEmpty { "<p><br></p>" }
                    blocks.add(Block(camelizeCss(curAttrs), text))
                    curStart = null
                }
            }
        }
        return blocks
    }

    // ── 标题 / 摘要提取 ──

    fun firstHeading(markdownText: String?): String {
        for (line in (markdownText ?: "").lines()) {
            val stripped = line.trim()
            if (stripped.startsWith("# ")) return stripped.substring(2).trim()
        }
        return ""
    }

    fun firstSummaryLine(markdownText: String?): String {
        for (line in (markdownText ?: "").lines()) {
            val stripped = line.trim()
            if (stripped.isEmpty()) continue
            if (stripped.startsWith("#")) continue
            if (stripped.startsWith("!")) continue
            val collapsed = Regex("\\s+").replace(stripped, " ")
            return collapsed.take(120)
        }
        return ""
    }

    // ── 图片识别 / 统计 ──

    fun isRemoteImageSrc(src: String?): Boolean =
        Regex("^(?:https?:)?//", RegexOption.IGNORE_CASE).matchAtStart(src ?: "")

    fun isDataImageSrc(src: String?): Boolean = (src ?: "").startsWith("data:")

    data class ImagePayloadStats(
        val htmlChars: Int,
        val imageCount: Int,
        val dataImageCount: Int,
        val localImageCount: Int,
        val dataImageChars: Int,
    )

    private val IMG_SRC_RE =
        Regex("<img\\b[^>]*\\bsrc=(['\"])(.*?)\\1", RegexOption.IGNORE_CASE)

    fun imagePayloadStats(htmlText: String?): ImagePayloadStats {
        val srcs = IMG_SRC_RE.findAll(htmlText ?: "").map { it.groupValues[2] }.toList()
        val dataUrls = srcs.filter { isDataImageSrc(it) }
        val localUrls = srcs.filter {
            it.isNotEmpty() && !isDataImageSrc(it) && !isRemoteImageSrc(it)
        }
        return ImagePayloadStats(
            htmlChars = (htmlText ?: "").length,
            imageCount = srcs.size,
            dataImageCount = dataUrls.size,
            localImageCount = localUrls.size,
            dataImageChars = dataUrls.sumOf { it.length },
        )
    }

    fun localImageSources(htmlText: String?): List<String> =
        IMG_SRC_RE.findAll(htmlText ?: "")
            .map { it.groupValues[2] }
            .filter { it.isNotEmpty() && !isDataImageSrc(it) && !isRemoteImageSrc(it) }
            .toList()

    // ── 图片删除 / 占位符 ──

    fun removeImagesForXiumi(htmlText: String?): String {
        var removed = 0
        var cleaned = Regex("<img\\b[^>]*>", RegexOption.IGNORE_CASE).replace(htmlText ?: "") {
            removed += 1
            "<p style=\"margin:8px 0;color:#8a7c58;font-size:14px;\">[配图已保留在本地 HTML，秀米草稿中未自动内联]</p>"
        }
        cleaned = Regex(
            "<section\\b([^>]*)>\\s*(?:<p[^>]*>\\[配图已保留在本地 HTML，秀米草稿中未自动内联\\]</p>\\s*)+</section>",
            RegexOption.IGNORE_CASE
        ).replace(cleaned, "")
        return cleaned
    }

    fun removeUnuploadedImagesForXiumi(htmlText: String?): String {
        var removed = 0
        val cleaned = Regex("<img\\b[^>]*>", RegexOption.IGNORE_CASE).replace(htmlText ?: "") { m ->
            val tag = m.value
            val srcM = Regex("\\bsrc=(['\"])(.*?)\\1", RegexOption.IGNORE_CASE).find(tag)
            val src = (srcM?.groupValues?.get(2) ?: "").trim()
            if (src.isNotEmpty() && isRemoteImageSrc(src)) {
                tag
            } else {
                removed += 1
                "<p style=\"margin:8px 0;color:#8a7c58;font-size:14px;\">[配图上传未完成，请在秀米图库中手动补充]</p>"
            }
        }
        return cleaned
    }

    fun replaceImagesWithPlaceholdersForXiumi(htmlText: String?, mode: String = "upload"): String {
        if (mode.trim().lowercase() != "upload") return htmlText ?: ""

        var index = 0
        return Regex("<img\\b[^>]*>", RegexOption.IGNORE_CASE).replace(htmlText ?: "") {
            index += 1
            "<p " +
                "data-wanyou-image-placeholder=\"$index\" " +
                "style=\"margin:8px 0;color:#8a7c58;font-size:14px;\">" +
                "[配图上传中]" +
                "</p>"
        }
    }

    // ── 图片内联 / 模式分发 ──

    fun inlineLocalImages(htmlText: String?, baseDir: File): String {
        return Regex("src=(['\"])(.*?)\\1", RegexOption.IGNORE_CASE).replace(htmlText ?: "") { m ->
            val quote = m.groupValues[1]
            val src = m.groupValues[2].trim()
            if (src.isEmpty() || isRemoteImageSrc(src) || isDataImageSrc(src)) return@replace m.value
            val cleaned = src.split("?", limit = 2)[0].trim().trim('\'').trim('"')
            var candidate = File(cleaned)
            if (!candidate.isAbsolute) candidate = File(baseDir, cleaned).canonicalFile
            if (!candidate.exists()) return@replace m.value
            val dataUrl = imageFileToDataUrl(candidate)
            "src=$quote$dataUrl$quote"
        }
    }

    /**
     * 图片处理模式分发（upload / auto / inline / omit）。
     * 注：Python 版 base 为 HTML 文件路径（取其父目录）；Android 侧直接传目录。
     */
    fun prepareXiumiImages(
        htmlText: String?,
        baseDir: File,
        mode: String = "upload",
        maxInlineChars: Int = 900000,
    ): String {
        var resolvedMode = mode.trim().lowercase()
        if (resolvedMode !in setOf("upload", "auto", "inline", "omit")) resolvedMode = "upload"

        if (resolvedMode == "omit") return removeImagesForXiumi(htmlText)
        if (resolvedMode == "upload") return htmlText ?: ""

        val inlined = inlineLocalImages(htmlText, baseDir)
        val after = imagePayloadStats(inlined)
        if (resolvedMode == "auto" && maxInlineChars > 0 && after.htmlChars > maxInlineChars) {
            return removeImagesForXiumi(htmlText)
        }
        return inlined
    }

    // ── data URL → 临时文件 / 上传路径解析 ──

    fun dataUrlToTempImage(src: String?, tempDir: File, index: Int): File? {
        val m = Regex(
            "^data:([^;,]+);base64,(.+)$",
            setOf(RegexOption.IGNORE_CASE, RegexOption.DOT_MATCHES_ALL)
        ).find(src ?: "")
            ?: return null
        val mimeType = m.groupValues[1].trim().lowercase()
        val ext = guessExtension(mimeType).let { if (it == ".jpe") ".jpg" else it }
        val data = try {
            // Python b64decode(validate=False) 忽略字母表外字符；MIME 解码器语义最接近
            Base64.getMimeDecoder().decode(m.groupValues[2])
        } catch (e: Exception) {
            return null
        }
        val path = File(tempDir, String.format("xiumi_inline_%04d%s", index, ext))
        path.writeBytes(data)
        return path
    }

    fun resolveUploadImagePath(
        src: String,
        baseDir: File,
        tempDir: File,
        index: Int,
        extraRoots: List<File> = emptyList(),
    ): File? {
        if (isDataImageSrc(src)) return dataUrlToTempImage(src, tempDir, index)
        if (src.isEmpty() || isRemoteImageSrc(src)) return null
        val resolved = ImagePaths.resolveExistingImagePath(src, baseDir = baseDir, extraRoots = extraRoots)
        if (resolved != null) return resolved
        val cleaned = ImagePaths.cleanMarkdownImageTarget(src)
        var path = File(cleaned)
        if (!path.isAbsolute) path = File(baseDir, cleaned).canonicalFile
        return if (path.exists()) path else null
    }

    // ── 上传条目 ──

    data class UploadEntry(
        val index: Int,
        val source: String,
        val path: File,
        val isData: Boolean,
        val key: String,
    )

    private val IMG_SRC_PLAIN_RE =
        Regex("<img\\b[^>]*\\bsrc=(?:['\"])(.*?)(?:['\"])", RegexOption.IGNORE_CASE)

    fun imageEntriesForUpload(htmlText: String?, baseDir: File, tempDir: File): List<UploadEntry> {
        val result = mutableListOf<UploadEntry>()
        val seen = mutableSetOf<String>()
        var index = 1
        for (m in IMG_SRC_PLAIN_RE.findAll(htmlText ?: "")) {
            val src = m.groupValues[1]
            if (src.isEmpty() || isRemoteImageSrc(src) || src in seen) {
                index += 1
                continue
            }
            val path = resolveUploadImagePath(src, baseDir, tempDir, index)
            if (path != null && path.exists()) {
                result.add(
                    UploadEntry(
                        index = index,
                        source = src,
                        path = path,
                        isData = isDataImageSrc(src),
                        key = uploadImageKey(path, src),
                    )
                )
                seen.add(src)
            }
            index += 1
        }
        return result
    }

    /** 本地资源先于 data URL 上传（秀米 COS 对转内联图片更不宽容）；最终正文顺序稍后恢复。 */
    fun uploadEntriesInSafeOrder(entries: List<UploadEntry>): List<UploadEntry> =
        entries.sortedWith(compareBy({ it.isData }, { it.index }))

    // ── 上传后 URL 匹配 ──

    fun uploadNameVariants(path: File): Set<String> {
        val name = path.name.lowercase()
        val idx = name.lastIndexOf('.')
        val stem = if (idx <= 0) name else name.substring(0, idx)
        val variants = mutableSetOf(name)
        if (stem.isNotEmpty()) {
            variants.add(stem)
            for (ext in listOf(".jpg", ".jpeg", ".png", ".gif", ".webp")) {
                variants.add(stem + ext)
            }
        }
        return variants.filter { it.isNotEmpty() }.toSet()
    }

    fun uploadImageKey(path: File?, source: String = ""): String {
        if (path != null) {
            val name = path.name.lowercase()
            val idx = name.lastIndexOf('.')
            val stem = if (idx <= 0) name else name.substring(0, idx)
            val trimmed = stem.trim()
            if (trimmed.isNotEmpty()) return trimmed
        }
        val cleaned = (source).split("?", limit = 2)[0].trim().trim('\'').trim('"')
        val name = File(cleaned).name.lowercase()
        val idx = name.lastIndexOf('.')
        return if (name.isEmpty()) "" else (if (idx <= 0) name else name.substring(0, idx))
    }

    fun assetMatchesUploadPath(asset: Map<String, Any?>, path: File): Pair<Boolean, Int> {
        @Suppress("UNCHECKED_CAST")
        val files = (asset["files"] as? List<Any?> ?: emptyList<Any?>())
            .map { it?.toString()?.lowercase() ?: "" }
            .filter { it.isNotEmpty() }
        val text = (asset["text"]?.toString() ?: "").lowercase()
        val haystack = (files + text).joinToString(" ")
        val variants = uploadNameVariants(path)
        val exactName = path.name.lowercase()
        if (exactName.isNotEmpty() && files.any { File(it).name.lowercase() == exactName }) {
            return true to 100
        }
        for (name in files) {
            val basename = File(name).name.lowercase()
            if (basename in variants) return true to 90
        }
        for (variant in variants) {
            if (variant.isNotEmpty() && variant in haystack) {
                return true to if ("." in variant) 60 else 30
            }
        }
        return false to 0
    }

    /** `_xiumi_uploaded_urls_for_paths` 的纯匹配核心（assets 已由 JS 收集）。 */
    fun matchUploadedUrls(assets: List<Map<String, Any?>>, imagePaths: List<File>): List<String> {
        val matched = HashMap<Int, String>()
        for (asset in assets) {
            val url = normalizeXiumiImageUrl(asset["url"]?.toString() ?: "")
            if (url.isEmpty()) continue
            var bestIndex = -1
            var bestScore = 0
            for ((i, path) in imagePaths.withIndex()) {
                if (i in matched) continue
                val (m, score) = assetMatchesUploadPath(asset, path)
                if (m && score > bestScore) {
                    bestIndex = i
                    bestScore = score
                }
            }
            if (bestIndex >= 0) matched[bestIndex] = url
        }

        val orderedByIndex = imagePaths.indices.map { matched[it] ?: "" }.toMutableList()
        return if (orderedByIndex.all { it.isNotEmpty() }) orderedByIndex
        else orderedByIndex.filter { it.isNotEmpty() }
    }

    // ── 秀米图片 URL 工具 ──

    fun shortUrl(value: String?): String {
        val text = value ?: ""
        return if (text.length <= 180) text else text.take(177) + "..."
    }

    fun normalizeXiumiImageUrl(value: String?): String {
        var text = (value ?: "").trim()
        text = text.replace("\\/", "/")
        return if (text.startsWith("//")) "https:$text" else text
    }

    fun xiumiImageUrlsFromText(text: String?): List<String> {
        val normalized = (text ?: "").replace("\\/", "/")
        val urls = mutableListOf<String>()
        val re = Regex(
            "(?:(?:https?:)?//)?img\\.xiumi\\.us/[^\\s\"'<>）)]+|(?:https?:)?//[^\\s\"'<>）)]*/xmi/ua/[^\\s\"'<>）)]+",
            RegexOption.IGNORE_CASE
        )
        for (m in re.findAll(normalized)) {
            var url = m.value
            if (url.startsWith("img.xiumi.us/")) url = "https://$url"
            url = normalizeXiumiImageUrl(url)
            if (looksLikeUserXiumiImage(url) && url !in urls) urls.add(url)
        }
        return urls
    }

    fun looksLikeUserXiumiImage(value: String?): Boolean {
        val text = (value ?: "").lowercase()
        if (text.isEmpty()) return false
        if ("statics.xiumi.us" in text || "/stc/" in text || "templates-assets" in text) return false
        return "img.xiumi.us" in text || "/xmi/ua/" in text
    }

    // ── 按 HTML 顺序回写图片 URL ──

    fun rewriteImagesByHtmlOrder(
        htmlText: String?,
        urlBySource: Map<String, String>,
        urlByKey: Map<String, String>,
    ): String {
        var replaced = 0
        val rewritten = Regex(
            "<img\\b[^>]*\\bsrc=(['\"])(.*?)\\1[^>]*>",
            RegexOption.IGNORE_CASE
        ).replace(htmlText ?: "") { m ->
            val tag = m.value
            val quote = m.groupValues[1]
            val src = m.groupValues[2].trim()
            if (src.isEmpty() || isRemoteImageSrc(src)) return@replace tag
            var remoteUrl = urlBySource[src] ?: ""
            if (remoteUrl.isEmpty()) {
                val key = uploadImageKey(null, src)
                remoteUrl = urlByKey[key] ?: ""
            }
            if (remoteUrl.isEmpty()) return@replace tag
            replaced += 1
            Regex("\\bsrc=(['\"])(.*?)\\1", RegexOption.IGNORE_CASE)
                .replaceFirst(tag, "src=$quote$remoteUrl$quote")
        }
        return rewritten
    }

    fun htmlImageSources(htmlText: String?): List<String> =
        IMG_SRC_PLAIN_RE.findAll(htmlText ?: "")
            .map { normalizeXiumiImageUrl(it.groupValues[1]) }
            .filter { it.isNotEmpty() }
            .toList()

    // ── 调试日志辅助 ──

    data class ImageEntryLog(
        val index: Int,
        val image: String,
        val key: String,
        val source: String,
        val remoteUrl: String,
        val uploaded: Boolean,
    )

    fun imageEntryForLog(entry: UploadEntry, remoteUrl: String = ""): ImageEntryLog {
        var source = entry.source
        if (isDataImageSrc(source)) source = source.split(";", limit = 2)[0] + ";base64,..."
        return ImageEntryLog(
            index = entry.index,
            image = entry.path.name,
            key = entry.key,
            source = shortUrl(source),
            remoteUrl = shortUrl(remoteUrl),
            uploaded = remoteUrl.isNotEmpty(),
        )
    }

    fun htmlImageOrderForLog(htmlText: String?): List<Map<String, Any?>> {
        val order = mutableListOf<Map<String, Any?>>()
        var index = 1
        for (m in IMG_SRC_PLAIN_RE.findAll(htmlText ?: "")) {
            val src = m.groupValues[1]
            val normalized = normalizeXiumiImageUrl(src)
            var loggedSrc = normalized
            if (isDataImageSrc(loggedSrc)) loggedSrc = loggedSrc.split(";", limit = 2)[0] + ";base64,..."
            order.add(
                mapOf(
                    "index" to index,
                    "key" to uploadImageKey(null, src),
                    "src" to shortUrl(loggedSrc),
                    "is_xiumi" to looksLikeUserXiumiImage(normalized),
                )
            )
            index += 1
        }
        return order
    }

    // ── 上传链路探测图 ──

    private const val PROBE_IMAGE_B64 =
        "iVBORw0KGgoAAAANSUhEUgAAAEAAAAAwCAIAAABOyVRHAAAAPElEQVR4nO3PQQ0AIBDAMMC/5+ONAvZoFSzZnYFn" +
            "NzMAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAADg1wGfXgAB3WQj8QAAAABJRU5ErkJggg=="

    fun writeProbeImage(tempDir: File): File {
        val path = File(tempDir, "wanyou_xiumi_upload_probe.png")
        path.writeBytes(Base64.getDecoder().decode(PROBE_IMAGE_B64))
        return path
    }
}
