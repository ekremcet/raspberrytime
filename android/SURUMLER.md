# Tablet app releases

Releases are built by [`.github/workflows/tablet.yml`](../.github/workflows/tablet.yml) on every push to the `tablet-yayin` branch and published as `tablet-v1.<run>` with `mesajkutusu.apk` attached.

## First release

- The voice message box server runs inside the app (Python via Chaquopy); the child screen is a full-screen WebView.
- QR setup from a phone, Telegram bot, admin page: same as the Raspberry Pi box.
- Kiosk: home screen app + screen pinning, or full device-owner lock (`adb shell dpm set-device-owner com.mesajkutusu/.YoneticiAlici`).
- Admin page: tablet info, temporary unlock, remove full lock, media volume, brightness, orientation, APK self-update.
- Tested on an Android 14 tablet emulator in CI; not yet on a physical tablet.
