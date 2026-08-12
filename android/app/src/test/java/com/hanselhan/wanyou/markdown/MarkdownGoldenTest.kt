package com.hanselhan.wanyou.markdown

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Markdown → HTML 金标测试：Kotlin 移植与 Python 参考实现逐字节比对。
 *
 * 金标由 `android/tools/gen_golden_tests.py` 用 Python 实现生成
 * （`app/src/test/resources/golden/markdown/` 下的 HTML 文件 + manifest.json）。
 * 重新生成后内容应保持不变；若需要更新金标，先确认 Python 侧行为确实变了。
 */
class MarkdownGoldenTest {

    @Test
    fun markdownGoldensMatchPythonOutput() {
        val manifest = JSONObject(resourceText("golden/manifest.json"))
        val rels = mutableListOf<String>()
        val keys = manifest.keys()
        while (keys.hasNext()) rels.add(keys.next())
        assertTrue("manifest 不应为空", rels.isNotEmpty())

        for (rel in rels.sorted()) {
            val entry = manifest.getJSONObject(rel)
            val fixtureName = entry.getString("input")
            val templateName = entry.getString("template")
            val markdown = resourceText("fixtures/$fixtureName")
            val expected = resourceText("golden/$rel")
            val actual = MarkdownToHtml.markdownToHtml(
                markdown,
                template = TemplateRegistry.getTemplate(templateName),
            )
            assertEquals("金标不一致: $rel（模板 $templateName）", expected, actual)
        }
    }

    private fun resourceText(path: String): String =
        requireNotNull(javaClass.classLoader?.getResource(path)) { "缺少测试资源: $path" }
            .readText(Charsets.UTF_8)
            // Windows/git 检出可能带 CRLF；Python 参考实现以 LF 比较，统一归一化
            .replace("\r\n", "\n")
}
