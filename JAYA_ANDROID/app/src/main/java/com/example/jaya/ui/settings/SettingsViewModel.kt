package com.example.jaya.ui.settings

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.example.jaya.BuildConfig
import com.example.jaya.data.ChatRepository
import com.example.jaya.data.local.AppDatabase
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

class SettingsViewModel(application: Application) : AndroidViewModel(application) {
    private val repository: ChatRepository

    private val _apiKey = MutableStateFlow("")
    val apiKey: StateFlow<String> = _apiKey.asStateFlow()

    private val _baseUrl = MutableStateFlow("https://integrate.api.nvidia.com/v1/")
    val baseUrl: StateFlow<String> = _baseUrl.asStateFlow()

    init {
        val database = AppDatabase.getDatabase(application)
        repository = ChatRepository(database.chatDao(), application.filesDir)
        
        viewModelScope.launch {
            _apiKey.value = repository.getPreference("API_KEY") ?: BuildConfig.NVIDIA_API_KEY
            _baseUrl.value = repository.getPreference("BASE_URL") ?: "https://integrate.api.nvidia.com/v1/"
        }
    }

    fun updateApiKey(newKey: String) {
        _apiKey.value = newKey
        viewModelScope.launch {
            repository.saveUserPreference("API_KEY", newKey)
        }
    }

    fun updateBaseUrl(newUrl: String) {
        _baseUrl.value = newUrl
        viewModelScope.launch {
            repository.saveUserPreference("BASE_URL", newUrl)
        }
    }
}
