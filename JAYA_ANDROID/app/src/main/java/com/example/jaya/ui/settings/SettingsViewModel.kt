package com.example.jaya.ui.settings

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.example.jaya.BuildConfig
import com.example.jaya.data.ChatRepository
import com.example.jaya.data.local.AppDatabase
import com.example.jaya.data.remote.NetworkModule
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

class SettingsViewModel(application: Application) : AndroidViewModel(application) {
    private val repository: ChatRepository

    private val _apiKey = MutableStateFlow("")
    val apiKey: StateFlow<String> = _apiKey.asStateFlow()

    private val _baseUrl = MutableStateFlow(NetworkModule.DEFAULT_JAYA_API_URL)
    val baseUrl: StateFlow<String> = _baseUrl.asStateFlow()

    init {
        val database = AppDatabase.getDatabase(application)
        repository = ChatRepository(database.chatDao(), application.filesDir)
        
        viewModelScope.launch {
            _apiKey.value = repository.getPreference("API_KEY") ?: "JAYA_SOVEREIGN_PASSPHRASE"
            _baseUrl.value = repository.getPreference("BASE_URL") ?: BuildConfig.JAYA_API_URL
        }
    }

    fun updateApiKey(newKey: String) {
        _apiKey.value = newKey
        viewModelScope.launch {
            repository.savePreference("API_KEY", newKey)
        }
    }

    fun updateBaseUrl(newUrl: String) {
        _baseUrl.value = newUrl
        viewModelScope.launch {
            repository.savePreference("BASE_URL", newUrl)
        }
    }
}
