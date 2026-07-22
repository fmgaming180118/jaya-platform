package com.example.jaya.ui.dashboard

import android.app.Application
import android.content.Intent
import android.os.Bundle
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import android.speech.tts.TextToSpeech
import android.util.Log
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.example.jaya.data.ChatRepository
import com.example.jaya.data.local.AppDatabase
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import java.util.Locale

enum class JarvisState {
    IDLE, LISTENING, PROCESSING, SPEAKING, ERROR
}

class DashboardViewModel(application: Application) : AndroidViewModel(application), RecognitionListener {

    private val repository: ChatRepository
    private val _state = MutableStateFlow(JarvisState.IDLE)
    val state: StateFlow<JarvisState> = _state.asStateFlow()

    private val _lastTranscribedText = MutableStateFlow("")
    val lastTranscribedText: StateFlow<String> = _lastTranscribedText.asStateFlow()

    private val _aiResponse = MutableStateFlow("")
    val aiResponse: StateFlow<String> = _aiResponse.asStateFlow()

    private var speechRecognizer: SpeechRecognizer? = null
    private var tts: TextToSpeech? = null

    init {
        val database = AppDatabase.getDatabase(application)
        repository = ChatRepository(database.chatDao(), application.filesDir)
        
        speechRecognizer = SpeechRecognizer.createSpeechRecognizer(application).apply {
            setRecognitionListener(this@DashboardViewModel)
        }
        tts = TextToSpeech(application) { status ->
            if (status == TextToSpeech.SUCCESS) {
                tts?.language = Locale.US
            }
        }
    }

    fun startListening() {
        if (_state.value == JarvisState.LISTENING) return
        
        val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
            putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
            putExtra(RecognizerIntent.EXTRA_LANGUAGE, Locale.getDefault())
        }
        _state.value = JarvisState.LISTENING
        _aiResponse.value = ""
        speechRecognizer?.startListening(intent)
    }

    fun stopListening() {
        speechRecognizer?.stopListening()
        _state.value = JarvisState.IDLE
    }

    private fun processUserQuery(text: String) {
        if (text.isBlank()) {
            _state.value = JarvisState.IDLE
            return
        }

        _state.value = JarvisState.PROCESSING
        viewModelScope.launch {
            try {
                val response = repository.sendPromptToJaya(0, text)
                _aiResponse.value = response
                speak(response)
            } catch (e: Exception) {
                _state.value = JarvisState.ERROR
                _aiResponse.value = "Error: ${e.localizedMessage}"
            }
        }
    }

    @Suppress("SpellCheckingInspection")
    private fun speak(text: String) {
        _state.value = JarvisState.SPEAKING
        val cleanText = text.replace(Regex("""\[.*?]"""), "").replace("*", "")
        tts?.speak(cleanText, TextToSpeech.QUEUE_FLUSH, null, "JayaTTS")
    }

    // RecognitionListener callbacks
    override fun onReadyForSpeech(params: Bundle?) { Log.d("Jarvis", "Ready for speech") }
    override fun onBeginningOfSpeech() { Log.d("Jarvis", "Beginning of speech") }
    override fun onRmsChanged(rmsdB: Float) {}
    override fun onBufferReceived(buffer: ByteArray?) {}
    override fun onEndOfSpeech() {
        Log.d("Jarvis", "End of speech")
        if (_state.value == JarvisState.LISTENING) {
            _state.value = JarvisState.PROCESSING
        }
    }
    override fun onError(error: Int) {
        Log.e("Jarvis", "STT Error: $error")
        _state.value = JarvisState.ERROR
    }
    override fun onResults(results: Bundle?) {
        val matches = results?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
        val text = matches?.firstOrNull() ?: ""
        _lastTranscribedText.value = text
        processUserQuery(text)
    }
    override fun onPartialResults(partialResults: Bundle?) {}
    override fun onEvent(eventType: Int, params: Bundle?) {}

    override fun onCleared() {
        speechRecognizer?.destroy()
        tts?.stop()
        tts?.shutdown()
    }
}
