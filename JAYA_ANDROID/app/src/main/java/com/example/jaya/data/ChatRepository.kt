package com.example.jaya.data

import com.example.jaya.data.core.JayaNanoEngine
import com.example.jaya.data.local.*
import com.example.jaya.data.remote.*
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.*
import kotlinx.coroutines.withContext
import java.io.File

class ChatRepository(private val chatDao: ChatDao, private val filesDir: File) {

    private val nanoEngine = JayaNanoEngine()

    val allSessions: Flow<List<ChatSession>> = chatDao.getAllSessions()

    fun getMessages(sessionId: Long): Flow<List<LocalChatMessage>> = chatDao.getMessagesForSession(sessionId)

    suspend fun createNewSession(title: String): Long {
        return chatDao.insertSession(ChatSession(title = title))
    }

    suspend fun saveMessage(sessionId: Long, role: String, content: String, fileId: Long? = null) {
        chatDao.insertMessage(LocalChatMessage(sessionId = sessionId, role = role, content = content, attachedFileId = fileId))
    }

    private suspend fun getApiService(): JayaApiService {
        val baseUrl = getPreference("BASE_URL") ?: NetworkModule.DEFAULT_JAYA_API_URL
        return NetworkModule.createJayaService(baseUrl)
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
        return fileId
    }

    suspend fun sendPromptToJaya(sessionId: Long, userPrompt: String): String = withContext(Dispatchers.IO) {
        saveMessage(sessionId, "user", userPrompt)
        
        // Dynamic Context Window: fetch full session history in chronological order
        val fullSessionHistory = chatDao.getAllMessagesForSessionList(sessionId)
        val historyPayload = fullSessionHistory.map { msg ->
            mapOf("role" to msg.role, "content" to msg.content)
        }

        return@withContext try {
            val response = getApiService().sendChatPrompt(
                JayaChatRequest(
                    prompt = userPrompt,
                    workspaceId = "android_client",
                    useLocalRag = true,
                    history = historyPayload
                )
            )
            if (response.isSuccessful && response.body() != null) {
                val jayaReply = response.body()!!.response
                saveMessage(sessionId, "assistant", jayaReply)
                jayaReply
            } else {
                // Connection failed -> Fallback to Space Mode Nano Engine immediately with full dynamic history context
                val nanoResult = nanoEngine.generateResponse(userPrompt, fullSessionHistory)
                val fallbackMsg = nanoResult.responseText
                saveMessage(sessionId, "assistant", fallbackMsg)
                fallbackMsg
            }
        } catch (e: Exception) {
            // Server unreachable or timeout -> Fallback to Space Mode Nano Engine immediately with full dynamic history context
            val nanoResult = nanoEngine.generateResponse(userPrompt, fullSessionHistory)
            val fallbackMsg = nanoResult.responseText
            saveMessage(sessionId, "assistant", fallbackMsg)
            fallbackMsg
        }
    }

    suspend fun getPreference(key: String): String? {
        return chatDao.getPreference(key)?.value
    }

    suspend fun savePreference(key: String, value: String) {
        chatDao.insertUserPreference(UserPreference(key = key, value = value))
    }

    suspend fun saveUserPreference(key: String, value: String) {
        savePreference(key, value)
    }
}
