# Software

The box is a single Python server (`mesajkutusu/server.py`) running on Raspberry Pi OS, plus a web interface that the server opens full screen. Messaging goes through the **Telegram Bot API**: no phone line, SIM or phone needed.

![Interface](gorseller/arayuz.png)

*Top left: home screen. Top right: person screen with no messages. Middle: a new message has arrived (the listen button glows). Middle right: recording. Bottom: back to the home screen after sending.*

> The device interface and the admin page are in Turkish by default. The child's screen and the bot messages can be switched to English on the admin page (**Genel › Dil**). Admin page labels are given below as they appear, with an English translation.

**You need:** a Mac/PC with an SD card reader, Telegram on your phone, and the Wi-Fi network the box will join.

---

## 1. Create the Telegram bot

On your phone, about 5 minutes:

1. In Telegram, search for **@BotFather** (the official account with the blue check mark) and tap **Start**.
2. Send `/newbot`.
3. It asks for a display name, e.g. `Ayşe's Box`. Family members will see this name.
4. It asks for a username: it must end in `bot` and be available, e.g. `aysebox_bot`.
5. BotFather replies with a **token** like `123456789:AAH...`. Copy it. The token is the bot's password; don't share it.
6. Send `/setjoingroups` → choose your bot → **Disable**, so the bot can't be added to groups.
7. Optionally set a bot photo with `/setuserpic`.

---

## 2. Write the SD card (Raspberry Pi Imager)

