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
    val sourceName: String
)

class SpaceModeFallbackManager(
    private val apiService: JayaApiService,
    private val nanoEngine: JayaNanoEngine
) {
    private val _currentMode = MutableStateFlow(ConnectionState.SPACE_MODE_OFFLINE)
    val currentMode: StateFlow<ConnectionState> = _currentMode.asStateFlow()

    fun updateNetworkStatus(isOnline: Boolean) {
        _currentMode.value = if (isOnline) ConnectionState.CONNECTED_ONLINE else ConnectionState.SPACE_MODE_OFFLINE
        Log.d("SpaceModeFallback", "Network status updated: ${_currentMode.value}")
    }

    suspend fun processPrompt(userPrompt: String): RoutingResult {
        return if (_currentMode.value == ConnectionState.CONNECTED_ONLINE) {
            try {
                Log.d("SpaceModeFallback", "Routing prompt to JAYA PC Server API...")
                val response = apiService.sendChatPrompt(
                    JayaChatRequest(prompt = userPrompt, workspaceId = "android_client", useLocalRag = true)
                )
                if (response.isSuccessful && response.body() != null) {
                    RoutingResult(
                        replyText = response.body()!!.response,
                        isSpaceMode = false,
                        sourceName = "JAYA PC Server (Online LAN)"
                    )
                } else {
                    fallbackToNano(userPrompt)
                }
            } catch (e: Exception) {
                Log.w("SpaceModeFallback", "Server error, falling back to local Space Mode: ${e.localizedMessage}")
                fallbackToNano(userPrompt)
            }
        } else {
            fallbackToNano(userPrompt)
        }
    }

    private suspend fun fallbackToNano(userPrompt: String): RoutingResult {
        val nanoResult = nanoEngine.generateResponse(userPrompt)
        return RoutingResult(
            replyText = nanoResult.responseText,
            isSpaceMode = true,
            sourceName = "JAYA Local Nano Kernel (Space Mode)"
        )
    }
}
