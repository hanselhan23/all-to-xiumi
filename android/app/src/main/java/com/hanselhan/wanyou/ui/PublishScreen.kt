package com.hanselhan.wanyou.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.compose.foundation.layout.width
import androidx.compose.material3.OutlinedButton

/** 发布页：秀米 WebView（登录/编辑实况）+ 进度浮层 + 日志。 */
@Composable
fun PublishScreen(vm: PublishViewModel) {
    val phase by vm.phase.collectAsState()
    val logLines by vm.logLines.collectAsState()
    val result = vm.result
    var logExpanded by remember { mutableStateOf(false) }
    val clipboard = LocalClipboardManager.current

    Box(Modifier.fillMaxSize()) {
        // WebView：同一个实例，摘挂不丢会话
        AndroidView(
            factory = { vm.webView },
            modifier = Modifier.fillMaxSize(),
        )

        // 顶栏
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .align(Alignment.TopCenter)
                .background(MaterialTheme.colorScheme.surface.copy(alpha = 0.95f))
                .padding(horizontal = 8.dp, vertical = 4.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            TextButton(onClick = { vm.navigate(PublishViewModel.Screen.Home) }) { Text("返回") }
            Text(
                text = phase.ifBlank { "秀米页面" },
                modifier = Modifier.weight(1f),
                style = MaterialTheme.typography.titleSmall,
            )
            if (vm.running) {
                CircularProgressIndicator(Modifier.width(18.dp).height(18.dp))
            }
        }

        // 结果横幅
        result?.let { r ->
            Card(
                modifier = Modifier
                    .fillMaxWidth()
                    .align(Alignment.BottomCenter)
                    .padding(12.dp),
                colors = CardDefaults.cardColors(
                    containerColor = when (r.status) {
                        "saved" -> MaterialTheme.colorScheme.primaryContainer
                        "dry_run" -> MaterialTheme.colorScheme.secondaryContainer
                        else -> MaterialTheme.colorScheme.errorContainer
                    },
                ),
            ) {
                Column(Modifier.padding(12.dp)) {
                    Text(
                        text = when (r.status) {
                            "saved" -> "✅ 草稿已保存"
                            "dry_run" -> "⏸ 已填充，未保存（仅填充模式）"
                            "uncertain" -> "⚠ 状态未能确认，请检查页面"
                            else -> "❌ ${r.error}"
                        },
                        style = MaterialTheme.typography.titleSmall,
                    )
                    if (r.draftUrl.isNotEmpty()) {
                        Spacer(Modifier.height(4.dp))
                        Text(
                            text = r.draftUrl,
                            style = MaterialTheme.typography.bodySmall,
                            fontFamily = FontFamily.Monospace,
                        )
                        Spacer(Modifier.height(8.dp))
                        Row {
                            Button(onClick = {
                                clipboard.setText(AnnotatedString(r.draftUrl))
                            }) { Text("复制链接") }
                            Spacer(Modifier.width(8.dp))
                            OutlinedButton(onClick = { vm.navigate(PublishViewModel.Screen.Home) }) {
                                Text("完成")
                            }
                        }
                    }
                }
            }
        }

        // 日志面板（收起时显示最后 3 行）
        Card(
            modifier = Modifier
                .fillMaxWidth()
                .align(Alignment.BottomCenter)
                .padding(horizontal = 12.dp, vertical = 8.dp),
            colors = CardDefaults.cardColors(
                containerColor = MaterialTheme.colorScheme.surface.copy(alpha = 0.92f),
            ),
        ) {
            Column(Modifier.padding(8.dp)) {
                val visible = if (logExpanded) logLines else logLines.takeLast(3)
                Text(
                    text = if (visible.isEmpty()) "等待日志…" else visible.joinToString("\n"),
                    style = MaterialTheme.typography.bodySmall,
                    fontFamily = FontFamily.Monospace,
                    modifier = Modifier
                        .heightIn(max = if (logExpanded) 220.dp else 72.dp)
                        .verticalScroll(rememberScrollState()),
                )
                TextButton(onClick = { logExpanded = !logExpanded }) {
                    Text(if (logExpanded) "收起日志" else "展开日志")
                }
            }
        }
    }
}
