package com.example.jaya

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.rounded.Chat
import androidx.compose.material.icons.rounded.Dashboard
import androidx.compose.material.icons.rounded.Person
import androidx.compose.material.icons.rounded.Settings
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.material3.adaptive.navigationsuite.NavigationSuiteScaffold
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import com.example.jaya.ui.theme.JayaTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            JayaTheme {
                var currentRoute by remember { mutableStateOf(JayaRoute.Dashboard) }

                NavigationSuiteScaffold(
                    modifier = Modifier.fillMaxSize(),
                    navigationSuiteItems = {
                        item(
                            selected = currentRoute == JayaRoute.Dashboard,
                            onClick = { currentRoute = JayaRoute.Dashboard },
                            icon = { Icon(Icons.Rounded.Dashboard, contentDescription = "Dashboard") },
                            label = { Text("Dashboard") }
                        )
                        item(
                            selected = currentRoute == JayaRoute.Chat,
                            onClick = { currentRoute = JayaRoute.Chat },
                            icon = { Icon(Icons.AutoMirrored.Rounded.Chat, contentDescription = "Chat") },
                            label = { Text("Chat") }
                        )
                        item(
                            selected = currentRoute == JayaRoute.Profile,
                            onClick = { currentRoute = JayaRoute.Profile },
                            icon = { Icon(Icons.Rounded.Person, contentDescription = "Profile") },
                            label = { Text("Profile") }
                        )
                        item(
                            selected = currentRoute == JayaRoute.Settings,
                            onClick = { currentRoute = JayaRoute.Settings },
                            icon = { Icon(Icons.Rounded.Settings, contentDescription = "Settings") },
                            label = { Text("Settings") }
                        )
                    }
                ) {
                    JayaNavDisplay(
                        currentRoute = currentRoute,
                        onBack = {
                            if (currentRoute != JayaRoute.Dashboard) {
                                currentRoute = JayaRoute.Dashboard
                            } else {
                                finish()
                            }
                        }
                    )
                }
            }
        }
    }
}
