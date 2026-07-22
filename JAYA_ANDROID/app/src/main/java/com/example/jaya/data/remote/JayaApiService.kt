package com.example.jaya.data.remote

import okhttp3.ResponseBody
import retrofit2.Response
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.Header
import retrofit2.http.POST
import retrofit2.http.Streaming

interface JayaApiService {
    @POST("chat")
    suspend fun sendChatPrompt(
        @Body request: JayaChatRequest
    ): Response<JayaChatResponse>

    @Streaming
    @POST("chat/stream")
    suspend fun streamChatPrompt(
        @Body request: JayaChatRequest
    ): Response<ResponseBody>

    @GET("evolution/status")
    suspend fun getEvolutionStatus(): Response<JayaEvolutionStatusResponse>

    @POST("evolution/auto-upgrade")
    suspend fun triggerAutoUpgrade(): Response<JayaAutoUpgradeResponse>

    @POST("thesis/analyze")
    suspend fun analyzeLocalDocument(
        @Body request: JayaDocumentAnalysisRequest
    ): Response<JayaDocumentAnalysisResponse>
}
