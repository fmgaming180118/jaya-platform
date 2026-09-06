package com.example.jaya.data.core

import com.example.jaya.data.local.LocalChatMessage

/**
 * Legacy facade kept for source compatibility. The former implementation used
 * random canned text and was not neural inference, so it now fails closed.
 */
@Deprecated(
    message = "Inject a verified NanoInferenceBackend into JayaNanoEngine",
    level = DeprecationLevel.WARNING,
)
class OnDeviceNeuralGenerator {
    fun generateNeuralResponse(
        userPrompt: String,
        history: List<LocalChatMessage> = emptyList(),
        temperature: Float = 0.7f,
    ): String {
        require(userPrompt.isNotBlank()) { "Prompt cannot be blank" }
        require(temperature in 0.0f..2.0f) { "Temperature is outside the supported range" }
        @Suppress("UNUSED_VARIABLE")
        val retainedForApiCompatibility = history.size
        throw NanoRuntimeUnavailableException(
            NanoRuntimeStatus.UNAVAILABLE,
            "Legacy template generation is disabled; no inference backend is configured",
        )
    }
}