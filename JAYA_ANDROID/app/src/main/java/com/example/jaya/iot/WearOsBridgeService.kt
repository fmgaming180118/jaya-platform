package com.example.jaya.iot

import android.util.Log
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

data class WearMessage(
    val senderDeviceId: String,
    val voicePrompt: String,
    val timestamp: Long
)

class WearOsBridgeService {
    private val _connectedWearables = MutableStateFlow<List<String>>(emptyList())
    val connectedWearables: StateFlow<List<String>> = _connectedWearables.asStateFlow()

    fun initializeWearBridge() {
        Log.d("WearOsBridge", "Initializing Wear OS Smartwatch Data Layer Bridge...")
        _connectedWearables.value = listOf("WearOS_GalaxyWatch_JAYA")
    }

    fun processWristVoicePrompt(wearMessage: WearMessage): String {
        Log.d("WearOsBridge", "Received wrist prompt from ${wearMessage.senderDeviceId}: '${wearMessage.voicePrompt}'")
        return "JAYA Wrist Companion: Perintah '${wearMessage.voicePrompt}' telah dieksekusi."
    }
}
