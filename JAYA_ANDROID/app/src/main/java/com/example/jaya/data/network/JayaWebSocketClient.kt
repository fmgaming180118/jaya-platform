package com.example.jaya.data.network

import android.util.Log
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.asSharedFlow
import okhttp3.*

class JayaWebSocketClient {
    private val client = OkHttpClient.Builder().build()
    private var webSocket: WebSocket? = null

    private val _incomingMessages = MutableSharedFlow<String>()
    val incomingMessages: SharedFlow<String> = _incomingMessages.asSharedFlow()

    fun connect(wsUrl: String) {
        val request = Request.Builder().url(wsUrl).build()
        webSocket = client.newWebSocket(request, object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: Response) {
                Log.d("JayaWebSocket", "WebSocket connected to $wsUrl")
            }

            override fun onMessage(webSocket: WebSocket, text: String) {
                Log.d("JayaWebSocket", "Message received: $text")
                _incomingMessages.tryEmit(text)
            }

            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                Log.e("JayaWebSocket", "WebSocket error: ${t.localizedMessage}", t)
            }

            override fun onClosing(webSocket: WebSocket, code: Int, reason: String) {
                Log.d("JayaWebSocket", "WebSocket closing: $reason")
                webSocket.close(code, reason)
            }
        })
    }

    fun sendMessage(message: String) {
        webSocket?.send(message)
    }

    fun disconnect() {
        webSocket?.close(1000, "Disconnecting client")
        webSocket = null
    }
}
