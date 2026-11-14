#!/usr/bin/env bash
# Sesli Mesaj Kutusu - Pi üzerinde güncelleme
# GitHub'daki son sürümü çeker ve ~/mesajkutusu klasörüne kurar.
# veri/ (kişiler, mesajlar, fotoğraflar) ve ayarlar.env korunur; yeni ayarlar varsa varsayılan değerleriyle eklenir.
# Kullanım (Pi'de):  bash ~/raspberrytime/yazilim/guncelle.sh
set -euo pipefail

# Ekrandaki tam ekran tarayıcıyı yeniden açar (masaüstü oturumu açıksa)
kiosk_yenile() {
  local sok
  export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
  sok="$(ls -d "$XDG_RUNTIME_DIR"/wayland-[0-9] 2>/dev/null | head -1 || true)"
  [ -n "$sok" ] || { echo "    (masaüstü açık değil, ekran bir sonraki açılışta güncellenir)"; return 0; }
  export WAYLAND_DISPLAY="$(basename "$sok")" DBUS_SESSION_BUS_ADDRESS="unix:path=$XDG_RUNTIME_DIR/bus"
  pkill -f chromium 2>/dev/null || true
  sleep 2
  # Uzak kabuk kapanınca ekran da kapanmasın diye kullanıcı servisi olarak başlatılır
  if systemd-run --user --collect --quiet --unit="mesajkutusu-ekran-$(date +%s)" \
       -E WAYLAND_DISPLAY="$WAYLAND_DISPLAY" -E XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR" \
       -E DBUS_SESSION_BUS_ADDRESS="$DBUS_SESSION_BUS_ADDRESS" "$1/sistem/kiosk.sh"; then
    echo "==> Ekran yeniden açıldı"
  else
    echo "    Ekran yeniden açılamadı; 'sudo reboot' ile yeniden başlat"
  fi
}

ana() {
  local REPO SRC APP f satir k
  REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
  SRC="$REPO/yazilim/mesajkutusu"
  APP="${MESAJKUTUSU_DIR:-$HOME/mesajkutusu}"

  echo "==> GitHub'dan son sürüm alınıyor"
  git -C "$REPO" pull --ff-only

  echo "==> Dosyalar $APP klasörüne kopyalanıyor"
  mkdir -p "$APP/static" "$APP/sistem"
  for f in server.py kur.sh sd-hazirla.sh ayarlar.env.ornek static/index.html static/yonetim.html \
           sistem/kiosk.sh sistem/mesajkutusu.service sistem/ilk-kurulum.sh sistem/mesajkutusu-kurulum.service; do
    cp "$SRC/$f" "$APP/$f"
  done
  chmod +x "$APP/sistem/kiosk.sh"

  echo "==> Yeni ayarlar ekleniyor (mevcut değerlere dokunulmaz)"
  [ -f "$APP/ayarlar.env" ] || cp "$SRC/ayarlar.env.ornek" "$APP/ayarlar.env"
  while IFS= read -r satir; do
    case "$satir" in ''|\#*) continue ;; esac
    k="${satir%%=*}"
    grep -q "^$k=" "$APP/ayarlar.env" || { echo "$satir" >> "$APP/ayarlar.env"; echo "    + $satir"; }
  done < "$SRC/ayarlar.env.ornek"

  echo "==> Servis yeniden başlatılıyor"
  mkdir -p "$HOME/.config/systemd/user"
  sed "s|__DIR__|$APP|g" "$SRC/sistem/mesajkutusu.service" > "$HOME/.config/systemd/user/mesajkutusu.service"
  systemctl --user daemon-reload
  systemctl --user restart mesajkutusu
  sleep 3
  if curl -fs http://localhost:8080/api/saglik >/dev/null; then
    kiosk_yenile "$APP"
    echo "Tamam: $(git -C "$REPO" log -1 --format='%h  %s')"
  else
    echo "UYARI: sunucu yanıt vermiyor. Günlük: sudo journalctl _SYSTEMD_USER_UNIT=mesajkutusu.service -n 30"
  fi
}
ana "$@"
