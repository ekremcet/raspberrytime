#!/usr/bin/env bash
# Masaüstü açılınca çocuk ekranını tam ekran açar (masaüstü otomatik başlatmadan çağrılır).
# Ekran yönü yönetim sayfasından ayarlanır (0 / 90 / 180 / 270; boşsa sistem ayarına dokunulmaz).
# Sunucuya ulaşılamazsa ayarlar.env içindeki EKRAN_DONDUR kullanılır.
# Yalnızca yönü uygulamak için:  bash kiosk.sh --dondur
DIR="$(cd "$(dirname "$0")/.." && pwd)"
ayar() { sed -n "s/^$1=//p" "$DIR/ayarlar.env" 2>/dev/null | tail -1 | tr -d '\r" '; }

ekran_dondur() {
  local aci t o RC
  aci="$(curl -fs "http://localhost:${PORT:-8080}/api/durum" 2>/dev/null \
        | python3 -c 'import json,sys; print(json.load(sys.stdin).get("ekran_yonu",""))' 2>/dev/null)" || aci="$(ayar EKRAN_DONDUR)"
  case "$aci" in 90|180|270) t="$aci" ;; 0) t=normal ;; *) return 0 ;; esac   # boş: sistem ayarı
  command -v wlr-randr >/dev/null || { echo "wlr-randr yok"; return 0; }
  o="$(wlr-randr 2>/dev/null | awk '/^[^ \t]/{print $1}' | grep '^DSI' | head -1)"
  [ -n "$o" ] || { echo "DSI ekranı bulunamadı"; return 0; }
  wlr-randr --output "$o" --transform "$t" && echo "$o yönü: $t"
  # Dokunmatik ekranla birlikte dönsün: dokunmatiği bu ekrana bağla
  RC="$HOME/.config/labwc/rc.xml"
  mkdir -p "$(dirname "$RC")"
  [ -f "$RC" ] || cp /etc/xdg/labwc/rc.xml "$RC" 2>/dev/null || printf '<?xml version="1.0"?>\n<labwc_config>\n</labwc_config>\n' > "$RC"
  if ! grep -q "<touch" "$RC"; then
    sed -i "s|</labwc_config>|  <touch deviceName=\"\" mapToOutput=\"$o\" />\n</labwc_config>|; s|</openbox_config>|  <touch deviceName=\"\" mapToOutput=\"$o\" />\n</openbox_config>|" "$RC"
    pkill -HUP -x labwc 2>/dev/null || true
    echo "dokunmatik $o ekranına bağlandı"
  fi
}

PORT="$(ayar PORT)"; PORT="${PORT:-8080}"
if [ "${1:-}" = "--dondur" ]; then ekran_dondur; exit 0; fi

for _ in $(seq 1 60); do
  curl -fs "http://localhost:$PORT/api/saglik" >/dev/null 2>&1 && break
  sleep 1
done
ekran_dondur
BIN="$(command -v chromium || command -v chromium-browser)"
exec "$BIN" \
  --kiosk "http://localhost:$PORT/" \
  --noerrdialogs --disable-infobars --no-first-run \
  --disable-session-crashed-bubble --disable-features=Translate,TouchpadOverscrollHistoryNavigation \
  --overscroll-history-navigation=0 --disable-pinch \
  --check-for-update-interval=31536000 --password-store=basic \
  --use-fake-ui-for-media-stream \
  --autoplay-policy=no-user-gesture-required
