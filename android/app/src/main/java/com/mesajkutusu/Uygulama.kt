package com.mesajkutusu

import android.app.Application
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import java.io.File

class Uygulama : Application() {
    override fun onCreate() {
        super.onCreate()
        Kopru.baslat(this)
        if (!Python.isStarted()) Python.start(AndroidPlatform(this))
    }

    companion object {
        const val PORT = 8080

        /** Web dosyalarını (assets/static) uygulama klasörüne açar; sürüm değişince yeniler. */
        fun webDosyalari(app: Application): File {
            val hedef = File(app.filesDir, "static")
            val isaret = File(hedef, ".surum")
            val surum = "${BuildConfig.VERSION_CODE}-${app.packageManager.getPackageInfo(app.packageName, 0).lastUpdateTime}"
            if (isaret.exists() && isaret.readText() == surum) return hedef
            hedef.deleteRecursively()
            kopyala(app, "static", hedef)
            isaret.writeText(surum)
            return hedef
        }

        private fun kopyala(app: Application, yol: String, hedef: File) {
            val icerik = app.assets.list(yol) ?: emptyArray()
            if (icerik.isEmpty()) {
                hedef.parentFile?.mkdirs()
                app.assets.open(yol).use { g -> hedef.outputStream().use { c -> g.copyTo(c) } }
                return
            }
            hedef.mkdirs()
            for (ad in icerik) kopyala(app, "$yol/$ad", File(hedef, ad))
        }
    }
}
