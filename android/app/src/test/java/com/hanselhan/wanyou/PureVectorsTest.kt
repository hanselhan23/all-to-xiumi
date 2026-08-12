package com.hanselhan.wanyou

import com.hanselhan.wanyou.markdown.ImagePaths
import com.hanselhan.wanyou.markdown.MarkdownToHtml
import com.hanselhan.wanyou.markdown.TemplateRegistry
import com.hanselhan.wanyou.publish.HtmlPrepare
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import java.io.File

/**
 * 纯函数测试向量：Kotlin 移植与 Python 参考实现逐字节比对。
 *
 * 向量由 `android/tools/gen_golden_tests.py` 生成
 * （`app/src/test/resources/golden/pure_vectors.json`）。
 * `inputs` 节是输入快照——测试直接从这里取输入，避免两侧输入漂移；
 * 其余节是 Python 参考实现的输出，即期望值。
 */
class PureVectorsTest {

    @get:Rule
    val tmp = TemporaryFolder()

    // ── 1. markdown_to_html 行内渲染 / 标签拆分 ──

    @Test
    fun renderInlineMarkdownMatchesPython() {
        val vectors = vectors().getJSONArray("render_inline_markdown")
        val tpl = TemplateRegistry.getTemplate("generic")
        assertTrue(vectors.length() > 0)
        for (i in 0 until vectors.length()) {
            val v = vectors.getJSONObject(i)
            assertEquals(
                "render_inline_markdown 金标不一致: ${v.getString("in")}",
                v.getString("out"),
                MarkdownToHtml.renderInlineMarkdown(v.getString("in"), tpl),
            )
        }
    }

    @Test
    fun renderInlineMarkdownRedMatchesPython() {
        val vectors = vectors().getJSONArray("render_inline_markdown_red")
        val tpl = TemplateRegistry.getTemplate("red")
        for (i in 0 until vectors.length()) {
            val v = vectors.getJSONObject(i)
            assertEquals(
                "render_inline_markdown(red) 金标不一致: ${v.getString("in")}",
                v.getString("out"),
                MarkdownToHtml.renderInlineMarkdown(v.getString("in"), tpl),
            )
        }
    }

    @Test
    fun splitLabelValueMatchesPython() {
        val vectors = vectors().getJSONArray("split_label_value")
        for (i in 0 until vectors.length()) {
            val v = vectors.getJSONObject(i)
            val input = v.getString("in")
            val (label, value) = MarkdownToHtml.splitLabelValue(input)
            assertEquals("label 不一致: $input", v.getJSONArray("out").getString(0), label)
            assertEquals("value 不一致: $input", v.getJSONArray("out").getString(1), value)
        }
    }

    @Test
    fun tableHelpersMatchPython() {
        val inputs = inputs()
        val expected = vectors().getJSONObject("table_helpers")

        val rows = inputs.getJSONArray("is_table_row")
        for (i in 0 until rows.length()) {
            assertEquals(
                "is_table_row 不一致: ${rows.getString(i)}",
                expected.getJSONArray("is_table_row").getBoolean(i),
                MarkdownToHtml.isTableRow(rows.getString(i)),
            )
        }
        val seps = inputs.getJSONArray("is_table_separator")
        for (i in 0 until seps.length()) {
            assertEquals(
                "is_table_separator 不一致: ${seps.getString(i)}",
                expected.getJSONArray("is_table_separator").getBoolean(i),
                MarkdownToHtml.isTableSeparator(seps.getString(i)),
            )
        }
        val splitInput = inputs.getString("split_table_row")
        val expectedSplit = expected.getJSONArray("split_table_row")
        val actualSplit = MarkdownToHtml.splitTableRow(splitInput)
        assertEquals("split_table_row 列数不一致", expectedSplit.length(), actualSplit.size)
        for (i in 0 until expectedSplit.length()) {
            assertEquals("split_table_row[$i] 不一致", expectedSplit.getString(i), actualSplit[i])
        }
        val items = inputs.getJSONArray("is_ordered_list_item")
        for (i in 0 until items.length()) {
            assertEquals(
                "is_ordered_list_item 不一致: ${items.getString(i)}",
                expected.getJSONArray("is_ordered_list_item").getBoolean(i),
                MarkdownToHtml.isOrderedListItem(items.getString(i)),
            )
        }
    }

    // ── 2. image_paths ──

