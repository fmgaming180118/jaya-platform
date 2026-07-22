package com.example.jaya.data.network

import android.util.Log
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import java.security.MessageDigest

enum class ConnectionState {
    DISCONNECTED,
    CONNECTING,
    CONNECTED_ONLINE,
    SPACE_MODE_OFFLINE
}

data class TunnelSession(
    val serverUrl: String,
    val isPaired: Boolean,
    val deviceFingerprint: String,
    val connectionState: ConnectionState
)

class SecureTunnelManager {
    private val _sessionState = MutableStateFlow(
        TunnelSession(
            serverUrl = "http://10.0.2.2:8000/",
            isPaired = true,
            deviceFingerprint = generateDeviceFingerprint(),
            connectionState = ConnectionState.DISCONNECTED
        )
    )
    val sessionState: StateFlow<TunnelSession> = _sessionState.asStateFlow()

    fun updateServerUrl(newUrl: String) {
        val sanitized = if (newUrl.endsWith("/")) newUrl else "$newUrl/"
        _sessionState.value = _sessionState.value.copy(serverUrl = sanitized)
        Log.d("SecureTunnel", "Server URL updated to $sanitized")
    }

    fun setConnectionState(state: ConnectionState) {
        _sessionState.value = _sessionState.value.copy(connectionState = state)
        Log.d("SecureTunnel", "Tunnel connection state changed to: $state")
    }

    private fun generateDeviceFingerprint(): String {
        val rawInfo = "${android.os.Build.MANUFACTURER}_${android.os.Build.MODEL}_JAYA_MOBILE"
        val bytes = MessageDigest.getInstance("SHA-256").digest(rawInfo.toByteArray())
        return bytes.joinToString("") { "%02x".format(it) }.take(16)
    }
}