1. Install and open [Raspberry Pi Imager](https://www.raspberrypi.com/software/).
2. **Device:** Raspberry Pi 5. **Operating system:** Raspberry Pi OS (64-bit), the desktop version. **Storage:** the SD card.
3. In the customization screen, be sure to fill in:
   - Hostname: `mesajkutusu`
   - Username and password (don't forget them; you need them for remote maintenance)
   - **Wi-Fi name and password** (the first-boot installation downloads packages from the internet)
   - Time zone and keyboard layout
   - Optionally enable SSH
4. Write the card. When it's done, don't eject it; it shows up on the Mac as a disk called `bootfs`.

---

## 3. Prepare the SD card for the box

This step copies the app to the card's boot partition and sets up the Pi to install itself on first boot. Since a Mac can't write to the card's Linux partition, the actual installation happens on the Pi's first boot.

1. Download this repository: **Code › Download ZIP**, or `git clone https://github.com/ekremcet/raspberrytime`.
2. With the card in the Mac, double-click `yazilim/mesajkutusu/SD-KARTA-KUR.command`.
   - If macOS blocks it: right-click › **Open**.
   - Or in Terminal: `bash yazilim/mesajkutusu/sd-hazirla.sh /Volumes/bootfs`
   - On Linux: `bash yazilim/mesajkutusu/sd-hazirla.sh /media/$USER/bootfs`
3. In Finder, open `bootfs › mesajkutusu › ayarlar.env` with TextEdit and fill it in:
   ```
   BOT_TOKEN=123456789:AAH...      # the token from step 1; no spaces or quotes
   YONETICI_PIN=4826               # digits of your choice for the admin page
   KUTU_ADI=Ayşe's Box             # name of the box
   ```
   For other settings see [10. Settings](#10-settings).
4. Save. In Finder, click ⏏ next to `bootfs` to **eject the card safely**.

The script detects which first-boot mechanism the card's Raspberry Pi OS uses (cloud-init `user-data`, Imager `firstrun.sh`, or neither). Running it twice does no harm.

---

## 4. Insert the card and power on

1. Insert the card into the Pi and connect power.
2. The Pi restarts a few times by itself (expanding the disk, applying user and Wi-Fi settings). This is normal.
3. The desktop appears. The installation runs in the background (5–10 min); nothing changes on screen meanwhile. The installer:
   - installs the `python3-aiohttp`, `ffmpeg` and `chromium` packages,
   - copies the app to `~/mesajkutusu`,
   - sets up the server as a user service that starts at boot (`mesajkutusu.service`),
   - enables automatic desktop login and the full-screen interface, and turns off the system's own screen blanking.
4. The Pi restarts once more and the home screen with the contact photos opens.

Installation progress is written to `mesajkutusu-kurulum.log` on the card's boot partition. If something goes wrong, put the card in the Mac and read that file. Without internet, the installer retries every 30 seconds.

---

## 5. Screen orientation

If the screen sits upside down in the case, the picture is upside down. Two ways to fix it:

**A. From the admin page (easiest):** on the **Ekran** (Screen) tab, set **Ekran yönü** (Screen orientation) to **Ters (180°)** (Inverted). The picture and the touch input rotate immediately and the setting is applied at every boot. With "Sistem ayarı" (System setting) selected, the box leaves the desktop setting from option B alone.

**B. From the desktop:**
1. In the remote shell or with a keyboard, run `pkill -f chromium`; the full-screen interface closes.
2. Raspberry menu › **Preferences › Control Centre › Screens**.
3. Right-click **DSI-1** › **Orientation › Inverted** › **Apply**. If there is a **Touchscreen** menu, assign the touchscreen to the DSI display as well.
4. `sudo reboot`. The setting is permanent.

---

## 6. Audio

Easiest: on the admin page's **Ses** (Sound) tab, pick the speaker and microphone, adjust the levels, and test with **Zili kutuda çal** (Ring the chime on the box).

It can also be done from the command line. The box uses the default speaker and microphone. Check:

```bash
wpctl status
```

Under `Sinks` the USB speaker (e.g. `UACDemoV1.0`) and under `Sources` the BOYA (`UAC 1.0 Microphone`) should be marked with an **asterisk**. If not:

```bash
wpctl set-default <id>                        # once for the speaker, once for the microphone
wpctl set-volume @DEFAULT_AUDIO_SINK@ 1.0     # speaker volume 100% (0.7 if too loud)
```

USB speakers may default to a low level (40%); if you can't hear the chime, check this first.

---

## 7. Admin page and first contact

1. Connect your phone to the **same Wi-Fi** as the box and open **http://mesajkutusu.local:8080/yonetim**.
   - If it doesn't open, find the IP with `hostname -I` on the Pi and use `http://IP:8080/yonetim`.
2. Log in with the PIN from `ayarlar.env`. (If you left the PIN empty, a random one was generated: `cat ~/mesajkutusu/veri/yonetici_pin.txt`)
3. The **Bot** section should show a green dot and a **t.me/...** link. Tap the link and press **Start** when Telegram opens.
4. Refresh the page: you appear under **Onay bekleyenler** (Waiting for approval). Type the name to show on the box (Dad, Mom…) and press **Onayla** (Approve).
5. Tap the photo box and pick a photo. The photo isn't cropped; it is fitted whole into the tile. Set the color and order here too.
6. Test the chime and the screen with **Deneme mesajı** (Test message).
7. Send a voice message to the bot from Telegram (hold the microphone button). The box chimes and your tile glows.
8. On the box, tap your tile, tap the **microphone**, talk, and tap the **square** button. The message is sent right away and arrives in your Telegram as a voice note.

---

## 8. Add the family

1. Send the **t.me/...** link from the admin page to your family members.
2. Each of them opens the link and taps **Start**. The bot tells them they are waiting for approval.
3. On the admin page, press **Onayla** (Approve) and give them a name and photo.

Telegram doesn't let a bot message someone who has never written to it, so everyone has to tap **Start** once. Messages from people you haven't approved are ignored.

How family members use it: they send the bot ordinary Telegram voice messages. The child's messages arrive in the same chat as voice notes. When the child listens to a message, a 👀 reaction appears on it in the sender's Telegram.

If anything other than a voice message is sent (text, photo, sticker, video), the bot immediately replies "⚠️ *Child's name* can't see this, only voice messages". Enter the child's name on the admin page's **Genel** (General) tab.

---

## 9. Remote access and updates

### Raspberry Pi Connect

Comes with Raspberry Pi OS. Pair the Pi with your Raspberry Pi account via the **Connect** icon in the taskbar (or `rpi-connect signin`). Then, at [connect.raspberrypi.com](https://connect.raspberrypi.com):
- **Remote shell:** a command line (updates, logs, settings)
- **Screen sharing:** see the screen and change desktop settings

### First time: get the repository onto the Pi

Once, in the remote shell:

```bash
git clone https://github.com/ekremcet/raspberrytime ~/raspberrytime
bash ~/raspberrytime/yazilim/guncelle.sh
```

### Every update

```bash
bash ~/raspberrytime/yazilim/guncelle.sh
```

The script:
1. pulls the latest version from GitHub (`git pull`),
2. copies the files to `~/mesajkutusu`; **it doesn't touch `veri/` (contacts, messages, photos) or `ayarlar.env`**,
3. adds any newly introduced settings to `ayarlar.env` with their default values,
4. restarts the service and reopens the interface on the screen.

### Updating from the admin page

Once the repository is on the Pi (the `git clone` above), you can also update without the remote shell: on the admin page's **Sistem** (System) tab, use **Güncellemeleri denetle** (Check for updates) → **Güncelle** (Update). The box comes back with the new version within about a minute.

---

## 10. Settings

After installation, **all settings are changed from the admin page** and take effect immediately; a green **Kaydedildi** (Saved) note appears at the bottom after every save. Settings are stored in the database on the device.

| Tab | Settings |
|---|---|
| **Kişiler** (People) | Bot status and invite link, people waiting for approval, contact name, photo, color, order, test message, remove/block |
| **Ses** (Sound) | Speaker and microphone selection, volume, microphone level, **Zili kutuda çal** (ring the chime on the box), chime on/off, chime volume, reminder interval for unheard messages |
| **Ekran** (Screen) | Day and night brightness, sleep timeout (default 2 min), show clock while sleeping, dark night theme, screen orientation (touch rotates along) |
| **Sessiz / Gece** (Quiet / Night) | Turn quiet mode on/off now, automatic quiet mode every night (default 19:30–07:30), "will be seen in the morning" note to senders at night |
| **Genel** (General) | Box name, child's name (used in bot warnings), language (Turkish/English: box screen + bot messages), maximum recording length, number of stored messages, 👀 listened reaction, network access to the child screen, **admin PIN**, **bot token** |
| **Sistem** (System) | Device info (version, IP, temperature, disk, memory), **check for and install updates**, restart the app / device, shut down |

**One-time permission:** For the brightness and "Restart / Shut down device" buttons, run `bash ~/raspberrytime/yazilim/guncelle.sh` once from the remote shell on the Pi and enter your password. The script only adds permissions for these two things (`/etc/sudoers.d/mesajkutusu` and a udev rule for the backlight).

`~/mesajkutusu/ayarlar.env` now only holds initial values (`BOT_TOKEN`, `YONETICI_PIN`, `KUTU_ADI`, `PORT`). A value changed on the admin page takes precedence over the file.

---

## 11. How the child's screen works

- **Home screen:** no text; the whole screen is contact photos (the name sits small at the bottom of the photo). At most 3×3 = 9 people per page; more go to the next pages, which you browse by swiping or with the side arrows, with page dots at the bottom. A contact with a new message glows orange with a count badge, their page dot turns orange, and the screen switches to that page by itself.
- **Person screen:** two big buttons.
  - Left, **listen**: if there are unheard messages (e.g. "3 new messages!") it plays **all of them in order, oldest first** ("Listening… 2/3"); once all are heard, it plays only the **last** message. The card glows while there are new messages.
  - Right, **microphone**: tap, talk, tap the square. The message is sent immediately and the screen returns home, showing "Sent to Mom" at the bottom.
- **Chime:** a three-note chime plays when a new message arrives, waking the screen if it's asleep. While there are unheard messages, a soft chime repeats at the set interval (default 10 min). Chime and volume are on the **Ses** (Sound) tab.
- **Sleep:** after 2 minutes without touch (default) the screen dims and shows a large 24-hour **clock** and the date (the clock shifts slightly every minute to avoid burn-in). Touch wakes it; the waking touch only turns the screen on and is not treated as a press on the contact or button underneath. On the person screen, the box returns home after at most 2 minutes.
- **Quiet mode:** no chime or reminder, and new messages don't wake the screen. Messages still arrive; tiles glow and badges show, and the child sees them on the next touch.
- **Night (default 19:30–07:30):** automatic quiet mode, and the screen switches to dark, dimmed colors; when sleeping, the clock shows in a warm, dim color with a moon icon.
- **If the internet drops:** "İnternet yok, mesajlar sonra gidecek" (No internet, messages will be sent later) appears at the top; outgoing messages are kept and sent when the connection returns.

---

## 12. Troubleshooting

To see the log (in the remote shell):

```bash
sudo journalctl _SYSTEMD_USER_UNIT=mesajkutusu.service -n 30 --no-pager
```

| Symptom | Cause and fix |
|---|---|
| **"İnternet yok"** (No internet) on screen, but the Pi is online | Check the log. `Conflict` means the same bot is running somewhere else too (e.g. a test server left running on a Mac): stop it. `Unauthorized` / `Not Found` means the token is wrong (the screen shows "Bot anahtarı hatalı" / bot key is wrong). |
| Red dot on the admin page | Right after the server starts, the first connection takes a few seconds. If it persists, check the log as above. |
| Picture upside down | [5. Screen orientation](#5-screen-orientation) |
| Touches land in the wrong place | The screen was rotated but touch wasn't mapped to it: use option A in section 5, or assign the touchscreen to DSI under Screens › Touchscreen |
| Can't hear the chime / sound | Admin › **Sessiz / Gece**: is quiet mode or night mode on? Admin › **Ses**: is the right speaker selected, what's the level? Test with **Zili kutuda çal**. |
| Brightness or "Restart device" doesn't work | One-time permission needed: run `bash ~/raspberrytime/yazilim/guncelle.sh` in the remote shell and enter your password. |
| "Mikrofon bulunamadı" (Microphone not found) | Does the BOYA appear under `Sources` in `wpctl status`? Unplug and replug the USB extension. |
| Admin page won't open | Is the phone on the same Wi-Fi? Try the IP instead of `mesajkutusu.local` (`hostname -I`). |
| First installation didn't finish | Put the card in the Mac and read `bootfs/mesajkutusu-kurulum.log`. "İnternet yok" means the Wi-Fi details are missing. |
| Screen goes dark now and then, or doesn't turn on | Most likely the display power wires (pin 4/6) or a ribbon cable is loose: [hardware › 3.9 Cable management](../donanim/README.md#39-cable-management) |
| Microphone drops out now and then | The joint between the microphone and the USB extension is loose: tape it ([hardware › 3.9](../donanim/README.md#39-cable-management)) |
| Server doesn't run at all | `systemctl --user status mesajkutusu` |

---

## 13. Development

### Try it on a computer (demo mode)

```bash
brew install ffmpeg                # Linux: sudo apt install ffmpeg
pip3 install aiohttp
cd yazilim/mesajkutusu
python3 server.py
```

- Child screen: http://localhost:8080 (Chrome recommended)
- Admin: http://localhost:8080/yonetim (the PIN is printed in the terminal)

With an empty `BOT_TOKEN` it starts in **demo mode** with sample contacts. When testing with the real bot, stop the server on the Pi: a bot can only be polled from one place at a time.

### Files

```
yazilim/
├── guncelle.sh                      on the Pi: git pull + install (data and settings kept)
└── mesajkutusu/
    ├── server.py                    server: Telegram bridge, audio conversion, API, WebSocket
    ├── static/index.html            child screen
    ├── static/yonetim.html          admin page
    ├── ayarlar.env.ornek            settings template
    ├── sd-hazirla.sh                prepares the SD card on Mac/Linux
    ├── SD-KARTA-KUR.command         double-click wrapper for macOS
    ├── kur.sh                       manual installation (over SSH, on the Pi)
    └── sistem/
        ├── ilk-kurulum.sh           runs once as root on first boot
        ├── mesajkutusu-kurulum.service
        ├── mesajkutusu.service      the server (user service)
        └── kiosk.sh                 full-screen Chromium + screen orientation
```

### API

| Path | Purpose |
|---|---|
| `GET /` | Child screen (only from the device itself, or from the network if enabled on the admin page) |
| `GET /api/durum` | Contacts, unread counts, connection state, settings |
| `GET /api/mesajlar/{kisi}` | A contact's recent messages |
| `POST /api/gonder?kisi=` | Upload a recording (webm/ogg/mp4); converted to Opus and sent to Telegram |
| `POST /api/dinlendi/{mesaj}` | Mark as listened (👀 reaction to the sender) |
| `GET /ws` | Live events: new message, connection, contact changes |
| `GET /yonetim` | Admin page |
| `/api/yonetim/...` | With the `X-Yonetici-Pin` header: info, contacts, approve/update, photo, order, delete, test |
| `GET/POST /api/yonetim/ayarlar` | All settings (language, chime, screen, quiet/night, messaging); stored in the database |
| `GET/POST /api/yonetim/ses` | Speaker/microphone selection and levels (PipeWire `wpctl`) |
| `POST /api/yonetim/zil` | Ring the chime on the box (test) |
| `GET/POST /api/yonetim/ekran` | Brightness state, apply screen orientation |
| `GET/POST /api/yonetim/guvenlik` | PIN and bot token |
| `GET/POST /api/yonetim/sistem` | Device info, update, restart, shut down |
| `POST /api/ekran` | Child screen went to sleep / woke up (backlight) |

### Manual installation (instead of the SD card method)

On a Pi with SSH enabled:

```bash
git clone https://github.com/ekremcet/raspberrytime ~/raspberrytime
cp -r ~/raspberrytime/yazilim/mesajkutusu ~/mesajkutusu
cd ~/mesajkutusu && bash kur.sh
nano ayarlar.env                     # BOT_TOKEN and YONETICI_PIN
systemctl --user restart mesajkutusu
sudo reboot
```
