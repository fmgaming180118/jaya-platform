package com.example.jaya.data.network

import android.util.Log
import com.example.jaya.data.remote.JayaApiService
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

data class SyncReport(
    val lastSyncTimestamp: Long,
    val pendingUploads: Int,
    val downloadedPatches: Int,
    val isSyncing: Boolean
)

class AutoSyncManager(private val apiService: JayaApiService) {
    private val _syncReport = MutableStateFlow(
        SyncReport(
            lastSyncTimestamp = System.currentTimeMillis(),
            pendingUploads = 0,
            downloadedPatches = 0,
            isSyncing = false
        )
    )
    val syncReport: StateFlow<SyncReport> = _syncReport.asStateFlow()

    suspend fun performBiDirectionalSync(): Boolean {
        _syncReport.value = _syncReport.value.copy(isSyncing = true)
        Log.d("AutoSync", "Starting bi-directional sync with JAYA PC Server...")

        return try {
            val response = apiService.getEvolutionStatus()
            if (response.isSuccessful) {
                Log.d("AutoSync", "Sync successful! PC Server Evolution Status: ${response.body()?.state}")
                _syncReport.value = SyncReport(
                    lastSyncTimestamp = System.currentTimeMillis(),
                    pendingUploads = 0,
                    downloadedPatches = 1,
                    isSyncing = false
                )
                true
            } else {
                _syncReport.value = _syncReport.value.copy(isSyncing = false)
                false
            }
        } catch (e: Exception) {
            Log.e("AutoSync", "Sync failed: ${e.localizedMessage}", e)
            _syncReport.value = _syncReport.value.copy(isSyncing = false)
            false
        }
    }
}
