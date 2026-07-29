package com.example.jaya.data.remote

import com.example.jaya.BuildConfig
import com.squareup.moshi.Moshi
import com.squareup.moshi.kotlin.reflect.KotlinJsonAdapterFactory
import okhttp3.HttpUrl.Companion.toHttpUrlOrNull
import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import retrofit2.converter.moshi.MoshiConverterFactory
import java.util.concurrent.TimeUnit

object NetworkModule {
    val DEFAULT_JAYA_API_URL: String = BuildConfig.JAYA_API_URL

    private val moshi = Moshi.Builder()
        .add(KotlinJsonAdapterFactory())
        .build()

    fun normalizeAndValidateBaseUrl(baseUrl: String): String {
        val candidate = if (baseUrl.endsWith('/')) baseUrl else "$baseUrl/"
        val parsed = candidate.toHttpUrlOrNull()
            ?: throw IllegalArgumentException("JAYA API URL is invalid")
        require(parsed.username.isEmpty() && parsed.password.isEmpty()) {
            "JAYA API URL cannot contain credentials"
        }
        require(parsed.query == null && parsed.fragment == null) {
            "JAYA API URL cannot contain a query or fragment"
        }
        val localDebugHost = parsed.host.lowercase() in setOf(
            "10.0.2.2",
            "127.0.0.1",
            "::1",
            "localhost",
        )
        require(parsed.isHttps || (BuildConfig.DEBUG && localDebugHost)) {
            "JAYA API URL must use HTTPS"
        }
        return parsed.toString()
    }

    fun createJayaService(
        baseUrl: String = DEFAULT_JAYA_API_URL,
        apiKey: String? = null,
    ): JayaApiService {
        val sanitizedUrl = normalizeAndValidateBaseUrl(baseUrl)
        return Retrofit.Builder()
            .baseUrl(sanitizedUrl)
            .client(buildHttpClient(apiKey))
            .addConverterFactory(MoshiConverterFactory.create(moshi))
            .build()
            .create(JayaApiService::class.java)
    }

    private fun buildHttpClient(apiKey: String?): OkHttpClient {
        val normalizedKey = apiKey?.trim()?.takeIf(String::isNotEmpty)
        require(normalizedKey?.none { it == '\r' || it == '\n' } != false) {
            "API key contains invalid characters"
        }
        val logging = HttpLoggingInterceptor().apply {
            redactHeader("Authorization")
            level = if (BuildConfig.DEBUG) {
                HttpLoggingInterceptor.Level.BASIC
            } else {
                HttpLoggingInterceptor.Level.NONE
            }
        }
        return OkHttpClient.Builder()
            .addInterceptor { chain ->
                val request = chain.request().newBuilder().apply {
                    normalizedKey?.let { header("Authorization", "Bearer $it") }
                }.build()
                chain.proceed(request)
            }
            .addInterceptor(logging)
            .connectTimeout(5, TimeUnit.SECONDS)
            .readTimeout(15, TimeUnit.SECONDS)
            .writeTimeout(15, TimeUnit.SECONDS)
            .build()
    }
}