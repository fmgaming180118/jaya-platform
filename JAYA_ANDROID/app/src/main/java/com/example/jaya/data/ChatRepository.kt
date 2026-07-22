package com.example.jaya.data

import com.example.jaya.BuildConfig
import com.example.jaya.data.local.*
import com.example.jaya.data.remote.*
import com.squareup.moshi.Moshi
import com.squareup.moshi.kotlin.reflect.KotlinJsonAdapterFactory
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.*
import kotlinx.coroutines.withContext
import java.io.File
import kotlin.math.sqrt

class ChatRepository(private val chatDao: ChatDao, private val filesDir: File) {

    private val moshi = Moshi.Builder().add(KotlinJsonAdapterFactory()).build()
    private val chatResponseAdapter = moshi.adapter(ChatResponse::class.java)

    val allSessions: Flow<List<ChatSession>> = chatDao.getAllSessions()

    fun getMessages(sessionId: Long): Flow<List<LocalChatMessage>> = chatDao.getMessagesForSession(sessionId)

    suspend fun createNewSession(title: String): Long {
        return chatDao.insertSession(ChatSession(title = title))
    }

    suspend fun saveMessage(sessionId: Long, role: String, content: String, fileId: Long? = null) {
        chatDao.insertMessage(LocalChatMessage(sessionId = sessionId, role = role, content = content, attachedFileId = fileId))
    }

    private suspend fun getApiService(): NvidiaApiService {
        val baseUrl = getPreference("BASE_URL") ?: "https://integrate.api.nvidia.com/v1/"
        return NetworkModule.createService(baseUrl)
    }

    suspend fun saveOrUpdateDocument(sessionId: Long, fileName: String, content: String, isGlobal: Boolean = false): Long {
        val existingFile = chatDao.getFileBySessionAndName(sessionId, fileName)
        val fileId = if (existingFile != null) {
            val file = File(existingFile.filePath)
            file.writeText(content)
            val updatedFile = existingFile.copy(
                contentSummary = if (content.length > 200) content.take(200) else content,
                isGlobal = isGlobal
            )
            chatDao.updateFile(updatedFile)
            existingFile.id
        } else {
            val file = File(filesDir, "${System.currentTimeMillis()}_$fileName")
            file.writeText(content)
            val chatFile = ChatFile(
                sessionId = sessionId,
                fileName = fileName,
                filePath = file.absolutePath,
                fileType = "text/plain",
                contentSummary = if (content.length > 200) content.take(200) else content,
                isGlobal = isGlobal
            )
            chatDao.insertFile(chatFile)
        }
        
        // Generate Embeddings for the new/updated file
        generateAndSaveEmbeddings(fileId, content)
        return fileId
    }

    private suspend fun generateAndSaveEmbeddings(fileId: Long, content: String) {
        val apiKey = getPreference("API_KEY") ?: BuildConfig.NVIDIA_API_KEY
        val chunks = content.split("\n\n").filter { it.isNotBlank() }
        
        try {
            val response = getApiService().getEmbeddings(
                authorization = "Bearer $apiKey",
                request = EmbeddingRequest(input = chunks, input_type = "passage")
            )
            
            if (response.isSuccessful) {
                val embeddings = response.body()?.data?.map { data ->
                    FileEmbedding(
                        fileId = fileId,
                        embedding = data.embedding.joinToString(","),
                        textChunk = chunks[data.index]
                    )
                }
                if (embeddings != null) {
                    chatDao.insertEmbeddings(embeddings)
                }
            }
        } catch (e: Exception) {
            e.printStackTrace()
        }
    }

    suspend fun compactChat(sessionId: Long, model: String) {
        val history = chatDao.getMessagesForSession(sessionId).first()
        if (history.size < 15) return

        val messagesToCompact = history.take(history.size - 5)
        val lastTimestamp = messagesToCompact.last().timestamp
        
        val summaryPrompt = "Summarize accurately: \n" + messagesToCompact.joinToString("\n") { "${it.role}: ${it.content}" }
        val response = getAiResponse(sessionId, summaryPrompt, model)
        
        chatDao.markMessagesAsCompacted(sessionId, lastTimestamp)
        chatDao.insertMessage(LocalChatMessage(
            sessionId = sessionId,
            role = "assistant",
            content = "[Memory Compacted]: $response",
            isCompacted = false
        ))
    }

