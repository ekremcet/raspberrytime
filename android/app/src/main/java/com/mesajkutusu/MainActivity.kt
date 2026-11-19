package com.mesajkutusu

import android.Manifest
import android.annotation.SuppressLint
import android.app.ActivityManager
import android.app.admin.DevicePolicyManager
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.ActivityInfo
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import android.util.Log
import android.view.View
import android.view.WindowInsets
import android.view.WindowInsetsController
import android.view.WindowManager
import android.webkit.PermissionRequest
import android.webkit.WebChromeClient
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.activity.OnBackPressedCallback
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat

/**
 * Çocuk ekranı: uygulamanın içindeki sunucudan (http://127.0.0.1:8080/) tam ekran WebView.
 * Kiosk: cihaz sahibiyse sessiz tam kilit; değilse Android'in "uygulama sabitleme" kilidi.
 */
class MainActivity : AppCompatActivity() {
    private lateinit var web: WebView
    private val ana = Handler(Looper.getMainLooper())
    private val adres = "http://127.0.0.1:${Uygulama.PORT}/"
    private var yuklendi = false

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        Kopru.etkinlikBagla(this)
        SunucuServisi.servisiBaslat(this)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        setShowWhenLocked(true)
        setTurnScreenOn(true)

        web = WebView(this).apply {
            setBackgroundColor(0xFFF3F6FB.toInt())
            settings.javaScriptEnabled = true
            settings.domStorageEnabled = true
            settings.mediaPlaybackRequiresUserGesture = false   // zil ve mesajlar dokunmadan çalabilsin
            settings.setSupportZoom(false)
            settings.builtInZoomControls = false
            isHapticFeedbackEnabled = false
            isLongClickable = false
            setOnLongClickListener { true }
            overScrollMode = View.OVER_SCROLL_NEVER
            webChromeClient = object : WebChromeClient() {
                override fun onPermissionRequest(istek: PermissionRequest) {
                    // Yalnızca kendi sunucumuzun sayfası mikrofon isteyebilir
                    if (istek.origin.host == "127.0.0.1" && mikrofonIzniVar()) {
                        istek.grant(arrayOf(PermissionRequest.RESOURCE_AUDIO_CAPTURE))
                    } else {
                        istek.deny()
                    }
                }
            }
            webViewClient = object : WebViewClient() {
                override fun shouldOverrideUrlLoading(view: WebView, istek: WebResourceRequest): Boolean =
                    istek.url.host != "127.0.0.1"           // dış bağlantılar açılmaz
                override fun onReceivedError(view: WebView, istek: WebResourceRequest, hata: WebResourceError) {
                    if (istek.isForMainFrame) {               // sunucu henüz açılmadı: biraz sonra yeniden dene
                        yuklendi = false
                        ana.postDelayed({ view.loadUrl(adres) }, 1500)
                    }
                }
                override fun onPageFinished(view: WebView, url: String) { yuklendi = true }
            }
        }
        setContentView(web)
        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() { /* çocuk geri tuşuyla çıkamasın */ }
        })
        tamEkran()
        yonUygula()
        mikrofonIste()
        web.loadUrl(adres)
    }

    override fun onResume() {
        super.onResume()
        Kopru.etkinlikBagla(this)
        tamEkran()
        if (!Kopru.kilitAcikMi()) kilitUygula()
        if (!yuklendi) web.loadUrl(adres)
    }

    override fun onWindowFocusChanged(hasFocus: Boolean) {
        super.onWindowFocusChanged(hasFocus)
        if (hasFocus) tamEkran()
    }

    override fun onDestroy() {
        Kopru.etkinlikBagla(null)
        super.onDestroy()
    }

    // ------------------------------------------------------------ ekran
    private fun tamEkran() {
        window.insetsController?.let {
            it.hide(WindowInsets.Type.systemBars())
            it.systemBarsBehavior = WindowInsetsController.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
        }
    }

    fun parlaklikAyarla(yuzde: Float) {
        val p = window.attributes
        p.screenBrightness = (yuzde / 100f).coerceIn(0.004f, 1f)
        window.attributes = p
    }

    fun oneGetir() {
        if (!hasWindowFocus()) {
            startActivity(Intent(this, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_REORDER_TO_FRONT))
        }
    }

    fun yonUygula() {
        requestedOrientation = when (Kopru.kayitliYon()) {
            "0" -> ActivityInfo.SCREEN_ORIENTATION_LANDSCAPE
            "180" -> ActivityInfo.SCREEN_ORIENTATION_REVERSE_LANDSCAPE
            "90" -> ActivityInfo.SCREEN_ORIENTATION_PORTRAIT
            "270" -> ActivityInfo.SCREEN_ORIENTATION_REVERSE_PORTRAIT
            else -> ActivityInfo.SCREEN_ORIENTATION_SENSOR_LANDSCAPE
        }
    }

    // ------------------------------------------------------------ mikrofon izni
    private fun mikrofonIzniVar() =
        ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED

    private fun mikrofonIste() {
        if (mikrofonIzniVar()) return
        if (Kopru.cihazSahibi()) {
            Kopru.dpm.setPermissionGrantState(Kopru.yonetici, packageName, Manifest.permission.RECORD_AUDIO,
                DevicePolicyManager.PERMISSION_GRANT_STATE_GRANTED)
            return
        }
        val izinler = mutableListOf(Manifest.permission.RECORD_AUDIO)
        if (Build.VERSION.SDK_INT >= 33) izinler += Manifest.permission.POST_NOTIFICATIONS
        ActivityCompat.requestPermissions(this, izinler.toTypedArray(), 1)
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (mikrofonIzniVar()) web.reload()
    }

    // ------------------------------------------------------------ kiosk kilidi
    fun kilitUygula() {
        try {
            if (Kopru.cihazSahibi()) tamKilitHazirla()
            val am = getSystemService(ActivityManager::class.java)
            if (am.lockTaskModeState == ActivityManager.LOCK_TASK_MODE_NONE) startLockTask()
        } catch (e: Exception) {
            Log.w("MesajKutusu", "kilit uygulanamadı: ${e.message}")
        }
    }

    fun kilitBirak() {
        try {
            stopLockTask()
            if (Kopru.cihazSahibi()) Kopru.dpm.setStatusBarDisabled(Kopru.yonetici, false)
        } catch (e: Exception) {
            Log.w("MesajKutusu", "kilit bırakılamadı: ${e.message}")
        }
    }

    /** Cihaz sahibiyken: kilit izni, ana ekran, durum çubuğu, ekran kilidi ve şarjda açık kalma. */
    private fun tamKilitHazirla() {
        val dpm = Kopru.dpm
        val y = Kopru.yonetici
        dpm.setLockTaskPackages(y, arrayOf(packageName))
        dpm.setLockTaskFeatures(y, DevicePolicyManager.LOCK_TASK_FEATURE_GLOBAL_ACTIONS)   // güç menüsü kalsın
        val ev = IntentFilter(Intent.ACTION_MAIN).apply {
            addCategory(Intent.CATEGORY_HOME)
            addCategory(Intent.CATEGORY_DEFAULT)
        }
        dpm.addPersistentPreferredActivity(y, ev, componentName)
        dpm.setStatusBarDisabled(y, true)
        dpm.setKeyguardDisabled(y, true)
        dpm.setGlobalSetting(y, Settings.Global.STAY_ON_WHILE_PLUGGED_IN, "7")
        dpm.setPermissionGrantState(y, packageName, Manifest.permission.RECORD_AUDIO,
            DevicePolicyManager.PERMISSION_GRANT_STATE_GRANTED)
    }
}
