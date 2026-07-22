package com.example.jaya.vision

import android.graphics.Bitmap
import android.util.Log
import com.example.jaya.data.core.DocumentChunk
import com.example.jaya.data.core.LocalVectorStore
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

data class ScanResult(
    val extractedText: String,
    val wordCount: Int,
    val confidence: Float,
    val savedChunkId: String
)

class SmartDocumentScanner(private val vectorStore: LocalVectorStore) {

    suspend fun scanAndExtractText(bitmap: Bitmap, documentTitle: String): ScanResult = withContext(Dispatchers.Default) {
        Log.d("SmartDocumentScanner", "Scanning physical document image: $documentTitle...")
        
        // Simulasi OCR Text Extraction dari gambar halaman skripsi
        val simulatedExtractedText = """
            HASIL DAN PEMBAHASAN
            Pengujian arsitektur JAYA Sovereign Dual-Engine menunjukkan peningkatan kecepatan penalaran 
            sub-milidetik dengan konsumsi RAM di bawah 200 MB pada perangkat Raspberry Pi dan Smartphone.
        """.trimIndent()

        val chunkId = "chunk-ocr-${System.currentTimeMillis()}"
        val dummyVector = List(16) { 0.1f * (it + 1) }

        vectorStore.addDocumentChunk(
            DocumentChunk(
                id = chunkId,
                documentName = documentTitle,
                textContent = simulatedExtractedText,
                embeddingVector = dummyVector
            )
        )

        Log.d("SmartDocumentScanner", "OCR Scan completed and indexed into LocalVectorStore.")

        return@withContext ScanResult(
            extractedText = simulatedExtractedText,
            wordCount = simulatedExtractedText.split("\\s+".toRegex()).size,
            confidence = 0.98f,
            savedChunkId = chunkId
        )
    }
}
