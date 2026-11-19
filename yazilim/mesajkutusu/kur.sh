#!/usr/bin/env bash
# Sesli Mesaj Kutusu - elle kurulum (Pi üzerinde, SSH ya da uzak kabukla)
# Kullanım:  bash kur.sh      (sonra: sudo reboot, ekrandaki QR kodu telefonla okut)
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
echo "==> Klasör: $DIR"
sudo env MESAJKUTUSU_IMAJ=1 MESAJKUTUSU_KAYNAK="$DIR" MESAJKUTUSU_KULLANICI="$USER" bash "$DIR/sistem/ilk-kurulum.sh"
systemctl --user daemon-reload || true
systemctl --user restart mesajkutusu || true
echo
echo "Kurulum tamam. Yeniden başlat:  sudo reboot"
echo "Açılınca ekranda bir QR kod çıkar: telefonunla okut ve kurulumu telefondan bitir."
