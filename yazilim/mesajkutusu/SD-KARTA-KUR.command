#!/bin/bash
# Çift tıkla: Mac'e takılı Raspberry Pi SD kartını Sesli Mesaj Kutusu için hazırlar.
cd "$(dirname "$0")"
B=/Volumes/bootfs
[ -d "$B" ] || B="$(ls -d /Volumes/boot* 2>/dev/null | head -1)"
if [ -z "$B" ] || [ ! -d "$B" ]; then echo "SD kart bulunamadı (/Volumes/bootfs). Kartı tak ve tekrar dene."; read -r -p "Enter..."; exit 1; fi
bash ./sd-hazirla.sh "$B"
echo; read -r -p "Kapatmak için Enter'a bas" _
