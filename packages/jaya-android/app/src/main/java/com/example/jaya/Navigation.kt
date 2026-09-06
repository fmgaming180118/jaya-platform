package com.example.jaya

import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import com.example.jaya.ui.screens.ChatScreen
import com.example.jaya.ui.screens.DashboardScreen
import com.example.jaya.ui.screens.ProfileScreen
import com.example.jaya.ui.screens.SettingsScreen

enum class JayaRoute {
    Dashboard,
    Chat,
    Profile,
    Settings
}

@Composable
fun JayaNavDisplay(
    currentRoute: JayaRoute,
    onBack: () -> Unit,
    modifier: Modifier = Modifier
) {
    when (currentRoute) {
        JayaRoute.Dashboard -> DashboardScreen()
        JayaRoute.Chat -> ChatScreen()
        JayaRoute.Profile -> ProfileScreen(onBack = onBack)
        JayaRoute.Settings -> SettingsScreen(onBack = onBack)
    }
}
