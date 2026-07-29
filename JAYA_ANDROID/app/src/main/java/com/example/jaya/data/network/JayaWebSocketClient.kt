package com.example.jaya.data.network

import android.util.Log
import com.example.jaya.BuildConfig
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.asSharedFlow
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import java.net.URI

class JayaWebSocketClient(
    private val client: OkHttpClient = OkHttpClient.Builder().build(),
) {
    private var webSocket: WebSocket? = null

    private val _incomingMessages = MutableSharedFlow<String>(extraBufferCapacity = 32)
    val incomingMessages: SharedFlow<String> = _incomingMessages.asSharedFlow()

    fun connect(wsUrl: String) {
        validateWebSocketUrl(wsUrl)
        check(webSocket == null) { "WebSocket is already connected or connecting" }
        val request = Request.Builder().url(wsUrl).build()
        webSocket = client.newWebSocket(request, object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: Response) {
                Log.i("JayaWebSocket", "WebSocket connected")
            }

            override fun onMessage(webSocket: WebSocket, text: String) {
                if (text.length <= MAX_MESSAGE_CHARACTERS) {
                    _incomingMessages.tryEmit(text)
                } else {
                    Log.w("JayaWebSocket", "Oversized WebSocket message rejected")
                }
            }

            override fun onFailure(
                webSocket: WebSocket,
                t: Throwable,
                response: Response?,
            ) {
                this@JayaWebSocketClient.webSocket = null
                Log.e("JayaWebSocket", "WebSocket transport failed")
            }

            override fun onClosing(webSocket: WebSocket, code: Int, reason: String) {
                Log.i("JayaWebSocket", "WebSocket closing with code $code")
                webSocket.close(code, "")
                this@JayaWebSocketClient.webSocket = null
            }
        })
    }

    fun sendMessage(message: String): Boolean {
        require(message.length <= MAX_MESSAGE_CHARACTERS) { "WebSocket message is too large" }
        return webSocket?.send(message) ?: false
    }

    fun disconnect() {
        webSocket?.close(NORMAL_CLOSURE_CODE, "")
        webSocket = null
    }

    private fun validateWebSocketUrl(value: String) {
        val uri = try {
            URI(value)
        } catch (error: Exception) {
            throw IllegalArgumentException("WebSocket URL is invalid", error)
        }
        val host = uri.host ?: throw IllegalArgumentException(
            "WebSocket URL must include a host"
        )
        val localDebugHost = host.lowercase() in setOf(
            "10.0.2.2",
            "127.0.0.1",
            "::1",
            "localhost",
        )
        require(
            uri.scheme.equals("wss", ignoreCase = true) ||
                (
                    BuildConfig.DEBUG &&
                        uri.scheme.equals("ws", ignoreCase = true) &&
                        localDebugHost
                    )
        ) { "WebSocket URL must use WSS" }
        require(uri.userInfo == null && uri.fragment == null) {
            "WebSocket URL cannot contain credentials or fragments"
        }
    }

    private companion object {
        const val MAX_MESSAGE_CHARACTERS = 1_000_000
        const val NORMAL_CLOSURE_CODE = 1000
    }
}