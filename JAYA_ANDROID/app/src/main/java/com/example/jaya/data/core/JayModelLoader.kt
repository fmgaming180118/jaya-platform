package com.example.jaya.data.core

import android.content.Context
import android.util.Log
import java.io.InputStream
import java.nio.ByteBuffer
import java.nio.ByteOrder

class JayModelLoader(private val context: Context) {

    var isLoaded: Boolean = false
        private set

    var modelVersion: String = "JAYA_SOVEREIGN_V18"
        private set

    private var packedPayloadSize: Long = 0

    fun loadModelFromAssets(assetPath: String = "models/JAYA_SOVEREIGN_V18.jay"): Boolean {
        return try {
            val inputStream: InputStream = context.assets.open(assetPath)
            val bytes = inputStream.readBytes()
            inputStream.close()

            if (bytes.size < 128) {
                Log.e("JayModelLoader", "Invalid .jay file: Header too small (${bytes.size} bytes)")
                return false
            }

            val buffer = ByteBuffer.wrap(bytes).order(ByteOrder.LITTLE_ENDIAN)

            // Read magic & flags (first 16 bytes)
            val magic = buffer.long
            val flags = buffer.long

            val packedWeightsBit = 1L shl 42
            val hasPackedWeights = (flags and packedWeightsBit) != 0L

            Log.d("JayModelLoader", "Loaded .jay binary: size=${bytes.size} B, packedWeights=$hasPackedWeights")

            // Scan section headers (128 bytes offset, 24 bytes per section header)
            var sectionOffset = 128
            val sectionHeaderSize = 24
            val footerSize = 32

            while (sectionOffset + sectionHeaderSize <= bytes.size - footerSize) {
                buffer.position(sectionOffset)
                val secType = buffer.int
                buffer.position(sectionOffset + 8)
                val secSize = buffer.long
                val secOffPl = buffer.long

                if (secType == 6 && secSize > 0) { // Section 6: IRON_BODY_PACKED
                    packedPayloadSize = secSize
                    Log.d("JayModelLoader", "Found IRON_BODY_PACKED section: size=$secSize B at offset=$secOffPl")
                    break
                }
                sectionOffset += sectionHeaderSize
            }

            isLoaded = true
            Log.d("JayModelLoader", "Successfully initialized physical .jay model ($modelVersion)")
            true
        } catch (e: Exception) {
            Log.e("JayModelLoader", "Error loading .jay model file", e)
            isLoaded = false
            false
        }
    }

    fun getModelSummary(): String {
        return if (isLoaded) {
            "Model Physical: $modelVersion | Mode: 2-bit Packed (.jay) | Size: ${packedPayloadSize}B"
        } else {
            "Model Physical: Not Loaded"
        }
    }
}
