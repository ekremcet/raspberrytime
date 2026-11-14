#!/bin/bash
# Sesli Mesaj Kutusu - ilk açılış kurulumu (root olarak, bir kez çalışır)
# SD karttaki /boot/firmware/mesajkutusu klasöründen kurar. İnternet gerekir.
set -euo pipefail
KAYIT=/boot/firmware/mesajkutusu-kurulum.log
exec > >(tee -a "$KAYIT") 2>&1
echo "=== $(date '+%F %T') kurulum başlıyor"
SRC=/boot/firmware/mesajkutusu

U="$(getent passwd 1000 | cut -d: -f1 || true)"
if [ -z "$U" ] || [ "$U" = "rpi-first-boot-wizard" ]; then
  echo "Henüz kullanıcı yok (ilk açılış sihirbazı bitmemiş). 30 sn sonra tekrar denenecek."
  exit 1
fi
H="$(getent passwd "$U" | cut -d: -f6)"
echo "Kullanıcı: $U ($H)"

echo "--> İnternet bekleniyor"
for _ in $(seq 1 60); do
  getent hosts archive.raspberrypi.com >/dev/null 2>&1 && break
  sleep 5
done
getent hosts archive.raspberrypi.com >/dev/null 2>&1 || { echo "İnternet yok. Wi-Fi/Ethernet bağlanınca kendiliğinden tekrar denenecek."; exit 1; }

echo "--> Paketler"
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y python3-aiohttp ffmpeg curl
if ! command -v chromium >/dev/null && ! command -v chromium-browser >/dev/null; then
  apt-get install -y chromium || apt-get install -y chromium-browser
fi

echo "--> Uygulama $H/mesajkutusu klasörüne kopyalanıyor"
APP="$H/mesajkutusu"
mkdir -p "$APP"
cp -r "$SRC"/. "$APP"/
[ -f "$APP/ayarlar.env" ] || cp "$APP/ayarlar.env.ornek" "$APP/ayarlar.env"
chmod +x "$APP/sistem/kiosk.sh"

echo "--> Sunucu servisi (kullanıcı servisi, açılışta başlar)"
mkdir -p "$H/.config/systemd/user/default.target.wants"
sed "s|__DIR__|$APP|g" "$APP/sistem/mesajkutusu.service" > "$H/.config/systemd/user/mesajkutusu.service"
ln -sf ../mesajkutusu.service "$H/.config/systemd/user/default.target.wants/mesajkutusu.service"
mkdir -p /var/lib/systemd/linger
touch "/var/lib/systemd/linger/$U"

echo "--> Ekran: masaüstü açılınca tam ekran çocuk arayüzü"
mkdir -p "$H/.config/autostart"
cat > "$H/.config/autostart/mesajkutusu.desktop" <<DESK
[Desktop Entry]
Type=Application
Name=Sesli Mesaj Kutusu
Exec=$APP/sistem/kiosk.sh
X-GNOME-Autostart-enabled=true
DESK
chown -R "$U:$U" "$H/.config" "$APP"

echo "--> Sistem ayarları"
raspi-config nonint do_boot_behaviour B4 || true   # masaüstüne otomatik giriş
raspi-config nonint do_wayland W3 || true          # labwc (Bookworm); Trixie'de zaten öyle
raspi-config nonint do_blanking 1 || true          # sistem ekran karartması kapalı
raspi-config nonint do_hostname mesajkutusu || true

mkdir -p /var/lib/mesajkutusu
touch /var/lib/mesajkutusu/kuruldu
systemctl disable mesajkutusu-kurulum.service || true
echo "=== $(date '+%F %T') kurulum tamam, yeniden başlatılıyor"
sync
systemctl --no-block reboot
