#!/usr/bin/env python3
"""Sesli Mesaj Kutusu - Wi-Fi yardımcısı (root olarak çalışır, NetworkManager/nmcli kullanır).

- Kutu internete (Wi-Fi ya da kablo) bağlıysa durumu yazar, başka bir şey yapmaz.
- Açılıştan ya da bağlantı kopunca BEKLE saniye boyunca bağlantı gelmezse kendi kurulum ağını açar:
  "MesajKutusu-XXXX" (WPA2, şifre /var/lib/mesajkutusu/hotspot.json içinde), adres 10.42.0.1.
  Kutunun ekranı bu ağın QR kodunu gösterir; telefon bağlanıp ev Wi-Fi'sini seçer.
- Sunucu (kullanıcı servisi) seçilen ağı /run/mesajkutusu/wifi-istek.json dosyasına yazar; yardımcı bağlanmayı dener,
  olmazsa kurulum ağını yeniden açar.
- Kurulum ağı açıkken, telefon bağlı değilse, birkaç dakikada bir bilinen ağları yeniden dener
  (ör. modem kutudan sonra açıldıysa).

Durum dosyaları (/run/mesajkutusu):
  wifi.json   {"mod": "bagli"|"hotspot"|"baglaniyor"|"yok", "ssid", "ip", "hotspot_ssid", "hotspot_sifre", "hata"}
  aglar.json  [{"ssid", "sinyal", "guvenli"}]  (son tarama)
"""
import json
import os
import pathlib
import pwd
import secrets
import shutil
import subprocess
import sys
import time

KLASOR = pathlib.Path(os.environ.get("WIFI_KLASORU", "/run/mesajkutusu"))
KALICI = pathlib.Path(os.environ.get("WIFI_KALICI", "/var/lib/mesajkutusu"))
HOTSPOT_AD = "MesajKutusu-Kurulum"      # NetworkManager bağlantı profili adı
BEKLE = int(os.environ.get("WIFI_BEKLE", "50"))           # bağlantısız bu kadar saniye sonra kurulum ağı
YENIDEN_DENE = int(os.environ.get("WIFI_YENIDEN_DENE", "240"))
ARAYUZ = os.environ.get("WIFI_ARAYUZ", "wlan0")


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def nmcli(*args, zaman=30):
    try:
        r = subprocess.run(["nmcli", *args], capture_output=True, text=True, timeout=zaman)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except (subprocess.TimeoutExpired, OSError) as e:
        return 1, str(e)


def ayir(satir):
    """nmcli -t çıktısında kaçışlı ':' ayrımı."""
    parca, cur, kac = [], "", False
    for ch in satir:
        if kac:
            cur += ch
            kac = False
        elif ch == "\\":
            kac = True
        elif ch == ":":
            parca.append(cur)
            cur = ""
        else:
            cur += ch
    parca.append(cur)
    return parca


def yaz(ad, veri):
    g = KLASOR / (ad + ".tmp")
    g.write_text(json.dumps(veri, ensure_ascii=False))
    os.chmod(g, 0o640)
    g.rename(KLASOR / ad)


def klasor_hazirla():
    KLASOR.mkdir(parents=True, exist_ok=True)
    KALICI.mkdir(parents=True, exist_ok=True)
    try:                                # sunucu (uid 1000 kullanıcısı) istek dosyası yazabilsin
        k = pwd.getpwuid(1000)
        os.chown(KLASOR, 0, k.pw_gid)
        os.chmod(KLASOR, 0o2770)
    except KeyError:
        os.chmod(KLASOR, 0o2777)


def hotspot_bilgisi():
    f = KALICI / "hotspot.json"
    try:
        return json.loads(f.read_text())
    except (OSError, ValueError):
        pass
    try:
        mac = pathlib.Path(f"/sys/class/net/{ARAYUZ}/address").read_text().strip().replace(":", "")
    except OSError:
        mac = secrets.token_hex(2)
    bilgi = {"ssid": "MesajKutusu-" + mac[-4:].upper(),
             "sifre": "".join(secrets.choice("abcdefghjkmnpqrstuvwxyz23456789") for _ in range(10))}
    f.write_text(json.dumps(bilgi))
    os.chmod(f, 0o600)
    return bilgi


def durum():
    """(bagli_mi, ssid, ip, hotspot_acik_mi)"""
    _, cikti = nmcli("-t", "-f", "DEVICE,TYPE,STATE,CONNECTION", "device")
    bagli, ssid, hotspot = False, None, False
    for satir in cikti.splitlines():
        p = ayir(satir)
        if len(p) < 4:
            continue
        cihaz, tur, hal, baglanti = p[:4]
        if tur == "loopback" or not hal.startswith("connected"):
            continue
        if baglanti == HOTSPOT_AD:
            hotspot = True
        elif tur in ("wifi", "ethernet"):
            bagli = True
            ssid = baglanti if tur == "wifi" else "kablo"
    ip = None
    if bagli:
        _, c = nmcli("-t", "-f", "IP4.ADDRESS", "device", "show", ARAYUZ if ssid != "kablo" else "eth0")
        for satir in c.splitlines():
            if ":" in satir and "/" in satir:
                ip = satir.split(":", 1)[1].split("/")[0]
                break
    return bagli, ssid, ip, hotspot


