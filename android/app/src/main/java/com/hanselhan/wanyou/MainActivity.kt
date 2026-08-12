package com.hanselhan.wanyou

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.viewModels
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import com.hanselhan.wanyou.ui.HomeScreen
import com.hanselhan.wanyou.ui.PublishScreen
import com.hanselhan.wanyou.ui.PublishViewModel
import com.hanselhan.wanyou.ui.SettingsScreen

/**
 * 应用入口。
 *
 * 页面：首页发布表单 → 发布页（秀米 WebView 实况）→ 设置页。
 * WebView 由 [PublishViewModel] 持有，页面切换只摘挂视图，
 * 秀米登录 Cookie 与会话在应用生命周期内保持。
 */
class MainActivity : ComponentActivity() {

    private val viewModel: PublishViewModel by viewModels()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            AppTheme {
                WanyouApp(viewModel)
            }
        }
    }

    override fun onDestroy() {
        if (isFinishing) {
            viewModel.releaseWebView()
        }
        super.onDestroy()
    }
}

@Composable
fun AppTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = lightColorScheme(
            primary = Color(0xFF2F6F9F),
        ),
    ) {
        Surface(modifier = Modifier.fillMaxSize()) {
            content()
        }
    }
}

@Composable
private fun WanyouApp(viewModel: PublishViewModel) {
    when (val screen = viewModel.screen) {
        is PublishViewModel.Screen.Home -> HomeScreen(viewModel)
        is PublishViewModel.Screen.Publish -> PublishScreen(viewModel)
        is PublishViewModel.Screen.Settings -> SettingsScreen(viewModel)
    }
}
