package com.example.jaya.vision

import android.graphics.Bitmap
import android.util.Log
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.ByteArrayOutputStream

data class MultimodalFrame(
    val jpegBytes: ByteArray,
    val promptContext: String,
    val capturedAtMillis: Long,
)

data class FrameTransportReceipt(
    val accepted: Boolean,
    val receiptId: String,
)

interface MultimodalFrameTransport {
    suspend fun send(frame: MultimodalFrame): FrameTransportReceipt
}

data class FrameStreamResult(
    val sent: Boolean,
    val receiptId: String? = null,
    val errorCode: String? = null,
)

class MultimodalFrameStreamer(
    private val transport: MultimodalFrameTransport? = null,
    private val clockMillis: () -> Long = System::currentTimeMillis,
) {
    suspend fun streamFrameToCore(
        bitmap: Bitmap,
        promptContext: String,
    ): FrameStreamResult = withContext(Dispatchers.IO) {
        require(promptContext.length <= MAX_PROMPT_CHARACTERS) {
            "Prompt context is too long"
        }
        val pixels = bitmap.width.toLong() * bitmap.height.toLong()
        require(pixels in 1..MAX_FRAME_PIXELS) { "Frame dimensions are invalid" }
        val configuredTransport = transport ?: return@withContext FrameStreamResult(
            sent = false,
            errorCode = "MULTIMODAL_TRANSPORT_UNAVAILABLE",
        )
        val output = ByteArrayOutputStream()
        if (!bitmap.compress(Bitmap.CompressFormat.JPEG, JPEG_QUALITY, output)) {
            return@withContext FrameStreamResult(false, errorCode = "FRAME_ENCODING_FAILED")
        }
        val bytes = output.toByteArray()
        if (bytes.isEmpty() || bytes.size > MAX_ENCODED_FRAME_BYTES) {
            return@withContext FrameStreamResult(false, errorCode = "FRAME_SIZE_INVALID")
        }
        try {
            val receipt = configuredTransport.send(
                MultimodalFrame(
                    jpegBytes = bytes.copyOf(),
                    promptContext = promptContext,
                    capturedAtMillis = clockMillis(),
                )
            )
            if (!receipt.accepted || receipt.receiptId.isBlank()) {
                FrameStreamResult(false, errorCode = "FRAME_REJECTED")
            } else {
                FrameStreamResult(true, receiptId = receipt.receiptId)
            }
        } catch (error: Exception) {
            Log.e("MultimodalStreamer", "Multimodal frame transport failed")
            FrameStreamResult(false, errorCode = "FRAME_TRANSPORT_FAILED")
        }
    }

    @Deprecated(
        message = "Frames must go through the authenticated Core transport",
        replaceWith = ReplaceWith("streamFrameToCore(bitmap, promptContext)"),
    )
    suspend fun streamFrameToResearchServer(
        bitmap: Bitmap,
        promptContext: String,
    ): FrameStreamResult = streamFrameToCore(bitmap, promptContext)

    private companion object {
        const val JPEG_QUALITY = 70
        const val MAX_ENCODED_FRAME_BYTES = 5 * 1024 * 1024
        const val MAX_FRAME_PIXELS = 12_000_000L
        const val MAX_PROMPT_CHARACTERS = 4_000
    }
}