def tara(yeniden=True):
    _, c = nmcli("-t", "-f", "SSID,SIGNAL,SECURITY", "device", "wifi", "list", "ifname", ARAYUZ,
                 "--rescan", "yes" if yeniden else "no", zaman=40)
    aglar = {}
    for satir in c.splitlines():
        p = ayir(satir)
        if len(p) < 3 or not p[0] or p[0].startswith("MesajKutusu-"):
            continue
        try:
            sinyal = int(p[1])
        except ValueError:
            sinyal = 0
        if p[0] not in aglar or aglar[p[0]]["sinyal"] < sinyal:
            aglar[p[0]] = {"ssid": p[0], "sinyal": sinyal, "guvenli": p[2] not in ("", "--")}
    liste = sorted(aglar.values(), key=lambda x: -x["sinyal"])
    if liste:
        yaz("aglar.json", liste)
    return liste


def hotspot_ac(bilgi, hata=None):
    tara(True)                                  # AP modunda tarama zayıf; açmadan önce listeyi tazele
    nmcli("connection", "delete", "id", HOTSPOT_AD)
    kod, c = nmcli("connection", "add", "type", "wifi", "ifname", ARAYUZ, "con-name", HOTSPOT_AD,
                   "autoconnect", "no", "ssid", bilgi["ssid"],
                   "802-11-wireless.mode", "ap", "802-11-wireless.band", "bg", "ipv4.method", "shared",
                   "ipv6.method", "disabled", "wifi-sec.key-mgmt", "wpa-psk", "wifi-sec.psk", bilgi["sifre"])
    if kod == 0:
        kod, c = nmcli("connection", "up", "id", HOTSPOT_AD, zaman=40)
    if kod == 0:
        log("kurulum ağı açıldı:", bilgi["ssid"])
        yaz("wifi.json", {"mod": "hotspot", "ip": "10.42.0.1", "hotspot_ssid": bilgi["ssid"],
                          "hotspot_sifre": bilgi["sifre"], "hata": hata})
        return True
    log("kurulum ağı açılamadı:", c.strip())
    yaz("wifi.json", {"mod": "yok", "hata": c.strip()[-200:]})
    return False


def hotspot_kapat():
    nmcli("connection", "down", "id", HOTSPOT_AD, zaman=20)


def baglanti_bekle(sn):
    for _ in range(sn):
        b, ssid, ip, _ = durum()
        if b:
            return ssid, ip
        time.sleep(1)
    return None, None


def istege_baglan(istek, bilgi):
    ssid, sifre = istek.get("ssid", ""), istek.get("sifre", "")
    log("ağa bağlanılıyor:", ssid)
    yaz("wifi.json", {"mod": "baglaniyor", "ssid": ssid})
    hotspot_kapat()
    time.sleep(2)
    nmcli("device", "wifi", "rescan", "ifname", ARAYUZ)
    time.sleep(4)
    arg = ["device", "wifi", "connect", ssid, "ifname", ARAYUZ]
    if sifre:
        arg += ["password", sifre]
    kod, c = nmcli(*arg, zaman=60)
    if kod == 0:
        s, ip = baglanti_bekle(20)
        if s:
            log("bağlandı:", s, ip)
            yaz("wifi.json", {"mod": "bagli", "ssid": s, "ip": ip})
            return True
    log("bağlanamadı:", c.strip())
    nmcli("connection", "delete", "id", ssid)     # yanlış şifreli profil kalmasın
    s, ip = baglanti_bekle(15)                    # eski ağa geri dönebildiyse
    if s:
        yaz("wifi.json", {"mod": "bagli", "ssid": s, "ip": ip, "hata": "baglanamadi"})
        return False
    hotspot_ac(bilgi, hata="baglanamadi")
    return False


def istemci_var():
    try:
        r = subprocess.run(["iw", "dev", ARAYUZ, "station", "dump"], capture_output=True, text=True, timeout=5)
        return "Station" in r.stdout
    except (OSError, subprocess.TimeoutExpired):
        return False


def main():
    if not shutil.which("nmcli"):
        log("nmcli yok; Wi-Fi yardımcısı kapalı")
        return 0
    klasor_hazirla()
    try:                                                   # ülke ayarlıysa Wi-Fi kapalı kalmasın
        subprocess.run(["rfkill", "unblock", "wifi"], capture_output=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        pass
    nmcli("radio", "wifi", "on")
    bilgi = hotspot_bilgisi()
    baglantisiz_bas = time.monotonic()
    son_deneme = time.monotonic()
    son_tarama = 0
    yaz("wifi.json", {"mod": "baglaniyor"})
    while True:
        istek_f = KLASOR / "wifi-istek.json"
        if istek_f.exists():
            try:
                istek = json.loads(istek_f.read_text())
            except ValueError:
                istek = {}
            istek_f.unlink(missing_ok=True)
            if istek.get("ssid"):
                istege_baglan(istek, bilgi)
                baglantisiz_bas = son_deneme = time.monotonic()
                continue
        bagli, ssid, ip, hotspot = durum()
        simdi = time.monotonic()
        if bagli:
            baglantisiz_bas = simdi
            yaz("wifi.json", {"mod": "bagli", "ssid": ssid, "ip": ip})
            if simdi - son_tarama > 120:
                tara(False)
                son_tarama = simdi
        elif hotspot:
            if simdi - son_deneme > YENIDEN_DENE and not istemci_var():
                log("kurulum ağı açık; bilinen ağlar yeniden deneniyor")
                hotspot_kapat()
                s, ip = baglanti_bekle(30)
                if s:
                    yaz("wifi.json", {"mod": "bagli", "ssid": s, "ip": ip})
                else:
                    hotspot_ac(bilgi)
                son_deneme = time.monotonic()
        else:
            if simdi - baglantisiz_bas > BEKLE:
                hotspot_ac(bilgi)
                son_deneme = time.monotonic()
            else:
                yaz("wifi.json", {"mod": "baglaniyor"})
        time.sleep(3)


if __name__ == "__main__":
    sys.exit(main())
