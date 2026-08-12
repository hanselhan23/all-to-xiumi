package com.hanselhan.wanyou.markdown

import java.io.File

/**
 * 图片路径解析 —— `all_to_xiumi/image_paths.py` 的移植。
 *
 * Python 版在 Windows 上用 `os.sep`（仅反斜杠）做拆分/拼装，用 `pathlib.Path`
 * 做组件归一化（`str(Path("a/b"))` → `"a\\b"`）。本移植用 `File.separatorChar`
 * 对齐 `os.sep` 语义，用 [normalizePathComponents] 对齐 `Path` 的组件归一化。
 * 金标向量（golden/pure_vectors.json）逐字节比对，勿改动行为。
 */
object ImagePaths {

    fun isRemoteOrDataImage(src: String?): Boolean {
        val value = (src ?: "").trim()
        if (Regex("^[a-zA-Z]:[\\\\/]").matchAtStart(value)) return false
        return Regex("^(https?:)?//").matchAtStart(value) ||
            Regex("^data:image/", RegexOption.IGNORE_CASE).matchAtStart(value) ||
            Regex("^[a-zA-Z][a-zA-Z0-9+.-]*:").matchAtStart(value)
    }

    fun cleanMarkdownImageTarget(src: String?): String {
        var cleaned = Html.unescape(src ?: "").trim().trim('<', '>').trim('"').trim('\'')
        if ('"' in cleaned) {
            cleaned = cleaned.substringBefore('"').trim()
        }
        cleaned = cleaned.substringBefore('?').trim()
        if (isRemoteOrDataImage(cleaned)) return cleaned

        // html2text 可能输出双反斜杠的 Windows 路径、并在 Markdown URL 中转义下划线，
        // 探测路径前先归一化两者。
        cleaned = cleaned.replace("\\/", "/")
        cleaned = Regex("\\\\([_])").replace(cleaned, "$1")
        cleaned = Regex("[\\\\/]+").replace(cleaned) { File.separator }
        return cleaned
    }

    /** 对应 `_with_fixed_inline_basename`：`name<4位数字>` → `name_<数字>`。 */
    private fun withFixedInlineBasename(pathText: String): String {
        // os.path.split 只按 os.sep 拆分（Windows 上反斜杠）——不用 java.io.File
        val dirname = pathText.substringBeforeLast(File.separatorChar, "")
        val basename = pathText.substringAfterLast(File.separatorChar)
        val fixed = Regex("^([A-Za-z]+)(\\d{4})(\\.[^.]+)$").replace(basename, "$1_$2$3")
        if (fixed == basename) return pathText
        return if (dirname.isEmpty()) fixed else dirname + File.separator + fixed
    }

    /** 对应 `_with_fixed_run_dir`：`output\20260428<1030>` → `output\20260428_1030`。 */
    private fun withFixedRunDir(pathText: String): String {
        val sep = Regex.escape(File.separator)
        return Regex("(^|$sep)output$sep(\\d{8})(\\d{4})(?=$sep)").replace(pathText) { m ->
            "${m.groupValues[1]}output${File.separator}${m.groupValues[2]}_${m.groupValues[3]}"
        }
    }

    /** 对应 `_with_fixed_wanyou_dir`：`images\wanyou<数字>` → `images\_wanyou_<数字>`。 */
    private fun withFixedWanyouDir(pathText: String): String {
        val sep = Regex.escape(File.separator)
        val first = Regex("images${sep}wanyou(?=\\d)").replace(pathText) { "images${File.separator}_wanyou_" }
        return Regex("images${sep}wanyou_(\\d{8}_\\d{4})").replace(first) { "images${File.separator}_wanyou_${it.groupValues[1]}" }
    }

    private fun candidateRoots(baseDir: File?): List<File> {
        val roots = mutableListOf<File>()
        if (baseDir != null) roots.add(baseDir)
        roots.add(File(System.getProperty("user.dir") ?: "."))
        val unique = mutableListOf<File>()
        val seen = mutableSetOf<String>()
        for (root in roots) {
            val key = runCatching { root.canonicalPath }.getOrElse { root.path }
            if (seen.add(key)) unique.add(root)
        }
        return unique
    }

    /**
     * 对应 `Path(variant)` 的组件归一化：按 `[\\/]+` 拆分为组件再以 os.sep 拼装。
     * 这样 `File` 的字符串形式与 Python `str(Path(...))` 在 Windows 上一致。
     */
    private fun normalizePathComponents(text: String): String {
        val parts = text.split(Regex("[\\\\/]+"))
        return parts.joinToString(File.separator)
    }

    /** 归一化后的变体文本 → File；驱动盘符 / 根路径保持 isAbsolute 语义。 */
    private fun variantFile(normalizedText: String): File {
        val normalized = normalizePathComponents(normalizedText)
        return if (normalized.isEmpty()) File(".") else File(normalized)
    }

    fun iterImagePathCandidates(
        src: String?,
        baseDir: File? = null,
        extraRoots: List<File> = emptyList(),
    ): List<File> {
        val cleaned = cleanMarkdownImageTarget(src)
        if (cleaned.isEmpty() || isRemoteOrDataImage(cleaned)) return emptyList()

        val normalized = cleaned
        val variants = listOf(
            normalized,
            withFixedInlineBasename(normalized),
            withFixedRunDir(normalized),
            withFixedInlineBasename(withFixedRunDir(normalized)),
            withFixedWanyouDir(normalized),
            withFixedWanyouDir(withFixedRunDir(normalized)),
        )
        // os.path.basename 只按 os.sep 拆分（Windows 上反斜杠）
        val basename = withFixedInlineBasename(normalized).substringAfterLast(File.separatorChar)

        val roots = candidateRoots(baseDir).toMutableList()
        roots.addAll(extraRoots)

        val candidates = mutableListOf<File>()
        for (variant in variants) {
            val path = variantFile(variant)
            if (path.isAbsolute) {
                candidates.add(path)
                continue
            }
            for (root in roots) {
                candidates.add(File(root, path.path))
            }
        }

        val inlineMarker = "images${File.separator}inline"
        if (inlineMarker in normalized) {
            for (root in roots) {
                candidates.add(File(root, "images${File.separator}inline${File.separator}$basename"))
            }
            val sep = Regex.escape(File.separator)
            val m = Regex(
                "output${sep}(\\d{8})_?(\\d{4})${sep}images${sep}inline${sep}([^${sep}]+)$"
            ).find(normalized)
            if (m != null) {
                val fixedRunDir = "${m.groupValues[1]}_${m.groupValues[2]}"
                val fixedBasename =
                    withFixedInlineBasename(m.groupValues[3]).substringAfterLast(File.separatorChar)
                for (root in roots) {
                    candidates.add(
                        File(root, "output${File.separator}$fixedRunDir${File.separator}images${File.separator}inline${File.separator}$fixedBasename")
                    )
                }
            }
        }

        // 去重（按解析后路径，与 Python resolve() 语义对齐）
        val unique = mutableListOf<File>()
        val seen = mutableSetOf<String>()
        for (candidate in candidates) {
            val key = runCatching { candidate.canonicalPath }.getOrElse { candidate.path }
            if (seen.add(key)) unique.add(candidate)
        }
        return unique
    }

    fun resolveExistingImagePath(
        src: String?,
        baseDir: File? = null,
        extraRoots: List<File> = emptyList(),
    ): File? {
        for (candidate in iterImagePathCandidates(src, baseDir, extraRoots)) {
            if (candidate.exists()) return candidate.canonicalFile
        }
        return null
    }
}
