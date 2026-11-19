package com.mesajkutusu

import android.app.ActivityManager
import android.app.PendingIntent
import android.app.admin.DevicePolicyManager
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.pm.PackageInstaller
import android.media.AudioManager
import android.os.BatteryManager
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.os.PowerManager
import android.os.SystemClock
import android.util.Log
import org.json.JSONObject
import java.lang.ref.WeakReference
import java.net.HttpURLConnection
import java.net.URL

/**
 * Python sunucusunun (server.py, ANDROID=True) tableti yönettiği köprü.
 * server.py: from java import jclass; jclass("com.mesajkutusu.Kopru").parlaklik(30.0)
 */
object Kopru {
    private const val ETIKET = "MesajKutusu"
    private lateinit var app: Context
    private val ana = Handler(Looper.getMainLooper())
    private var etkinlik: WeakReference<MainActivity>? = null
    @Volatile private var sonParlaklik = 70f
    /** Kilit geçici olarak açıkken bitiş zamanı (elapsedRealtime); 0 = kilitli olmalı */
    @Volatile var kilitAcikBitis = 0L
        private set

    fun baslat(c: Context) { app = c.applicationContext }

    fun etkinlikBagla(a: MainActivity?) { etkinlik = a?.let { WeakReference(it) } }

    private fun ui(is_: (MainActivity) -> Unit) {
        ana.post { etkinlik?.get()?.let(is_) }
    }

    val dpm: DevicePolicyManager get() = app.getSystemService(DevicePolicyManager::class.java)
    val yonetici: ComponentName get() = ComponentName(app, YoneticiAlici::class.java)
    fun cihazSahibi(): Boolean = dpm.isDeviceOwnerApp(app.packageName)

    // ------------------------------------------------------------ ekran
    @JvmStatic fun parlaklik(yuzde: Float) {
        val onceki = sonParlaklik
        sonParlaklik = yuzde
        if (onceki <= 15f && yuzde > 15f) uyandir()
        ui { it.parlaklikAyarla(yuzde) }
    }

    @JvmStatic fun parlaklikOku(): Float = sonParlaklik

    /** Güç tuşuyla kapatılmış ekranı açar (yeni mesaj). */
    @JvmStatic fun uyandir() {
        try {
            val pm = app.getSystemService(PowerManager::class.java)
            if (!pm.isInteractive) {
                @Suppress("DEPRECATION")
                pm.newWakeLock(PowerManager.SCREEN_BRIGHT_WAKE_LOCK or PowerManager.ACQUIRE_CAUSES_WAKEUP, "mesajkutusu:uyan")
                    .acquire(5000)
            }
        } catch (e: Exception) {
            Log.w(ETIKET, "uyandırılamadı", e)
        }
        ui { it.oneGetir() }
    }

    /** "" = otomatik yatay, "0" yatay, "180" ters yatay, "90" dikey, "270" ters dikey */
    @JvmStatic fun yon(deger: String?) {
        app.getSharedPreferences("kutu", 0).edit().putString("yon", deger ?: "").apply()
        ui { it.yonUygula() }
    }

    fun kayitliYon(): String = app.getSharedPreferences("kutu", 0).getString("yon", "") ?: ""

    // ------------------------------------------------------------ ses
    private val ses: AudioManager get() = app.getSystemService(AudioManager::class.java)

    @JvmStatic fun sesSeviyesi(): Int {
        val mx = ses.getStreamMaxVolume(AudioManager.STREAM_MUSIC).coerceAtLeast(1)
        return Math.round(ses.getStreamVolume(AudioManager.STREAM_MUSIC) * 100f / mx)
    }

    @JvmStatic fun sesAyarla(yuzde: Int) {
        val mx = ses.getStreamMaxVolume(AudioManager.STREAM_MUSIC)
        ses.setStreamVolume(AudioManager.STREAM_MUSIC, Math.round(mx * yuzde.coerceIn(0, 100) / 100f), 0)
    }

