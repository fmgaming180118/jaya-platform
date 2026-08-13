package com.example.jaya.security

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import java.security.GeneralSecurityException
import java.security.KeyStore
import java.security.SecureRandom
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

class SecretStoreException(message: String, cause: Throwable? = null) :
    IllegalStateException(message, cause)

/**
 * Stores only AES-GCM ciphertext in SharedPreferences. The wrapping key remains
 * non-exportable inside AndroidKeyStore; there is intentionally no plaintext
 * fallback when the keystore is unavailable.
 */
class KeystoreSecretStore(
    context: Context,
    private val keyAlias: String = DEFAULT_KEY_ALIAS,
    preferencesName: String = DEFAULT_PREFERENCES_NAME,
) {
    private val preferences = context.applicationContext.getSharedPreferences(
        preferencesName,
        Context.MODE_PRIVATE,
    )
    private val secureRandom = SecureRandom()

    @Synchronized
    fun putString(name: String, value: String) {
        require(name.isNotBlank()) { "Secret name cannot be blank" }
        if (value.isEmpty()) {
            remove(name)
            return
        }
        try {
            val cipher = Cipher.getInstance(TRANSFORMATION)
            cipher.init(Cipher.ENCRYPT_MODE, getOrCreateKey())
            val ciphertext = cipher.doFinal(value.toByteArray(Charsets.UTF_8))
            val payload = listOf(
                PAYLOAD_VERSION,
                Base64.encodeToString(cipher.iv, Base64.NO_WRAP),
                Base64.encodeToString(ciphertext, Base64.NO_WRAP),
            ).joinToString(":")
            if (!preferences.edit().putString(name, payload).commit()) {
                throw SecretStoreException("Secure secret persistence failed")
            }
        } catch (error: SecretStoreException) {
            throw error
        } catch (error: GeneralSecurityException) {
            throw SecretStoreException("Android keystore encryption failed", error)
        }
    }

    @Synchronized
    fun getString(name: String): String? {
        require(name.isNotBlank()) { "Secret name cannot be blank" }
        val payload = preferences.getString(name, null) ?: return null
        val fields = payload.split(':')
        if (fields.size != 3 || fields[0] != PAYLOAD_VERSION) {
            throw SecretStoreException("Unsupported secure secret payload")
        }
        try {
            val iv = Base64.decode(fields[1], Base64.NO_WRAP)
            val ciphertext = Base64.decode(fields[2], Base64.NO_WRAP)
            require(iv.size == GCM_IV_BYTES) { "Invalid AES-GCM IV" }
            val cipher = Cipher.getInstance(TRANSFORMATION)
            cipher.init(
                Cipher.DECRYPT_MODE,
                getOrCreateKey(),
                GCMParameterSpec(GCM_TAG_BITS, iv),
            )
            return cipher.doFinal(ciphertext).toString(Charsets.UTF_8)
        } catch (error: IllegalArgumentException) {
            throw SecretStoreException("Secure secret payload is invalid", error)
        } catch (error: GeneralSecurityException) {
            throw SecretStoreException("Android keystore decryption failed", error)
        }
    }

    @Synchronized
    fun remove(name: String) {
        require(name.isNotBlank()) { "Secret name cannot be blank" }
        if (!preferences.edit().remove(name).commit()) {
            throw SecretStoreException("Secure secret deletion failed")
        }
    }

    @Synchronized
    fun getOrCreateRandom(name: String, byteCount: Int): ByteArray {
        require(byteCount >= 32) { "Secrets must contain at least 256 bits" }
        getString(name)?.let { encoded ->
            return try {
                Base64.decode(encoded, Base64.NO_WRAP)
            } catch (error: IllegalArgumentException) {
                throw SecretStoreException("Stored random secret is invalid", error)
            }
        }
        val generated = ByteArray(byteCount).also(secureRandom::nextBytes)
        putString(name, Base64.encodeToString(generated, Base64.NO_WRAP))
        return generated.copyOf()
    }

    private fun getOrCreateKey(): SecretKey {
        val keyStore = KeyStore.getInstance(ANDROID_KEYSTORE).apply { load(null) }
        (keyStore.getKey(keyAlias, null) as? SecretKey)?.let { return it }

        val keyGenerator = KeyGenerator.getInstance(
            KeyProperties.KEY_ALGORITHM_AES,
            ANDROID_KEYSTORE,
        )
        val specification = KeyGenParameterSpec.Builder(
            keyAlias,
            KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT,
        )
            .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
            .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
            .setKeySize(256)
            .build()
        keyGenerator.init(specification)
        return keyGenerator.generateKey()
    }

    private companion object {
        const val ANDROID_KEYSTORE = "AndroidKeyStore"
        const val DEFAULT_KEY_ALIAS = "jaya.settings.aes_gcm.v1"
        const val DEFAULT_PREFERENCES_NAME = "jaya_secure_secrets"
        const val GCM_IV_BYTES = 12
        const val GCM_TAG_BITS = 128
        const val PAYLOAD_VERSION = "v1"
        const val TRANSFORMATION = "AES/GCM/NoPadding"
    }
}
