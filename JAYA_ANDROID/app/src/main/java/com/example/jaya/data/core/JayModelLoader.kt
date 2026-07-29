package com.example.jaya.data.core

import android.content.Context
import android.util.Log
import com.example.jaya.BuildConfig
import java.io.ByteArrayOutputStream
import java.io.InputStream
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.security.MessageDigest
import java.util.zip.CRC32

class JayModelLoader(
    private val context: Context,
    private val expectedSha256: String = BuildConfig.JAYA_MODEL_SHA256,
) {
    var isLoaded: Boolean = false
        private set

    var modelVersion: String = "unavailable"
        private set

    var artifactSha256: String? = null
        private set

    private var packedPayloadSize: Long = 0
    private var loadedAssetPath: String? = null

    fun loadModelFromAssets(assetPath: String = DEFAULT_MODEL_ASSET): Boolean {
        reset()
        if (!expectedSha256.matches(SHA256_PATTERN)) {
            Log.w("JayModelLoader", "Model allowlist digest is not configured")
            return false
        }
        return try {
            val bytes = context.assets.open(assetPath).use(::readBounded)
            val fullDigest = MessageDigest.getInstance("SHA-256").digest(bytes)
            val expectedDigest = expectedSha256.hexToBytes()
            if (!MessageDigest.isEqual(fullDigest, expectedDigest)) {
                Log.e("JayModelLoader", "Model artifact digest mismatch")
                return false
            }
            val metadata = validateJayV18(bytes) ?: return false
            modelVersion = "${metadata.major}.${metadata.minor}"
            packedPayloadSize = metadata.packedPayloadSize
            artifactSha256 = fullDigest.toHex()
            loadedAssetPath = assetPath
            isLoaded = true
            Log.i("JayModelLoader", "Verified local model artifact loaded")
            true
        } catch (error: Exception) {
            reset()
            Log.e("JayModelLoader", "Verified local model could not be loaded")
            false
        }
    }

    fun openVerifiedModel(): InputStream {
        check(isLoaded) { "Model must be verified before opening" }
        val assetPath = loadedAssetPath ?: error("Verified asset path is unavailable")
        return context.assets.open(assetPath)
    }

    fun getModelSummary(): String = if (isLoaded) {
        "Verified JAYA model v$modelVersion | packed=${packedPayloadSize}B | sha256=${artifactSha256?.take(12)}"
    } else {
        "Verified local model unavailable"
    }

    private fun validateJayV18(bytes: ByteArray): ModelMetadata? {
        if (bytes.size < HEADER_BYTES + SECTION_HEADER_BYTES + FOOTER_BYTES) {
            return invalid("Model artifact is too small")
        }
        if (!bytes.copyOfRange(0, MAGIC.size).contentEquals(MAGIC)) {
            return invalid("Model magic is invalid")
        }
        val buffer = ByteBuffer.wrap(bytes).order(ByteOrder.LITTLE_ENDIAN)
        val major = buffer.getShort(4).toInt() and 0xffff
        val minor = buffer.getShort(6).toInt() and 0xffff
        val flags = buffer.getLong(8)
        if (major != SUPPORTED_MAJOR_VERSION) {
            return invalid("Model version is unsupported")
        }
        if ((flags and PACKED_WEIGHTS_FLAG) == 0L) {
            return invalid("Model does not declare packed weights")
        }

        val bodyEnd = bytes.size - FOOTER_BYTES
        val body = bytes.copyOfRange(0, bodyEnd)
        val expectedCrc = buffer.getInt(bodyEnd).toLong() and UINT32_MASK
        val actualCrc = CRC32().apply { update(body) }.value
        if (actualCrc != expectedCrc) {
            return invalid("Model CRC check failed")
        }
        val storedBodyDigest = bytes.copyOfRange(bodyEnd + CRC_BYTES, bytes.size)
        val actualBodyDigest = MessageDigest.getInstance("SHA-256")
            .digest(body)
            .copyOf(storedBodyDigest.size)
        if (!MessageDigest.isEqual(storedBodyDigest, actualBodyDigest)) {
            return invalid("Model footer digest check failed")
        }

        var sectionOffset = HEADER_BYTES
        var packedSize = 0L
        while (sectionOffset + SECTION_HEADER_BYTES <= bodyEnd) {
            val sectionType = buffer.getInt(sectionOffset)
            if (sectionType == 0) break
            val sectionSize = buffer.getLong(sectionOffset + 8)
            val payloadOffset = buffer.getLong(sectionOffset + 16)
            if (
                sectionSize <= 0 ||
                payloadOffset < HEADER_BYTES ||
                payloadOffset > bodyEnd ||
                sectionSize > bodyEnd - payloadOffset
            ) {
                return invalid("Model section bounds are invalid")
            }
            if (sectionType == PACKED_WEIGHTS_SECTION) {
                val start = payloadOffset.toInt()
                if (
                    sectionSize < PACKED_PAYLOAD_MAGIC.size ||
                    !bytes.copyOfRange(
                        start,
                        start + PACKED_PAYLOAD_MAGIC.size,
                    ).contentEquals(PACKED_PAYLOAD_MAGIC)
                ) {
                    return invalid("Packed weight payload is invalid")
                }
                packedSize = sectionSize
            }
            sectionOffset += SECTION_HEADER_BYTES
        }
        if (packedSize == 0L) {
            return invalid("Packed weight section is missing")
        }
        return ModelMetadata(major, minor, packedSize)
    }

    private fun readBounded(input: InputStream): ByteArray {
        val output = ByteArrayOutputStream()
        val buffer = ByteArray(READ_BUFFER_BYTES)
        var total = 0
        while (true) {
            val read = input.read(buffer)
            if (read < 0) break
            total += read
            require(total <= MAX_MODEL_BYTES) { "Model artifact exceeds size limit" }
            output.write(buffer, 0, read)
        }
        return output.toByteArray()
    }

    private fun invalid(message: String): ModelMetadata? {
        Log.e("JayModelLoader", message)
        return null
    }

    private fun reset() {
        isLoaded = false
        modelVersion = "unavailable"
        artifactSha256 = null
        packedPayloadSize = 0
        loadedAssetPath = null
    }

    private data class ModelMetadata(
        val major: Int,
        val minor: Int,
        val packedPayloadSize: Long,
    )

    private companion object {
        val MAGIC = "JAYA".toByteArray(Charsets.US_ASCII)
        val PACKED_PAYLOAD_MAGIC = "T2BV".toByteArray(Charsets.US_ASCII)
        val SHA256_PATTERN = Regex("[a-fA-F0-9]{64}")
        const val CRC_BYTES = 4
        const val DEFAULT_MODEL_ASSET = "models/JAYA_SOVEREIGN_V18.jay"
        const val FOOTER_BYTES = 32
        const val HEADER_BYTES = 128
        const val MAX_MODEL_BYTES = 320 * 1024 * 1024
        const val PACKED_WEIGHTS_FLAG = 1L shl 42
        const val PACKED_WEIGHTS_SECTION = 6
        const val READ_BUFFER_BYTES = 64 * 1024
        const val SECTION_HEADER_BYTES = 24
        const val SUPPORTED_MAJOR_VERSION = 18
        const val UINT32_MASK = 0xffff_ffffL
    }
}

private fun String.hexToBytes(): ByteArray =
    chunked(2).map { it.toInt(16).toByte() }.toByteArray()

private fun ByteArray.toHex(): String =
    joinToString(separator = "") { byte -> "%02x".format(byte) }