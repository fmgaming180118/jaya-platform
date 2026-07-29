package com.example.jaya.security

import android.util.Base64
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

class PqcProviderUnavailableException(message: String) : IllegalStateException(message)

data class PqcCiphertext(
    val ciphertext: ByteArray,
    val signature: ByteArray,
)

data class PqcBackupPayload(
    val encryptedDataBase64: String,
    val pqcSignatureBase64: String,
    val algorithm: String,
    val keyId: String,
)

/** Real providers must be backed by reviewed ML-KEM/ML-DSA implementations. */
interface PqcBackupProvider {
    val algorithm: String
    val keyId: String

    fun selfTest(): Boolean
    fun encryptAndSign(plaintext: ByteArray): PqcCiphertext
}

/**
 * Fail-closed PQC backup facade. No provider is bundled yet, so callers receive
 * an explicit unavailable error instead of Base64 data mislabeled as PQC.
 */
class PqcEncryptedBackup(
    private val provider: PqcBackupProvider? = null,
    private val maxPayloadBytes: Int = DEFAULT_MAX_PAYLOAD_BYTES,
) {
    suspend fun createPqcEncryptedBackup(rawMemoryJson: String): PqcBackupPayload =
        withContext(Dispatchers.Default) {
            val implementation = provider ?: throw PqcProviderUnavailableException(
                "PQC backup provider is not configured"
            )
            val plaintext = rawMemoryJson.toByteArray(Charsets.UTF_8)
            require(plaintext.isNotEmpty()) { "Backup payload cannot be empty" }
            require(plaintext.size <= maxPayloadBytes) { "Backup payload exceeds size limit" }
            require(implementation.algorithm in APPROVED_ALGORITHMS) {
                "PQC provider algorithm is not approved"
            }
            require(implementation.keyId.isNotBlank()) { "PQC provider key ID is required" }
            if (!implementation.selfTest()) {
                throw PqcProviderUnavailableException("PQC provider self-test failed")
            }

            val result = implementation.encryptAndSign(plaintext.copyOf())
            require(result.ciphertext.isNotEmpty()) { "PQC ciphertext cannot be empty" }
            require(result.signature.isNotEmpty()) { "PQC signature cannot be empty" }
            PqcBackupPayload(
                encryptedDataBase64 = Base64.encodeToString(
                    result.ciphertext,
                    Base64.NO_WRAP,
                ),
                pqcSignatureBase64 = Base64.encodeToString(
                    result.signature,
                    Base64.NO_WRAP,
                ),
                algorithm = implementation.algorithm,
                keyId = implementation.keyId,
            )
        }

    private companion object {
        const val DEFAULT_MAX_PAYLOAD_BYTES = 10 * 1024 * 1024
        val APPROVED_ALGORITHMS = setOf(
            "ML-KEM-768+ML-DSA-65+AES-256-GCM",
            "ML-KEM-1024+ML-DSA-87+AES-256-GCM",
        )
    }
}