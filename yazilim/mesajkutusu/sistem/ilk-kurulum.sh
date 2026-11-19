#!/bin/bash
# Sesli Mesaj Kutusu - sistem kurulumu (root olarak)
#
# İki şekilde çalışır:
#   1) SD kart yolu: ilk açılışta bir kez, /boot/firmware/mesajkutusu klasöründen kurar (internet gerekir).
#   2) Hazır imaj yolu: imaj üretilirken chroot içinde çalışır:
#        MESAJKUTUSU_IMAJ=1 MESAJKUTUSU_KAYNAK=/tmp/mesajkutusu MESAJKUTUSU_KULLANICI=kutu bash ilk-kurulum.sh
#      Paketleri kurar, uygulamayı yerleştirir, servisleri açar; yeniden başlatmaz.
set -euo pipefail
IMAJ="${MESAJKUTUSU_IMAJ:-0}"
SRC="${MESAJKUTUSU_KAYNAK:-/boot/firmware/mesajkutusu}"
if [ "$IMAJ" != 1 ]; then
  KAYIT=/boot/firmware/mesajkutusu-kurulum.log
  exec > >(tee -a "$KAYIT") 2>&1
fi
echo "=== $(date '+%F %T') kurulum başlıyor (imaj=$IMAJ)"

U="${MESAJKUTUSU_KULLANICI:-$(getent passwd 1000 | cut -d: -f1 || true)}"
if [ -z "$U" ] || [ "$U" = "rpi-first-boot-wizard" ]; then
  echo "Henüz kullanıcı yok (ilk açılış sihirbazı bitmemiş). 30 sn sonra tekrar denenecek."
  exit 1
fi
H="$(getent passwd "$U" | cut -d: -f6)"
echo "Kullanıcı: $U ($H)"

PAKETLER="python3-aiohttp ffmpeg curl wlr-randr iw dnsmasq-base"
eksik_paket() {
  local p
  for p in $PAKETLER; do dpkg -s "$p" >/dev/null 2>&1 || return 0; done
  command -v chromium >/dev/null || command -v chromium-browser >/dev/null || return 0
  return 1
}

if eksik_paket; then
  if [ "$IMAJ" != 1 ]; then
    echo "--> İnternet bekleniyor"
    for _ in $(seq 1 60); do
      getent hosts archive.raspberrypi.com >/dev/null 2>&1 && break
      sleep 5
    done
    getent hosts archive.raspberrypi.com >/dev/null 2>&1 || { echo "İnternet yok. Wi-Fi/Ethernet bağlanınca kendiliğinden tekrar denenecek."; exit 1; }
  fi
  echo "--> Paketler"
  export DEBIAN_FRONTEND=noninteractive
  apt-get update
  # shellcheck disable=SC2086
  apt-get install -y $PAKETLER || apt-get install -y python3-aiohttp ffmpeg curl
  if ! command -v chromium >/dev/null && ! command -v chromium-browser >/dev/null; then
    apt-get install -y chromium || apt-get install -y chromium-browser
  fi
else
  echo "--> Paketler zaten kurulu"
fi

echo "--> Uygulama $H/mesajkutusu klasörüne kopyalanıyor"
APP="$H/mesajkutusu"
mkdir -p "$APP"
if [ "$(realpath "$SRC")" != "$(realpath "$APP")" ]; then
  cp -r "$SRC"/. "$APP"/
  [ "$IMAJ" = 1 ] && rm -rf "$APP/veri"
fi
[ -f "$APP/ayarlar.env" ] || cp "$APP/ayarlar.env.ornek" "$APP/ayarlar.env"
chmod +x "$APP/sistem/kiosk.sh"

echo "--> Sunucu servisi (kullanıcı servisi, açılışta başlar)"
mkdir -p "$H/.config/systemd/user/default.target.wants"
sed "s|__DIR__|$APP|g" "$APP/sistem/mesajkutusu.service" > "$H/.config/systemd/user/mesajkutusu.service"
ln -sf ../mesajkutusu.service "$H/.config/systemd/user/default.target.wants/mesajkutusu.service"
mkdir -p /var/lib/systemd/linger
touch "/var/lib/systemd/linger/$U"

echo "--> Wi-Fi yardımcısı (bağlantı yoksa kurulum ağı açar)"
sed "s|__DIR__|$APP|g" "$APP/sistem/mesajkutusu-wifi.service" > /etc/systemd/system/mesajkutusu-wifi.service
systemctl enable mesajkutusu-wifi.service || ln -sf /etc/systemd/system/mesajkutusu-wifi.service /etc/systemd/system/multi-user.target.wants/mesajkutusu-wifi.service

echo "--> Yönetim sayfasından yeniden başlatma/kapatma ve ekran parlaklığı izinleri"
mkdir -p /etc/sudoers.d /etc/udev/rules.d
printf '%s ALL=(root) NOPASSWD: /usr/bin/systemctl reboot, /usr/bin/systemctl poweroff\n' "$U" > /etc/sudoers.d/mesajkutusu
chmod 0440 /etc/sudoers.d/mesajkutusu
echo 'SUBSYSTEM=="backlight", ACTION=="add", RUN+="/bin/chmod 0666 /sys%p/brightness"' > /etc/udev/rules.d/90-mesajkutusu-arka-isik.rules

echo "--> Ekran: masaüstü açılınca tam ekran çocuk arayüzü"
mkdir -p "$H/.config/autostart"
cat > "$H/.config/autostart/mesajkutusu.desktop" <<DESK
[Desktop Entry]
Type=Application
Name=Sesli Mesaj Kutusu
Exec=$APP/sistem/kiosk.sh
X-GNOME-Autostart-enabled=true
DESK

echo "--> Güncellemeler için kaynak kod (git)"
if command -v git >/dev/null && [ ! -d "$H/raspberrytime/.git" ]; then
  git clone --depth 50 https://github.com/ekremcet/raspberrytime.git "$H/raspberrytime" 2>/dev/null \
    || echo "    (şimdilik klonlanamadı; yönetim sayfasındaki güncelleme ilk seferde klonlar)"
fi
chown -R "$U:$U" "$H/.config" "$APP"
[ -d "$H/raspberrytime" ] && chown -R "$U:$U" "$H/raspberrytime"

echo "--> Sistem ayarları"
raspi-config nonint do_boot_behaviour B4 || true   # masaüstüne otomatik giriş
raspi-config nonint do_wayland W3 || true          # labwc (Bookworm); Trixie'de zaten öyle
raspi-config nonint do_blanking 1 || true          # sistem ekran karartması kapalı
raspi-config nonint do_hostname mesajkutusu || true

mkdir -p /var/lib/mesajkutusu
touch /var/lib/mesajkutusu/kuruldu
systemctl disable mesajkutusu-kurulum.service 2>/dev/null || true
if [ "$IMAJ" = 1 ]; then
  echo "=== $(date '+%F %T') imaj kurulumu tamam"
  exit 0
fi
echo "=== $(date '+%F %T') kurulum tamam, yeniden başlatılıyor"
sync
systemctl --no-block reboot
