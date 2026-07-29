package com.example.jaya.data

import android.content.Context
import com.example.jaya.data.core.JayaNanoEngine
import com.example.jaya.data.core.NanoRuntimeStatus
import com.example.jaya.data.core.NanoRuntimeUnavailableException
import com.example.jaya.data.local.ChatDao
import com.example.jaya.data.local.ChatFile
import com.example.jaya.data.local.ChatSession
import com.example.jaya.data.local.LocalChatMessage
import com.example.jaya.data.local.UserPreference
import com.example.jaya.data.remote.JayaApiService
import com.example.jaya.data.remote.JayaChatRequest
import com.example.jaya.data.remote.NetworkModule
import com.example.jaya.security.KeystoreSecretStore
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.withContext
import java.io.File

class ChatRepository(private val chatDao: ChatDao, context: Context) {
    private val filesDir: File = context.applicationContext.filesDir.canonicalFile
    private val secretStore = KeystoreSecretStore(context)
    private val nanoEngine = JayaNanoEngine(context.applicationContext)

    val allSessions: Flow<List<ChatSession>> = chatDao.getAllSessions()

    fun getMessages(sessionId: Long): Flow<List<LocalChatMessage>> =
        chatDao.getMessagesForSession(sessionId)

    suspend fun createNewSession(title: String): Long =
        chatDao.insertSession(ChatSession(title = title))

    suspend fun saveMessage(
        sessionId: Long,
        role: String,
        content: String,
        fileId: Long? = null,
    ) {
        chatDao.insertMessage(
            LocalChatMessage(
                sessionId = sessionId,
                role = role,
                content = content,
                attachedFileId = fileId,
            )
        )
    }

    private suspend fun getApiService(): JayaApiService {
        val baseUrl = getPreference(BASE_URL_PREFERENCE)
            ?: NetworkModule.DEFAULT_JAYA_API_URL
        val apiKey = secretStore.getString(API_KEY_SECRET_NAME)
        return NetworkModule.createJayaService(baseUrl, apiKey)
    }

    suspend fun saveOrUpdateDocument(
        sessionId: Long,
        fileName: String,
        content: String,
        isGlobal: Boolean = false,
    ): Long {
        val safeName = validateDocumentName(fileName)
        val existingFile = chatDao.getFileBySessionAndName(sessionId, safeName)
        return if (existingFile != null) {
            val file = confineStoredPath(existingFile.filePath)
            file.writeText(content)
            chatDao.updateFile(
                existingFile.copy(
                    contentSummary = content.take(MAX_SUMMARY_CHARACTERS),
                    isGlobal = isGlobal,
                )
            )
            existingFile.id
        } else {
            val file = confineStoredPath(
                File(filesDir, "${System.currentTimeMillis()}_$safeName").path
            )
            file.writeText(content)
            chatDao.insertFile(
                ChatFile(
                    sessionId = sessionId,
                    fileName = safeName,
                    filePath = file.absolutePath,
                    fileType = "text/plain",
                    contentSummary = content.take(MAX_SUMMARY_CHARACTERS),
                    isGlobal = isGlobal,
                )
            )
        }
    }

    suspend fun sendPromptToJaya(
        sessionId: Long,
        userPrompt: String,
    ): String = withContext(Dispatchers.IO) {
        require(userPrompt.isNotBlank()) { "Prompt cannot be blank" }
        saveMessage(sessionId, "user", userPrompt)

        val fullSessionHistory = chatDao.getAllMessagesForSessionList(sessionId)

        val remoteReply = try {
            val response = getApiService().sendChatPrompt(
                JayaChatRequest(message = userPrompt)
            )
            response.body()?.response?.takeIf {
                response.isSuccessful && it.isNotBlank()
            }
        } catch (error: Exception) {
            null
        }
        val reply = remoteReply ?: localFallback(userPrompt, fullSessionHistory)
        saveMessage(sessionId, "assistant", reply)
        reply
    }

    private suspend fun localFallback(
        userPrompt: String,
        history: List<LocalChatMessage>,
    ): String = try {
        nanoEngine.generateResponse(userPrompt, history).responseText
    } catch (error: NanoRuntimeUnavailableException) {
        when (error.status) {
            NanoRuntimeStatus.UNAVAILABLE -> LOCAL_MODEL_UNAVAILABLE_MESSAGE
            NanoRuntimeStatus.DEGRADED -> LOCAL_MODEL_DEGRADED_MESSAGE
            NanoRuntimeStatus.READY -> LOCAL_MODEL_DEGRADED_MESSAGE
        }
    }

    suspend fun getPreference(key: String): String? =
        chatDao.getPreference(key)?.value

    suspend fun savePreference(key: String, value: String) {
        chatDao.insertUserPreference(UserPreference(key = key, value = value))
    }

    suspend fun deletePreference(key: String) {
        chatDao.deletePreference(key)
    }

    suspend fun saveUserPreference(key: String, value: String) {
        savePreference(key, value)
    }

    private fun validateDocumentName(fileName: String): String {
        require(fileName.isNotBlank()) { "Document name cannot be blank" }
        require(fileName.length <= MAX_FILE_NAME_CHARACTERS) {
            "Document name is too long"
        }
        require(File(fileName).name == fileName) {
            "Document name cannot contain a path"
        }
        require(fileName != "." && fileName != "..") {
            "Document name is invalid"
        }
        return fileName
    }

    private fun confineStoredPath(path: String): File {
        val candidate = File(path).canonicalFile
        val rootPrefix = filesDir.path + File.separator
        require(candidate.path.startsWith(rootPrefix) && candidate != filesDir) {
            "Document path escapes app-private storage"
        }
        return candidate
    }

    companion object {
        const val API_KEY_SECRET_NAME = "jaya_api_bearer_token"
        private const val BASE_URL_PREFERENCE = "BASE_URL"
        private const val LOCAL_MODEL_DEGRADED_MESSAGE =
            "JAYA Core tidak dapat dijangkau dan runtime model lokal sedang bermasalah."
        private const val LOCAL_MODEL_UNAVAILABLE_MESSAGE =
            "JAYA Core tidak dapat dijangkau dan model lokal terverifikasi belum tersedia."
        private const val MAX_FILE_NAME_CHARACTERS = 160
        private const val MAX_SUMMARY_CHARACTERS = 200
    }
}