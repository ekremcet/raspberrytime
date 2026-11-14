#!/bin/bash
# Raspberry Pi OS yazılmış SD kartı Sesli Mesaj Kutusu için hazırlar (Mac veya Linux'ta çalışır).
# Kullanım:  bash sd-hazirla.sh /Volumes/bootfs
# Kartın boot bölümüne uygulamayı kopyalar ve Pi ilk açıldığında kendini kuracak şekilde ayarlar.
set -eu
BOOT="${1:-/Volumes/bootfs}"
HERE="$(cd "$(dirname "$0")" && pwd)"
[ -f "$BOOT/config.txt" ] && [ -f "$BOOT/cmdline.txt" ] || { echo "HATA: $BOOT bir Raspberry Pi boot bölümü değil."; exit 1; }
echo "SD kart: $BOOT"
[ -f "$BOOT/issue.txt" ] && head -1 "$BOOT/issue.txt"

echo "1) Uygulama kopyalanıyor"
mkdir -p "$BOOT/mesajkutusu/static" "$BOOT/mesajkutusu/sistem"
for f in server.py kur.sh ayarlar.env.ornek static/index.html static/yonetim.html \
         sistem/kiosk.sh sistem/mesajkutusu.service sistem/ilk-kurulum.sh sistem/mesajkutusu-kurulum.service; do
  cp "$HERE/$f" "$BOOT/mesajkutusu/$f"
done
[ -f "$BOOT/mesajkutusu/ayarlar.env" ] || cp "$HERE/ayarlar.env.ornek" "$BOOT/mesajkutusu/ayarlar.env"

SATIR1='cp /boot/firmware/mesajkutusu/sistem/mesajkutusu-kurulum.service /etc/systemd/system/'
SATIR2='systemctl enable mesajkutusu-kurulum.service'

if [ -f "$BOOT/user-data" ]; then
  echo "2) cloud-init (user-data) bulundu"
  if grep -q "mesajkutusu-kurulum" "$BOOT/user-data"; then
    echo "   zaten ekli"
  elif grep -q '^runcmd:' "$BOOT/user-data"; then
    awk '
      { print }
      /^runcmd:/ && !done {
        getline nxt
        ind = "  "; if (nxt ~ /^- /) ind = ""; else if (match(nxt, /^ *-/)) ind = substr(nxt, 1, RLENGTH-1)
        print ind "- [ cp, /boot/firmware/mesajkutusu/sistem/mesajkutusu-kurulum.service, /etc/systemd/system/ ]"
        print ind "- [ systemctl, enable, mesajkutusu-kurulum.service ]"
        print ind "- [ systemctl, start, --no-block, mesajkutusu-kurulum.service ]"
        print nxt; done = 1
      }' "$BOOT/user-data" > "$BOOT/user-data.yeni" && mv "$BOOT/user-data.yeni" "$BOOT/user-data"
  else
    [ -n "$(tail -c1 "$BOOT/user-data")" ] && echo >> "$BOOT/user-data"
    cat >> "$BOOT/user-data" <<'YAML'
runcmd:
  - [ cp, /boot/firmware/mesajkutusu/sistem/mesajkutusu-kurulum.service, /etc/systemd/system/ ]
  - [ systemctl, enable, mesajkutusu-kurulum.service ]
  - [ systemctl, start, --no-block, mesajkutusu-kurulum.service ]
YAML
  fi
elif [ -f "$BOOT/firstrun.sh" ]; then
  echo "2) Imager ilk açılış betiği (firstrun.sh) bulundu"
  if grep -q "mesajkutusu-kurulum" "$BOOT/firstrun.sh"; then
    echo "   zaten ekli"
  else
    awk -v a="$SATIR1" -v b="$SATIR2" '
      /^rm -f .*firstrun\.sh/ && !done { print a; print b; done = 1 }
      { print }' "$BOOT/firstrun.sh" > "$BOOT/firstrun.yeni" && mv "$BOOT/firstrun.yeni" "$BOOT/firstrun.sh"
    grep -q "mesajkutusu-kurulum" "$BOOT/firstrun.sh" || { echo "HATA: firstrun.sh beklenen biçimde değil"; exit 1; }
  fi
else
  echo "2) Imager özelleştirmesi yok: kendi ilk açılış betiği ekleniyor"
  cat > "$BOOT/mesajkutusu-ilk.sh" <<SH
#!/bin/bash
$SATIR1
$SATIR2
sed -i 's| systemd.run=/boot/firmware/mesajkutusu-ilk.sh systemd.run_success_action=reboot systemd.unit=kernel-command-line.target||' /boot/firmware/cmdline.txt
rm -f /boot/firmware/mesajkutusu-ilk.sh
exit 0
SH
  if ! grep -q "mesajkutusu-ilk.sh" "$BOOT/cmdline.txt"; then
    tr -d '\n' < "$BOOT/cmdline.txt" > "$BOOT/cmdline.yeni"
    printf ' systemd.run=/boot/firmware/mesajkutusu-ilk.sh systemd.run_success_action=reboot systemd.unit=kernel-command-line.target\n' >> "$BOOT/cmdline.yeni"
    mv "$BOOT/cmdline.yeni" "$BOOT/cmdline.txt"
  fi
fi
rm -f "$BOOT"/._* "$BOOT/mesajkutusu"/._* "$BOOT/mesajkutusu"/*/._* 2>/dev/null || true
sync
echo
echo "Tamam. Bot anahtarını şimdi eklemek istersen: $BOOT/mesajkutusu/ayarlar.env dosyasında BOT_TOKEN= satırını doldur."
echo "Sonra kartı çıkar, Pi'ye tak ve aç. Kurulum internet gerektirir ve birkaç dakika sürer; bitince Pi kendini yeniden başlatır."
