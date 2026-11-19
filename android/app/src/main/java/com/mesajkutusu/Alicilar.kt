package com.mesajkutusu

import android.app.admin.DeviceAdminReceiver
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.pm.PackageInstaller
import android.util.Log

/** Açılışta ve güncellemeden sonra sunucuyu ve çocuk ekranını başlatır. */
class AcilisAlici : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        SunucuServisi.servisiBaslat(context)
        try {
            context.startActivity(Intent(context, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        } catch (e: Exception) {
            // Ana ekran (launcher) olarak seçiliyse Android zaten açar
            Log.i("MesajKutusu", "ekran açılışta başlatılamadı: ${e.message}")
        }
    }
}

/** Tam kilit için cihaz yöneticisi (cihaz sahibi). */
class YoneticiAlici : DeviceAdminReceiver()

/** APK güncellemesinin sonucu; onay gerekiyorsa Android'in onay penceresini açar. */
class KurulumAlici : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        when (intent.getIntExtra(PackageInstaller.EXTRA_STATUS, -999)) {
            PackageInstaller.STATUS_PENDING_USER_ACTION -> {
                @Suppress("DEPRECATION")
                val onay = intent.getParcelableExtra<Intent>(Intent.EXTRA_INTENT) ?: return
                context.startActivity(onay.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
            }
            PackageInstaller.STATUS_SUCCESS -> Log.i("MesajKutusu", "güncelleme kuruldu")
            else -> Log.w("MesajKutusu", "güncelleme: ${intent.getStringExtra(PackageInstaller.EXTRA_STATUS_MESSAGE)}")
        }
    }
}
