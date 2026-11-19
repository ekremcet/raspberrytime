package com.mesajkutusu

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import android.util.Log
import com.chaquo.python.Python
import java.io.File

/**
 * Python sunucusunu (server.android_calistir) arka planda çalıştırır.
 * Ön plan servisi olduğu için Android süreci öldürmez; çocuk ekranı (WebView) bu sunucuya bağlanır.
 */
class SunucuServisi : Service() {

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        onPlanaGec()
        baslat(application as Uygulama)
        return START_STICKY
    }

    private fun onPlanaGec() {
        val nm = getSystemService(NotificationManager::class.java)
        nm.createNotificationChannel(NotificationChannel(KANAL, getString(R.string.servis_kanal), NotificationManager.IMPORTANCE_MIN))
        val bildirim = Notification.Builder(this, KANAL)
            .setContentTitle(getString(R.string.app_name))
            .setContentText(getString(R.string.servis_metin))
            .setSmallIcon(android.R.drawable.ic_btn_speak_now)
            .setOngoing(true)
            .build()
        if (Build.VERSION.SDK_INT >= 34) {
            startForeground(1, bildirim, ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE)
        } else {
            startForeground(1, bildirim)
        }
    }

    companion object {
        private const val KANAL = "sunucu"
        @Volatile private var calisiyor = false

        fun baslat(app: Uygulama) {
            synchronized(this) {
                if (calisiyor) return
                calisiyor = true
            }
            Thread({
                try {
                    val py = Python.getInstance()
                    val ortam = py.getModule("os").get("environ")!!
                    val veri = File(app.filesDir, "veri").apply { mkdirs() }
                    mapOf(
                        "MESAJKUTUSU_PLATFORM" to "android",
                        "MESAJKUTUSU_STATIK" to Uygulama.webDosyalari(app).absolutePath,
                        "VERI_KLASORU" to veri.absolutePath,
                        "WIFI_KLASORU" to File(app.filesDir, "wifi-yok").absolutePath,
                        "PORT" to Uygulama.PORT.toString(),
                    ).forEach { (k, v) -> ortam.callAttr("__setitem__", k, v) }
                    py.getModule("server").callAttr("android_calistir")
                } catch (e: Throwable) {
                    Log.e("MesajKutusu", "sunucu durdu", e)
                } finally {
                    calisiyor = false
                }
            }, "python-sunucu").start()
        }

        fun servisiBaslat(context: Context) {
            context.startForegroundService(Intent(context, SunucuServisi::class.java))
        }
    }
}
