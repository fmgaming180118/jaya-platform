package com.example.jaya.data.remote

import com.squareup.moshi.Json
import com.squareup.moshi.JsonClass

@JsonClass(generateAdapter = true)
data class JayaChatRequest(
    @param:Json(name = "message") val message: String,
)

@JsonClass(generateAdapter = true)
data class JayaChatResponse(
    @param:Json(name = "response") val response: String,
)