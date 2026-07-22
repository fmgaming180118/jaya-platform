package com.example.jaya.vision

import android.graphics.Bitmap
import android.util.Base64
import android.util.Log
import com.example.jaya.data.network.JayaWebSocketClient
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.ByteArrayOutputStream

class MultimodalFrameStreamer(private val webSocketClient: JayaWebSocketClient) {

    suspend fun streamFrameToResearchServer(bitmap: Bitmap, promptContext: String) = withContext(Dispatchers.IO) {
        try {
            val outputStream = ByteArrayOutputStream()
            bitmap.compress(Bitmap.CompressFormat.JPEG, 70, outputStream)
            val byteArray = outputStream.toByteArray()
            val base64Image = Base64.encodeToString(byteArray, Base64.NO_WRAP)

            val jsonPayload = """
                {
                    "type": "multimodal_frame",
                    "prompt": "$promptContext",
                    "image_base64": "$base64Image",
                    "timestamp": ${System.currentTimeMillis()}
                }
            """.trimIndent()

            webSocketClient.sendMessage(jsonPayload)
            Log.d("MultimodalStreamer", "Camera frame successfully streamed to JAYA_RESEARCH multimodal engine.")
        } catch (e: Exception) {
            Log.e("MultimodalStreamer", "Error streaming frame to server", e)
        }
    }
}
