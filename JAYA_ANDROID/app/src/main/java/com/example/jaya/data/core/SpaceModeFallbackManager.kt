package com.example.jaya.data.core

import android.util.Log
import com.example.jaya.data.network.ConnectionState
import com.example.jaya.data.remote.JayaApiService
import com.example.jaya.data.remote.JayaChatRequest
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

data class RoutingResult(
    val replyText: String,
    val isSpaceMode: Boolean,
    val sourceName: String,
)

class SpaceModeFallbackManager(
    private val apiService: JayaApiService,
    private val nanoEngine: JayaNanoEngine,
) {
    private val _currentMode = MutableStateFlow(ConnectionState.SPACE_MODE_OFFLINE)
    val currentMode: StateFlow<ConnectionState> = _currentMode.asStateFlow()

    fun updateNetworkStatus(isOnline: Boolean) {
        _currentMode.value = if (isOnline) {
            ConnectionState.CONNECTED_ONLINE
        } else {
            ConnectionState.SPACE_MODE_OFFLINE
        }
        Log.i("SpaceModeFallback", "Network routing state changed to ${_currentMode.value}")
    }

    suspend fun processPrompt(userPrompt: String): RoutingResult {
        require(userPrompt.isNotBlank()) { "Prompt cannot be blank" }
        if (_currentMode.value != ConnectionState.CONNECTED_ONLINE) {
            return fallbackToNano(userPrompt)
        }
        return try {
            val response = apiService.sendChatPrompt(
                JayaChatRequest(message = userPrompt)
            )
            val reply = response.body()?.response
            if (response.isSuccessful && !reply.isNullOrBlank()) {
                RoutingResult(
                    replyText = reply,
                    isSpaceMode = false,
                    sourceName = "JAYA Core",
                )
            } else {
                fallbackToNano(userPrompt)
            }
        } catch (error: Exception) {
            Log.w("SpaceModeFallback", "JAYA Core request failed; checking local runtime")
            fallbackToNano(userPrompt)
        }
    }

    private suspend fun fallbackToNano(userPrompt: String): RoutingResult = try {
        val nanoResult = nanoEngine.generateResponse(userPrompt)
        RoutingResult(
            replyText = nanoResult.responseText,
            isSpaceMode = true,
            sourceName = "JAYA verified local model",
        )
    } catch (error: NanoRuntimeUnavailableException) {
        RoutingResult(
            replyText = if (error.status == NanoRuntimeStatus.UNAVAILABLE) {
                "Model lokal terverifikasi belum tersedia. Sambungkan kembali ke JAYA Core."
            } else {
                "Runtime model lokal sedang bermasalah. Sambungkan kembali ke JAYA Core."
            },
            isSpaceMode = true,
            sourceName = "Local model unavailable",
        )
    }
}