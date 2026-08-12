package com.hanselhan.wanyou.ui

import android.annotation.SuppressLint
import android.app.Application
import android.webkit.CookieManager
import android.webkit.ValueCallback
import android.webkit.WebChromeClient
import android.webkit.WebView
import android.net.Uri
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.hanselhan.wanyou.data.SettingsStore
import com.hanselhan.wanyou.publish.FileChooserBridge
import com.hanselhan.wanyou.publish.XiumiPublisher
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch

/**
 * 应用级 ViewModel：持有 WebView、发布编排器与页面导航状态。
 *
 * WebView 在 VM 生命周期内只创建一次（页面间切换时从 Compose 树摘挂，
 * 内存中的页面状态与 Cookie 会话不丢失）。
 */
class PublishViewModel(application: Application) : AndroidViewModel(application) {

    val settings = SettingsStore(application)
    private val fileChooser = FileChooserBridge()

    @SuppressLint("SetJavaScriptEnabled")
    val webView: WebView = WebView(application).apply {
        // 秀米编辑器是桌面端 Web 应用：JS + DOM 存储 + 桌面 Chrome UA
        settings.javaScriptEnabled = true
        settings.domStorageEnabled = true
        settings.userAgentString = DESKTOP_CHROME_UA
        // 登录态持久化：秀米 Cookie 保存在应用私有目录，下次发布免登录
        CookieManager.getInstance().apply {
            setAcceptCookie(true)
            setAcceptThirdPartyCookies(this@apply, true)
        }
        webChromeClient = object : WebChromeClient() {
            override fun onShowFileChooser(
                view: WebView?,
                filePathCallback: ValueCallback<Array<Uri>>?,
                fileChooserParams: FileChooserParams?,
            ): Boolean = fileChooser.onShowFileChooser(filePathCallback, fileChooserParams)
        }
    }

    val publisher = XiumiPublisher(application, webView, settings, fileChooser)

    val logLines: StateFlow<List<String>> get() = publisher.logLines
    val phase: StateFlow<String> get() = publisher.phase

    // ── 导航 ──

    sealed interface Screen {
        object Home : Screen
        object Publish : Screen
        object Settings : Screen
    }

    var screen by mutableStateOf<Screen>(Screen.Home)
        private set

    fun navigate(target: Screen) {
        screen = target
    }

    // ── 发布状态 ──

    var running by mutableStateOf(false)
        private set

    var result by mutableStateOf<XiumiPublisher.PublishResult?>(null)
        private set

    /** 启动发布（协程跑在 Main dispatcher，满足 WebView 主线程约束）。 */
    fun publish(request: XiumiPublisher.PublishRequest) {
        if (running) return
        running = true
        result = null
        screen = Screen.Publish
        viewModelScope.launch {
            try {
                result = publisher.publish(request)
            } finally {
                running = false
            }
        }
    }

    /** Activity 结束时释放 WebView 原生资源。 */
    fun releaseWebView() {
        webView.destroy()
    }

    companion object {
        /**
         * 桌面 Chrome UA —— 秀米编辑器按桌面端布局渲染；
         * 移动端 UA 会触发其移动版页面（无图文编辑器）。
         */
        private const val DESKTOP_CHROME_UA =
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 " +
                "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    }
}
