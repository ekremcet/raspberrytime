// Sesli Mesaj Kutusu - tablet uygulaması
// Sunucu (yazilim/mesajkutusu/server.py) Chaquopy ile uygulamanın içinde Python olarak çalışır,
// çocuk ekranı tam ekran bir WebView'da açılır.
plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("com.chaquo.python")
}

val kaynak = rootProject.file("../yazilim/mesajkutusu")
val uretilenPython = "build/generated/mesajkutusu/python"
val uretilenVarlik = "build/generated/mesajkutusu/assets"

// Yalnızca sunucu modülleri ve web dosyaları pakete girer (ayarlar.env, veri/ asla)
val sunucuKopyala by tasks.registering(Copy::class) {
    from(kaynak) { include("server.py", "opusogg.py") }
    into(file(uretilenPython))
}
val webKopyala by tasks.registering(Copy::class) {
    from(File(kaynak, "static"))
    into(file("$uretilenVarlik/static"))
}

val surumNo = (System.getenv("GITHUB_RUN_NUMBER") ?: "1").toInt()
val etiket = System.getenv("APK_ETIKET") ?: "gelistirme"

android {
    namespace = "com.mesajkutusu"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.mesajkutusu"
        minSdk = 26
        targetSdk = 34
        versionCode = surumNo
        versionName = "1.0.$surumNo"
        buildConfigField("String", "ETIKET", "\"$etiket\"")
        ndk { abiFilters += listOf("arm64-v8a", "x86_64") }
    }

    signingConfigs {
        // Sabit imza: güncellemeler eskisinin üzerine kurulabilsin. Depoda açık durur (hobi projesi);
        // kendi dağıtımın için kendi anahtarını oluştur (README).
        create("kutu") {
            storeFile = rootProject.file("imza/mesajkutusu.jks")
            storePassword = "mesajkutusu"
            keyAlias = "mesajkutusu"
            keyPassword = "mesajkutusu"
        }
    }
    buildTypes {
        getByName("release") {
            isMinifyEnabled = false
            signingConfig = signingConfigs.getByName("kutu")
        }
        getByName("debug") {
            signingConfig = signingConfigs.getByName("kutu")
        }
    }
    buildFeatures { buildConfig = true }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
    sourceSets {
        getByName("main").assets.srcDir(uretilenVarlik)
    }
}

chaquopy {
    defaultConfig {
        version = "3.12"
        System.getenv("BUILD_PYTHON")?.let { buildPython(it) }
        pip {
            install("aiohttp==3.14.5")
            install("certifi")
        }
    }
    sourceSets {
        getByName("main") { srcDir(uretilenPython) }
    }
}

tasks.named("preBuild") { dependsOn(sunucuKopyala, webKopyala) }
tasks.configureEach {
    if (name.contains("Python") || (name.startsWith("merge") && name.endsWith("Assets"))) {
        dependsOn(sunucuKopyala, webKopyala)
    }
}

dependencies {
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.appcompat:appcompat:1.7.0")
    implementation("androidx.webkit:webkit:1.11.0")
}
