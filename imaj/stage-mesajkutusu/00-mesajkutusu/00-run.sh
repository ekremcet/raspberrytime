#!/bin/bash -e
# pi-gen aşaması: Sesli Mesaj Kutusu uygulamasını imaja kurar.
# files/mesajkutusu klasörünü iş akışı (.github/workflows/imaj.yml) imajdan önce doldurur.
rm -rf "${ROOTFS_DIR}/tmp/mesajkutusu"
cp -r files/mesajkutusu "${ROOTFS_DIR}/tmp/mesajkutusu"

on_chroot << CHEOF
set -e
MESAJKUTUSU_IMAJ=1 MESAJKUTUSU_KAYNAK=/tmp/mesajkutusu MESAJKUTUSU_KULLANICI="${FIRST_USER_NAME}" \
  bash /tmp/mesajkutusu/sistem/ilk-kurulum.sh
rm -rf /tmp/mesajkutusu
CHEOF
