package com.example.jaya.iot

import android.util.Log
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

data class SmartDevice(
    val id: String,
    val name: String,
    val room: String,
    val type: String,
    val isOnline: Boolean
)

class SmartDeviceRegistry {
    private val _devices = MutableStateFlow<List<SmartDevice>>(
        listOf(
            SmartDevice("dev-1", "Lampu Kamar Utama", "Kamar Tidur", "Light", true),
            SmartDevice("dev-2", "AC Inverter 1PK", "Ruang Tamu", "Climate", true),
            SmartDevice("dev-3", "Smart Door Lock", "Pintu Depan", "Lock", true)
        )
    )
    val devices: StateFlow<List<SmartDevice>> = _devices.asStateFlow()

    fun getDevicesInRoom(roomName: String): List<SmartDevice> {
        return _devices.value.filter { it.room.equals(roomName, ignoreCase = true) }
    }

    fun registerDevice(device: SmartDevice) {
        val current = _devices.value.toMutableList()
        current.add(device)
        _devices.value = current
        Log.d("SmartDeviceRegistry", "Registered new IoT device: ${device.name} in ${device.room}")
    }
}