    suspend fun getAiResponse(sessionId: Long, userContent: String, model: String, apiKey: String? = null): String {
        val finalApiKey = apiKey ?: getPreference("API_KEY") ?: BuildConfig.NVIDIA_API_KEY
        val context = buildContext(sessionId, userContent, finalApiKey)
        val history = chatDao.getMessagesForSession(sessionId).first()

        val messages = mutableListOf<ChatMessage>()
        messages.add(ChatMessage(role = "system", content = "You are Jaya, a smart AI. Context: $context"))
        messages.addAll(history.map { ChatMessage(role = it.role, content = it.content) })
        messages.add(ChatMessage(role = "user", content = userContent))

        val response = getApiService().getChatCompletion(
            authorization = "Bearer $finalApiKey",
            request = ChatRequest(model = model, messages = messages, tools = getTools())
        )

        val choice = response.body()?.choices?.firstOrNull()
        val message = choice?.message
        
        return if (message?.tool_calls != null) {
            val toolCall = message.tool_calls.first()
            "[Tool Call: ${toolCall.function.name}] ${toolCall.function.arguments}"
        } else {
            message?.content ?: "Error: ${response.code()} ${response.message()}"
        }
    }

    fun getAiResponseStream(sessionId: Long, userContent: String, model: String): Flow<String> = flow {
        val apiKey = getPreference("API_KEY") ?: BuildConfig.NVIDIA_API_KEY
        val context = buildContext(sessionId, userContent, apiKey)
        val history = chatDao.getMessagesForSession(sessionId).first()

        val messages = mutableListOf<ChatMessage>()
        messages.add(ChatMessage(role = "system", content = "You are Jaya. Stream your response. Context: $context"))
        messages.addAll(history.map { ChatMessage(role = it.role, content = it.content) })
        messages.add(ChatMessage(role = "user", content = userContent))

        val response = getApiService().getChatCompletionStream(
            authorization = "Bearer $apiKey",
            request = ChatRequest(model = model, messages = messages, stream = true)
        )

        if (response.isSuccessful) {
            val reader = response.body()?.byteStream()?.bufferedReader()
            reader?.use { br ->
                var line: String?
                while (br.readLine().also { line = it } != null) {
                    if (line!!.startsWith("data: ")) {
                        val data = line!!.substring(6)
                        if (data == "[DONE]") break
                        try {
                            val chunk = chatResponseAdapter.fromJson(data)
                            chunk?.choices?.firstOrNull()?.delta?.content?.let { emit(it) }
                        } catch (e: Exception) {}
                    }
                }
            }
        } else {
            emit("Error: ${response.code()} ${response.message()}")
        }
    }.flowOn(Dispatchers.IO)

    private suspend fun buildContext(sessionId: Long, query: String, apiKey: String): String {
        // Semantic Search using Embeddings
        val queryEmbedding = getQueryEmbedding(query, apiKey)
        val allEmbeddings = chatDao.getRelevantEmbeddings(sessionId)
        
        val semanticResults = if (queryEmbedding != null && allEmbeddings.isNotEmpty()) {
            allEmbeddings.mapNotNull { 
                try {
                    val vector = it.embedding.split(",").filter { s -> s.isNotBlank() }.map { f -> f.toFloat() }
                    if (vector.size == queryEmbedding.size) {
                        it to cosineSimilarity(queryEmbedding, vector)
                    } else null
                } catch (e: Exception) { null }
            }
            .sortedByDescending { it.second }
            .take(3)
            .joinToString("\n") { it.first.textChunk }
        } else ""

        val userPrefs = chatDao.getAllUserPreferences().first().joinToString("\n") { "${it.key}: ${it.value}" }
        
        return """
            Global Info: $userPrefs
            Semantic File Context: $semanticResults
        """.trimIndent()
    }

    private suspend fun getQueryEmbedding(query: String, apiKey: String): List<Float>? {
        return try {
            val resp = getApiService().getEmbeddings(
                authorization = "Bearer $apiKey",
                request = EmbeddingRequest(input = listOf(query), input_type = "query")
            )
            resp.body()?.data?.firstOrNull()?.embedding
        } catch (e: Exception) { null }
    }

    private fun cosineSimilarity(v1: List<Float>, v2: List<Float>): Float {
        if (v1.size != v2.size || v1.isEmpty()) return 0f
        var dot = 0f
        var n1 = 0f
        var n2 = 0f
        for (i in v1.indices) {
            dot += v1[i] * v2[i]
            n1 += v1[i] * v1[i]
            n2 += v2[i] * v2[i]
        }
        val denom = sqrt(n1) * sqrt(n2)
        return if (denom > 0) dot / denom else 0f
    }

    private fun getTools(): List<Tool> = listOf(
        Tool(function = FunctionDef("web_search", "Search internet for latest info", Parameters(properties = mapOf("query" to PropertyDef("string")), required = listOf("query")))),
        Tool(function = FunctionDef("manage_document", "Create or edit a text document", Parameters(properties = mapOf("name" to PropertyDef("string"), "content" to PropertyDef("string")), required = listOf("name", "content"))))
    )

    suspend fun getPreference(key: String): String? = chatDao.getAllUserPreferences().first().find { it.key == key }?.value
    suspend fun saveUserPreference(key: String, value: String) = chatDao.insertUserPreference(UserPreference(key, value))
}
