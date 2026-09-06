package com.example.jaya.data.network

import android.util.Log
import com.example.jaya.BuildConfig
import com.example.jaya.data.remote.NetworkModule
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

class SecureTunnelManager(
    initialServerUrl: String = BuildConfig.JAYA_API_URL,
) {
    private val _sessionState = MutableStateFlow(
        TunnelSession(
            serverUrl = NetworkModule.normalizeAndValidateBaseUrl(initialServerUrl),
            isPaired = false,
            deviceFingerprint = generateDeviceFingerprint(),
            connectionState = ConnectionState.DISCONNECTED,
        )
    )
    val sessionState: StateFlow<TunnelSession> = _sessionState.asStateFlow()

    fun updateServerUrl(newUrl: String) {
        val sanitized = NetworkModule.normalizeAndValidateBaseUrl(newUrl)
        _sessionState.value = _sessionState.value.copy(
            serverUrl = sanitized,
            isPaired = false,
            connectionState = ConnectionState.DISCONNECTED,
        )
        Log.i("SecureTunnel", "Server endpoint updated; device pairing was reset")
    }

    fun markPaired(isPaired: Boolean) {
        _sessionState.value = _sessionState.value.copy(
            isPaired = isPaired,
            connectionState = if (isPaired) {
                _sessionState.value.connectionState
            } else {
                ConnectionState.DISCONNECTED
            },
        )
    }

    fun setConnectionState(state: ConnectionState) {
        require(state != ConnectionState.CONNECTED_ONLINE || _sessionState.value.isPaired) {
            "A device must be paired before an online tunnel is marked connected"
        }
        _sessionState.value = _sessionState.value.copy(connectionState = state)
        Log.i("SecureTunnel", "Tunnel connection state changed to $state")
    }

    private fun generateDeviceFingerprint(): String {
        val rawInfo = "${android.os.Build.MANUFACTURER}_${android.os.Build.MODEL}_JAYA_MOBILE"
        val bytes = MessageDigest.getInstance("SHA-256").digest(rawInfo.toByteArray())
        return bytes.joinToString("") { "%02x".format(it) }.take(16)
    }
}