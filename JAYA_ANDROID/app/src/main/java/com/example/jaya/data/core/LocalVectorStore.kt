package com.example.jaya.data.core

import android.util.Log
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlin.math.sqrt

data class DocumentChunk(
    val id: String,
    val documentName: String,
    val textContent: String,
    val embeddingVector: List<Float>
)

class LocalVectorStore {
    private val memoryStore = mutableListOf<DocumentChunk>()

    suspend fun addDocumentChunk(chunk: DocumentChunk) = withContext(Dispatchers.IO) {
        memoryStore.add(chunk)
        Log.d("LocalVectorStore", "Added document chunk: ${chunk.documentName} (ID: ${chunk.id})")
    }

    suspend fun searchRelevantChunks(queryEmbedding: List<Float>, topK: Int = 3): List<DocumentChunk> = withContext(Dispatchers.Default) {
        if (memoryStore.isEmpty() || queryEmbedding.isEmpty()) {
            return@withContext emptyList()
        }

        return@withContext memoryStore
            .map { chunk -> chunk to calculateCosineSimilarity(queryEmbedding, chunk.embeddingVector) }
            .sortedByDescending { it.second }
            .take(topK)
            .map { it.first }
    }

    private fun calculateCosineSimilarity(vecA: List<Float>, vecB: List<Float>): Float {
        if (vecA.size != vecB.size || vecA.isEmpty()) return 0f
        var dot = 0f
        var normA = 0f
        var normB = 0f
        for (i in vecA.indices) {
            dot += vecA[i] * vecB[i]
            normA += vecA[i] * vecA[i]
            normB += vecB[i] * vecB[i]
        }
        val denom = sqrt(normA) * sqrt(normB)
        return if (denom == 0f) 0f else dot / denom
    }
}
