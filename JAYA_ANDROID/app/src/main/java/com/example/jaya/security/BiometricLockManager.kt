package com.example.jaya.security

import android.util.Log
import androidx.biometric.BiometricManager
import androidx.biometric.BiometricPrompt
import androidx.core.content.ContextCompat
import androidx.fragment.app.FragmentActivity
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

class BiometricLockManager(
    private val activity: FragmentActivity,
) {
    private val _isUnlocked = MutableStateFlow(false)
    val isUnlocked: StateFlow<Boolean> = _isUnlocked.asStateFlow()

    fun canAuthenticate(): Boolean =
        BiometricManager.from(activity).canAuthenticate(AUTHENTICATORS) ==
            BiometricManager.BIOMETRIC_SUCCESS

    fun promptBiometricAuth(
        onSuccess: () -> Unit,
        onError: (String) -> Unit,
    ) {
        _isUnlocked.value = false
        if (!canAuthenticate()) {
            onError("Biometrik kuat tidak tersedia atau belum didaftarkan")
            return
        }
        try {
            val executor = ContextCompat.getMainExecutor(activity)
            val prompt = BiometricPrompt(
                activity,
                executor,
                object : BiometricPrompt.AuthenticationCallback() {
                    override fun onAuthenticationSucceeded(
                        result: BiometricPrompt.AuthenticationResult,
                    ) {
                        super.onAuthenticationSucceeded(result)
                        _isUnlocked.value = true
                        Log.i("BiometricLock", "Biometric authentication succeeded")
                        onSuccess()
                    }

                    override fun onAuthenticationError(
                        errorCode: Int,
                        errString: CharSequence,
                    ) {
                        super.onAuthenticationError(errorCode, errString)
                        _isUnlocked.value = false
                        Log.e("BiometricLock", "Biometric authentication error code $errorCode")
                        onError(errString.toString())
                    }

                    override fun onAuthenticationFailed() {
                        super.onAuthenticationFailed()
                        _isUnlocked.value = false
                        Log.w("BiometricLock", "Biometric authentication failed")
                    }
                },
            )
            val promptInfo = BiometricPrompt.PromptInfo.Builder()
                .setTitle("Autentikasi Biometrik JAYA")
                .setSubtitle("Verifikasi identitas untuk membuka vault sensitif")
                .setNegativeButtonText("Batal")
                .setAllowedAuthenticators(AUTHENTICATORS)
                .build()
            prompt.authenticate(promptInfo)
        } catch (error: Exception) {
            _isUnlocked.value = false
            Log.e("BiometricLock", "Biometric prompt could not be launched")
            onError("Gagal meluncurkan autentikasi biometrik")
        }
    }

    fun lock() {
        _isUnlocked.value = false
    }

    private companion object {
        const val AUTHENTICATORS = BiometricManager.Authenticators.BIOMETRIC_STRONG
    }
}