package com.example.jaya.ui.settings

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.example.jaya.BuildConfig
import com.example.jaya.data.ChatRepository
import com.example.jaya.data.local.AppDatabase
import com.example.jaya.data.remote.NetworkModule
import com.example.jaya.security.KeystoreSecretStore
import com.example.jaya.security.SecretStoreException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

class SettingsViewModel(application: Application) : AndroidViewModel(application) {
    private val repository: ChatRepository
    private val secretStore = KeystoreSecretStore(application)

    private val _apiKey = MutableStateFlow("")
    val apiKey: StateFlow<String> = _apiKey.asStateFlow()

    private val _baseUrl = MutableStateFlow(BuildConfig.JAYA_API_URL)
    val baseUrl: StateFlow<String> = _baseUrl.asStateFlow()

    private val _settingsError = MutableStateFlow<String?>(null)
    val settingsError: StateFlow<String?> = _settingsError.asStateFlow()

    init {
        val database = AppDatabase.getDatabase(application)
        repository = ChatRepository(database.chatDao(), application)

        viewModelScope.launch(Dispatchers.IO) {
            try {
                // Never migrate the legacy plaintext API_KEY row; require re-entry.
                repository.deletePreference(LEGACY_API_KEY_PREFERENCE)
                _apiKey.value = secretStore.getString(
                    ChatRepository.API_KEY_SECRET_NAME
                ).orEmpty()
                val configuredUrl = repository.getPreference(BASE_URL_PREFERENCE)
                    ?: BuildConfig.JAYA_API_URL
                _baseUrl.value = NetworkModule.normalizeAndValidateBaseUrl(configuredUrl)
            } catch (error: SecretStoreException) {
                _apiKey.value = ""
                _settingsError.value = "Secure API-key storage is unavailable"
            } catch (error: IllegalArgumentException) {
                _baseUrl.value = BuildConfig.JAYA_API_URL
                _settingsError.value = "Saved server URL is invalid"
            }
        }
    }

    fun updateApiKey(newKey: String) {
        viewModelScope.launch(Dispatchers.IO) {
            try {
                secretStore.putString(ChatRepository.API_KEY_SECRET_NAME, newKey)
                _apiKey.value = newKey
                _settingsError.value = null
            } catch (error: SecretStoreException) {
                _settingsError.value = "API key was not saved securely"
            }
        }
    }

    fun updateBaseUrl(newUrl: String) {
        viewModelScope.launch(Dispatchers.IO) {
            try {
                val normalized = NetworkModule.normalizeAndValidateBaseUrl(newUrl)
                repository.savePreference(BASE_URL_PREFERENCE, normalized)
                _baseUrl.value = normalized
                _settingsError.value = null
            } catch (error: IllegalArgumentException) {
                _settingsError.value = "Server URL must be valid and use HTTPS"
            }
        }
    }

    fun dismissError() {
        _settingsError.value = null
    }

    private companion object {
        const val BASE_URL_PREFERENCE = "BASE_URL"
        const val LEGACY_API_KEY_PREFERENCE = "API_KEY"
    }
}