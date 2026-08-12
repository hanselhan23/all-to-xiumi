package com.hanselhan.wanyou.publish

import android.util.Base64
import android.webkit.WebView
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException
import kotlinx.coroutines.suspendCancellableCoroutine
import org.json.JSONArray
import org.json.JSONTokener

/**
 * WebView `evaluateJavascript` 的 Kotlin 封装。
 *
 * Python 版用 Selenium 的 `execute_script(script, args...)`，参数经
 * `arguments[i]` 传入；WebView 的 `evaluateJavascript` 没有参数通道，
 * 这里把参数编码为 base64 JSON 内嵌进脚本（`JSON.parse(atob(...))`），
 * base64 字符集不含引号，天然免转义。
 */
object JsBridge {

    /**
     * 把以 `function(a, b, ...) { ... }` 形式编写的片段包装成可执行脚本：
     * `(function(...) {...}).apply(null, JSON.parse(atob('<base64 json>')));`
     */
    fun withArgs(functionJs: String, args: List<Any?>): String {
        val payload = Base64.encodeToString(
            JSONArray(args).toString().toByteArray(Charsets.UTF_8),
            Base64.NO_WRAP,
        )
        return "($functionJs).apply(null, JSON.parse(atob('$payload')));"
    }

    /**
     * 在主线程求值一段 JS，返回解码后的值（JSONObject/JSONArray/String/…/null）。
     * 页面返回 `undefined` 时 WebView 给 `"null"`，同样映射为 null。
     */
    suspend fun WebView.evalJs(script: String): Any? = suspendCancellableCoroutine { cont ->
        try {
            evaluateJavascript(script) { raw ->
                if (cont.isActive) cont.resume(decode(raw))
            }
        } catch (e: Exception) {
            if (cont.isActive) cont.resumeWithException(e)
        }
    }

    /** 解码 evaluateJavascript 的 JSON 编码返回值。 */
    fun decode(raw: String?): Any? {
        if (raw == null || raw == "null") return null
        return try {
            JSONTokener(raw).nextValue()
        } catch (e: Exception) {
            null
        }
    }

    /** 便捷：把返回值安全转成字符串。 */
    fun Any?.asString(): String = when (this) {
        null -> ""
        JSONArray.NULL -> ""
        is String -> this
        else -> toString()
    }
}
