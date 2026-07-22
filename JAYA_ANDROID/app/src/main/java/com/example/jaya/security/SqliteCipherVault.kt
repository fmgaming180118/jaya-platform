package com.example.jaya.security

import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Log
import java.security.KeyStore
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey

class SqliteCipherVault {

    private val KEY_ALIAS = "JayaMasterEncryptionKeyAES256"

    fun getOrCreateMasterKey(): ByteArray {
        val keyStore = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        
        if (!keyStore.containsAlias(KEY_ALIAS)) {
            val keyGenerator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore")
            val spec = KeyGenParameterSpec.Builder(
                KEY_ALIAS,
                KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT
            )
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setKeySize(256)
                .build()

            keyGenerator.init(spec)
            keyGenerator.generateKey()
            Log.d("SqliteCipherVault", "Hardware-backed AES-256 master key generated in Android KeyStore.")
        } else {
            Log.d("SqliteCipherVault", "Retrieved existing AES-256 master key from Android KeyStore.")
        }

        val secretKey = keyStore.getKey(KEY_ALIAS, null) as SecretKey
        return secretKey.encoded ?: "JAYA_DEFAULT_AES_PASSPHRASE_256".toByteArray()
    }
}
