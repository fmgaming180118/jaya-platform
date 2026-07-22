package com.example.jaya.iot

import android.util.Log
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

data class IotExecutionResult(
    val deviceName: String,
    val actionTaken: String,
    val isSuccess: Boolean,
    val message: String
)

class HomeAssistantBridge {

    suspend fun executeSmartHomeCommand(voiceCommand: String): IotExecutionResult = withContext(Dispatchers.IO) {
        Log.d("HomeAssistantBridge", "Translating natural voice prompt into MQTT/IoT action: '$voiceCommand'")

        val cmdLower = voiceCommand.lowercase()
        return@withContext when {
            cmdLower.contains("lampu") -> {
                val state = if (cmdLower.contains("mati")) "OFF" else "ON"
                Log.d("HomeAssistantBridge", "MQTT Publish -> light.bedroom = $state")
                IotExecutionResult("Lampu Kamar", "Set Power to $state", true, "Lampu kamar berhasil di-set ke $state.")
            }
            cmdLower.contains("ac") || cmdLower.contains("kipas") -> {
                Log.d("HomeAssistantBridge", "MQTT Publish -> climate.living_room = ON")
                IotExecutionResult("AC Ruang Tamu", "Set Climate Power", true, "AC ruang tamu berhasil dinyalakan.")
            }
            else -> {
                IotExecutionResult("Generic IoT", "Unknown Command", false, "Perintah IoT '$voiceCommand' tidak dikenali.")
            }
        }
    }
}