    @Test
    fun imagePathsMatchPython() {
        val inputs = inputs()
        val expected = vectors().getJSONObject("image_paths")

        val remoteInputs = inputs.getJSONArray("is_remote_or_data")
        val expectedRemote = expected.getJSONArray("is_remote_or_data")
        for (i in 0 until remoteInputs.length()) {
            assertEquals(
                "is_remote_or_data 不一致: ${remoteInputs.getString(i)}",
                expectedRemote.getBoolean(i),
                ImagePaths.isRemoteOrDataImage(remoteInputs.getString(i)),
            )
        }

        val cleanInputs = inputs.getJSONArray("clean_target")
        val expectedClean = expected.getJSONArray("clean_target")
        for (i in 0 until cleanInputs.length()) {
            assertEquals(
                "clean_target 不一致: ${cleanInputs.getString(i)}",
                expectedClean.getString(i),
                ImagePaths.cleanMarkdownImageTarget(cleanInputs.getString(i)),
            )
        }

        // 与 gen_golden_tests.py 相同的目录布置：无下划线文件名命中 variants[0]
        val base = tmp.newFolder("imgbase")
        File(base, "images${File.separator}wanyou20260531_1131").mkdirs()
        File(base, "images${File.separator}wanyou20260531_1131${File.separator}1.jpg")
            .writeBytes(byteArrayOf(0x78))

        val userDir = File(System.getProperty("user.dir") ?: ".").canonicalPath
        fun mask(text: String): String =
            text.replace(base.canonicalPath, "<TMP>").replace(userDir, "<ROOT>")

        val iterInputs = inputs.getJSONArray("iter_candidates")
        val expectedIter = expected.getJSONArray("iter_candidates")
        assertEquals(iterInputs.length(), expectedIter.length())
        for (i in 0 until iterInputs.length()) {
            val actual = ImagePaths.iterImagePathCandidates(iterInputs.getString(i), baseDir = base)
                .map { mask(it.path) }
            val exp = expectedIter.getJSONArray(i)
            assertEquals("iter_candidates[$i] 数量不一致", exp.length(), actual.size)
            for (j in 0 until exp.length()) {
                assertEquals("iter_candidates[$i][$j] 不一致", exp.getString(j), actual[j])
            }
        }

        val resolveInputs = inputs.getJSONArray("resolve_existing")
        val expectedResolve = expected.getJSONArray("resolve_existing")
        for (i in 0 until resolveInputs.length()) {
            val resolved = ImagePaths.resolveExistingImagePath(resolveInputs.getString(i), baseDir = base)
            assertEquals(
                "resolve_existing 不一致: ${resolveInputs.getString(i)}",
                expectedResolve.getString(i),
                if (resolved != null) mask(resolved.path) else "",
            )
        }
    }

    // ── 3. xiumi_publish 纯 HTML 预处理 ──

    @Test
    fun xiumiPureMatchesPython() {
        val inputs = inputs()
        val expected = vectors().getJSONObject("xiumi_pure")

        val sampleHtml = inputs.getString("sample_html")
        assertEquals("extract_main_html 不一致", expected.getString("extract_main_html"),
            HtmlPrepare.extractMainHtml(sampleHtml))
        assertEquals("extract_main_html(body) 不一致", expected.getString("extract_main_html_body"),
            HtmlPrepare.extractMainHtml(inputs.getString("extract_main_html_body")))
        assertEquals("extract_main_html(raw) 不一致", expected.getString("extract_main_html_raw"),
            HtmlPrepare.extractMainHtml(inputs.getString("extract_main_html_raw")))
        assertEquals("apply_base_format 不一致", expected.getString("apply_base_format"),
            HtmlPrepare.applyXiumiBaseFormat(sampleHtml))
        assertEquals("promote_headings 不一致", expected.getString("promote_headings"),
            HtmlPrepare.promoteHeadingsForXiumi(sampleHtml))
        assertJsonEquals(
            "camelize_css 不一致",
            expected.get("camelize_css"),
            HtmlPrepare.camelizeCss(inputs.getString("camelize_css")).toJsonObject(),
        )
        assertEquals("flatten_inner_html 不一致", expected.getString("flatten_inner_html"),
            HtmlPrepare.flattenInnerHtml(inputs.getString("flatten_inner_html")))

        val actualBlocks = JSONArray()
        for (block in HtmlPrepare.htmlToBlocks(sampleHtml)) {
            val style = JSONObject()
            for ((k, v) in block.style) style.put(k, v)
            val obj = JSONObject()
            obj.put("style", style)
            obj.put("text", block.text)
            actualBlocks.put(obj)
        }
        assertJsonEquals("blocks 不一致", expected.get("blocks"), actualBlocks)

        assertEquals("first_heading 不一致", expected.getString("first_heading"),
            HtmlPrepare.firstHeading(inputs.getString("first_heading")))
        assertEquals("first_summary_line 不一致", expected.getString("first_summary_line"),
            HtmlPrepare.firstSummaryLine(inputs.getString("first_summary_line")))
        assertEquals("image_urls_from_text 不一致",
            expected.getJSONArray("image_urls_from_text").toList(),
            HtmlPrepare.xiumiImageUrlsFromText(inputs.getString("image_urls_from_text")))

        val urlInputs = inputs.getJSONArray("normalize_urls")
        val expectedUrls = expected.getJSONArray("normalize_urls")
        for (i in 0 until urlInputs.length()) {
            assertEquals("normalize_urls[$i] 不一致", expectedUrls.getString(i),
                HtmlPrepare.normalizeXiumiImageUrl(urlInputs.getString(i)))
        }
        val lookInputs = inputs.getJSONArray("looks_like_user_image")
        val expectedLook = expected.getJSONArray("looks_like_user_image")
        for (i in 0 until lookInputs.length()) {
            assertEquals("looks_like_user_image[$i] 不一致", expectedLook.getBoolean(i),
                HtmlPrepare.looksLikeUserXiumiImage(lookInputs.getString(i)))
        }

        val expectedVariants = expected.getJSONArray("upload_name_variants").toList()
        assertEquals(
            "upload_name_variants 不一致",
            expectedVariants,
            HtmlPrepare.uploadNameVariants(File(inputs.getString("upload_name_variants_path"))).sorted(),
        )

        val expectedKeys = expected.getJSONArray("upload_image_key")
        assertEquals("upload_image_key(path) 不一致", expectedKeys.getString(0),
            HtmlPrepare.uploadImageKey(File(inputs.getString("upload_image_key_path"))))
        assertEquals("upload_image_key(source) 不一致", expectedKeys.getString(1),
            HtmlPrepare.uploadImageKey(null, inputs.getString("upload_image_key_source")))

        val asset = jsonToMap(inputs.getJSONObject("asset_matches_asset"))
        val (matched, score) =
            HtmlPrepare.assetMatchesUploadPath(asset, File(inputs.getString("asset_matches_path")))
        val expectedMatches = expected.getJSONArray("asset_matches")
        assertEquals("asset_matches 数量不一致", 1, expectedMatches.length())
        assertEquals("asset_matches 结果不一致", expectedMatches.getJSONArray(0).getBoolean(0), matched)
        assertEquals("asset_matches 分数不一致", expectedMatches.getJSONArray(0).getInt(1), score)
    }

