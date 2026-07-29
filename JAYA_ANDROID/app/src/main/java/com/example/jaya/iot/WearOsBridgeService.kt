package com.example.jaya.iot

import android.util.Log
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

data class WearMessage(
    val senderDeviceId: String,
    val voicePrompt: String,
    val timestamp: Long,
)

data class WearPromptResult(
    val accepted: Boolean,
    val response: String,
    val errorCode: String? = null,
)

interface WearCommandHandler {
    suspend fun handle(prompt: String, senderDeviceId: String): String
}

class WearOsBridgeService(
    private val commandHandler: WearCommandHandler? = null,
    private val clockMillis: () -> Long = System::currentTimeMillis,
) {
    private val _connectedWearables = MutableStateFlow<List<String>>(emptyList())
    val connectedWearables: StateFlow<List<String>> = _connectedWearables.asStateFlow()

    fun initializeWearBridge() {
        Log.i("WearOsBridge", "Wear OS bridge initialized without assumed devices")
    }

    fun updateConnectedWearables(deviceIds: Collection<String>) {
        _connectedWearables.value = deviceIds
            .map(String::trim)
            .filter(String::isNotEmpty)
            .distinct()
    }

    suspend fun processWristVoicePrompt(wearMessage: WearMessage): WearPromptResult {
        if (wearMessage.senderDeviceId !in _connectedWearables.value) {
            return WearPromptResult(false, "Perangkat belum dipasangkan.", "DEVICE_NOT_PAIRED")
        }
        if (wearMessage.voicePrompt.isBlank() ||
            wearMessage.voicePrompt.length > MAX_PROMPT_CHARACTERS
        ) {
            return WearPromptResult(false, "Perintah tidak valid.", "INVALID_PROMPT")
        }
        val age = clockMillis() - wearMessage.timestamp
        if (age !in 0..MAX_MESSAGE_AGE_MILLIS) {
            return WearPromptResult(false, "Perintah sudah kedaluwarsa.", "STALE_MESSAGE")
        }
        val handler = commandHandler ?: return WearPromptResult(
            false,
            "Handler tindakan JAYA belum dikonfigurasi.",
            "HANDLER_UNAVAILABLE",
        )
        return try {
            val response = handler.handle(
                wearMessage.voicePrompt,
                wearMessage.senderDeviceId,
            )
            require(response.isNotBlank()) { "Wear command handler returned an empty result" }
            WearPromptResult(true, response)
        } catch (error: Exception) {
            Log.e("WearOsBridge", "Wear command handler failed")
            WearPromptResult(false, "Perintah gagal diproses.", "HANDLER_FAILED")
        }
    }

    private companion object {
        const val MAX_MESSAGE_AGE_MILLIS = 60_000L
        const val MAX_PROMPT_CHARACTERS = 2_000
    }
}