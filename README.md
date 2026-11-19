# Raspberry Time · Voice Message Box

A desk device with a screen that lets young children **exchange voice messages** with their family.
Inspired by [button.box](https://button.box); it uses a 7" touchscreen instead of physical buttons and a **Telegram bot** instead of WhatsApp.

- The child taps a person's photo, taps the microphone, talks, and taps again: the message arrives in that person's Telegram as a voice note.
- Family members send ordinary Telegram voice messages; the box chimes, the person's tile glows, and the child presses play.
- No reading or writing needed: the screen only shows photos and two big buttons (listen / talk).
- No SIM card, phone line or app required. Only people you approve can reach the box.
- Plug-and-play setup: flash the ready-made SD card image, power on, scan the QR code on the screen and finish everything (Wi-Fi, Telegram bot, PIN, yourself as the first contact) from your phone.

**Two ways to build it:**
- **Raspberry Pi box** (this page): a Pi with a 7" touchscreen in a 3D-printed case.
- **[Android tablet](android/README.md)**: the same software as one app on an ordinary tablet (e.g. Galaxy Tab A11), locked to the app. Cheaper, has a battery, nothing to assemble.

![Case](donanim/gorseller/kasa_onizleme.png)
![Interface](yazilim/gorseller/arayuz.png)

> The device interface and the admin page are in Turkish by default; the child's screen and the bot messages can be switched to English from the admin page (**Genel › Dil**).

## Repository layout

| Folder | Contents |
|---|---|
| [`donanim/`](donanim/) (hardware) | Parts list, 3D-print files (STL), parametric case model (`kasa.py`), step-by-step assembly |
| [`yazilim/`](yazilim/) (software) | The box software (`mesajkutusu/`), installation, setup wizard, Telegram bot, remote updates, troubleshooting |
| [`android/`](android/) (tablet) | Android kiosk app that runs the same server; build, emulator test and release workflow |
| [`imaj/`](imaj/) (image) | pi-gen stage for the ready-made SD card image, built by [`.github/workflows/imaj.yml`](.github/workflows/imaj.yml) |

## Roadmap from start to finish

| # | Step | Guide |
|---|---|---|
| 1 | Gather the parts | [hardware › 1. Parts list](donanim/README.md#1-parts-list) |
| 2 | Print the case (small test piece first) | [hardware › 2. 3D printing](donanim/README.md#2-3d-printing) |
| 3 | Flash the SD card (ready-made image, or stock OS + script) | [software › 1. Prepare the SD card](yazilim/README.md#1-prepare-the-sd-card) |
| 4 | Assemble the electronics and the case (glue the screen in, tape the cables) | [hardware › 3. Assembly](donanim/README.md#3-step-by-step-assembly) · [3.9 Cable management](donanim/README.md#39-cable-management) |
| 5 | Power on, scan the QR code, set up Wi-Fi, the Telegram bot and yourself from your phone | [software › 2–3](yazilim/README.md#2-insert-the-card-and-power-on) |
| 6 | Photos, audio, add the family | [software › 5–7](yazilim/README.md#5-audio) |
| 7 | Remote maintenance and updates | [software › 9](yazilim/README.md#9-remote-access-and-updates) |

## How it works

```mermaid
flowchart LR
  A["Family member<br/>Telegram app"] <-- "voice note" --> T[("Telegram<br/>Bot API")]
  T <-- "HTTPS long polling" --> S["server.py<br/>Raspberry Pi 5"]
  S <-- "WebSocket + HTTP" --> K["Chromium full screen<br/>7-inch touchscreen"]
  S --- D[("SQLite + audio files<br/>~/mesajkutusu/veri")]
  M["BOYA USB microphone"] --> K
  K --> H["USB speaker"]
  Y["Admin page<br/>phone or computer"] -- "PIN" --> S
```

- A single Python server (`aiohttp`) runs on the Pi. It listens to Telegram, converts audio to Opus with `ffmpeg`, and keeps contacts and messages in SQLite.
- The screen is a web page served by the same server (Chromium kiosk mode). Recording happens in the browser; the clip is uploaded to the server and sent to Telegram.
- The admin page opens from any device on the home network with a PIN: approve contacts, photos, colors, order, sound, screen, quiet hours, Wi-Fi, updates and more.
- A small root helper (`wifi-yardimci.py`) watches the connection through NetworkManager. If the box can't get online it opens its own `MesajKutusu-XXXX` network so a phone can pick the home Wi-Fi.

## Privacy

- The bot only accepts messages from people you **approve** on the admin page; groups and strangers are ignored.
- The bot token and PIN live only on the device (the local database, or `ayarlar.env` if you used it) and never enter this repository (`.gitignore`). The setup page only works with the one-time code shown on the box's screen and shuts itself off once setup is done.
- Messages and photos are stored on the device (`~/mesajkutusu/veri`); by default the last 40 messages per person are kept.