    // ── 辅助 ──

    private fun vectors(): JSONObject = JSONObject(resourceText("golden/pure_vectors.json"))

    private fun inputs(): JSONObject = vectors().getJSONObject("inputs")

    private fun resourceText(path: String): String =
        requireNotNull(javaClass.classLoader?.getResource(path)) { "缺少测试资源: $path" }
            .readText(Charsets.UTF_8)

    /** Map<String, String> → JSONObject（键值顺序无关，树比对不依赖插入顺序）。 */
    private fun Map<String, String>.toJsonObject(): JSONObject {
        val obj = JSONObject()
        for ((k, v) in this) obj.put(k, v)
        return obj
    }

    /** JSONObject → Map（assets 等输入参数还原）。 */
    private fun jsonToMap(obj: JSONObject): Map<String, Any?> {
        val map = HashMap<String, Any?>()
        val keys = obj.keys()
        while (keys.hasNext()) {
            val k = keys.next()
            map[k] = when (val v = obj.get(k)) {
                is JSONArray -> (0 until v.length()).map { v.get(it) }
                is JSONObject -> jsonToMap(v)
                JSONObject.NULL -> null
                else -> v
            }
        }
        return map
    }

    /**
     * org.json 树递归比对（对象键序无关）。
     * org.json 的 JSONObject 内部是 HashMap，toString 顺序不定，
     * 不能直接做字符串比对，必须逐节点比对。
     */
    private fun assertJsonEquals(message: String, expected: Any?, actual: Any?) {
        assertTrue("$message（值不相等）\n期望: $expected\n实际: $actual", jsonEquals(expected, actual))
    }

    private fun jsonEquals(expected: Any?, actual: Any?): Boolean {
        if (expected is JSONObject && actual is JSONObject) {
            val expKeys = expected.keys().asSequence().toList()
            val actKeys = actual.keys().asSequence().toList()
            if (expKeys.size != actKeys.size) return false
            for (k in expKeys) {
                if (!actual.has(k)) return false
                if (!jsonEquals(expected.get(k), actual.get(k))) return false
            }
            return true
        }
        if (expected is JSONArray && actual is JSONArray) {
            if (expected.length() != actual.length()) return false
            for (i in 0 until expected.length()) {
                if (!jsonEquals(expected.get(i), actual.get(i))) return false
            }
            return true
        }
        if (expected === JSONObject.NULL || actual === JSONObject.NULL) {
            return expected === JSONObject.NULL && actual === JSONObject.NULL
        }
        return expected == actual
    }

    private fun JSONArray.toList(): List<Any?> = (0 until length()).map { get(it) }
}
