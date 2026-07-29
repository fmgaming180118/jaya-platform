package com.example.jaya.service

import android.content.Context
import android.speech.tts.TextToSpeech
import android.util.Log
import java.util.Locale

class JayaTextToSpeechManager(context: Context) : TextToSpeech.OnInitListener {

    private var tts: TextToSpeech? = TextToSpeech(context, this)
    private var isReady = false

    override fun onInit(status: Int) {
        if (status == TextToSpeech.SUCCESS) {
            val indonesianLocale = Locale.forLanguageTag("id-ID")
            val result = tts?.setLanguage(indonesianLocale)
            if (result == TextToSpeech.LANG_MISSING_DATA || result == TextToSpeech.LANG_NOT_SUPPORTED) {
                tts?.setLanguage(Locale.US)
            }
            isReady = true
            Log.d("JayaTTS", "Text-to-Speech Engine initialized successfully.")
        } else {
            Log.e("JayaTTS", "Text-to-Speech initialization failed with status $status")
        }
    }

    fun speak(text: String) {
        if (isReady && tts != null) {
            tts?.speak(text, TextToSpeech.QUEUE_FLUSH, null, "JayaTTSID")
        } else {
            Log.w("JayaTTS", "TTS not ready; speech was skipped")
        }
    }

    fun stop() {
        tts?.stop()
    }

    fun shutdown() {
        tts?.stop()
        tts?.shutdown()
        tts = null
        isReady = false
    }
}
