package com.example.jaya.service

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.IBinder
import android.util.Log
import androidx.core.app.NotificationCompat

class JayaVoiceService : Service() {

    private val CHANNEL_ID = "JayaVoiceServiceChannel"
    private val NOTIFICATION_ID = 1001

    override fun onCreate() {
        super.onCreate()
        Log.d("JayaVoiceService", "Creating JAYA Hands-Free Voice Foreground Service...")
        createNotificationChannel()
        startForeground(NOTIFICATION_ID, createNotification())
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        Log.d("JayaVoiceService", "JAYA Voice Service active and listening for 'Hey Jaya' wake-word.")
        return START_STICKY
    }

    override fun onBind(intent: Intent?): IBinder? = null

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                "JAYA Voice Assistant",
                NotificationManager.IMPORTANCE_LOW
            ).apply {
                description = "Hands-free voice assistant listening channel"
            }
            val manager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
            manager.createNotificationChannel(channel)
        }
    }

    private fun createNotification(): Notification {
        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("JAYA Voice Assistant Active")
            .setContentText("Mendengarkan kata kunci 'Hey Jaya' di latar belakang...")
            .setSmallIcon(android.R.drawable.ic_btn_speak_now)
            .setOngoing(true)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .build()
    }

    override fun onDestroy() {
        super.onDestroy()
        Log.d("JayaVoiceService", "JAYA Voice Service destroyed.")
    }
}
