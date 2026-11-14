#!/usr/bin/env bash
# Sesli Mesaj Kutusu - Raspberry Pi kurulum betiği
# Kullanım:  bash kur.sh
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
echo "==> Klasör: $DIR"

echo "==> Paketler kuruluyor (python3-aiohttp, ffmpeg, chromium)"
sudo apt-get update
sudo apt-get install -y python3-aiohttp ffmpeg curl
if ! command -v chromium >/dev/null && ! command -v chromium-browser >/dev/null; then
  sudo apt-get install -y chromium || sudo apt-get install -y chromium-browser
fi

if [ ! -f "$DIR/ayarlar.env" ]; then
  cp "$DIR/ayarlar.env.ornek" "$DIR/ayarlar.env"
  echo "==> ayarlar.env oluşturuldu. BOT_TOKEN ve YONETICI_PIN'i doldurmayı unutma."
fi

echo "==> Sunucu servisi kuruluyor (açılışta kendiliğinden başlar)"
mkdir -p "$HOME/.config/systemd/user"
sed "s|__DIR__|$DIR|g" "$DIR/sistem/mesajkutusu.service" > "$HOME/.config/systemd/user/mesajkutusu.service"
systemctl --user daemon-reload
systemctl --user enable --now mesajkutusu.service
sudo loginctl enable-linger "$USER"

echo "==> Ekran (kiosk) otomatik açılışı ayarlanıyor"
chmod +x "$DIR/sistem/kiosk.sh"
mkdir -p "$HOME/.config/autostart"
cat > "$HOME/.config/autostart/mesajkutusu.desktop" <<DESK
[Desktop Entry]
Type=Application
Name=Sesli Mesaj Kutusu
Exec=$DIR/sistem/kiosk.sh
X-GNOME-Autostart-enabled=true
DESK

echo "==> Sistemin kendi ekran karartması kapatılıyor (kutu kendi uyku modunu kullanır)"
sudo raspi-config nonint do_blanking 1 || true

IP="$(hostname -I | awk '{print $1}')"
echo
echo "Kurulum tamam."
echo "  Yönetim sayfası:  http://$IP:8080/yonetim   (ya da http://$(hostname).local:8080/yonetim)"
echo "  Günlük:           journalctl --user -u mesajkutusu -f"
echo "  Ekranı başlatmak için Pi'yi yeniden başlat:  sudo reboot"