    // ------------------------------------------------------------ bilgi
    @JvmStatic fun bilgi(): String {
        val pil = app.getSystemService(BatteryManager::class.java)
        val pi = app.packageManager.getPackageInfo(app.packageName, 0)
        return JSONObject()
            .put("ad", "${Build.MANUFACTURER} ${Build.MODEL}")
            .put("android", "${Build.VERSION.RELEASE} (API ${Build.VERSION.SDK_INT})")
            .put("uygulama_surum", "${pi.versionName} · ${BuildConfig.ETIKET}")
            .put("uygulama_etiket", BuildConfig.ETIKET)
            .put("pil", pil.getIntProperty(BatteryManager.BATTERY_PROPERTY_CAPACITY))
            .put("sarj", pil.isCharging)
            .put("cihaz_sahibi", cihazSahibi())
            .toString()
    }

    // ------------------------------------------------------------ kiosk kilidi
    @JvmStatic fun kilitDurumu(): String {
        val am = app.getSystemService(ActivityManager::class.java)
        val kalan = (kilitAcikBitis - SystemClock.elapsedRealtime()) / 60000
        return JSONObject()
            .put("kilitli", am.lockTaskModeState != ActivityManager.LOCK_TASK_MODE_NONE)
            .put("cihaz_sahibi", cihazSahibi())
            .put("kalan_dk", if (kalan > 0) kalan + 1 else 0)
            .toString()
    }

    @JvmStatic fun kilitAc(dakika: Int) {
        kilitAcikBitis = SystemClock.elapsedRealtime() + dakika * 60_000L
        ui { it.kilitBirak() }
        ana.postDelayed({ if (SystemClock.elapsedRealtime() >= kilitAcikBitis) kilitle() }, dakika * 60_000L + 500)
    }

    @JvmStatic fun kilitle() {
        kilitAcikBitis = 0L
        ui { it.kilitUygula() }
        // Kutu arka plandaysa öne getir (kilit onResume'da uygulanır)
        app.startActivity(Intent(app, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
    }

    fun kilitAcikMi(): Boolean = SystemClock.elapsedRealtime() < kilitAcikBitis

    @JvmStatic fun cihazYenidenBaslat(): Boolean {
        if (!cihazSahibi()) return false
        dpm.reboot(yonetici)
        return true
    }

    // ------------------------------------------------------------ güncelleme (APK)
    @JvmStatic fun apkKur(adres: String) {
        Thread({
            try {
                val dosya = java.io.File(app.cacheDir, "guncelleme.apk")
                var url = URL(adres)
                var baglanti: HttpURLConnection
                var yonlendirme = 0
                while (true) {
                    baglanti = url.openConnection() as HttpURLConnection
                    baglanti.instanceFollowRedirects = false
                    baglanti.connectTimeout = 20000
                    baglanti.readTimeout = 60000
                    val kod = baglanti.responseCode
                    if (kod in 300..399 && yonlendirme++ < 5) {
                        url = URL(url, baglanti.getHeaderField("Location"))
                        baglanti.disconnect()
                        continue
                    }
                    if (kod != 200) throw IllegalStateException("indirme: HTTP $kod")
                    break
                }
                baglanti.inputStream.use { g -> dosya.outputStream().use { c -> g.copyTo(c) } }
                val yukleyici = app.packageManager.packageInstaller
                val parametre = PackageInstaller.SessionParams(PackageInstaller.SessionParams.MODE_FULL_INSTALL)
                    .apply { setAppPackageName(app.packageName) }
                val no = yukleyici.createSession(parametre)
                yukleyici.openSession(no).use { oturum ->
                    oturum.openWrite("kutu.apk", 0, dosya.length()).use { c -> dosya.inputStream().use { it.copyTo(c) }; oturum.fsync(c) }
                    val niyet = PendingIntent.getBroadcast(
                        app, no, Intent(app, KurulumAlici::class.java),
                        PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_MUTABLE,
                    )
                    // Cihaz sahibi değilse Android bir onay penceresi açar; kilit buna engel olmasın
                    if (!cihazSahibi()) kilitAc(10)
                    oturum.commit(niyet.intentSender)
                }
            } catch (e: Exception) {
                Log.e(ETIKET, "güncelleme kurulamadı", e)
            }
        }, "apk-guncelle").start()
    }
}
