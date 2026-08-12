package com.hanselhan.wanyou.publish

import android.content.Context
import android.os.SystemClock
import android.webkit.WebView
import com.hanselhan.wanyou.data.SettingsStore
import com.hanselhan.wanyou.markdown.MarkdownToHtml
import com.hanselhan.wanyou.markdown.TemplateRegistry
import com.hanselhan.wanyou.publish.JsBridge.asString
import com.hanselhan.wanyou.publish.JsBridge.evalJs
import java.io.File
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import org.json.JSONObject

/**
 * 秀米草稿发布编排 —— `xiumi_publish.py` 的 `publish_xiumi_draft` WebView 移植。
 *
 * 流程：内容准备（HTML 提取/基础格式/图片准备）→ 打开编辑器（登录由用户在
 * WebView 中完成，Cookie 持久化）→ 填字段 → 注入正文（模型直构 comps）→
 * 上传图片 → 重建 comps → 标记脏 → 保存 → 轮询草稿 URL。
 *
 * 线程约束：WebView 的 `loadUrl`/`evaluateJavascript` 必须主线程调用，
 * 本类所有方法应在 Main dispatcher 的协程中运行（UI 层负责）。
 */
class XiumiPublisher(
    context: Context,
    private val webView: WebView,
    private val settings: SettingsStore,
    fileChooser: FileChooserBridge,
) {

    private val uploader = XiumiUploader(context, webView, fileChooser, settings) { log(it) }

    // ── 状态（UI 订阅） ──

    private val _logLines = MutableStateFlow<List<String>>(emptyList())
    val logLines: StateFlow<List<String>> = _logLines.asStateFlow()

    private val _phase = MutableStateFlow("")
    val phase: StateFlow<String> = _phase.asStateFlow()

    private fun log(line: String) {
        val now = System.currentTimeMillis()
        val stamp = java.text.SimpleDateFormat("HH:mm:ss", java.util.Locale.getDefault())
            .format(java.util.Date(now))
        _logLines.value = (_logLines.value + "[$stamp] $line").takeLast(300)
    }

    private fun phase(value: String) {
        _phase.value = value
        log("▶ $value")
    }

    // ── 输入 / 输出 ──

    data class PublishRequest(
        /** Markdown 源文本（与 [htmlPath] 二选一；非空时用模板就地渲染）。 */
        val markdownText: String = "",
        /** 模板名（generic / wanyou / red）。 */
        val templateName: String = "generic",
        /** 或直接提供 HTML 文件路径（提取 main/body 内容）。 */
        val htmlPath: String = "",
        /** 本地图片解析根（markdown 文件路径，用于相对路径图片）。 */
        val markdownPath: String = "",
        val title: String = "",
        val author: String = "",
        val digest: String = "",
        val sourceUrl: String = "",
        val dryRun: Boolean = false,
        val uploadProbe: Boolean = false,
    )

    data class PublishResult(
        val status: String,   // saved / dry_run / uncertain / error
        val editorUrl: String = "",
        val draftUrl: String = "",
        val title: String = "",
        val error: String = "",
    )

    data class LoginState(
        val authenticated: Boolean,
        val hasPaperEntry: Boolean,
        val hasEditor: Boolean,
        val settling: Boolean,
        val loginControls: List<Map<String, Any?>>,
        val headerLoginControls: List<Map<String, Any?>>,
        val url: String,
        val excerpt: String,
    )

    // ── 主流程 ──

    suspend fun publish(request: PublishRequest): PublishResult {
        var editorUrl = ""
        try {
            phase("内容准备")
            val content = prepareContent(request)
            var contentHtml = content.first
            val baseDir = content.second

            val markdownText = if (request.htmlPath.isEmpty()) request.markdownText else {
                val mdPath = File(request.markdownPath.ifEmpty { request.htmlPath.replaceSuffix(".md") })
                if (mdPath.exists()) mdPath.readText(Charsets.UTF_8) else ""
            }
            val finalTitle = request.title.ifEmpty { HtmlPrepare.firstHeading(markdownText) }.ifEmpty { "万有预报" }.trim()
            val finalDigest = request.digest.ifEmpty { HtmlPrepare.firstSummaryLine(markdownText) }.trim()
            val finalAuthor = request.author.trim()
            val finalSourceUrl = request.sourceUrl.trim()

            phase("打开图文编辑器")
            openEditor()
            editorUrl = currentUrl()

            phase("填充标题、作者和摘要")
            fillFields(finalTitle, finalAuthor, finalSourceUrl, finalDigest)

            phase("写入正文")
            fillBody(contentHtml, baseDir, request.uploadProbe)

            editorUrl = currentUrl()
            if (request.dryRun) {
                log("秀米：已完成自动填充，未点击保存")
                return PublishResult("dry_run", editorUrl = editorUrl, title = finalTitle)
            }

            phase("保存草稿")
            var (saveState, afterUrl) = saveDraft()

            if (saveState == "login_required") {
                log("秀米：保存前需要重新登录")
                if (!waitForManualLogin(settings.loginWaitSeconds * 1000L)) {
                    return PublishResult("uncertain", editorUrl = afterUrl, title = finalTitle,
                        error = "秀米保存前登录未完成，已超过等待时间。")
                }
                openEditor()
                fillFields(finalTitle, finalAuthor, finalSourceUrl, finalDigest)
                fillBody(contentHtml, baseDir, request.uploadProbe)
                log("秀米：登录完成，重新点击保存")
                val retry = saveDraft()
                saveState = retry.first
                afterUrl = retry.second
            }

            return if (saveState == "url_changed") {
                log("秀米：草稿已保存")
                log("秀米草稿地址：$afterUrl")
                PublishResult("saved", editorUrl = afterUrl, draftUrl = afterUrl, title = finalTitle)
            } else {
                log("秀米：保存状态未能自动确认，请在页面中检查是否已保存")
                PublishResult("uncertain", editorUrl = afterUrl, title = finalTitle)
            }
        } catch (e: Exception) {
            val url = runCatching { currentUrl() }.getOrDefault(editorUrl)
            log("秀米：发生异常：${e::class.simpleName}: ${e.message}")
            return PublishResult("error", editorUrl = url, error = "${e::class.simpleName}: ${e.message}")
        }
    }

    /** 内容准备：提取 HTML + 基础格式 + 图片准备，返回 (contentHtml, baseDir)。 */
    private suspend fun prepareContent(request: PublishRequest): Pair<String, File> {
        val htmlPath = request.htmlPath
        val htmlText: String
        val baseDir: File
        if (htmlPath.isNotEmpty()) {
            val file = File(htmlPath)
            if (!file.exists()) throw java.io.FileNotFoundException("HTML 文件不存在: $file")
            htmlText = file.readText(Charsets.UTF_8)
            val mdPath = File(request.markdownPath.ifEmpty { file.absolutePath.replaceSuffix(".md") })
            baseDir = if (mdPath.exists()) mdPath.parentFile ?: file.parentFile ?: File(".") else file.parentFile ?: File(".")
        } else if (request.markdownText.isNotBlank()) {
            val tpl = TemplateRegistry.getTemplate(request.templateName)
            htmlText = MarkdownToHtml.markdownToHtml(request.markdownText, template = tpl)
            val mdPath = File(request.markdownPath)
            baseDir = if (mdPath.exists()) mdPath.parentFile ?: File(".") else File(System.getProperty("user.dir") ?: ".")
        } else {
            throw IllegalArgumentException("请提供 Markdown 文本或 HTML 文件路径")
        }

        var contentHtml = HtmlPrepare.extractMainHtml(htmlText)
        if (!settings.preserveStyles) {
            contentHtml = if (settings.applyBaseFormat) {
                HtmlPrepare.applyXiumiBaseFormat(contentHtml)
            } else {
                HtmlPrepare.promoteHeadingsForXiumi(contentHtml)
            }
        }
        contentHtml = HtmlPrepare.prepareXiumiImages(contentHtml, baseDir)
        return contentHtml to baseDir
    }

    // ── 编辑器打开 / 登录 ──

    private suspend fun eval(script: String): Any? = webView.evalJs(script)

    private suspend fun currentUrl(): String = eval(XiumiJs.CURRENT_URL).asString()

    private suspend fun waitForReadyState(timeoutMs: Long): Boolean {
        val deadline = SystemClock.elapsedRealtime() + timeoutMs
        while (SystemClock.elapsedRealtime() < deadline) {
            val state = eval(XiumiJs.READY_STATE).asString()
            if (state == "interactive" || state == "complete") return true
            delay(500)
        }
        return false
    }

    private suspend fun waitEditorReady(timeoutMs: Long): Boolean {
        val deadline = SystemClock.elapsedRealtime() + timeoutMs
        while (SystemClock.elapsedRealtime() < deadline) {
            val hasSave = eval(XiumiJs.HAS_SAVE_BUTTON) == true
            val hasEdit = eval(XiumiJs.HAS_EDITABLE) == true
            if (hasSave && hasEdit) return true
            delay(1000)
        }
        return false
    }

    private suspend fun pageExcerpt(limit: Int): String =
        Regex("\\s+").replace(eval(XiumiJs.BODY_TEXT).asString(), " ").trim().take(limit)

    private suspend fun loginState(): LoginState {
        val controls = (eval(XiumiJs.VISIBLE_LOGIN_CONTROLS) as? org.json.JSONArray)?.toMaps()
            ?: emptyList()
        val headerControls = (eval(XiumiJs.VISIBLE_HEADER_LOGIN_LINKS) as? org.json.JSONArray)?.toMaps()
            ?: emptyList()
        val excerpt = pageExcerpt(500)
        val effectiveHasControls = controls.isNotEmpty() || headerControls.isNotEmpty() || (
            Regex("(?<!退出)(登录|登陆|注册)").containsMatchIn(excerpt) &&
                !Regex("(登录中|正在登录|退出登录|退出登陆)").containsMatchIn(excerpt)
            )
        val hasPaperEntry = "我的秀米" in excerpt && "图文排版" in excerpt
        val settling = listOf("正在登录", "登录中").any { it in excerpt }
        val hasEditor = (eval(XiumiJs.HAS_SAVE_BUTTON) == true) && (eval(XiumiJs.HAS_EDITABLE) == true)
        val authenticated = (hasPaperEntry || hasEditor) && !effectiveHasControls && !settling
        return LoginState(
            authenticated = authenticated,
            hasPaperEntry = hasPaperEntry,
            hasEditor = hasEditor,
            settling = settling,
            loginControls = controls,
            headerLoginControls = headerControls,
            url = currentUrl(),
            excerpt = excerpt,
        )
    }

    /** 用户在 WebView 中手动登录；先尝试 JS 点击登录入口。 */
    suspend fun waitForManualLogin(timeoutMs: Long): Boolean {
        runCatching { eval(XiumiJs.CLICK_FIRST_LOGIN_LINK) }
        log("请在下方秀米页面完成登录")
        val deadline = SystemClock.elapsedRealtime() + timeoutMs
        while (SystemClock.elapsedRealtime() < deadline) {
            val state = loginState()
            if (state.authenticated) {
                log("秀米：已确认登录状态")
                return true
            }
            delay(1000)
        }
        return false
    }

    private suspend fun waitUntilHomeSettled(timeoutMs: Long): Boolean {
        val deadline = SystemClock.elapsedRealtime() + maxOf(5000, timeoutMs)
        while (SystemClock.elapsedRealtime() < deadline) {
            if (loginState().authenticated) return true
            delay(1000)
        }
        return false
    }

    /** `_dismiss_xiumi_recover_dialog`：点掉恢复弹窗（WebView 无 CDP 鼠标分支）。 */
    private suspend fun dismissRecoverDialog() {
        delay(1500)
        val result = runCatching { eval(XiumiJs.DISMISS_RECOVER_DIALOG) as? JSONObject }
            .getOrNull() ?: return
        if (result.optString("text").isEmpty()) return
        delay(1500)
        val still = eval(XiumiJs.BODY_TEXT).asString().contains("上次没有保存")
        if (still) {
            runCatching { eval(XiumiJs.DISMISS_RECOVER_DIALOG) }
            delay(1500)
        }
    }

    /** `_open_xiumi_editor_from_my_xiumi` + 登录守卫。 */
    suspend fun openEditor() {
        val homeUrl = settings.xiumiHomeUrl
        webView.loadUrl(homeUrl)
        if (!waitForReadyState(settings.loginWaitSeconds * 1000L)) {
            throw RuntimeException("秀米页面加载超时")
        }

        if (homeUrl.contains("#/paper/")) {
            // 直连编辑器 URL：登录态由持久化 Cookie 承载，直接等编辑器就绪
            if (waitEditorReady(settings.loginWaitSeconds * 1000L)) {
                log("秀米：已进入图文编辑器")
                return
            }
            throw RuntimeException("未能进入图文编辑器（可能未登录）。")
        }

        if (!loginState().authenticated) {
            if (!waitForManualLogin(settings.loginWaitSeconds * 1000L)) {
                throw RuntimeException("秀米登录未完成，已超过等待时间。")
            }
            webView.loadUrl(homeUrl)
            waitForReadyState(settings.loginWaitSeconds * 1000L)
        }

        if (!waitUntilHomeSettled(minOf(settings.loginWaitSeconds * 1000L, maxOf(20_000, settings.saveWaitSeconds * 2000L)))) {
            throw RuntimeException("秀米登录态仍在初始化，未确认进入“我的秀米”。")
        }
        log("秀米：已确认登录状态")

        val paperState = uploader.clickUiCandidates(
            listOf("图文排版"),
            excludeTerms = listOf("选择编辑器", "模板", "教程"),
        )
        if (((paperState["clicked"] as? Number)?.toInt() ?: 0) > 0) {
            log("秀米：已进入图文排版")
            delay(2000)
            dismissRecoverDialog()
            if (waitEditorReady(3000)) return
        }

        if (waitEditorReady(2000)) return

        val createSteps = listOf(
            listOf("新建图文", "创建图文", "新建空白图文", "空白图文"),
            listOf("新建", "空白"),
        )
        val exclude = listOf("保存", "预览", "删除", "导出", "登录", "注册", "会员", "教程", "模板", "选择编辑器", "图文排版")
        for (terms in createSteps) {
            val state = uploader.clickUiCandidates(terms, excludeTerms = exclude)
            if (((state["clicked"] as? Number)?.toInt() ?: 0) > 0) {
                log("秀米：已新建图文")
                delay(1000)
                uploader.clickUiCandidates(
                    listOf("图文排版", "图文", "公众号图文"),
                    excludeTerms = listOf("H5", "设计", "文档", "模板", "教程", "返回", "取消"),
                )
                val deadline = SystemClock.elapsedRealtime() + settings.saveWaitSeconds * 1000L
                while (SystemClock.elapsedRealtime() < deadline) {
                    if (waitEditorReady(2000)) {
                        ensureLoggedInBeforeEdit("editor_ready")
                        return
                    }
                    delay(1000)
                }
            }
        }
        throw RuntimeException("未能在“我的秀米”页面找到可用的新建图文入口，请检查页面状态或更新首页地址。")
    }

    /** `_ensure_xiumi_logged_in_before_edit`。 */
    private suspend fun ensureLoggedInBeforeEdit(contextLabel: String) {
        val state = loginState()
        if (state.authenticated) return
        if (state.loginControls.isNotEmpty() || state.headerLoginControls.isNotEmpty()) {
            throw RuntimeException("秀米尚未登录，页面仍显示登录入口，已停止自动编辑。context=$contextLabel")
        }
        throw RuntimeException("秀米登录状态未确认，已停止自动编辑。context=$contextLabel")
    }

    // ── 字段 / 正文 ──

    /** `_fill_xiumi_fields`。 */
    suspend fun fillFields(title: String, author: String, sourceUrl: String, digest: String) {
        runCatching { eval(JsBridge.withArgs(XiumiJs.SET_INPUT_VALUE_FN, listOf("input.title", title))) }
        runCatching { eval(JsBridge.withArgs(XiumiJs.SET_INPUT_VALUE_FN, listOf("input.author", author))) }
        if (sourceUrl.isNotEmpty()) {
            runCatching { eval(JsBridge.withArgs(XiumiJs.SET_INPUT_VALUE_FN, listOf("input.link", sourceUrl))) }
        }
        if (digest.isNotEmpty()) {
            runCatching { eval(JsBridge.withArgs(XiumiJs.SET_INPUT_VALUE_FN, listOf("textarea.desc", digest))) }
        }
    }

    /**
     * `_set_editor_html` 的 WebView 实现：模型直构 comps（PRIMARY）。
     * 无 section 结构的 HTML 退化为单个文本 comp（flattenInnerHtml 保 p/span 等）。
     */
    suspend fun setEditorHtml(htmlText: String): Boolean {
        val blocks = HtmlPrepare.htmlToBlocks(htmlText)
        val effective = if (blocks.isNotEmpty()) blocks else listOf(
            HtmlPrepare.Block(style = emptyMap(), text = HtmlPrepare.flattenInnerHtml(htmlText)),
        )
        return buildCompsFromBlocks(effective)
    }

    /** `_build_xiumi_comps_from_blocks`。 */
    suspend fun buildCompsFromBlocks(blocks: List<HtmlPrepare.Block>): Boolean {
        val payload = blocks.map { mapOf("style" to it.style, "text" to it.text) }
        val result = runCatching {
            eval(JsBridge.withArgs(XiumiJs.BUILD_COMPS_FROM_BLOCKS_FN, listOf(payload))) as? JSONObject
        }.getOrNull() ?: return false
        return result.optBoolean("ok", false)
    }

    /** `_mark_xiumi_document_dirty`。 */
    suspend fun markDirty(): Map<String, Any?> {
        val result = runCatching { eval(XiumiJs.MARK_DOCUMENT_DIRTY) as? JSONObject }.getOrNull()
        return result?.toMap() ?: emptyMap()
    }

    /**
     * `_fill_xiumi_body_then_images` 的 WebView 版：
     * 占位直构 → 上传 → 按 HTML 顺序重写 → 重建 comps → 标记脏。
     */
    suspend fun fillBody(contentHtml: String, baseDir: File, uploadProbe: Boolean): Boolean {
        val textFirstHtml = HtmlPrepare.replaceImagesWithPlaceholdersForXiumi(contentHtml)
        var modelApplied = setEditorHtml(textFirstHtml)
        log("秀米：正在写入正文文字")

        var uploadState: Map<String, Any?> = mapOf("status" to "skipped", "uploaded" to 0, "total" to 0)
        if (settings.imageMode.trim().lowercase() == "upload") {
            if (uploadProbe) {
                // 探针上传：临时小图验证链路（HtmlPrepare.writeProbeImage）
                val probe = HtmlPrepare.writeProbeImage(File(baseDir, "xiumi_probe").apply { mkdirs() })
                val probeUrl = uploader.uploadOneImage(probe)
                if (probeUrl.isEmpty()) {
                    log("秀米：测试图片上传失败，跳过正文图片上传。")
                    uploadState = mapOf(
                        "status" to "probe_failed", "uploaded" to 0,
                        "total" to HtmlPrepare.imagePayloadStats(contentHtml).imageCount,
                    )
                    val finalHtml = HtmlPrepare.removeImagesForXiumi(contentHtml)
                    modelApplied = setEditorHtml(finalHtml)
                    markDirty()
                    return modelApplied
                }
            }
            log("秀米：正在上传正文图片")
            val outcome = uploader.uploadImagesAndRewrite(contentHtml, baseDir)
            uploadState = mapOf(
                "status" to outcome.status,
                "uploaded" to outcome.uploaded,
                "total" to outcome.total,
            )
            if (outcome.html != textFirstHtml) {
                log("秀米：正在应用最终排版")
                modelApplied = setEditorHtml(outcome.html)
            }
        }

        markDirty()
        return modelApplied
    }

    // ── 保存 ──

    /** `_click_save` + `_wait_for_save_result`。 */
    suspend fun saveDraft(): Pair<String, String> {
        runCatching { eval(XiumiJs.CLICK_SAVE) }
        val deadline = SystemClock.elapsedRealtime() + settings.saveWaitSeconds * 1000L
        while (SystemClock.elapsedRealtime() < deadline) {
            val url = currentUrl()
            if ("/for/new/" !in url) return "url_changed" to url
            val controls = eval(XiumiJs.VISIBLE_LOGIN_CONTROLS) as? org.json.JSONArray
            val links = eval(XiumiJs.VISIBLE_LOGIN_LINKS) as? org.json.JSONArray
            if ((controls != null && controls.length() > 0) || (links != null && links.length() > 0)) {
                return "login_required" to url
            }
            delay(1000)
        }
        return "timeout" to currentUrl()
    }

    // ── 辅助 ──

    private fun String.replaceSuffix(newSuffix: String): String =
        substringBeforeLast('.', this).let { if (it == this) "$this$newSuffix" else "$it$newSuffix" }

    private fun org.json.JSONArray.toMaps(): List<Map<String, Any?>> =
        (0 until length()).mapNotNull { i ->
            val obj = optJSONObject(i) ?: return@mapNotNull null
            obj.toMap()
        }

    private fun JSONObject.toMap(): Map<String, Any?> {
        val map = HashMap<String, Any?>()
        val keys = keys()
        while (keys.hasNext()) {
            val key = keys.next()
            val value = get(key)
            map[key] = when (value) {
                is JSONObject -> value.toMap()
                is org.json.JSONArray -> (0 until value.length()).map { value.get(it) }
                JSONObject.NULL -> null
                else -> value
            }
        }
        return map
    }
}
