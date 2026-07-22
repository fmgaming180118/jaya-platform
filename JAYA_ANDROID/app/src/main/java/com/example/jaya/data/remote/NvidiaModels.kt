package com.example.jaya.data.remote

import com.squareup.moshi.Json
import com.squareup.moshi.JsonClass

@JsonClass(generateAdapter = true)
data class ChatRequest(
    val model: String,
    val messages: List<ChatMessage>,
    val temperature: Float = 0.5f,
    val top_p: Float = 1.0f,
    val max_tokens: Int = 1024,
    val stream: Boolean = false,
    val tools: List<Tool>? = null,
    val tool_choice: String? = null
)

@JsonClass(generateAdapter = true)
data class Tool(
    val type: String = "function",
    val function: FunctionDef
)

@JsonClass(generateAdapter = true)
data class FunctionDef(
    val name: String,
    val description: String,
    val parameters: Parameters
)

@JsonClass(generateAdapter = true)
data class Parameters(
    val type: String = "object",
    val properties: Map<String, PropertyDef>,
    val required: List<String>? = null
)

@JsonClass(generateAdapter = true)
data class PropertyDef(
    val type: String,
    val description: String? = null
)

@JsonClass(generateAdapter = true)
data class ChatMessage(
    val role: String,
    val content: String? = null,
    val tool_calls: List<ToolCall>? = null,
    val tool_call_id: String? = null
)

@JsonClass(generateAdapter = true)
data class ToolCall(
    val id: String,
    val type: String = "function",
    val function: FunctionCall
)

@JsonClass(generateAdapter = true)
data class FunctionCall(
    val name: String,
    val arguments: String // JSON string
)

@JsonClass(generateAdapter = true)
data class ChatResponse(
    val id: String? = null,
    val choices: List<Choice>? = null,
    val usage: Usage? = null
)

@JsonClass(generateAdapter = true)
data class Choice(
    val index: Int,
    val message: ChatMessage? = null,
    val delta: ChatMessage? = null, // For streaming
    val finish_reason: String?
)

@JsonClass(generateAdapter = true)
data class Usage(
    val prompt_tokens: Int,
    val completion_tokens: Int,
    val total_tokens: Int
)

@JsonClass(generateAdapter = true)
data class EmbeddingRequest(
    val input: List<String>,
    val model: String = "nvidia/nv-embedqa-e5-v5",
    val input_type: String = "query",
    val encoding_format: String = "float"
)

@JsonClass(generateAdapter = true)
data class EmbeddingResponse(
    val data: List<EmbeddingData>
)

@JsonClass(generateAdapter = true)
data class EmbeddingData(
    val embedding: List<Float>,
    val index: Int
)
