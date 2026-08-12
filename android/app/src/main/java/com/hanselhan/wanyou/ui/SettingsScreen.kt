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
import androidx.compose.material3.Card
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
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

/** 设置页：所有字段直写 SettingsStore（即时生效）。 */
@Composable
fun SettingsScreen(vm: PublishViewModel) {
    val s = vm.settings

    Scaffold(Modifier.fillMaxSize()) { padding ->
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
                TextButton(onClick = { vm.navigate(PublishViewModel.Screen.Home) }) { Text("返回") }
                Spacer(Modifier.weight(1f))
                Text("设置", style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
            }

            // ── 秀米自动化 ──
            Card(Modifier.fillMaxWidth()) {
                Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("秀米自动化", style = MaterialTheme.typography.titleMedium)
                    TextSetting("秀米首页地址", s.xiumiHomeUrl) { s.xiumiHomeUrl = it }
                    IntSetting("保存等待秒数", s.saveWaitSeconds) { s.saveWaitSeconds = it }
                    IntSetting("登录等待秒数", s.loginWaitSeconds) { s.loginWaitSeconds = it }

                    val imageModes = listOf("upload", "skip")
                    var menuOpen by remember { mutableStateOf(false) }
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text("图片模式", Modifier.width(140.dp))
                        OutlinedButton(onClick = { menuOpen = true }) { Text(s.imageMode) }
                        DropdownMenu(expanded = menuOpen, onDismissRequest = { menuOpen = false }) {
                            imageModes.forEach { mode ->
                                DropdownMenuItem(
                                    text = { Text(mode) },
                                    onClick = {
                                        s.imageMode = mode
                                        menuOpen = false
                                    },
                                )
                            }
                        }
                    }
                    IntSetting("上传停滞判定秒数", s.imageUploadStallSeconds) { s.imageUploadStallSeconds = it }
                    IntSetting("最大连续失败数", s.imageUploadMaxFailures) { s.imageUploadMaxFailures = it }
                    IntSetting("单张上传重试次数", s.imageUploadRetries) { s.imageUploadRetries = it }
                    IntSetting("批量上传大小", s.imageUploadBatchSize) { s.imageUploadBatchSize = it }
                }
            }

            // ── 发布默认值 ──
            Card(Modifier.fillMaxWidth()) {
                Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("发布默认值", style = MaterialTheme.typography.titleMedium)
                    TextSetting("默认标题", s.defaultTitle) { s.defaultTitle = it }
                    TextSetting("默认作者", s.defaultAuthor) { s.defaultAuthor = it }
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text("应用秀米基础格式", Modifier.weight(1f))
                        Switch(checked = s.applyBaseFormat, onCheckedChange = { s.applyBaseFormat = it })
                    }
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text("保留设计稿样式", Modifier.weight(1f))
                        Switch(checked = s.preserveStyles, onCheckedChange = { s.preserveStyles = it })
                    }
                }
            }
            Spacer(Modifier.height(8.dp))
        }
    }
}

/** 文本设置项：直写。 */
@Composable
private fun TextSetting(label: String, initial: String, onCommit: (String) -> Unit) {
    var value by rememberSaveable(label) { mutableStateOf(initial) }
    OutlinedTextField(
        value = value,
        onValueChange = { newValue ->
            value = newValue
            onCommit(newValue)
        },
        modifier = Modifier.fillMaxWidth(),
        label = { Text(label) },
        singleLine = true,
    )
}

/** 整数设置项：仅接受合法整数。 */
@Composable
private fun IntSetting(label: String, initial: Int, onCommit: (Int) -> Unit) {
    var value by rememberSaveable(label) { mutableStateOf(initial.toString()) }
    OutlinedTextField(
        value = value,
        onValueChange = { newValue ->
            value = newValue
            newValue.toIntOrNull()?.let(onCommit)
        },
        modifier = Modifier.fillMaxWidth(),
        label = { Text(label) },
        singleLine = true,
    )
}
