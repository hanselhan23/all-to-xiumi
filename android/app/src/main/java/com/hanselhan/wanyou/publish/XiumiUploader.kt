package com.hanselhan.wanyou.publish

import android.content.Context
import android.net.Uri
import android.os.SystemClock
import android.webkit.WebView
import androidx.core.content.FileProvider
import com.hanselhan.wanyou.data.SettingsStore
import com.hanselhan.wanyou.publish.JsBridge.asString
import com.hanselhan.wanyou.publish.JsBridge.evalJs
import java.io.File
import kotlinx.coroutines.delay
import org.json.JSONArray
import org.json.JSONObject

/**
 * 秀米图片上传子系统 —— `xiumi_publish.py` 上传链路的 WebView 移植。
 *
 * 与 Python 版的差异：
 * - 文件经 [FileChooserBridge] 以 content URI 供给（Python: send_keys/CDP）；
 * - `input[type="file"]` 用 DOM 序号定位（Python: WebElement 引用）；
 * - 轮询等待一律用协程 `delay`（Python: time.sleep 轮询循环）。
 */
class XiumiUploader(
    private val context: Context,
    private val webView: WebView,
    private val fileChooser: FileChooserBridge,
    private val settings: SettingsStore,
    private val log: (String) -> Unit = {},
) {

    data class UploadState(
        val busy: Boolean,
        val failed: Boolean,
        val success: Boolean,
        val successCount: Int,
        val messages: List<String>,
    )

    data class UploadOutcome(
        val status: String,   // ok / partial / failed / skipped / no_images
        val html: String,
        val uploaded: Int,
        val total: Int,
    )

    // ── 页面状态 ──

    private suspend fun eval(script: String): Any? = webView.evalJs(script)

    private suspend fun evalBool(script: String): Boolean = eval(script) == true

    private suspend fun evalInt(script: String): Int =
        (eval(script) as? Number)?.toInt() ?: 0

    private suspend fun evalStr(script: String): String = eval(script).asString()

    /** 安装 fetch/XHR 上传观察器（幂等）。 */
    suspend fun installObserver() {
        runCatching { eval(XiumiJs.UPLOAD_OBSERVER_INSTALL) }
    }

    /** 上传事件数（`_xiumi_upload_event_count`）。 */
    suspend fun uploadEventCount(): Int = runCatching {
        (eval(XiumiJs.UPLOAD_EVENTS) as? JSONArray)?.length() ?: 0
    }.getOrDefault(0)

    /** 页面中全部远程图片 src（有序、去重）。 */
    suspend fun remoteImageSources(): List<String> = runCatching {
        val arr = eval(XiumiJs.REMOTE_IMAGE_SOURCES) as? JSONArray ?: JSONArray()
        val out = mutableListOf<String>()
        val seen = mutableSetOf<String>()
        for (i in 0 until arr.length()) {
            val text = arr.optString(i)
            if (text.isNotEmpty() && seen.add(text)) out.add(text)
        }
        out
    }.getOrDefault(emptyList())

    /** 页面可见的上传提示文案 → 上传状态（`_xiumi_upload_state`）。 */
    suspend fun uploadState(): UploadState = runCatching {
        val messages = (eval(XiumiJs.UPLOAD_MESSAGES) as? JSONArray)?.let { arr ->
            (0 until arr.length()).map { arr.optString(i) }.filter { it.isNotEmpty() }
        } ?: emptyList()
        val text = messages.joinToString("\n")
        val busy = Regex("(正在上传|上传中|请稍后再试|稍后再试)", RegexOption.IGNORE_CASE).containsMatchIn(text)
        val failed = Regex("(上传失败|失败|错误|超过|太大|超出|大小限制|不支持|MB)", RegexOption.IGNORE_CASE).containsMatchIn(text)
        val successCounts = Regex("(\\d+)\\s*张(?:图片)?上传成功").findAll(text)
            .map { it.groupValues[1].toIntOrNull() ?: 0 }.toList()
        val success = successCounts.isNotEmpty() ||
            Regex("(上传成功|上传完成|已上传)", RegexOption.IGNORE_CASE).containsMatchIn(text)
        UploadState(
            busy = busy,
            failed = failed,
            success = success,
            successCount = successCounts.maxOrNull() ?: 0,
            messages = messages,
        )
    }.getOrDefault(UploadState(false, false, false, 0, emptyList()))

    /** 观察器记录的上传资产（`_xiumi_observed_upload_assets`）。 */
    suspend fun observedAssets(since: Int): List<Map<String, Any?>> = runCatching {
        val events = eval(XiumiJs.UPLOAD_EVENTS) as? JSONArray ?: JSONArray()
        val assets = mutableListOf<Map<String, Any?>>()
        val seen = mutableSetOf<String>()
        for (i in maxOf(0, since) until events.length()) {
            val event = events.optJSONObject(i) ?: continue
            val files = (event.optJSONArray("files") ?: JSONArray()).let { arr ->
                (0 until arr.length()).map { arr.optString(it) }.filter { it.isNotEmpty() }
            }
            for (value in listOf(event.optString("url"), event.optString("body"))) {
                for (url in HtmlPrepare.xiumiImageUrlsFromText(value)) {
                    val key = url + "|" + files.joinToString("\u0000")
                    if (seen.add(key)) {
                        assets.add(mapOf(
                            "url" to url,
                            "text" to files.joinToString(" "),
                            "files" to files,
                            "source" to "observer",
                        ))
                    }
                }
            }
        }
        assets
    }.getOrDefault(emptyList())

    /** 图库 DOM/Angular 资产（`_xiumi_gallery_assets`）。 */
    suspend fun galleryAssets(): List<Map<String, Any?>> = runCatching {
        val arr = eval(XiumiJs.GALLERY_ASSETS) as? JSONArray ?: JSONArray()
        (0 until arr.length()).mapNotNull { i ->
            val item = arr.optJSONObject(i) ?: return@mapNotNull null
            if (!HtmlPrepare.looksLikeUserXiumiImage(item.optString("url"))) return@mapNotNull null
            mapOf(
                "url" to item.optString("url"),
                "text" to item.optString("text"),
                "files" to emptyList<String>(),
                "source" to item.optString("source"),
            )
        }
    }.getOrDefault(emptyList())

    /** `_xiumi_uploaded_urls_for_paths`：按文件名把资产 URL 匹配回待传路径。 */
    suspend fun uploadedUrlsForPaths(
        imagePaths: List<File>,
        observedSince: Int = 0,
    ): List<String> = runCatching {
        val assets = observedAssets(observedSince) + galleryAssets()
        val matched = HashMap<Int, String>()
        for (asset in assets) {
            val url = HtmlPrepare.normalizeXiumiImageUrl(asset["url"]?.toString() ?: "")
            if (url.isEmpty()) continue
            var bestIndex = -1
            var bestScore = 0
            for ((index, path) in imagePaths.withIndex()) {
                if (index in matched) continue
                val (isMatch, score) = HtmlPrepare.assetMatchesUploadPath(asset, path)
                if (isMatch && score > bestScore) {
                    bestIndex = index
                    bestScore = score
                }
            }
            if (bestIndex >= 0) matched[bestIndex] = url
        }
        val orderedByIndex = imagePaths.indices.map { matched[it] ?: "" }
        if (orderedByIndex.all { it.isNotEmpty() }) orderedByIndex
        else orderedByIndex.filter { it.isNotEmpty() }
    }.getOrDefault(emptyList())

    // ── 文件输入 ──

    private suspend fun fileInputCount(): Int = runCatching { evalInt(XiumiJs.FILE_INPUT_COUNT) }.getOrDefault(0)

    private suspend fun fileInputDiagnostics(): List<JSONObject> = runCatching {
        val arr = eval(XiumiJs.FILE_INPUT_DIAGNOSTICS) as? JSONArray ?: JSONArray()
        (0 until arr.length()).mapNotNull { arr.optJSONObject(it) }
    }.getOrDefault(emptyList())

    /** `_open_xiumi_image_library`：点击图库与上传入口。 */
    suspend fun openImageLibrary(): Map<String, Any?> {
        val state = mutableMapOf<String, Any?>("gallery" to 0, "upload_button" to 0)
        state["file_inputs_before"] = fileInputCount()
        val exclude = listOf("保存", "预览", "导出", "关闭", "删除", "推送", "上传推送", "打开", "save", "preview", "export", "close", "delete")
        val steps = listOf(
            "gallery" to listOf("我的图库", "图库", "图片库"),
            "upload_button" to listOf("上传图片", "无水印", "图片上传"),
        )
        for ((key, terms) in steps) {
            val result = clickUiCandidates(terms, exclude, limit = 1)
            val clicked = ((result["clicked"] as? Number)?.toInt() ?: 0)
            state[key] = (state[key] as? Int ?: 0) + clicked
            if (clicked > 0) delay(800)
        }
        state["file_inputs_after"] = fileInputCount()
        return state
    }

    /** `_find_image_file_input`：定位图片上传用的 file input（返回 DOM 序号）。 */
    suspend fun findImageFileInput(): Pair<Int?, Map<String, Any?>> {
        val libraryState = openImageLibrary()
        val inputs = fileInputCount()
        val diagnostics = fileInputDiagnostics()
        val metaByIndex = diagnostics.associateBy { it.optInt("index", -1) }

        data class Ranked(val score: Int, val index: Int)
        val ranked = mutableListOf<Ranked>()
        for ((index, meta) in metaByIndex) {
            if (index < 0 || index >= inputs) continue
            val accept = meta.optString("accept")
            val isImageInput = Regex("(?:image|\\.png|\\.jpe?g|\\.gif)", RegexOption.IGNORE_CASE).containsMatchIn(accept)
            if (!isImageInput) continue

            val text = listOf("id", "name", "className", "parentClass", "parentText")
                .joinToString(" ") { meta.optString(it) }.lowercase()
            var score = index
            score += 100
            val inputId = meta.optString("id")
            if (inputId == "imageFileUploadInput") score += 80
            if (inputId == "teamImageFileUploadInput") score -= 60
            if (!meta.optBoolean("disabled")) score += 20
            if (meta.optBoolean("visible")) score += 40
            if (meta.optBoolean("multiple")) score += 15
            if ("无水印" in meta.optString("parentText")) score += 40
            if (listOf("上传", "图片", "图库", "image", "img", "pic", "upload", "gallery").any { it in text }) score += 30
            if (listOf("team", "团队", "cover", "封面", "video", "audio", "file-attachment", "附件").any { it in text }) score -= 80
            ranked.add(Ranked(score, index))
        }
        val chosen = ranked.maxByOrNull { it.score }
        return chosen?.index to libraryState
    }

    private suspend fun inputState(index: Int): JSONObject = runCatching {
        (eval(JsBridge.withArgs(XiumiJs.FILE_INPUT_STATE_FN, listOf(index))) as? JSONObject) ?: JSONObject()
    }.getOrDefault(JSONObject())

    private suspend fun prepareInput(index: Int) {
        runCatching { eval(JsBridge.withArgs(XiumiJs.PREPARE_FILE_INPUT_FN, listOf(index))) }
    }

    private suspend fun activateUploadControl(index: Int): JSONObject = runCatching {
        (eval(JsBridge.withArgs(XiumiJs.ACTIVATE_FILE_UPLOAD_CONTROL_FN, listOf(index))) as? JSONObject) ?: JSONObject()
    }.getOrDefault(JSONObject())

    private suspend fun dispatchInputEvents(index: Int) {
        runCatching { eval(JsBridge.withArgs(XiumiJs.DISPATCH_FILE_INPUT_EVENTS_FN, listOf(index))) }
    }

    // ── 文件供给（WebView 特有） ──

    private fun copyToUploadCache(file: File): Uri {
        val dir = File(context.cacheDir, "xiumi_upload").apply { mkdirs() }
        val target = File(dir, file.name)
        if (!target.exists() || target.length() != file.length()) {
            file.copyTo(target, overwrite = true)
        }
        return FileProvider.getUriForFile(
            context,
            "${context.packageName}.fileprovider",
            target,
        )
    }

    /** 等待 onShowFileChooser 回调挂起。 */
    private suspend fun waitForChooser(timeoutMs: Long): Boolean {
        val deadline = SystemClock.elapsedRealtime() + timeoutMs
        while (SystemClock.elapsedRealtime() < deadline) {
            if (fileChooser.hasPending) return true
            delay(100)
        }
        return false
    }

    /** 等待 input.files 数量到位。 */
    private suspend fun waitForFilesLength(index: Int, expected: Int, timeoutMs: Long): Boolean {
        val deadline = SystemClock.elapsedRealtime() + timeoutMs
        while (SystemClock.elapsedRealtime() < deadline) {
            val state = inputState(index)
            if (state.optInt("filesLength", -1) >= expected) return true
            delay(200)
        }
        return false
    }

    /**
     * `_attach_files_to_input` 的 WebView 实现：
     * 复制到缓存目录 → 激活控件（触发文件选择器）→ 供给 content URI →
     * 派发 input/change 事件 → 确认 files 到账。
     */
    suspend fun supplyFilesToInput(index: Int, files: List<File>): Boolean {
        if (files.isEmpty()) return false
        fileChooser.cancel()
        val uris = files.map { copyToUploadCache(it) }

        prepareInput(index)
        activateUploadControl(index)
        if (!waitForChooser(5_000)) {
            log("：未收到文件选择器回调（部分设备需要点击页面上的上传按钮）")
            return false
        }
        fileChooser.supplyFiles(uris.toTypedArray())
        dispatchInputEvents(index)
        return waitForFilesLength(index, files.size, 8_000)
    }

    // ── UI 候选点击 ──

    /** `_click_xiumi_ui_candidates`。 */
    suspend fun clickUiCandidates(
        includeTerms: List<String>,
        excludeTerms: List<String> = emptyList(),
        limit: Int = 1,
    ): Map<String, Any?> = runCatching {
        val value = eval(JsBridge.withArgs(XiumiJs.CLICK_UI_CANDIDATES_FN, listOf(includeTerms, excludeTerms, limit)))
        if (value is JSONObject) value.toMap()
        else mapOf("clicked" to ((value as? Number)?.toInt() ?: 0), "candidates" to 0, "items" to emptyList<Any>())
    }.getOrDefault(mapOf("clicked" to 0, "candidates" to 0, "items" to emptyList<Any>()))

    // ── 等待 ──

    /** `_wait_xiumi_upload_idle`：等秀米处理完上一批上传。 */
    suspend fun waitUploadIdle(contextLabel: String = "") {
        val stallMs = maxOf(30, settings.imageUploadStallSeconds) * 1000L
        var lastBusy = SystemClock.elapsedRealtime()
        var announced = false
        while (true) {
            val state = uploadState()
            if (!state.busy) return
            if (!announced) {
                log("：秀米仍在处理上一批上传，等待完成")
                announced = true
            }
            if (SystemClock.elapsedRealtime() - lastBusy > stallMs) {
                log("：上传等待超时（$contextLabel），继续")
                return
            }
            delay(600)
        }
    }

    /** `_wait_for_xiumi_uploaded_sources`：等待本批上传的 CDN URL 可确认。 */
    suspend fun waitForUploadedSources(
        before: Set<String>,
        expected: Int,
        contextLabel: String,
        imagePaths: List<File>? = null,
        observedSince: Int = 0,
    ): List<String> {
        val stallMs = maxOf(30, settings.imageUploadStallSeconds) * 1000L
        var lastProgress = SystemClock.elapsedRealtime()
        var lastCount = -1
        var lastStateKey = ""
        var announcedBusy = false
        var lastResolveAt = 0L
        var lastNamedSources = emptyList<String>()

        while (true) {
            val now = SystemClock.elapsedRealtime()
            val afterOrdered = remoteImageSources()
            val newSources = afterOrdered.filter { it.isNotEmpty() && it !in before && !it.startsWith("data:") }
            val userSources = newSources
                .filter { HtmlPrepare.looksLikeUserXiumiImage(it) }
                .map { HtmlPrepare.normalizeXiumiImageUrl(it) }
                .toMutableList()
            val state = uploadState()
            var namedSources = emptyList<String>()
            val shouldResolve = imagePaths != null && (
                userSources.size >= expected ||
                    state.success ||
                    state.successCount > 0 ||
                    newSources.isNotEmpty() ||
                    now - lastResolveAt > 5000
                )
            if (shouldResolve) {
                lastResolveAt = now
                namedSources = uploadedUrlsForPaths(imagePaths ?: emptyList(), observedSince)
                if (namedSources.isNotEmpty()) lastNamedSources = namedSources
                for (url in namedSources) {
                    if (url !in userSources) userSources.add(url)
                }
            }

            val stateKey = listOf(newSources.size, userSources.size, state.busy, state.success, state.failed, state.successCount).joinToString("|")
            if (state.busy && !announcedBusy) {
                log("：等待秀米完成当前上传")
                announcedBusy = true
            }
            if (userSources.size != lastCount || stateKey != lastStateKey) {
                lastProgress = now
                lastCount = userSources.size
                lastStateKey = stateKey
            }

            if (state.failed) {
                return if (imagePaths != null) namedSources else userSources
            }

            // 空闲且报告部分成功（如个别图片过大失败）——按已确认的返回
            val settledCount = state.successCount
            if (settledCount > 0 && !state.busy) {
                val result = if (imagePaths != null) namedSources else userSources
                if (result.isNotEmpty()) return result
            }

            if (namedSources.size >= expected && !state.busy) {
                return namedSources.takeLast(expected)
            }

            if (imagePaths != null && userSources.size >= expected && !state.busy && namedSources.isEmpty()) {
                log("：上传完成但未按文件名匹配到 URL（$contextLabel）")
                return emptyList()
            }

            if (imagePaths != null) {
                if (now - lastProgress > stallMs) return lastNamedSources
                delay(600)
                continue
            }

            if (userSources.size >= expected && !state.busy) {
                return userSources.takeLast(expected)
            }

            val genericSingleSuccess = expected == 1 && state.success && !state.busy
            if ((state.successCount >= expected || genericSingleSuccess) && !state.busy) {
                namedSources = uploadedUrlsForPaths(emptyList(), observedSince)
                if (namedSources.size >= expected) return namedSources.takeLast(expected)
                return namedSources
            }

            if (now - lastProgress > stallMs) return userSources

            delay(600)
        }
    }

    // ── 上传入口 ──

    /** `_upload_one_xiumi_image`。 */
    suspend fun uploadOneImage(imagePath: File): String {
        waitUploadIdle(contextLabel = "before_single:${imagePath.name}")
        val (inputIndex, libraryState) = findImageFileInput()
        if (inputIndex == null) {
            log("：上传入口不可用（${imagePath.name}）")
            return ""
        }
        val before = remoteImageSources().toSet()
        val observedSince = uploadEventCount()

        val ok = supplyFilesToInput(inputIndex, listOf(imagePath))
        if (!ok) {
            log("：文件供给失败（${imagePath.name}）")
            return ""
        }
        val sources = waitForUploadedSources(
            before, 1,
            contextLabel = "single:${imagePath.name}",
            imagePaths = listOf(imagePath),
            observedSince = observedSince,
        )
        return if (sources.isNotEmpty()) {
            HtmlPrepare.normalizeXiumiImageUrl(sources.last())
        } else {
            log("：上传未确认（${imagePath.name}）")
            ""
        }
    }

    /** `_upload_xiumi_image_batch`。 */
    suspend fun uploadBatch(imagePaths: List<File>): List<String> {
        if (imagePaths.isEmpty()) return emptyList()
        waitUploadIdle(contextLabel = "before_batch:${imagePaths.joinToString(",") { it.name }}")
        val (inputIndex, _) = findImageFileInput()
        if (inputIndex == null) {
            log("：批量上传入口不可用")
            return emptyList()
        }
        val before = remoteImageSources().toSet()
        val observedSince = uploadEventCount()

        if (!supplyFilesToInput(inputIndex, imagePaths)) {
            log("：批量文件供给失败")
            return emptyList()
        }
        val sources = waitForUploadedSources(
            before, imagePaths.size,
            contextLabel = "batch:${imagePaths.joinToString(",") { it.name }}",
            imagePaths = imagePaths,
            observedSince = observedSince,
        )
        return if (sources.size >= imagePaths.size) sources.takeLast(imagePaths.size) else sources
    }

    /** `_upload_xiumi_images_and_rewrite`。 */
    suspend fun uploadImagesAndRewrite(htmlText: String, baseDir: File): UploadOutcome {
        val mode = settings.imageMode.trim().lowercase()
        if (mode != "upload") {
            return UploadOutcome("skipped", htmlText, 0, 0)
        }

        val tempDir = File(context.cacheDir, "xiumi_inline").apply { mkdirs() }
        val htmlOrderEntries = HtmlPrepare.imageEntriesForUpload(htmlText, baseDir, tempDir)
        val uploadEntries = HtmlPrepare.uploadEntriesInSafeOrder(htmlOrderEntries)
        log("：发现 ${uploadEntries.size} 张待上传图片")
        if (uploadEntries.isEmpty()) {
            return UploadOutcome("no_images", htmlText, 0, 0)
        }
        installObserver()

        val urlBySource = HashMap<String, String>()
        val urlByKey = HashMap<String, String>()
        var uploaded = 0
        var failures = 0
        var consecutiveFailures = 0
        val skippedImages = mutableListOf<String>()
        val maxFailures = maxOf(1, settings.imageUploadMaxFailures)
        val retries = maxOf(0, settings.imageUploadRetries)
        val batchSize = maxOf(1, settings.imageUploadBatchSize)
        val totalBatches = (uploadEntries.size + batchSize - 1) / batchSize

        fun recordUpload(entry: HtmlPrepare.UploadEntry, remoteUrl: String) {
            urlBySource[entry.source] = remoteUrl
            if (entry.key.isNotEmpty()) urlByKey[entry.key] = remoteUrl
            uploaded += 1
            consecutiveFailures = 0
        }

        outer@ for ((batchIndex, batch) in uploadEntries.chunked(batchSize).withIndex()) {
            var batchUrls = emptyList<String>()
            if (batch.size > 1) {
                log("：第 ${batchIndex + 1}/$totalBatches 批上传中（${batch.size} 张，已完成 $uploaded/${uploadEntries.size}）")
                batchUrls = uploadBatch(batch.map { it.path })
                if (batchUrls.size == batch.size) {
                    log("：第 ${batchIndex + 1}/$totalBatches 批完成，累计 ${uploaded + batchUrls.size}/${uploadEntries.size}")
                } else {
                    log("：第 ${batchIndex + 1}/$totalBatches 批未完整确认，改为逐张补传")
                    batchUrls = emptyList()
                }
            } else {
                log("：第 ${batchIndex + 1}/$totalBatches 批逐张上传中（已完成 $uploaded/${uploadEntries.size}）")
            }

            if (batchUrls.isNotEmpty()) {
                for ((entry, remoteUrl) in batch.zip(batchUrls)) {
                    recordUpload(entry, remoteUrl)
                }
                continue
            }

            for (entry in batch) {
                var remoteUrl = ""
                for (attempt in 0..retries) {
                    remoteUrl = uploadOneImage(entry.path)
                    if (remoteUrl.isNotEmpty()) break
                    if (attempt < retries) {
                        log("：${entry.path.name} 上传失败，重试 ${attempt + 1}/$retries")
                        delay(1000)
                    }
                }
                if (remoteUrl.isEmpty()) {
                    val state = uploadState()
                    val reason = state.messages.take(2).joinToString("; ").ifEmpty { "未知错误（可能文件过大或格式不支持）" }
                    log("：${entry.path.name} 经 ${retries + 1} 次尝试后仍上传失败：$reason")
                }
                if (remoteUrl.isNotEmpty()) {
                    recordUpload(entry, remoteUrl)
                    log("：已上传 $uploaded/${uploadEntries.size}")
                    continue
                }
                failures += 1
                consecutiveFailures += 1
                skippedImages.add(entry.path.name)
                log("：${entry.path.name} 未确认上传成功，暂跳过（已上传 $uploaded/${uploadEntries.size}，跳过 ${skippedImages.size}）")
                if (uploaded == 0 && consecutiveFailures >= maxFailures) {
                    break@outer
                }
            }
            if (uploaded == 0 && consecutiveFailures >= maxFailures) break
        }

        val status = if (uploaded == uploadEntries.size) "ok" else if (uploaded > 0) "partial" else "failed"
        if (status == "ok") {
            log("：正文图片已上传完成（$uploaded/${uploadEntries.size}）")
        } else if (uploaded > 0) {
            log("：部分正文图片已上传（$uploaded/${uploadEntries.size}），未上传图片将保留提示")
        } else {
            log("：正文图片未能自动上传，将在草稿中保留提示")
        }

        if (uploaded > 0) {
            val rewritten = HtmlPrepare.rewriteImagesByHtmlOrder(htmlText, urlBySource, urlByKey)
            return UploadOutcome(status, HtmlPrepare.removeUnuploadedImagesForXiumi(rewritten), uploaded, uploadEntries.size)
        }
        return UploadOutcome(status, HtmlPrepare.removeImagesForXiumi(htmlText), 0, uploadEntries.size)
    }
}

/** JSONObject → Map（供 [XiumiUploader.clickUiCandidates] 等返回值使用）。 */
private fun JSONObject.toMap(): Map<String, Any?> {
    val map = HashMap<String, Any?>()
    val keys = keys()
    while (keys.hasNext()) {
        val key = keys.next()
        val value = get(key)
        map[key] = when (value) {
            is JSONObject -> value.toMap()
            is JSONArray -> (0 until value.length()).map { value.get(it) }
            JSONObject.NULL -> null
            else -> value
        }
    }
    return map
}
