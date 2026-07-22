package com.example.jaya.data.remote

import com.squareup.moshi.Json
import com.squareup.moshi.JsonClass

@JsonClass(generateAdapter = true)
data class JayaChatRequest(
    @Json(name = "prompt") val prompt: String,
    @Json(name = "workspace_id") val workspaceId: String = "default",
    @Json(name = "use_local_rag") val useLocalRag: Boolean = true
)

@JsonClass(generateAdapter = true)
data class JayaChatResponse(
    @Json(name = "ok") val ok: Boolean,
    @Json(name = "response") val response: String,
    @Json(name = "sources") val sources: List<String>? = emptyList()
)

@JsonClass(generateAdapter = true)
data class JayaEvolutionStatusResponse(
    @Json(name = "state") val state: String,
    @Json(name = "is_awake") val isAwake: Boolean,
    @Json(name = "latest_thought") val latestThought: String? = null
)

@JsonClass(generateAdapter = true)
data class JayaAutoUpgradeResponse(
    @Json(name = "ok") val ok: Boolean,
    @Json(name = "message") val message: String
)

@JsonClass(generateAdapter = true)
data class JayaDocumentAnalysisRequest(
    @Json(name = "document_path") val documentPath: String,
    @Json(name = "topic") val topic: String = "thesis"
)

@JsonClass(generateAdapter = true)
data class JayaDocumentAnalysisResponse(
    @Json(name = "ok") val ok: Boolean,
    @Json(name = "summary") val summary: String
)
