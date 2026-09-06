package com.example.jaya.iot

import android.util.Log
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

data class IotExecutionResult(
    val deviceName: String,
    val actionTaken: String,
    val isSuccess: Boolean,
    val message: String,
)

data class IotActionRequest(
    val deviceId: String,
    val action: String,
    val value: String,
)

data class IotGatewayReceipt(
    val success: Boolean,
    val message: String,
)

interface SmartHomeGateway {
    suspend fun execute(request: IotActionRequest): IotGatewayReceipt
}

class HomeAssistantBridge(
    private val gateway: SmartHomeGateway? = null,
) {
    suspend fun executeSmartHomeCommand(voiceCommand: String): IotExecutionResult =
        withContext(Dispatchers.IO) {
            require(voiceCommand.isNotBlank()) { "Voice command cannot be blank" }
            require(voiceCommand.length <= MAX_COMMAND_CHARACTERS) {
                "Voice command is too long"
            }
            val request = parseCommand(voiceCommand) ?: return@withContext IotExecutionResult(
                deviceName = "Unknown",
                actionTaken = "NONE",
                isSuccess = false,
                message = "Perintah perangkat tidak dikenali.",
            )
            val configuredGateway = gateway ?: return@withContext IotExecutionResult(
                deviceName = request.deviceId,
                actionTaken = request.action,
                isSuccess = false,
                message = "Gateway smart-home belum dikonfigurasi; tidak ada tindakan dijalankan.",
            )
            try {
                val receipt = configuredGateway.execute(request)
                IotExecutionResult(
                    deviceName = request.deviceId,
                    actionTaken = request.action,
                    isSuccess = receipt.success,
                    message = receipt.message,
                )
            } catch (error: Exception) {
                Log.e("HomeAssistantBridge", "Smart-home gateway execution failed")
                IotExecutionResult(
                    deviceName = request.deviceId,
                    actionTaken = request.action,
                    isSuccess = false,
                    message = "Gateway smart-home gagal menjalankan tindakan.",
                )
            }
        }

    private fun parseCommand(command: String): IotActionRequest? {
        val normalized = command.lowercase()
        return when {
            normalized.contains("lampu") -> IotActionRequest(
                deviceId = "light.bedroom",
                action = "SET_POWER",
                value = if (normalized.contains("mati")) "OFF" else "ON",
            )
            normalized.contains("ac") || normalized.contains("kipas") -> IotActionRequest(
                deviceId = "climate.living_room",
                action = "SET_POWER",
                value = if (normalized.contains("mati")) "OFF" else "ON",
            )
            else -> null
        }
    }

    private companion object {
        const val MAX_COMMAND_CHARACTERS = 2_000
    }
}