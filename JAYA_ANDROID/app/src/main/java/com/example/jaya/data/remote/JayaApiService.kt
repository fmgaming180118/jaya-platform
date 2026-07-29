package com.example.jaya.data.remote

import retrofit2.Response
import retrofit2.http.Body
import retrofit2.http.POST

/** Public Android-facing subset of the JAYA Core API. */
interface JayaApiService {
    @POST("v1/chat")
    suspend fun sendChatPrompt(
        @Body request: JayaChatRequest,
    ): Response<JayaChatResponse>
}