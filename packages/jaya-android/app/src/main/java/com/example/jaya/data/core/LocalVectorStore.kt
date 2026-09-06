package com.example.jaya.data.core

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import kotlin.math.sqrt

data class DocumentChunk(
    val id: String,
    val documentName: String,
    val textContent: String,
    val embeddingVector: List<Float>,
)

/** Ephemeral in-process vector store; callers must not treat it as durable storage. */
class LocalVectorStore {
    private val mutex = Mutex()
    private val memoryStore = mutableListOf<DocumentChunk>()

    suspend fun addDocumentChunk(chunk: DocumentChunk) {
        require(chunk.id.isNotBlank()) { "Chunk ID cannot be blank" }
        require(chunk.documentName.isNotBlank()) { "Document name cannot be blank" }
        require(chunk.textContent.isNotBlank()) { "Chunk text cannot be blank" }
        require(chunk.embeddingVector.isNotEmpty()) { "Embedding cannot be empty" }
        require(chunk.embeddingVector.all { it.isFinite() }) {
            "Embedding contains a non-finite value"
        }
        mutex.withLock {
            val expectedDimension = memoryStore.firstOrNull()?.embeddingVector?.size
            require(expectedDimension == null || expectedDimension == chunk.embeddingVector.size) {
                "Embedding dimension does not match the store"
            }
            val existingIndex = memoryStore.indexOfFirst { it.id == chunk.id }
            if (existingIndex >= 0) {
                memoryStore[existingIndex] = chunk.copy(
                    embeddingVector = chunk.embeddingVector.toList()
                )
            } else {
                memoryStore.add(
                    chunk.copy(embeddingVector = chunk.embeddingVector.toList())
                )
            }
        }
    }

    suspend fun searchRelevantChunks(
        queryEmbedding: List<Float>,
        topK: Int = 3,
    ): List<DocumentChunk> = withContext(Dispatchers.Default) {
        require(topK in 1..MAX_TOP_K) { "topK is outside the allowed range" }
        require(queryEmbedding.all { it.isFinite() }) {
            "Query embedding contains a non-finite value"
        }
        if (queryEmbedding.isEmpty()) return@withContext emptyList()
        val snapshot = mutex.withLock { memoryStore.toList() }
        if (snapshot.isEmpty()) return@withContext emptyList()
        require(snapshot.first().embeddingVector.size == queryEmbedding.size) {
            "Query embedding dimension does not match the store"
        }
        snapshot
            .map { chunk ->
                chunk to calculateCosineSimilarity(
                    queryEmbedding,
                    chunk.embeddingVector,
                )
            }
            .sortedByDescending { it.second }
            .take(topK)
            .map { it.first }
    }

    private fun calculateCosineSimilarity(
        vectorA: List<Float>,
        vectorB: List<Float>,
    ): Float {
        require(vectorA.size == vectorB.size && vectorA.isNotEmpty()) {
            "Cosine similarity requires equal non-empty vectors"
        }
        var dot = 0f
        var normA = 0f
        var normB = 0f
        for (index in vectorA.indices) {
            dot += vectorA[index] * vectorB[index]
            normA += vectorA[index] * vectorA[index]
            normB += vectorB[index] * vectorB[index]
        }
        val denominator = sqrt(normA) * sqrt(normB)
        return if (denominator == 0f) 0f else dot / denominator
    }

    private companion object {
        const val MAX_TOP_K = 100
    }
}