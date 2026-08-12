package com.hanselhan.wanyou.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.weight
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.hanselhan.wanyou.publish.XiumiPublisher

/** 首页：发布表单。Markdown 文本（模板渲染）或 HTML 文件路径二选一。 */
@Composable
fun HomeScreen(vm: PublishViewModel) {

    var markdownText by rememberSaveable { mutableStateOf("") }
    var htmlPath by rememberSaveable { mutableStateOf("") }
    var markdownPath by rememberSaveable { mutableStateOf("") }
    var title by rememberSaveable { mutableStateOf("") }
    var author by rememberSaveable { mutableStateOf("") }
    var digest by rememberSaveable { mutableStateOf("") }
    var sourceUrl by rememberSaveable { mutableStateOf("") }
    var templateName by rememberSaveable { mutableStateOf("generic") }
    var dryRun by rememberSaveable { mutableStateOf(false) }
    var uploadProbe by rememberSaveable { mutableStateOf(false) }

    val templateNames = remember { listOf("generic", "wanyou", "red") }
    var templateMenuOpen by remember { mutableStateOf(false) }

    Scaffold(modifier = Modifier.fillMaxSize()) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .verticalScroll(rememberScrollState())
                .imePadding()
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text("万有预报 · 秀米发布", style = MaterialTheme.typography.headlineSmall,
                    fontWeight = FontWeight.Bold)
                Spacer(Modifier.weight(1f))
                OutlinedButton(onClick = { vm.navigate(PublishViewModel.Screen.Settings) }) {
                    Text("设置")
                }
            }

            Text("将 Markdown / HTML 一键发布为秀米图文草稿。第一次发布时请先登录。",
                style = MaterialTheme.typography.bodyMedium)

            // ── 内容 ──
            Card(Modifier.fillMaxWidth()) {
                Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("内容", style = MaterialTheme.typography.titleMedium)
                    OutlinedTextField(
                        value = markdownText,
                        onValueChange = { markdownText = it },
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(220.dp),
                        label = { Text("Markdown 文本") },
                        placeholder = { Text("粘贴 Markdown 原文（推荐）") },
                    )
                    OutlinedTextField(
                        value = htmlPath,
                        onValueChange = { htmlPath = it },
                        modifier = Modifier.fillMaxWidth(),
                        label = { Text("或：HTML 文件路径（可选）") },
                        placeholder = { Text("/storage/emulated/0/Download/xx.html") },
                        singleLine = true,
                    )
                    OutlinedTextField(
                        value = markdownPath,
                        onValueChange = { markdownPath = it },
                        modifier = Modifier.fillMaxWidth(),
                        label = { Text("Markdown 文件路径（本地图片根目录，可选）") },
                        placeholder = { Text("用于解析正文里的相对路径图片") },
                        singleLine = true,
                    )
                }
            }

            // ── 元信息 ──
            Card(Modifier.fillMaxWidth()) {
                Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("标题与作者", style = MaterialTheme.typography.titleMedium)
                    OutlinedTextField(
                        value = title,
                        onValueChange = { title = it },
                        modifier = Modifier.fillMaxWidth(),
                        label = { Text("标题（留空自动取首行标题）") },
                        singleLine = true,
                    )
                    OutlinedTextField(
                        value = author,
                        onValueChange = { author = it },
                        modifier = Modifier.fillMaxWidth(),
                        label = { Text("作者") },
                        singleLine = true,
                    )
                    OutlinedTextField(
                        value = digest,
                        onValueChange = { digest = it },
                        modifier = Modifier.fillMaxWidth(),
                        label = { Text("摘要（留空自动取首段）") },
                        singleLine = true,
                    )
                    OutlinedTextField(
                        value = sourceUrl,
                        onValueChange = { sourceUrl = it },
                        modifier = Modifier.fillMaxWidth(),
                        label = { Text("原文链接（可选）") },
                        singleLine = true,
                    )
                }
            }

            // ── 选项 ──
            Card(Modifier.fillMaxWidth()) {
                Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("选项", style = MaterialTheme.typography.titleMedium)

                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text("模板", Modifier.width(72.dp))
                        OutlinedButton(onClick = { templateMenuOpen = true }) {
                            Text(templateName)
                        }
                        DropdownMenu(
                            expanded = templateMenuOpen,
                            onDismissRequest = { templateMenuOpen = false },
                        ) {
                            templateNames.forEach { name ->
                                DropdownMenuItem(
                                    text = { Text(name) },
                                    onClick = {
                                        templateName = name
                                        templateMenuOpen = false
                                    },
                                )
                            }
                        }
                    }

                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text("仅填充不保存", Modifier.width(180.dp))
                        Switch(checked = dryRun, onCheckedChange = { dryRun = it })
                    }
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text("上传前探测", Modifier.width(180.dp))
                        Switch(checked = uploadProbe, onCheckedChange = { uploadProbe = it })
                    }
                    Text("上传前探测：先上传一张小图验证图库链路，失败则自动移除正文图片。",
                        style = MaterialTheme.typography.bodySmall)
                }
            }

            val canPublish = markdownText.isNotBlank() || htmlPath.isNotBlank()
            Button(
                onClick = {
                    vm.publish(
                        XiumiPublisher.PublishRequest(
                            markdownText = markdownText,
                            htmlPath = htmlPath,
                            markdownPath = markdownPath,
                            templateName = templateName,
                            title = title,
                            author = author.ifBlank { vm.settings.defaultAuthor },
                            digest = digest,
                            sourceUrl = sourceUrl,
                            dryRun = dryRun,
                            uploadProbe = uploadProbe,
                        )
                    )
                },
                modifier = Modifier
                    .fillMaxWidth()
                    .height(52.dp),
                enabled = canPublish && !vm.running,
            ) {
                Text(if (vm.running) "发布中…" else "发布到秀米")
            }
            Spacer(Modifier.height(8.dp))
        }
    }
}
