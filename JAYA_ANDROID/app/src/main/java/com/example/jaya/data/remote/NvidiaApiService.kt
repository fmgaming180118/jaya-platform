package com.example.jaya.data.remote

import okhttp3.ResponseBody
import retrofit2.Response
import retrofit2.http.Body
import retrofit2.http.Header
import retrofit2.http.POST
import retrofit2.http.Streaming

interface NvidiaApiService {
    @POST("chat/completions")
    suspend fun getChatCompletion(
        @Header("Authorization") authorization: String,
        @Body request: ChatRequest
    ): Response<ChatResponse>

    @Streaming
    @POST("chat/completions")
    suspend fun getChatCompletionStream(
        @Header("Authorization") authorization: String,
        @Body request: ChatRequest
    ): Response<ResponseBody>

    @POST("embeddings")
    suspend fun getEmbeddings(
        @Header("Authorization") authorization: String,
        @Body request: EmbeddingRequest
    ): Response<EmbeddingResponse>
}
