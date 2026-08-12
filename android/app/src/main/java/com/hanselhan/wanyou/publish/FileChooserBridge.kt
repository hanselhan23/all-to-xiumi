package com.hanselhan.wanyou.publish

import android.net.Uri
import android.os.SystemClock
import android.webkit.ValueCallback
import android.webkit.WebChromeClient
import android.webkit.WebView

/**
 * 秀米图片上传的文件选择器桥。
 *
 * Python 版用 Selenium `send_keys` / CDP `DOM.setFileInputFiles` 直接给
 * `input[type="file"]` 塞文件；WebView 里这不可行——文件只能经
 * `WebChromeClient.onShowFileChooser` 的 `ValueCallback` 供给。
 *
 * 流程：
 * 1. Kotlin 侧把待上传图片复制到 `cacheDir/xiumi_upload/`，做成 content URI
 *    （FileProvider 授权）；
 * 2. JS 激活页面的上传控件 → 触发 [onShowFileChooser]，回调在此挂起；
 * 3. Kotlin 侧调用 [supplyFiles] 把 content URI 交给 WebView；
 * 4. JS 派发 input/change 事件（[XiumiJs.DISPATCH_FILE_INPUT_EVENTS_FN]）。
 *
 * WebView 的脚本 `el.click()` 对 file input 同样会唤起 onShowFileChooser
 * （与桌面 Chrome 不同，无用户手势限制）；若个别设备上未触发，UI 层会
 * 显示"点击上传"横幅，由用户点击后再重试激活。
 */
class FileChooserBridge {

    class PendingChooser(
        val callback: ValueCallback<Array<Uri>>?,
        val params: WebChromeClient.FileChooserParams?,
        val startedAtMs: Long,
    )

    @Volatile
    var pending: PendingChooser? = null
        private set

    /** 是否正在等待文件供给。 */
    val hasPending: Boolean get() = pending != null

    /**
     * 由 WebChromeClient 转发。返回 true 表示由本桥接管；
     * 旧回调先以 null 收尾，避免泄漏。
     */
    fun onShowFileChooser(
        callback: ValueCallback<Array<Uri>>?,
        params: WebChromeClient.FileChooserParams?,
    ): Boolean {
        pending?.callback?.onReceiveValue(null)
        pending = PendingChooser(callback, params, SystemClock.elapsedRealtime())
        return true
    }

    /** 供给文件（content URI 数组）。null 表示取消。 */
    fun supplyFiles(uris: Array<Uri>?) {
        val chooser = pending ?: return
        pending = null
        chooser.callback?.onReceiveValue(uris)
    }

    /** 取消挂起的文件选择（如上传中止、页面跳转）。 */
    fun cancel() = supplyFiles(null)
}
