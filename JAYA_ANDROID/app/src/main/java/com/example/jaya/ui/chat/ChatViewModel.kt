package com.example.jaya.ui.chat

import android.app.Application
import android.util.Log
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.example.jaya.data.ChatRepository
import com.example.jaya.data.local.AppDatabase
import com.example.jaya.data.local.ChatSession
import com.example.jaya.data.local.LocalChatMessage
import com.example.jaya.skills.AiSkill
import com.example.jaya.skills.BlueprintSkill
import com.example.jaya.skills.DocumentSkill
import com.example.jaya.skills.SearchSkill
import kotlinx.coroutines.flow.*
import kotlinx.coroutines.launch

class ChatViewModel(application: Application) : AndroidViewModel(application) {

    private val repository: ChatRepository
    private val skills: List<AiSkill> = listOf(
        DocumentSkill(),
        BlueprintSkill(application),
        SearchSkill()
    )
    
    private val _sessions = MutableStateFlow<List<ChatSession>>(emptyList())
    val sessions: StateFlow<List<ChatSession>> = _sessions.asStateFlow()

    private val _currentSessionId = MutableStateFlow<Long?>(null)
    val currentSessionId: StateFlow<Long?> = _currentSessionId.asStateFlow()

    private val _messages = MutableStateFlow<List<LocalChatMessage>>(emptyList())
    val messages: StateFlow<List<LocalChatMessage>> = _messages.asStateFlow()

    private val _isLoading = MutableStateFlow(false)
    val isLoading: StateFlow<Boolean> = _isLoading.asStateFlow()

    private val _selectedModel = MutableStateFlow("JAYA Sovereign Brain (Remote Server / LAN)")
    val selectedModel: StateFlow<String> = _selectedModel.asStateFlow()

    val availableModels = listOf(
        "JAYA Sovereign Brain (Remote Server / LAN)",
        "JAYA Local GGUF Nano Kernel (Space Mode)",
        "JAYA Dynamic Research Engine"
    )

    init {
        val database = AppDatabase.getDatabase(application)
        repository = ChatRepository(database.chatDao(), application.filesDir)
        
        viewModelScope.launch {
            repository.allSessions.collect { sessionList ->
                Log.d("ChatViewModel", "Sessions updated: ${sessionList.size}")
                _sessions.value = sessionList
                if (_currentSessionId.value == null && sessionList.isNotEmpty()) {
                    selectSession(sessionList.first().id)
                } else if (sessionList.isEmpty()) {
                    createNewChat()
                }
            }
        }
    }

    private var messagesJob: kotlinx.coroutines.Job? = null

    fun selectSession(sessionId: Long) {
        Log.d("ChatViewModel", "Selecting session: $sessionId")
        _currentSessionId.value = sessionId
        messagesJob?.cancel()
        messagesJob = viewModelScope.launch {
            repository.getMessages(sessionId).collect { dbMessages ->
                if (!_isLoading.value) {
                    _messages.value = dbMessages
                }
            }
        }
    }

    fun createNewChat() {
        viewModelScope.launch {
            val id = repository.createNewSession("JAYA Chat ${System.currentTimeMillis() / 100000}")
            _currentSessionId.value = id
            selectSession(id)
        }
    }

    fun selectModel(model: String) {
        _selectedModel.value = model
    }

    fun sendMessage(content: String) {
        val sessionId = _currentSessionId.value ?: return
        if (content.isBlank()) return

        viewModelScope.launch {
            _isLoading.value = true
            
            val matchedSkill = skills.find { it.matches(content) }
            
            if (matchedSkill != null) {
                try {
                    repository.saveMessage(sessionId, "user", content)
                    val result = matchedSkill.execute(content, sessionId)
                    var fileId: Long? = null
                    if (result.attachedFileContent != null && result.attachedFileName != null) {
                        fileId = repository.saveOrUpdateDocument(sessionId, result.attachedFileName, result.attachedFileContent)
                    }
                    repository.saveMessage(sessionId, "assistant", result.content, fileId)
                } catch (e: Exception) {
                    repository.saveMessage(sessionId, "assistant", "Error executing skill: ${e.localizedMessage}")
                } finally {
                    _isLoading.value = false
                }
            } else {
                try {
                    repository.sendPromptToJaya(sessionId, content)
                } catch (e: Exception) {
                    Log.e("ChatViewModel", "Error sending prompt to JAYA", e)
                } finally {
                    _isLoading.value = false
                }
            }
        }
    }
}
