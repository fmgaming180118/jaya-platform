package com.example.jaya.data.network

import android.util.Log
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

data class SyncReceipt(
    val uploadedItems: Int,
    val downloadedItems: Int,
    val serverRevision: String,
)

interface EcosystemSyncAdapter {
    suspend fun synchronize(): SyncReceipt
}

data class SyncReport(
    val lastSyncTimestamp: Long?,
    val pendingUploads: Int,
    val downloadedPatches: Int,
    val isSyncing: Boolean,
    val lastErrorCode: String? = null,
)

class AutoSyncManager(
    private val syncAdapter: EcosystemSyncAdapter? = null,
    private val clockMillis: () -> Long = System::currentTimeMillis,
) {
    private val _syncReport = MutableStateFlow(
        SyncReport(
            lastSyncTimestamp = null,
            pendingUploads = 0,
            downloadedPatches = 0,
            isSyncing = false,
        )
    )
    val syncReport: StateFlow<SyncReport> = _syncReport.asStateFlow()

    suspend fun performBiDirectionalSync(): Boolean {
        val adapter = syncAdapter
        if (adapter == null) {
            _syncReport.value = _syncReport.value.copy(
                isSyncing = false,
                lastErrorCode = "SYNC_ADAPTER_UNAVAILABLE",
            )
            return false
        }
        _syncReport.value = _syncReport.value.copy(
            isSyncing = true,
            lastErrorCode = null,
        )
        return try {
            val receipt = adapter.synchronize()
            require(receipt.uploadedItems >= 0 && receipt.downloadedItems >= 0) {
                "Sync receipt counters cannot be negative"
            }
            require(receipt.serverRevision.isNotBlank()) {
                "Sync receipt must include a server revision"
            }
            _syncReport.value = SyncReport(
                lastSyncTimestamp = clockMillis(),
                pendingUploads = 0,
                downloadedPatches = receipt.downloadedItems,
                isSyncing = false,
            )
            true
        } catch (error: Exception) {
            Log.e("AutoSync", "Ecosystem sync failed")
            _syncReport.value = _syncReport.value.copy(
                isSyncing = false,
                lastErrorCode = "SYNC_FAILED",
            )
            false
        }
    }
}