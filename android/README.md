# Tablet version (Android)

The same voice message box as a single app on an ordinary Android tablet: no Raspberry Pi, no 3D printing, no wiring. The box software ([`server.py`](../yazilim/mesajkutusu/server.py)) runs inside the app, the child's screen is shown full screen, and the tablet is locked to the app so the child can't leave it.

| | Raspberry Pi box | Tablet |
|---|---|---|
| Parts | Pi 5, 7" display, USB speaker, USB mic, PSU, printed case | One tablet + charger |
| Cost in Turkey (Nov 2026) | ≈ 12–14k TL | ≈ 6k TL (Galaxy Tab A11) + charger |
| Battery | No | Yes, the child can carry it around |
| Setup | Flash SD card, assemble | Install one APK |
| Kiosk lock | Built in | Screen pinning, or full lock with one `adb` command |

Everything else is the same: QR setup from your phone, the Telegram bot, the admin page, quiet hours, the night clock.

---

## 1. What to buy

- **A tablet with Android 8 or newer, a microphone and a speaker.** Target model: **Samsung Galaxy Tab A11** (8.7", SM-X130). Any recent Samsung, Lenovo or Xiaomi tablet should work. Avoid no-name "kids tablets" with unrealistic specs.
- **A USB-C charger** (the Tab A11 ships without one) and a **stand or a case with a stand**.

## 2. First start of the tablet

1. Go through the tablet's own setup: language, Wi-Fi.
2. **For the full lock (recommended), skip adding a Google or Samsung account.** Android only lets an app become the "device owner" on a tablet with no accounts. You can add accounts afterwards.
3. Turn on battery protection, because the tablet will stay plugged in: on Samsung, **Settings › Battery › More battery settings › Protect battery** (stops charging at 80–85%).

## 3. Install the app

1. On the tablet, open the browser and go to **github.com/ekremcet/raspberrytime/releases**.
2. Download `mesajkutusu.apk` from the latest **tablet-v…** release.
3. Open the download. Android asks to allow installs from the browser: allow it, then **Install**.
4. Open **Mesaj Kutusu**. Allow the microphone when asked.

## 4. Lock the tablet to the app

### A. Full lock (recommended)

The child can't leave the app at all: no home button, no notification shade, no settings. The tablet also stays on while charging, the lock screen is skipped, and the microphone permission is granted automatically. You need a computer with [Android platform tools](https://developer.android.com/tools/releases/platform-tools) (`adb`) and a USB cable, once.

1. On the tablet: **Settings › About tablet › Software information**, tap **Build number** 7 times. This turns on developer options.
2. **Settings › Developer options › USB debugging**: on. Connect the tablet to the computer and accept the prompt.
3. On the computer:
   ```bash
   adb shell dpm set-device-owner com.mesajkutusu/.YoneticiAlici
   ```
   It should print `Success: Device owner set…`. If it says there are accounts on the device, remove them under **Settings › Accounts**, or factory-reset and skip accounts.
4. Open **Mesaj Kutusu** again. It locks itself.
5. Turn USB debugging off again.

### B. Screen pinning (no computer)

1. **Settings › Security and privacy › More security settings › Pin app**: on, together with **Ask for PIN before unpinning**.
2. Open **Mesaj Kutusu**. Android asks whether to pin the app: confirm.
3. When Android asks which app to use as the home screen, choose **Mesaj Kutusu › Always**.

Unpinning needs holding Back and Recents together plus your PIN. A determined older child might find it; for small children it's enough.

## 5. Set up from your phone

The tablet shows a QR code. From here it's the same as the Pi box: scan it, set names, the PIN and the Telegram bot, and add yourself ([software › 3. Set up from your phone](../yazilim/README.md#3-set-up-from-your-phone)). The tablet handles Wi-Fi itself, so the box's own setup network isn't used.

## 6. Day to day

- **Admin page:** `http://<tablet-ip>:8080/yonetim` from a phone on the same Wi-Fi. The address is shown under the QR during setup and on the **Sistem** tab.
- **Using the tablet yourself:** admin page › **Sistem › Tablet kilidi › Kilidi 10 dakika aç** (unlock for 10 minutes). It locks again when the time runs out or when you press **Şimdi kilitle** (lock now).
- **Screen:** when the box "sleeps" the screen dims to the clock instead of turning off; new messages wake it. If someone presses the power button, a new message turns the screen back on.
- **Sound:** the **Ses** tab sets the tablet's media volume. Speaker and microphone pickers are hidden; the tablet's own are used.
- **Orientation:** **Ekran › Ekran yönü**: "Sistem ayarı" follows the tablet (landscape, either way up); you can fix it to normal or inverted landscape, or portrait.
- **Updates:** **Sistem › Güncellemeleri denetle** finds a newer APK on the Releases page. **Güncelle** downloads and installs it. With the full lock it installs silently. Without it, the tablet shows Android's install prompt; the kiosk unlocks for 10 minutes so you can confirm it.
- **Removing the full lock:** **Sistem › Tablet kilidi › Tam kilidi kaldır** (tap twice). After that the app is an ordinary app and can be uninstalled.

## 7. Troubleshooting

| Symptom | Fix |
|---|---|
| "Mikrofon bulunamadı" (Microphone not found) | **Settings › Apps › Mesaj Kutusu › Permissions › Microphone: Allow**. With the full lock it's granted automatically. |
| No chime | Admin › **Ses**: volume; also check the tablet isn't on silent / Do Not Disturb. |
| Admin page doesn't open | Phone and tablet on the same Wi-Fi? Use the IP from the **Sistem** tab. Some routers isolate devices on the guest network. |
| `adb … set-device-owner` says "already several accounts" | Remove all accounts (**Settings › Accounts and backup › Manage accounts**) or factory-reset, then try again. |
| App closed after an Android update | Open it once; with the full lock it's also the home screen and comes back by itself. |

## How it's built

- [`app/`](app/) is a Kotlin app using [Chaquopy](https://chaquo.com/chaquopy/) to run Python 3.12. The build copies `server.py`, `opusogg.py` and `static/` from [`yazilim/mesajkutusu`](../yazilim/mesajkutusu); there is one code base for both versions.
- There is no ffmpeg on Android: [`opusogg.py`](../yazilim/mesajkutusu/opusogg.py) repackages the WebView's WebM/Opus recordings as the Ogg/Opus files Telegram expects, without re-encoding.
- `Kopru.kt` is the bridge the server calls for brightness, volume, orientation, waking the screen, the kiosk lock and APK updates. The admin page and the server detect the tablet through `MESAJKUTUSU_PLATFORM=android`.
- [`.github/workflows/tablet.yml`](../.github/workflows/tablet.yml) builds the APK on every change. It installs it on an Android 14 tablet emulator and checks the server, the setup API, Telegram over TLS, the bridge, the full lock and the in-app restart ([`ci/duman-testi.sh`](ci/duman-testi.sh)). Pushing to the `tablet-yayin` branch (or a `tablet-v*` tag) publishes the APK as a release named `tablet-v1.<run>`; the admin page's update check looks for the newest release with an `.apk`.
- **Signing key:** `imza/mesajkutusu.jks` (password `mesajkutusu`) is in the repository so every build can update the previous one. It's fine for a family project. If you distribute your own builds, make your own key with `keytool -genkeypair` and point `app/build.gradle.kts` at it.

Build locally: Android SDK, JDK 17 and Python 3.12, then `gradle -p android assembleRelease` (or open `android/` in Android Studio).
