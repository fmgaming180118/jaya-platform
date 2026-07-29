package com.example.jaya

import com.example.jaya.data.core.DocumentChunk
import com.example.jaya.data.core.JayaNanoEngine
import com.example.jaya.data.core.LocalVectorStore
import com.example.jaya.data.core.NanoRuntimeStatus
import com.example.jaya.data.core.NanoRuntimeUnavailableException
import com.example.jaya.data.core.OnDeviceNeuralGenerator
import com.example.jaya.data.network.AutoSyncManager
import com.example.jaya.data.network.EcosystemSyncAdapter
import com.example.jaya.data.network.SyncReceipt
import com.example.jaya.iot.HomeAssistantBridge
import com.example.jaya.iot.IotActionRequest
import com.example.jaya.iot.IotGatewayReceipt
import com.example.jaya.iot.SmartHomeGateway
import com.example.jaya.iot.WearCommandHandler
import com.example.jaya.iot.WearMessage
import com.example.jaya.iot.WearOsBridgeService
import com.example.jaya.security.PqcEncryptedBackup
import com.example.jaya.security.PqcProviderUnavailableException
import com.example.jaya.skills.SearchProvider
import com.example.jaya.skills.SearchSkill
import com.example.jaya.skills.WebSearchItem
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Test

class SecurityTruthfulnessTest {
    @Test
    fun templateGeneratorAndUnconfiguredNanoFailClosed() = runTest {
        try {
            OnDeviceNeuralGenerator().generateNeuralResponse("hello")
            fail("Legacy template generator must not produce an answer")
        } catch (error: NanoRuntimeUnavailableException) {
            assertEquals(NanoRuntimeStatus.UNAVAILABLE, error.status)
        }

        val engine = JayaNanoEngine()
        assertFalse(engine.initializeNanoKernel())
        try {
            engine.generateResponse("hello")
            fail("Nano engine without artifact/backend must fail")
        } catch (error: NanoRuntimeUnavailableException) {
            assertEquals(NanoRuntimeStatus.UNAVAILABLE, error.status)
        }
    }

    @Test
    fun searchNeverFabricatesProviderResults() = runTest {
        val unavailable = SearchSkill().execute("cari di internet topik", 1)
        assertFalse(unavailable.success)
        assertEquals("SEARCH_PROVIDER_UNAVAILABLE", unavailable.errorCode)

        val provider = object : SearchProvider {
            override suspend fun search(query: String, limit: Int) = listOf(
                WebSearchItem("Unsafe", "http://example.com", "ignored"),
                WebSearchItem("Verified", "https://example.org/source", "evidence"),
            )
        }
        val result = SearchSkill(provider).execute("cari di internet topik", 1)
        assertTrue(result.success)
        assertTrue(result.content.contains("https://example.org/source"))
        assertFalse(result.content.contains("http://example.com"))
    }

    @Test
    fun iotDoesNotClaimExecutionWithoutGateway() = runTest {
        val unavailable = HomeAssistantBridge().executeSmartHomeCommand("nyalakan lampu")
        assertFalse(unavailable.isSuccess)
        assertTrue(unavailable.message.contains("tidak ada tindakan"))

        var received: IotActionRequest? = null
        val gateway = object : SmartHomeGateway {
            override suspend fun execute(request: IotActionRequest): IotGatewayReceipt {
                received = request
                return IotGatewayReceipt(true, "receipt-ok")
            }
        }
        val executed = HomeAssistantBridge(gateway)
            .executeSmartHomeCommand("matikan lampu")
        assertTrue(executed.isSuccess)
        assertEquals("OFF", received?.value)
    }

    @Test
    fun syncCountersComeFromAdapterReceipt() = runTest {
        val unavailable = AutoSyncManager()
        assertFalse(unavailable.performBiDirectionalSync())
        assertEquals(0, unavailable.syncReport.value.downloadedPatches)

        val adapter = object : EcosystemSyncAdapter {
            override suspend fun synchronize() = SyncReceipt(2, 3, "revision-1")
        }
        val manager = AutoSyncManager(adapter) { 1234L }
        assertTrue(manager.performBiDirectionalSync())
        assertEquals(3, manager.syncReport.value.downloadedPatches)
        assertEquals(1234L, manager.syncReport.value.lastSyncTimestamp)
    }

    @Test
    fun wearPromptRequiresPairingAndConfiguredHandler() = runTest {
        val now = 10_000L
        val service = WearOsBridgeService(clockMillis = { now })
        val unpaired = service.processWristVoicePrompt(
            WearMessage("watch-1", "status", now)
        )
        assertFalse(unpaired.accepted)
        assertEquals("DEVICE_NOT_PAIRED", unpaired.errorCode)

        service.updateConnectedWearables(listOf("watch-1"))
        val unavailable = service.processWristVoicePrompt(
            WearMessage("watch-1", "status", now)
        )
        assertFalse(unavailable.accepted)
        assertEquals("HANDLER_UNAVAILABLE", unavailable.errorCode)

        val handler = object : WearCommandHandler {
            override suspend fun handle(prompt: String, senderDeviceId: String) = "ok"
        }
        val configured = WearOsBridgeService(handler) { now }
        configured.updateConnectedWearables(listOf("watch-1"))
        assertTrue(
            configured.processWristVoicePrompt(
                WearMessage("watch-1", "status", now)
            ).accepted
        )
    }

    @Test
    fun localVectorStoreRejectsDimensionMismatch() = runTest {
        val store = LocalVectorStore()
        store.addDocumentChunk(DocumentChunk("a", "doc", "text", listOf(1f, 0f)))
        try {
            store.addDocumentChunk(DocumentChunk("b", "doc", "text", listOf(1f)))
            fail("Dimension mismatch must be rejected")
        } catch (error: IllegalArgumentException) {
            assertTrue(error.message.orEmpty().contains("dimension"))
        }
    }

    @Test(expected = PqcProviderUnavailableException::class)
    fun pqcBackupRequiresRealProvider() = runTest {
        PqcEncryptedBackup().createPqcEncryptedBackup("{\"memory\":[]}")
    }
}
