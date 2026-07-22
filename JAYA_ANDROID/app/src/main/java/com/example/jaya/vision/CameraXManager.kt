package com.example.jaya.vision

import android.content.Context
import android.graphics.Bitmap
import android.util.Log
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.ImageProxy
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.core.content.ContextCompat
import androidx.lifecycle.LifecycleOwner
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import java.util.concurrent.Executors

class CameraXManager(private val context: Context) {
    private val cameraExecutor = Executors.newSingleThreadExecutor()

    private val _isCameraActive = MutableStateFlow(false)
    val isCameraActive: StateFlow<Boolean> = _isCameraActive.asStateFlow()

    private val _lastCapturedFrame = MutableStateFlow<Bitmap?>(null)
    val lastCapturedFrame: StateFlow<Bitmap?> = _lastCapturedFrame.asStateFlow()

    fun startCamera(lifecycleOwner: LifecycleOwner) {
        val cameraProviderFuture = ProcessCameraProvider.getInstance(context)

        cameraProviderFuture.addListener({
            try {
                val cameraProvider = cameraProviderFuture.get()
                val cameraSelector = CameraSelector.DEFAULT_BACK_CAMERA

                val imageAnalysis = ImageAnalysis.Builder()
                    .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
                    .build()

                imageAnalysis.setAnalyzer(cameraExecutor) { imageProxy ->
                    processFrame(imageProxy)
                }

                cameraProvider.unbindAll()
                cameraProvider.bindToLifecycle(
                    lifecycleOwner,
                    cameraSelector,
                    imageAnalysis
                )

                _isCameraActive.value = true
                Log.d("CameraXManager", "CameraX initialized and analyzing live frames successfully.")
            } catch (e: Exception) {
                Log.e("CameraXManager", "Error starting CameraX", e)
                _isCameraActive.value = false
            }
        }, ContextCompat.getMainExecutor(context))
    }

    private fun processFrame(imageProxy: ImageProxy) {
        // Frame analysis loop
        imageProxy.close()
    }

    fun stopCamera() {
        _isCameraActive.value = false
        cameraExecutor.shutdown()
        Log.d("CameraXManager", "CameraX stopped.")
    }
}
