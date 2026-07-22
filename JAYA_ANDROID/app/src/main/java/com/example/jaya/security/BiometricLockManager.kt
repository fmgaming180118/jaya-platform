package com.example.jaya.security

import android.app.KeyguardManager
import android.content.Context
import android.hardware.biometrics.BiometricManager
import android.hardware.biometrics.BiometricPrompt
import android.os.Build
import android.os.CancellationSignal
import android.util.Log
import androidx.annotation.RequiresApi
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

class BiometricLockManager(private val context: Context) {

    private val _isUnlocked = MutableStateFlow(false)
    val isUnlocked: StateFlow<Boolean> = _isUnlocked.asStateFlow()

    fun canAuthenticate(): Boolean {
        return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            val biometricManager = context.getSystemService(Context.BIOMETRIC_SERVICE) as? BiometricManager
            biometricManager?.canAuthenticate(BiometricManager.Authenticators.BIOMETRIC_STRONG) == BiometricManager.BIOMETRIC_SUCCESS
        } else {
            val keyguardManager = context.getSystemService(Context.KEYGUARD_SERVICE) as? KeyguardManager
            keyguardManager?.isKeyguardSecure == true
        }
    }

    @RequiresApi(Build.VERSION_CODES.P)
    fun promptBiometricAuth(onSuccess: () -> Unit, onError: (String) -> Unit) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
            try {
                val cancellationSignal = CancellationSignal()
                val executor = context.mainExecutor

                val biometricPrompt = BiometricPrompt.Builder(context)
                    .setTitle("Autentikasi Biometrik JAYA Sovereign")
                    .setSubtitle("Gunakan Sidik Jari atau Pemindai Wajah untuk Membuka Vault Sensitif")
                    .setNegativeButton("Batal", executor) { _, _ ->
                        onError("Autentikasi Dibatalkan")
                    }
                    .build()

                biometricPrompt.authenticate(
                    cancellationSignal,
                    executor,
                    object : BiometricPrompt.AuthenticationCallback() {
                        override fun onAuthenticationSucceeded(result: BiometricPrompt.AuthenticationResult?) {
                            super.onAuthenticationSucceeded(result)
                            _isUnlocked.value = true
                            Log.d("BiometricLock", "Biometric authentication SUCCEEDED. Unlocking JAYA Vault.")
                            onSuccess()
                        }

                        override fun onAuthenticationError(errorCode: Int, errString: CharSequence?) {
                            super.onAuthenticationError(errorCode, errString)
                            _isUnlocked.value = false
                            Log.e("BiometricLock", "Biometric authentication ERROR ($errorCode): $errString")
                            onError(errString?.toString() ?: "Error Autentikasi")
                        }

                        override fun onAuthenticationFailed() {
                            super.onAuthenticationFailed()
                            Log.w("BiometricLock", "Biometric authentication FAILED.")
                        }
                    }
                )
            } catch (e: Exception) {
                Log.e("BiometricLock", "Error launching BiometricPrompt: ${e.localizedMessage}", e)
                onError(e.localizedMessage ?: "Gagal meluncurkan biometrik")
            }
        } else {
            // Fallback for older API levels
            _isUnlocked.value = true
            onSuccess()
        }
    }
}
