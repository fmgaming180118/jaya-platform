package com.example.jaya.data.remote

import com.squareup.moshi.Json
import com.squareup.moshi.JsonClass

@JsonClass(generateAdapter = true)
data class JayaChatRequest(
    @param:Json(name = "prompt") val prompt: String,
    @param:Json(name = "workspace_id") val workspaceId: String = "default",
    @param:Json(name = "use_local_rag") val useLocalRag: Boolean = true
)

@JsonClass(generateAdapter = true)
data class JayaChatResponse(
    @param:Json(name = "ok") val ok: Boolean,
    @param:Json(name = "response") val response: String,
    @param:Json(name = "sources") val sources: List<String>? = emptyList()
)

@JsonClass(generateAdapter = true)
data class JayaEvolutionStatusResponse(
    @param:Json(name = "state") val state: String,
    @param:Json(name = "is_awake") val isAwake: Boolean,
    @param:Json(name = "latest_thought") val latestThought: String? = null
)

@JsonClass(generateAdapter = true)
data class JayaAutoUpgradeResponse(
    @param:Json(name = "ok") val ok: Boolean,
    @param:Json(name = "message") val message: String
)

@JsonClass(generateAdapter = true)
data class JayaDocumentAnalysisRequest(
    @param:Json(name = "document_path") val documentPath: String,
    @param:Json(name = "topic") val topic: String = "thesis"
)

@JsonClass(generateAdapter = true)
data class JayaDocumentAnalysisResponse(
    @param:Json(name = "ok") val ok: Boolean,
    @param:Json(name = "summary") val summary: String
)
