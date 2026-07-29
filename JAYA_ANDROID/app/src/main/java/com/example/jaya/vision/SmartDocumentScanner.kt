package com.example.jaya.vision

import android.graphics.Bitmap
import com.example.jaya.data.core.DocumentChunk
import com.example.jaya.data.core.LocalVectorStore
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.util.UUID

class DocumentScanUnavailableException(message: String) : IllegalStateException(message)

data class OcrObservation(
    val text: String,
    val confidence: Float,
)

interface OcrEngine {
    suspend fun recognize(bitmap: Bitmap): OcrObservation
}

interface DocumentEmbeddingEncoder {
    suspend fun encode(text: String): List<Float>
}

data class ScanResult(
    val extractedText: String,
    val wordCount: Int,
    val confidence: Float,
    val savedChunkId: String,
)

class SmartDocumentScanner(
    private val vectorStore: LocalVectorStore,
    private val ocrEngine: OcrEngine? = null,
    private val embeddingEncoder: DocumentEmbeddingEncoder? = null,
) {
    suspend fun scanAndExtractText(
        bitmap: Bitmap,
        documentTitle: String,
    ): ScanResult = withContext(Dispatchers.Default) {
        require(documentTitle.isNotBlank()) { "Document title cannot be blank" }
        require(documentTitle.length <= MAX_TITLE_CHARACTERS) {
            "Document title is too long"
        }
        require(bitmap.width > 0 && bitmap.height > 0) { "Document bitmap is empty" }
        val configuredOcr = ocrEngine ?: throw DocumentScanUnavailableException(
            "OCR engine is not configured"
        )
        val configuredEncoder = embeddingEncoder ?: throw DocumentScanUnavailableException(
            "Document embedding encoder is not configured"
        )

        val observation = configuredOcr.recognize(bitmap)
        val extractedText = observation.text.trim()
        require(extractedText.isNotEmpty()) { "OCR returned no text" }
        require(observation.confidence in 0.0f..1.0f) {
            "OCR confidence is outside the valid range"
        }
        val embedding = configuredEncoder.encode(extractedText)
        require(embedding.isNotEmpty() && embedding.all(Float::isFinite)) {
            "Embedding encoder returned an invalid vector"
        }

        val chunkId = "ocr-${UUID.randomUUID()}"
        vectorStore.addDocumentChunk(
            DocumentChunk(
                id = chunkId,
                documentName = documentTitle,
                textContent = extractedText,
                embeddingVector = embedding,
            )
        )
        ScanResult(
            extractedText = extractedText,
            wordCount = extractedText.split(WHITESPACE_PATTERN).size,
            confidence = observation.confidence,
            savedChunkId = chunkId,
        )
    }

    private companion object {
        val WHITESPACE_PATTERN = Regex("\\s+")
        const val MAX_TITLE_CHARACTERS = 240
    }
}