package com.example.jaya.data.core

import android.content.Context
import com.example.jaya.data.local.LocalChatMessage
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

enum class NanoRuntimeStatus {
    UNAVAILABLE,
    DEGRADED,
    READY,
}

class NanoRuntimeUnavailableException(
    val status: NanoRuntimeStatus,
    message: String,
    cause: Throwable? = null,
) : IllegalStateException(message, cause)

data class NanoInferenceResult(
    val responseText: String,
    val isLocalNano: Boolean,
    val latencyMs: Long,
    val ramUsedMb: Float?,
    val modelSource: String,
    val runtimeStatus: NanoRuntimeStatus = NanoRuntimeStatus.READY,
)

/** Adapter boundary for a genuine on-device inference implementation. */
interface NanoInferenceBackend {
    suspend fun initialize(modelLoader: JayModelLoader): Boolean

    suspend fun generate(
        prompt: String,
        historyMessages: List<LocalChatMessage>,
    ): String
}

class JayaNanoEngine(
    private val context: Context? = null,
    private val inferenceBackend: NanoInferenceBackend? = null,
) {
    @Volatile
    var runtimeStatus: NanoRuntimeStatus = NanoRuntimeStatus.UNAVAILABLE
        private set

    private var jayLoader: JayModelLoader? = null

    suspend fun initializeNanoKernel(): Boolean = withContext(Dispatchers.IO) {
        val appContext = context?.applicationContext
        if (appContext == null) {
            runtimeStatus = NanoRuntimeStatus.UNAVAILABLE
            return@withContext false
        }
        val backend = inferenceBackend
        if (backend == null) {
            runtimeStatus = NanoRuntimeStatus.DEGRADED
            return@withContext false
        }
        val loader = JayModelLoader(appContext)
        if (!loader.loadModelFromAssets()) {
            runtimeStatus = NanoRuntimeStatus.UNAVAILABLE
            return@withContext false
        }
        val initialized = try {
            backend.initialize(loader)
        } catch (error: Exception) {
            runtimeStatus = NanoRuntimeStatus.DEGRADED
            throw NanoRuntimeUnavailableException(
                NanoRuntimeStatus.DEGRADED,
                "Local inference backend initialization failed",
                error,
            )
        }
        if (!initialized) {
            runtimeStatus = NanoRuntimeStatus.DEGRADED
            return@withContext false
        }
        jayLoader = loader
        runtimeStatus = NanoRuntimeStatus.READY
        true
    }

    suspend fun generateResponse(
        prompt: String,
        historyMessages: List<LocalChatMessage> = emptyList(),
    ): NanoInferenceResult {
        require(prompt.isNotBlank()) { "Prompt cannot be blank" }
        if (runtimeStatus != NanoRuntimeStatus.READY && !initializeNanoKernel()) {
            throw NanoRuntimeUnavailableException(
                runtimeStatus,
                "A verified on-device model and inference backend are required",
            )
        }
        val backend = inferenceBackend ?: throw NanoRuntimeUnavailableException(
            NanoRuntimeStatus.DEGRADED,
            "Local inference backend is unavailable",
        )
        val startedAt = System.nanoTime()
        val response = try {
            withContext(Dispatchers.Default) {
                backend.generate(prompt, historyMessages)
            }
        } catch (error: Exception) {
            runtimeStatus = NanoRuntimeStatus.DEGRADED
            throw NanoRuntimeUnavailableException(
                NanoRuntimeStatus.DEGRADED,
                "Local inference probe failed",
                error,
            )
        }
        if (response.isBlank()) {
            runtimeStatus = NanoRuntimeStatus.DEGRADED
            throw NanoRuntimeUnavailableException(
                NanoRuntimeStatus.DEGRADED,
                "Local inference returned an empty response",
            )
        }
        return NanoInferenceResult(
            responseText = response,
            isLocalNano = true,
            latencyMs = (System.nanoTime() - startedAt) / 1_000_000,
            ramUsedMb = null,
            modelSource = jayLoader?.getModelSummary() ?: "verified-local-model",
            runtimeStatus = NanoRuntimeStatus.READY,
        )
    }
}