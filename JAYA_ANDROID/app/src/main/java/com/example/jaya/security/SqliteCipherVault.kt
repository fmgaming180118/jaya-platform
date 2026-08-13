package com.example.jaya.security

import android.content.Context

/**
 * Supplies SQLCipher with a random database passphrase wrapped by an
 * AndroidKeyStore key. The keystore key itself is never exported.
 */
class SqliteCipherVault(
    context: Context,
    private val secretStore: KeystoreSecretStore = KeystoreSecretStore(
        context = context,
        keyAlias = "jaya.database.wrapping_key.v1",
        preferencesName = "jaya_database_secrets",
    ),
) {
    fun getOrCreateDatabasePassphrase(): ByteArray =
        secretStore.getOrCreateRandom(DATABASE_PASSPHRASE_NAME, DATABASE_KEY_BYTES)

    @Deprecated(
        message = "Use getOrCreateDatabasePassphrase; this returns a wrapped database secret, not the master key",
        replaceWith = ReplaceWith("getOrCreateDatabasePassphrase()"),
    )
    fun getOrCreateMasterKey(): ByteArray = getOrCreateDatabasePassphrase()

    private companion object {
        const val DATABASE_KEY_BYTES = 32
        const val DATABASE_PASSPHRASE_NAME = "sqlcipher_passphrase_v1"
    }
}