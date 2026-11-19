#!/usr/bin/env bash
# Emülatörde duman testi: APK kurulur, sunucu açılır, kurulum API'si, Android köprüsü, tam kilit ve
# Telegram'a TLS bağlantısı denenir. Ekran görüntüleri ve logcat ci-cikti/ klasörüne yazılır.
set -uo pipefail
APK="$1"
C=ci-cikti
mkdir -p "$C"
HATA=0
kontrol() { if eval "$2"; then echo "OK   $1"; else echo "HATA $1"; HATA=1; fi; }
api() { curl -s -m 20 "$@"; }

adb install -r "$APK"
adb shell pm grant com.mesajkutusu android.permission.RECORD_AUDIO || true
adb shell am start -n com.mesajkutusu/.MainActivity
adb forward tcp:8080 tcp:8080

echo "sunucu bekleniyor"
for i in $(seq 1 90); do
  api http://127.0.0.1:8080/api/saglik >/dev/null && break
  sleep 2
done
kontrol "sunucu açıldı" 'api http://127.0.0.1:8080/api/saglik >/dev/null'
sleep 6
adb exec-out screencap -p > "$C/1-acilis.png"
adb shell uiautomator dump /sdcard/ekran.xml >/dev/null 2>&1; adb pull /sdcard/ekran.xml "$C/ekran.xml" >/dev/null 2>&1
kontrol "çocuk ekranı WebView'da çizildi (kurulum yazısı)" 'grep -q "Kurulumu telefonundan yap\|Set me up from your phone" $C/ekran.xml'

api http://127.0.0.1:8080/api/durum > "$C/durum.json"
KOD=$(python3 -c "import json;print((json.load(open('$C/durum.json')).get('kurulum') or {}).get('kod',''))")
kontrol "kurulum kodu ekranda ($KOD)" '[ -n "$KOD" ]'

H=(-H "X-Kurulum-Kodu: $KOD" -H "Content-Type: application/json")
api "${H[@]}" -X POST http://127.0.0.1:8080/api/kurulum/genel -d '{"kisi_adi":"Baba","cocuk_adi":"Deniz","kutu_adi":"Deneme","dil":"tr"}' > "$C/genel.json"
kontrol "kurulum: adlar" 'grep -q "\"ok\": true" $C/genel.json'
api "${H[@]}" -X POST http://127.0.0.1:8080/api/kurulum/pin -d '{"pin":"2468"}' > "$C/pin.json"
kontrol "kurulum: PIN" 'grep -q "\"ok\": true" $C/pin.json'

# Telegram'a gerçek TLS bağlantısı (certifi): sahte ama biçimi doğru anahtar Telegram'dan "reddedildi" dönmeli
api "${H[@]}" -X POST http://127.0.0.1:8080/api/kurulum/token -d '{"bot_token":"123456789:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"}' > "$C/token.txt"
cat "$C/token.txt"; echo
kontrol "Telegram'a ulaşıldı (TLS)" 'grep -q "kabul etmedi" $C/token.txt'

P=(-H "X-Yonetici-Pin: 2468" -H "Content-Type: application/json")
api "${P[@]}" http://127.0.0.1:8080/api/yonetim/sistem > "$C/sistem.json"; cat "$C/sistem.json"; echo
kontrol "sistem bilgisi (android)" 'grep -q "\"platform\": \"android\"" $C/sistem.json'
api "${P[@]}" http://127.0.0.1:8080/api/yonetim/ses > "$C/ses.json"; cat "$C/ses.json"; echo
kontrol "ses seviyesi okundu" 'grep -q "\"android\": true" $C/ses.json'
api "${P[@]}" -X POST http://127.0.0.1:8080/api/yonetim/ses -d '{"ses":40}' >/dev/null
api "${P[@]}" -X POST http://127.0.0.1:8080/api/ekran -d '{"uyku":true}' >/dev/null
sleep 2; adb exec-out screencap -p > "$C/2-kurulum-ekrani.png"

echo "--- tam kilit (cihaz sahibi)"
adb shell dpm set-device-owner com.mesajkutusu/.YoneticiAlici
adb shell am force-stop com.mesajkutusu
adb shell am start -n com.mesajkutusu/.MainActivity
for i in $(seq 1 60); do api http://127.0.0.1:8080/api/saglik >/dev/null && break; sleep 2; done
sleep 6
api "${P[@]}" http://127.0.0.1:8080/api/yonetim/kilit > "$C/kilit.json"; cat "$C/kilit.json"; echo
kontrol "tam kilit açık" 'grep -q "\"kilitli\": true" $C/kilit.json && grep -q "\"cihaz_sahibi\": true" $C/kilit.json'
adb exec-out screencap -p > "$C/3-kilitli.png"
api "${P[@]}" -X POST http://127.0.0.1:8080/api/yonetim/kilit -d '{"ac":true,"dakika":5}' > "$C/kilit-ac.json"; cat "$C/kilit-ac.json"; echo
kontrol "kilit geçici açıldı" 'grep -q "\"kilitli\": false" $C/kilit-ac.json'
api "${P[@]}" -X POST http://127.0.0.1:8080/api/yonetim/sistem -d '{"islem":"uygulama"}' >/dev/null
sleep 5
kontrol "sunucu kendi içinde yeniden başladı" 'api http://127.0.0.1:8080/api/saglik >/dev/null'

# Ekran görüntüleri günlüğe (indirmeden bakabilmek için)
for f in "$C/1-acilis.png" "$C/3-kilitli.png"; do
  echo "=====PNG $(basename "$f")"; base64 -w0 "$f"; echo; echo "=====SON"
done
adb logcat -d > "$C/logcat.txt"
grep -n "Traceback\|python.stderr" "$C/logcat.txt" | head -40
kontrol "Python hatası yok" '! grep -q "Traceback" $C/logcat.txt'
exit $HATA
