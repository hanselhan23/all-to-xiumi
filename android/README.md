# android/ — 万有预报 · 秀米发布（Android 应用）

all-to-xiumi 与 Wanyou 的 Android 实现（第一期：工程骨架 + 秀米发布核心）。

## 构建（需 JDK 17 + Android SDK 35，本机暂缺时在 Android Studio 中打开此目录即可）

```powershell
cd android
.\gradlew.bat testDebugUnitTest   # 金标单元测试（纯 JVM，无需设备）
.\gradlew.bat assembleDebug       # 产出 app/build/outputs/apk/debug/app-debug.apk
```

## 与 Python 版的对应关系

| Python（`all-to-xiumi` / `Wanyou`） | Android（本目录） |
| --- | --- |
| `markdown_to_html` + 三套模板 | `markdown/MarkdownToHtml.kt`、`Templates.kt` |
| `image_paths` | `markdown/ImagePaths.kt` |
| `xiumi_publish` 纯 HTML 预处理 | `publish/HtmlPrepare.kt` |
| Selenium + CDP 编辑器自动化 | `publish/XiumiPublisher.kt` + `XiumiUploader.kt` + WebView JS 注入 |
| `xiumi_publish` JS 片段 | `publish/XiumiJs.kt`（经 `JsBridge.withArgs` 参数化） |

金标测试向量由 `tools/gen_golden_tests.py` 生成（需 Python 环境），
生成后 `app/src/test/resources/golden/` 应与 Python 实现逐字节一致。

## WebView 自动化要点（秀米编辑器陷阱的对应方案）

- **正文注入**：直接 `innerHTML`/execCommand 会落进 `_qiBlock`、保存后不渲染。
  方案为模型直构 comps（`BUILD_COMPS_FROM_BLOCKS_FN`）：找到 Angular scope
  （`s.cell` 存在），清空 `layer._qiBlock.items`，写入
  `scope._$.pages[0].layers[0].comps`（text-first 模式先传图、再以最终 HTML 重建）。
- **图片上传**：WebView 无 CDP `setFileInputFiles`。JS `el.click()` 唤起
  `onShowFileChooser`（WebView 无用户手势限制）→ Kotlin 复制图片到
  `cacheDir/xiumi_upload/` → FileProvider content URI 供给 → 派发 input/change 事件
  → fetch/XHR 观察器（`__wanyouXiumiUploadEvents`）轮询 CDN URL → 按 HTML 顺序重写。
- **登录**：用户在 WebView 内手动完成（Cookie 持久化，二次发布免登录），
  Kotlin 侧轮询登录态（我的秀米/图文排版入口 + 登录控件 + 文案摘录）。
- **桌面 UA**：秀米编辑器是桌面端 Web 应用，WebView 固定使用桌面 Chrome UA。
- **线程**：`loadUrl`/`evaluateJavascript` 必须主线程；发布流程运行在
  Main dispatcher 协程（`PublishViewModel.viewModelScope`）。

## 页面

- 首页：Markdown（模板渲染）或 HTML 文件路径 → 标题/作者/摘要/原文链接 → 发布
- 发布页：秀米 WebView 实况 + 阶段/日志浮层 + 结果横幅（复制草稿链接）
- 设置页：秀米首页地址、保存/登录等待、图片模式与上传参数、默认值

## 已知限制（第一期）

- 仅在真机/模拟器手动验证过前请勿直接用于正式发布；
- 部分设备上 WebView `el.click()` 可能不唤起文件选择器，上传链路有兜底重试与
  逐张降级，且失败图片会保留占位提示（不丢内容）；
- Wanyou 抓取/LLM 流水线（预报自动生成）留待后续迭代。
