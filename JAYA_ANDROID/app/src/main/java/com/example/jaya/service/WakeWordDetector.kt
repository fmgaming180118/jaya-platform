package com.example.jaya.service

import android.util.Log
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

class WakeWordDetector {
    private val targetWakeWord = "hey jaya"
    
    private val _isListening = MutableStateFlow(false)
    val isListening: StateFlow<Boolean> = _isListening.asStateFlow()

    private val _wakeWordTriggered = MutableStateFlow(false)
    val wakeWordTriggered: StateFlow<Boolean> = _wakeWordTriggered.asStateFlow()

    fun startListening() {
        _isListening.value = true
        _wakeWordTriggered.value = false
        Log.d("WakeWordDetector", "Listening for '$targetWakeWord' wake-word in background...")
    }

    fun processAudioText(recognizedText: String): Boolean {
        if (recognizedText.lowercase().contains(targetWakeWord) || recognizedText.lowercase().contains("jaya")) {
            Log.d("WakeWordDetector", "Wake-word '$targetWakeWord' DETECTED!")
            _wakeWordTriggered.value = true
            return true
        }
        return false
    }

    fun stopListening() {
        _isListening.value = false
        _wakeWordTriggered.value = false
        Log.d("WakeWordDetector", "Wake-word detector stopped.")
    }
}
