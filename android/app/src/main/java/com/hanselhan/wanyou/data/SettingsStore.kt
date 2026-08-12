package com.hanselhan.wanyou.data

import android.content.Context
import android.content.SharedPreferences

/**
 * 应用设置 —— 对应 Python 端 `all_to_xiumi/config.py` 的秀米相关配置项。
 *
 * 当前阶段无 API key 类机密，用普通 SharedPreferences；
 * 后续接入 Wanyou LLM 流水线时，密钥类改用 EncryptedSharedPreferences
 * （依赖 androidx.security:security-crypto 已就位）。
 */
class SettingsStore(context: Context) {

    private val prefs: SharedPreferences =
        context.applicationContext.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)

    // ── 秀米自动化 ──

    /** 秀米首页/编辑器地址（Python: XIUMI_HOME_URL）。 */
    var xiumiHomeUrl: String
        get() = prefs.getString(KEY_HOME_URL, DEFAULT_HOME_URL) ?: DEFAULT_HOME_URL
        set(value) = prefs.edit().putString(KEY_HOME_URL, value).apply()

    /** 保存后等待草稿 URL 生成的秒数（Python: XIUMI_SAVE_WAIT_SECONDS）。 */
    var saveWaitSeconds: Int
        get() = prefs.getInt(KEY_SAVE_WAIT, 30)
        set(value) = prefs.edit().putInt(KEY_SAVE_WAIT, value).apply()

    /** 登录等待秒数（Python: XIUMI_LOGIN_WAIT_SECONDS）。 */
    var loginWaitSeconds: Int
        get() = prefs.getInt(KEY_LOGIN_WAIT, 600)
        set(value) = prefs.edit().putInt(KEY_LOGIN_WAIT, value).apply()

    /** 图片模式：upload / skip（Python: XIUMI_IMAGE_MODE）。 */
    var imageMode: String
        get() = prefs.getString(KEY_IMAGE_MODE, "upload") ?: "upload"
        set(value) = prefs.edit().putString(KEY_IMAGE_MODE, value).apply()

    /** 上传停滞判定秒数（Python: XIUMI_IMAGE_UPLOAD_STALL_SECONDS）。 */
    var imageUploadStallSeconds: Int
        get() = prefs.getInt(KEY_UPLOAD_STALL, 180)
        set(value) = prefs.edit().putInt(KEY_UPLOAD_STALL, value).apply()

    /** 连续失败多少次中止上传（Python: XIUMI_IMAGE_UPLOAD_MAX_FAILURES）。 */
    var imageUploadMaxFailures: Int
        get() = prefs.getInt(KEY_UPLOAD_MAX_FAILURES, 3)
        set(value) = prefs.edit().putInt(KEY_UPLOAD_MAX_FAILURES, value).apply()

    /** 单张上传重试次数（Python: XIUMI_IMAGE_UPLOAD_RETRIES）。 */
    var imageUploadRetries: Int
        get() = prefs.getInt(KEY_UPLOAD_RETRIES, 2)
        set(value) = prefs.edit().putInt(KEY_UPLOAD_RETRIES, value).apply()

    /** 批量上传大小（Python: XIUMI_IMAGE_UPLOAD_BATCH_SIZE）。 */
    var imageUploadBatchSize: Int
        get() = prefs.getInt(KEY_UPLOAD_BATCH_SIZE, 6)
        set(value) = prefs.edit().putInt(KEY_UPLOAD_BATCH_SIZE, value).apply()

    // ── 发布默认值 ──

    var defaultTitle: String
        get() = prefs.getString(KEY_DEFAULT_TITLE, "万有预报") ?: "万有预报"
        set(value) = prefs.edit().putString(KEY_DEFAULT_TITLE, value).apply()

    var defaultAuthor: String
        get() = prefs.getString(KEY_DEFAULT_AUTHOR, "物理系学生会") ?: "物理系学生会"
        set(value) = prefs.edit().putString(KEY_DEFAULT_AUTHOR, value).apply()

    /** 是否先应用秀米基础格式（Python: apply_base_format）。 */
    var applyBaseFormat: Boolean
        get() = prefs.getBoolean(KEY_APPLY_BASE_FORMAT, true)
        set(value) = prefs.edit().putBoolean(KEY_APPLY_BASE_FORMAT, value).apply()

    /** 是否保留设计稿样式（Python: preserve_styles，模型直构模式）。 */
    var preserveStyles: Boolean
        get() = prefs.getBoolean(KEY_PRESERVE_STYLES, false)
        set(value) = prefs.edit().putBoolean(KEY_PRESERVE_STYLES, value).apply()

    companion object {
        private const val PREFS_NAME = "wanyou_settings"
        private const val DEFAULT_HOME_URL = "https://xiumi.us/studio/v5?lang=zh_CN#/"
        private const val KEY_HOME_URL = "xiumi_home_url"
        private const val KEY_SAVE_WAIT = "xiumi_save_wait"
        private const val KEY_LOGIN_WAIT = "xiumi_login_wait"
        private const val KEY_IMAGE_MODE = "xiumi_image_mode"
        private const val KEY_UPLOAD_STALL = "xiumi_upload_stall"
        private const val KEY_UPLOAD_MAX_FAILURES = "xiumi_upload_max_failures"
        private const val KEY_UPLOAD_RETRIES = "xiumi_upload_retries"
        private const val KEY_UPLOAD_BATCH_SIZE = "xiumi_upload_batch_size"
        private const val KEY_DEFAULT_TITLE = "default_title"
        private const val KEY_DEFAULT_AUTHOR = "default_author"
        private const val KEY_APPLY_BASE_FORMAT = "apply_base_format"
        private const val KEY_PRESERVE_STYLES = "preserve_styles"
    }
}
