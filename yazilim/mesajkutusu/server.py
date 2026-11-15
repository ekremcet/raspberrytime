#!/usr/bin/env python3
"""
Sesli Mesaj Kutusu - sunucu

Telegram botu üzerinden aile üyeleriyle sesli mesajlaşan çocuk cihazının arka ucu.
 - Telegram Bot API ile long-polling (açık port ya da alan adı gerekmez)
 - Yalnızca onaylı kişilerden gelen sesli mesajlar gösterilir
 - Çocuk ekranı (static/index.html) ve yönetim sayfası (static/yonetim.html) bu sunucudan açılır
 - BOT_TOKEN yoksa DEMO modunda çalışır: Telegram'a bağlanmadan ekranı ve kaydı denersin

Bağımlılıklar: Python 3.9+, aiohttp, ffmpeg (ffprobe dahil)
"""
import asyncio
import json
import logging
import os
import pathlib
import re
import secrets
import shutil
import signal
import socket
import sqlite3
import time
from datetime import datetime

from aiohttp import ClientSession, TCPConnector, ThreadedResolver, ClientTimeout, FormData, WSMsgType, web

BASE = pathlib.Path(__file__).resolve().parent
# Ekran sürümü: index.html değişince kiosk sayfası kendini yeniler
SURUM = __import__("hashlib").sha1((BASE / "static" / "index.html").read_bytes()).hexdigest()[:10]
log = logging.getLogger("kutu")
RENKLER = ["#F28B50", "#4D8DF7", "#9B6BE0", "#2FA98C", "#E0588E", "#E3A21A", "#5B7CFA", "#D1495B"]


# ----------------------------------------------------------------- ayarlar
def ayarlari_oku():
    cfg = {
        "BOT_TOKEN": "",
        "YONETICI_PIN": "",
        "KUTU_ADI": "",
        "PORT": "8080",
        "MAKS_SANIYE": "",
        "HATIRLAT_DAKIKA": "",
        "UZAKTAN_ARAYUZ": "",
        "EKRAN_DONDUR": "",
        "VERI_KLASORU": str(BASE / "veri"),
        "TELEGRAM_API": "https://api.telegram.org",
    }
    dosya = BASE / "ayarlar.env"
    if dosya.exists():
        for satir in dosya.read_text(encoding="utf-8").splitlines():
            satir = satir.strip()
            if not satir or satir.startswith("#") or "=" not in satir:
                continue
            k, v = satir.split("=", 1)
            cfg[k.strip()] = v.strip().strip('"').strip("'")
    for k in list(cfg):
        if k in os.environ:
            cfg[k] = os.environ[k]
    return cfg


SAAT_RE = re.compile(r"([01]?\d|2[0-3]):([0-5]\d)")


def dakika(saat):
    m = SAAT_RE.fullmatch((saat or "").strip())
    return int(m[1]) * 60 + int(m[2]) if m else None


def aralikta(bas, bit, simdi=None):
    """'19:30' ile '07:30' arası gibi (gece yarısını geçebilen) bir aralıkta mıyız?"""
    a, b = dakika(bas), dakika(bit)
    if a is None or b is None or a == b:
        return False
    simdi = simdi or datetime.now()
    t = simdi.hour * 60 + simdi.minute
    return a <= t < b if a < b else (t >= a or t < b)


# Yönetim sayfasından değiştirilebilen ayarlar (veritabanında saklanır).
# anahtar: (varsayılan, tür, ayarlar.env'deki eski karşılığı)
# tür: bool | sayi:min:max | saat | secim:a,b,... | metin:uzunluk
AYARLAR = {
    # genel
    "kutu_adi": ("Mesaj Kutusu", "metin:40", "KUTU_ADI"),
    "cocuk_adi": ("", "bosmetin:30", None),     # bot uyarılarında geçer ("Bunu ... göremez")
    "dil": ("tr", "secim:tr,en", None),
    "maks_saniye": ("60", "sayi:5:300", "MAKS_SANIYE"),
    "saklanan_mesaj": ("40", "sayi:5:500", None),
    "dinlendi_tepki": ("1", "bool", None),
    "uzaktan_arayuz": ("0", "bool", "UZAKTAN_ARAYUZ"),
    # ses
    "zil_acik": ("1", "bool", None),
    "zil_seviye": ("80", "sayi:0:100", None),
    "hatirlat_dakika": ("10", "sayi:0:240", "HATIRLAT_DAKIKA"),
    # ekran
    "uyku_dakika": ("2", "sayi:0.5:120", None),
    "saat_goster": ("1", "bool", None),
    "ekran_yonu": ("", "secim:,0,90,180,270", "EKRAN_DONDUR"),
    "gece_tema": ("1", "bool", None),
    "parlaklik": ("100", "sayi:5:100", None),
    "gece_parlaklik": ("30", "sayi:5:100", None),
    # sessiz mod ve gece
    "sessiz_elle": ("0", "bool", None),
    "gece_otomatik": ("1", "bool", None),
    "gece_baslangic": ("19:30", "saat", None),
    "gece_bitis": ("07:30", "saat", None),
    "gece_yanit": ("1", "bool", None),
}


def ayar_dogrula(k, v):
    """Değeri türüne göre denetler, düzgün metin hâlini döndürür; uymazsa ValueError."""
    if k not in AYARLAR:
        raise ValueError(f"bilinmeyen ayar: {k}")
    tur = AYARLAR[k][1]
    v = "" if v is None else str(v).strip()
    if tur == "bool":
        return "1" if v.lower() in ("1", "true", "evet", "on") else "0"
    if tur == "saat":
        if dakika(v) is None:
            raise ValueError("Saat SS:DD biçiminde olmalı (örn. 19:30)")
        m = dakika(v)
        return f"{m // 60:02d}:{m % 60:02d}"
    if tur.startswith("sayi:"):
        _, lo, hi = tur.split(":")
        try:
            x = float(v.replace(",", "."))
        except ValueError:
            raise ValueError("Sayı olmalı")
        if not float(lo) <= x <= float(hi):
            raise ValueError(f"{lo} ile {hi} arasında olmalı")
        return str(int(x)) if x == int(x) else str(x)
    if tur.startswith("secim:"):
        if v not in tur[6:].split(","):
            raise ValueError("Geçersiz seçim")
        return v
    if tur.startswith("metin:"):
        if not v:
            raise ValueError("Boş olamaz")
        return v[: int(tur[6:])]
    if tur.startswith("bosmetin:"):
        return v[: int(tur[9:])]
    return v


# Bot mesajları (aile üyelerinin Telegram'ında görünür)
METINLER = {
    "tr": {
        "hosgeldin": "Merhaba {ad}! Burası {kutu}. Ailen seni onayladığında buradan sesli mesaj gönderip alabileceksin.",
        "onay_bekleniyor": "Onay bekleniyor. Onaylandığında sana haber vereceğim.",
        "onaylandi": "Onaylandın! Artık buradan {kutu} ile sesli mesajlaşabilirsin. Mikrofon tuşuna basılı tutup konuş, gönder.",
        "start": "Merhaba {ad}! Buraya gönderdiğin sesli mesajlar {kutu} ekranına düşer.",
        "sadece_ses": "⚠️ Bunu {kim} göremez, yalnızca sesli mesajları görebilir. Mikrofon tuşuna basılı tutup konuşarak sesli mesaj gönder.",
        "kim_yok": "kutu",
        "sessiz_not": "🌙 {kutu} şu an sessiz modda. Mesajın kaydedildi, {ne_zaman} bildirim olarak görünecek.",
        "ne_zaman_saat": "saat {saat} olunca",
        "ne_zaman_elle": "sessiz mod kapanınca",
    },
    "en": {
        "hosgeldin": "Hi {ad}! This is {kutu}. Once the family approves you, you can send and receive voice messages here.",
        "onay_bekleniyor": "Waiting for approval. I'll let you know when you're approved.",
        "onaylandi": "You're approved! You can now exchange voice messages with {kutu}. Hold the microphone button, talk and send.",
        "start": "Hi {ad}! Voice messages you send here show up on {kutu}'s screen.",
        "sadece_ses": "⚠️ {kim} can't see this, only voice messages. Hold the microphone button and talk to send one.",
        "kim_yok": "The box",
        "sessiz_not": "🌙 {kutu} is in quiet mode right now. Your message is saved and will show up {ne_zaman}.",
        "ne_zaman_saat": "at {saat}",
        "ne_zaman_elle": "when quiet mode ends",
    },
}


# ----------------------------------------------------------------- veri
class Depo:
    def __init__(self, yol):
        self.db = sqlite3.connect(yol, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS kisiler(
                id INTEGER PRIMARY KEY, chat_id INTEGER UNIQUE, ad TEXT, tg_ad TEXT, tg_kullanici TEXT,
                renk TEXT, foto TEXT, sira INTEGER DEFAULT 0,
                durum INTEGER DEFAULT 0,          -- 0 bekliyor, 1 onaylı, -1 engelli
                olusturma REAL);
            CREATE TABLE IF NOT EXISTS mesajlar(
                id INTEGER PRIMARY KEY, kisi INTEGER, yon TEXT, dosya TEXT, sure REAL DEFAULT 0,
                zaman REAL, dinlendi INTEGER DEFAULT 0, durum TEXT, tg_id INTEGER, deneme INTEGER DEFAULT 0);
            CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v TEXT);
            """
        )
        self.db.commit()

    def q(self, sql, args=()):
        return [dict(r) for r in self.db.execute(sql, args).fetchall()]

    def x(self, sql, args=()):
        c = self.db.execute(sql, args)
        self.db.commit()
        return c.lastrowid

    def meta(self, k, v=None):
        if v is None:
            r = self.q("SELECT v FROM meta WHERE k=?", (k,))
            return r[0]["v"] if r else None
        self.x("INSERT OR REPLACE INTO meta(k,v) VALUES(?,?)", (k, str(v)))

    def kisi(self, kid):
        r = self.q("SELECT * FROM kisiler WHERE id=?", (kid,))
        return r[0] if r else None

    def kisi_chat(self, chat_id):
        r = self.q("SELECT * FROM kisiler WHERE chat_id=?", (chat_id,))
        return r[0] if r else None

    def kisi_ekle(self, chat_id, tg_ad, tg_kullanici, durum=0, ad=None):
        n = self.q("SELECT COUNT(*) n FROM kisiler")[0]["n"]
        return self.x(
            "INSERT INTO kisiler(chat_id, ad, tg_ad, tg_kullanici, renk, sira, durum, olusturma) VALUES(?,?,?,?,?,?,?,?)",
            (chat_id, ad or tg_ad, tg_ad, tg_kullanici, RENKLER[n % len(RENKLER)], n, durum, time.time()),
        )

    def mesaj(self, mid):
        r = self.q("SELECT * FROM mesajlar WHERE id=?", (mid,))
        return r[0] if r else None

    def mesaj_ekle(self, kisi, yon, durum, sure=0.0, tg_id=None):
        return self.x(
            "INSERT INTO mesajlar(kisi, yon, durum, sure, zaman, tg_id) VALUES(?,?,?,?,?,?)",
            (kisi, yon, durum, sure, time.time(), tg_id),
        )

    def mesaj_guncelle(self, mid, **alan):
        if alan:
            self.x(f"UPDATE mesajlar SET {', '.join(k + '=?' for k in alan)} WHERE id=?", (*alan.values(), mid))


# ----------------------------------------------------------------- telegram
class TelegramHatasi(Exception):
    pass


class Telegram:
    def __init__(self, token, api, oturum):
        self.url = f"{api}/bot{token}"
        self.dosya_url = f"{api}/file/bot{token}"
        self.s = oturum

    async def cagir(self, yontem, veri=None, dosyalar=None, sure=40):
        zaman = ClientTimeout(total=sure)
        if dosyalar:
            form = FormData()
            for k, v in (veri or {}).items():
                form.add_field(k, json.dumps(v) if isinstance(v, (dict, list)) else str(v))
            for k, (ad, yol, tur) in dosyalar.items():
                form.add_field(k, pathlib.Path(yol).read_bytes(), filename=ad, content_type=tur)
            istek = self.s.post(f"{self.url}/{yontem}", data=form, timeout=zaman)
        else:
            istek = self.s.post(f"{self.url}/{yontem}", json=veri or {}, timeout=zaman)
        async with istek as r:
            j = await r.json(content_type=None)
        if not j.get("ok"):
            raise TelegramHatasi(f"{yontem}: {j.get('description')}")
        return j["result"]

    async def indir(self, dosya_yolu, hedef):
        async with self.s.get(f"{self.dosya_url}/{dosya_yolu}", timeout=ClientTimeout(total=60)) as r:
            r.raise_for_status()
            hedef.write_bytes(await r.read())


# ----------------------------------------------------------------- ses
async def calistir(*args):
    p = await asyncio.create_subprocess_exec(*args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    out, err = await p.communicate()
    return p.returncode, out.decode(errors="ignore"), err.decode(errors="ignore")


async def opus_yap(girdi, cikti):
    """Her türlü ses girdisini Telegram sesli notu biçimine (mono OGG/Opus) çevirir."""
    kod, _, err = await calistir(
        "ffmpeg", "-y", "-loglevel", "error", "-i", str(girdi), "-vn", "-ac", "1", "-ar", "48000",
        "-c:a", "libopus", "-b:a", "32k", "-application", "voip", "-avoid_negative_ts", "make_zero", str(cikti),
    )
    if kod != 0:
        raise RuntimeError("ffmpeg: " + err[-400:])


async def sure_olc(dosya):
    kod, out, _ = await calistir("ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(dosya))
    try:
        return round(float(out.strip()), 1)
    except ValueError:
        return 0.0


async def deneme_sesi(cikti, saniye=3):
    """Hoparlör testi için kısa bir melodi üretir."""
    kod, _, err = await calistir(
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "lavfi", "-i", f"sine=frequency=523:duration={saniye/3}",
        "-f", "lavfi", "-i", f"sine=frequency=659:duration={saniye/3}",
        "-f", "lavfi", "-i", f"sine=frequency=784:duration={saniye/3}",
        "-filter_complex", "[0][1][2]concat=n=3:v=0:a=1,volume=0.4",
        "-ac", "1", "-ar", "48000", "-c:a", "libopus", "-b:a", "32k", str(cikti),
    )
    if kod != 0:
        raise RuntimeError("ffmpeg: " + err[-400:])


# ----------------------------------------------------------------- uygulama
class Kutu:
    def __init__(self, cfg):
        self.cfg = cfg
        self.veri = pathlib.Path(cfg["VERI_KLASORU"])
        self.medya = self.veri / "medya"
        self.medya.mkdir(parents=True, exist_ok=True)
        self.depo = Depo(self.veri / "kutu.db")
        # Yönetim sayfasından değiştirilen anahtar ayar dosyasındakinin önüne geçer
        self.token = self.depo.meta("gizli_bot_token") or cfg["BOT_TOKEN"]
        self.demo = not self.token
        self.wslar = set()
        self.cevrimici = self.demo
        self.neden = ""                     # bağlantı yoksa: "internet" ya da "anahtar"
        self.bot_kullanici = None
        self.uykuda = False
        self.tg = None
        self.gorevler = []
        self.pin = self.depo.meta("gizli_pin") or cfg["YONETICI_PIN"] or self._pin_uret()
        if self.demo and not self.depo.q("SELECT id FROM kisiler"):
            for i, ad in enumerate(["Anne", "Baba", "Babaanne"]):
                self.depo.kisi_ekle(-(i + 1), ad, None, durum=1)

    # ---- ayarlar ve sessiz mod
    def ayar(self, k):
        v = self.depo.meta("ayar_" + k)
        if v is not None:
            return v
        varsayilan, _, env = AYARLAR[k]
        if env and self.cfg.get(env):
            try:
                return ayar_dogrula(k, self.cfg[env])
            except ValueError:
                pass
        return varsayilan

    def m(self, anahtar, **kw):
        """Seçili dilde bot mesajı."""
        dil = METINLER.get(self.ayar("dil"), METINLER["tr"])
        return dil[anahtar].format(kutu=self.ayar("kutu_adi"), **kw)

    def ayar_yaz(self, k, v):
        self.depo.meta("ayar_" + k, v)

    def gece_mi(self):
        return self.ayar("gece_otomatik") == "1" and aralikta(self.ayar("gece_baslangic"), self.ayar("gece_bitis"))

    def sessiz_mi(self):
        return self.ayar("sessiz_elle") == "1" or self.gece_mi()

    def parlaklik_uygula(self):
        """Arka ışık: uykuda kısık (saat görünüyorsa) ya da kapalı, gece ayrı seviye, gündüz normal."""
        if self.uykuda:
            hedef = min(10, float(self.ayar("gece_parlaklik"))) if self.ayar("saat_goster") == "1" else 0
        elif self.gece_mi():
            hedef = float(self.ayar("gece_parlaklik"))
        else:
            hedef = float(self.ayar("parlaklik"))
        if getattr(self, "_son_parlaklik", None) != hedef and parlaklik_yaz(hedef):
            self._son_parlaklik = hedef

    async def parlaklik_dongusu(self):
        while True:
            self.parlaklik_uygula()
            await asyncio.sleep(30)

    def sessiz_donemi(self):
        """Aynı sessiz dönem içinde gönderene yalnızca bir kez not yazmak için dönem kimliği."""
        if self.ayar("sessiz_elle") == "1":
            return "elle-" + (self.depo.meta("sessiz_elle_zaman") or "")
        simdi = datetime.now()
        gun = simdi.date()
        if dakika(self.ayar("gece_baslangic")) > simdi.hour * 60 + simdi.minute:   # gece yarısından sonra
            gun = gun.fromordinal(gun.toordinal() - 1)
        return "gece-" + gun.isoformat()

    def ayarlar_json(self):
        d = {k: self.ayar(k) for k in AYARLAR}
        d.update(simdi_sessiz=self.sessiz_mi(), simdi_gece=self.gece_mi(), saat=datetime.now().strftime("%H:%M"))
        return d

    def _pin_uret(self):
        f = self.veri / "yonetici_pin.txt"
        if f.exists():
            return f.read_text().strip()
        pin = f"{secrets.randbelow(900000) + 100000}"
        f.write_text(pin)
        return pin

    # ---- yayın
    async def yayinla(self, olay):
        veri = json.dumps(olay)
        for ws in list(self.wslar):
            try:
                await ws.send_str(veri)
            except Exception:
                self.wslar.discard(ws)

    # ---- bakım: eski mesajları ve dosyalarını sil
    def budama(self, kisi):
        eski = self.depo.q("SELECT id, dosya FROM mesajlar WHERE kisi=? ORDER BY id DESC LIMIT -1 OFFSET ?", (kisi, int(float(self.ayar("saklanan_mesaj")))))
        for m in eski:
            if m["dosya"]:
                (self.medya / m["dosya"]).unlink(missing_ok=True)
            self.depo.x("DELETE FROM mesajlar WHERE id=?", (m["id"],))

    # ---- telegram tarafı
    async def metin(self, chat_id, yazi):
        if self.tg:
            try:
                await self.tg.cagir("sendMessage", {"chat_id": chat_id, "text": yazi})
            except Exception as e:
                log.warning("mesaj gönderilemedi: %s", e)

    async def dinleme_dongusu(self):
        offset = int(self.depo.meta("offset") or 0)
        bekle = 2
        while True:
            try:
                if not self.bot_kullanici:
                    me = await self.tg.cagir("getMe")
                    self.bot_kullanici = me.get("username")
                    log.info("bot: @%s", self.bot_kullanici)
                    if not self.cevrimici:          # uzun beklemeyi (50 sn) beklemeden bağlı say
                        self.cevrimici = True
                        await self.yayinla({"tur": "baglanti", "cevrimici": True})
                guncel = await self.tg.cagir(
                    "getUpdates", {"offset": offset, "timeout": 50, "allowed_updates": ["message"]}, sure=70
                )
                if not self.cevrimici:
                    self.cevrimici = True
                    await self.yayinla({"tur": "baglanti", "cevrimici": True})
                bekle = 2
                for g in guncel:
                    offset = g["update_id"] + 1
                    self.depo.meta("offset", offset)
                    try:
                        await self.gelen(g.get("message"))
                    except Exception:
                        log.exception("mesaj işlenemedi")
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.warning("telegram bağlantısı: %s", e)
                neden = "anahtar" if isinstance(e, TelegramHatasi) and any(
                    w in str(e) for w in ("Unauthorized", "Not Found")) else "internet"
                if self.cevrimici or neden != self.neden:
                    self.cevrimici = False
                    self.neden = neden
                    await self.yayinla({"tur": "baglanti", "cevrimici": False, "neden": neden})
                await asyncio.sleep(bekle)
                bekle = min(60, bekle * 2)

    async def gelen(self, msg):
        if not msg or msg.get("chat", {}).get("type") != "private":
            return
        chat_id = msg["chat"]["id"]
        kimden = msg.get("from", {})
        ilk_ad = kimden.get("first_name") or ""
        k = self.depo.kisi_chat(chat_id)
        if k is None:
            tam = " ".join(x for x in [ilk_ad, kimden.get("last_name")] if x) or kimden.get("username") or "Bilinmeyen"
            self.depo.kisi_ekle(chat_id, tam, kimden.get("username"))
            log.info("onay bekleyen yeni kişi: %s (%s)", tam, chat_id)
            await self.metin(chat_id, self.m("hosgeldin", ad=ilk_ad))
            await self.yayinla({"tur": "yonetim"})
            return
        if k["durum"] == -1:
            return
        if k["durum"] == 0:
            if (msg.get("text") or "").startswith("/start"):
                await self.metin(chat_id, self.m("onay_bekleniyor"))
            return
        ses = msg.get("voice") or msg.get("audio")
        if ses:
            bilgi = await self.tg.cagir("getFile", {"file_id": ses["file_id"]})
            uzanti = pathlib.Path(bilgi.get("file_path", "")).suffix.lower()
            mid = self.depo.mesaj_ekle(k["id"], "gelen", "alindi", float(ses.get("duration") or 0), msg["message_id"])
            ham = self.medya / f"ham_{mid}{uzanti or '.bin'}"
            await self.tg.indir(bilgi["file_path"], ham)
            if uzanti in (".oga", ".ogg", ".opus"):
                hedef = self.medya / f"gelen_{mid}.ogg"
                ham.rename(hedef)
            elif uzanti in (".mp3", ".m4a"):
                hedef = self.medya / f"gelen_{mid}{uzanti}"
                ham.rename(hedef)
            else:
                hedef = self.medya / f"gelen_{mid}.ogg"
                await opus_yap(ham, hedef)
                ham.unlink(missing_ok=True)
            sure = float(ses.get("duration") or 0) or await sure_olc(hedef)
            self.depo.mesaj_guncelle(mid, dosya=hedef.name, sure=sure)
            self.budama(k["id"])
            log.info("sesli mesaj geldi: %s (%.1f sn)%s", k["ad"], sure, " [sessiz]" if self.sessiz_mi() else "")
            await self.yayinla({"tur": "mesaj", "kisi": k["id"], "yon": "gelen"})
            if self.sessiz_mi() and self.ayar("gece_yanit") == "1":
                donem = self.sessiz_donemi()
                if self.depo.meta(f"sessiz_not_{k['id']}") != donem:
                    self.depo.meta(f"sessiz_not_{k['id']}", donem)
                    ne_zaman = (self.m("ne_zaman_saat", saat=self.ayar("gece_bitis")) if self.ayar("sessiz_elle") != "1"
                                else self.m("ne_zaman_elle"))
                    await self.metin(chat_id, self.m("sessiz_not", ne_zaman=ne_zaman))
        elif msg.get("text", "").startswith("/start"):
            await self.metin(chat_id, self.m("start", ad=ilk_ad))
        else:
            await self.metin(chat_id, self.m("sadece_ses", kim=self.ayar("cocuk_adi") or self.m("kim_yok")))

    async def teslim_et(self, mid):
        m = self.depo.mesaj(mid)
        if not m or m["yon"] != "giden" or m["durum"] == "gonderildi" or not m["dosya"]:
            return
        k = self.depo.kisi(m["kisi"])
        if not k or k["durum"] != 1:
            self.depo.mesaj_guncelle(mid, durum="hata")
            return
        self.depo.mesaj_guncelle(mid, deneme=m["deneme"] + 1)
        try:
            if self.demo:
                await asyncio.sleep(0.6)
                tg_id = None
            else:
                r = await self.tg.cagir(
                    "sendVoice", {"chat_id": k["chat_id"], "duration": max(1, int(round(m["sure"])))},
                    {"voice": ("sesli-mesaj.ogg", self.medya / m["dosya"], "audio/ogg")}, sure=60,
                )
                tg_id = r["message_id"]
            self.depo.mesaj_guncelle(mid, durum="gonderildi", tg_id=tg_id)
            log.info("sesli mesaj gönderildi: %s", k["ad"])
        except Exception as e:
            log.warning("gönderilemedi (#%s): %s", mid, e)
            self.depo.mesaj_guncelle(mid, durum="hata")
        await self.yayinla({"tur": "mesaj", "kisi": k["id"], "yon": "giden"})

    async def yeniden_deneme_dongusu(self):
        while True:
            await asyncio.sleep(30)
            for m in self.depo.q("SELECT id FROM mesajlar WHERE yon='giden' AND durum='hata' AND deneme < 30"):
                await self.teslim_et(m["id"])

    async def tepki(self, m):
        """Çocuk mesajı dinleyince gönderenin Telegram'ında mesaja 👀 tepkisi bırakır."""
        if self.demo or not m["tg_id"] or self.ayar("dinlendi_tepki") != "1":
            return
        k = self.depo.kisi(m["kisi"])
        try:
            await self.tg.cagir("setMessageReaction", {"chat_id": k["chat_id"], "message_id": m["tg_id"],
                                                       "reaction": [{"type": "emoji", "emoji": "👀"}]})
        except Exception as e:
            log.info("tepki bırakılamadı: %s", e)


# ----------------------------------------------------------------- http
ADLAR = re.compile(r"^[a-z0-9_]+\.(ogg|mp3|m4a|jpg)$")


def kutu(req) -> Kutu:
    return req.app["kutu"]


def yerel_mi(req):
    if kutu(req).ayar("uzaktan_arayuz") == "1":
        return
    if req.remote not in ("127.0.0.1", "::1", None):
        raise web.HTTPForbidden(text="Çocuk ekranı yalnızca cihazın kendisinden açılır.")


def yonetici(req):
    if req.headers.get("X-Yonetici-Pin") != kutu(req).pin:
        raise web.HTTPUnauthorized(text="PIN hatalı")


def kisi_json(k, okunmamis=0):
    return {"id": k["id"], "ad": k["ad"], "renk": k["renk"], "foto": k["foto"], "okunmamis": okunmamis}


async def durum(req):
    yerel_mi(req)
    b = kutu(req)
    kisiler = b.depo.q("SELECT * FROM kisiler WHERE durum=1 ORDER BY sira, id")
    sayi = {r["kisi"]: r["n"] for r in b.depo.q(
        "SELECT kisi, COUNT(*) n FROM mesajlar WHERE yon='gelen' AND dinlendi=0 AND dosya IS NOT NULL GROUP BY kisi")}
    return web.json_response({
        "kutu_adi": b.ayar("kutu_adi"), "maks_saniye": float(b.ayar("maks_saniye")), "dil": b.ayar("dil"),
        "uyku_dakika": float(b.ayar("uyku_dakika")), "sessiz": b.sessiz_mi(),
        "gece": b.gece_mi() and b.ayar("gece_tema") == "1", "gece_bitis": b.ayar("gece_bitis"),
        "zil_acik": b.ayar("zil_acik") == "1", "zil_seviye": float(b.ayar("zil_seviye")),
        "saat_goster": b.ayar("saat_goster") == "1", "ekran_yonu": b.ayar("ekran_yonu"),
        "hatirlat_dakika": float(b.ayar("hatirlat_dakika")), "surum": SURUM,
        "cevrimici": b.cevrimici, "demo": b.demo, "neden": b.neden,
        "kisiler": [kisi_json(k, sayi.get(k["id"], 0)) for k in kisiler],
    })


async def mesajlar(req):
    yerel_mi(req)
    b = kutu(req)
    kid = int(req.match_info["kid"])
    rows = b.depo.q("SELECT id, yon, dosya, sure, zaman, dinlendi, durum FROM mesajlar "
                    "WHERE kisi=? AND dosya IS NOT NULL ORDER BY id DESC LIMIT 30", (kid,))
    return web.json_response(list(reversed(rows)))


async def gonder(req):
    yerel_mi(req)
    b = kutu(req)
    k = b.depo.kisi(int(req.query.get("kisi", 0)))
    if not k or k["durum"] != 1:
        raise web.HTTPNotFound(text="kişi yok")
    veri = await req.read()
    if len(veri) < 800:
        raise web.HTTPBadRequest(text="kayıt çok kısa")
    gecici = b.medya / f"gecici_{secrets.token_hex(4)}"
    gecici.write_bytes(veri)
    mid = b.depo.mesaj_ekle(k["id"], "giden", "bekliyor")
    hedef = b.medya / f"giden_{mid}.ogg"
    try:
        await opus_yap(gecici, hedef)
    except Exception as e:
        b.depo.x("DELETE FROM mesajlar WHERE id=?", (mid,))
        log.error("kayıt dönüştürülemedi: %s", e)
        raise web.HTTPInternalServerError(text="kayıt dönüştürülemedi")
    finally:
        gecici.unlink(missing_ok=True)
    b.depo.mesaj_guncelle(mid, dosya=hedef.name, sure=await sure_olc(hedef))
    b.budama(k["id"])
    asyncio.create_task(b.teslim_et(mid))
    await b.yayinla({"tur": "mesaj", "kisi": k["id"], "yon": "giden"})
    return web.json_response({"id": mid})


async def dinlendi(req):
    yerel_mi(req)
    b = kutu(req)
    m = b.depo.mesaj(int(req.match_info["mid"]))
    if m and m["yon"] == "gelen" and not m["dinlendi"]:
        b.depo.mesaj_guncelle(m["id"], dinlendi=1)
        asyncio.create_task(b.tepki(m))
        await b.yayinla({"tur": "okundu", "kisi": m["kisi"]})
    return web.json_response({"ok": True})


async def medya(req):
    ad = req.match_info["ad"]
    if not ADLAR.match(ad):
        raise web.HTTPNotFound()
    yol = kutu(req).medya / ad
    if not yol.exists():
        raise web.HTTPNotFound()
    tur = {"ogg": "audio/ogg", "mp3": "audio/mpeg", "m4a": "audio/mp4", "jpg": "image/jpeg"}[ad.rsplit(".", 1)[1]]
    return web.FileResponse(yol, headers={"Content-Type": tur, "Cache-Control": "max-age=86400"})


async def ws(req):
    sock = web.WebSocketResponse(heartbeat=25)
    await sock.prepare(req)
    b = kutu(req)
    b.wslar.add(sock)
    try:
        async for m in sock:
            if m.type == WSMsgType.ERROR:
                break
    finally:
        b.wslar.discard(sock)
    return sock


async def saglik(req):
    return web.json_response({"ok": True})


# ---- yönetim
async def y_bilgi(req):
    yonetici(req)
    b = kutu(req)
    return web.json_response({
        "kutu_adi": b.ayar("kutu_adi"), "demo": b.demo, "cevrimici": b.cevrimici, "neden": b.neden,
        "bot": b.bot_kullanici, "baglanti": f"https://t.me/{b.bot_kullanici}" if b.bot_kullanici else None,
        "ffmpeg": bool(shutil.which("ffmpeg")),
    })


async def y_kisiler(req):
    yonetici(req)
    b = kutu(req)
    rows = b.depo.q("SELECT id, ad, tg_ad, tg_kullanici, renk, foto, sira, durum FROM kisiler ORDER BY durum DESC, sira, id")
    return web.json_response(rows)


async def y_kisi_guncelle(req):
    yonetici(req)
    b = kutu(req)
    k = b.depo.kisi(int(req.match_info["kid"]))
    if not k:
        raise web.HTTPNotFound()
    veri = await req.json()
    alan = {}
    if isinstance(veri.get("ad"), str) and veri["ad"].strip():
        alan["ad"] = veri["ad"].strip()[:30]
    if isinstance(veri.get("renk"), str) and re.fullmatch(r"#[0-9A-Fa-f]{6}", veri["renk"]):
        alan["renk"] = veri["renk"]
    if veri.get("durum") in (-1, 0, 1):
        alan["durum"] = veri["durum"]
    if alan:
        b.depo.x(f"UPDATE kisiler SET {', '.join(k2 + '=?' for k2 in alan)} WHERE id=?", (*alan.values(), k["id"]))
    if alan.get("durum") == 1 and k["durum"] != 1 and k["chat_id"] > 0:
        await b.metin(k["chat_id"], b.m("onaylandi"))
    await b.yayinla({"tur": "kisiler"})
    return web.json_response(b.depo.kisi(k["id"]))


async def y_foto(req):
    yonetici(req)
    b = kutu(req)
    k = b.depo.kisi(int(req.match_info["kid"]))
    if not k:
        raise web.HTTPNotFound()
    veri = await req.read()
    if not veri.startswith(b"\xff\xd8") or len(veri) > 3_000_000:
        raise web.HTTPBadRequest(text="JPEG bekleniyor")
    if k["foto"]:
        (b.medya / k["foto"]).unlink(missing_ok=True)
    ad = f"foto_{k['id']}_{secrets.token_hex(3)}.jpg"
    (b.medya / ad).write_bytes(veri)
    b.depo.x("UPDATE kisiler SET foto=? WHERE id=?", (ad, k["id"]))
    await b.yayinla({"tur": "kisiler"})
    return web.json_response({"foto": ad})


async def y_sira(req):
    yonetici(req)
    b = kutu(req)
    for i, kid in enumerate((await req.json()).get("idler", [])):
        b.depo.x("UPDATE kisiler SET sira=? WHERE id=?", (i, int(kid)))
    await b.yayinla({"tur": "kisiler"})
    return web.json_response({"ok": True})


async def y_sil(req):
    yonetici(req)
    b = kutu(req)
    kid = int(req.match_info["kid"])
    k = b.depo.kisi(kid)
    if not k:
        raise web.HTTPNotFound()
    for m in b.depo.q("SELECT dosya FROM mesajlar WHERE kisi=?", (kid,)):
        if m["dosya"]:
            (b.medya / m["dosya"]).unlink(missing_ok=True)
    if k["foto"]:
        (b.medya / k["foto"]).unlink(missing_ok=True)
    b.depo.x("DELETE FROM mesajlar WHERE kisi=?", (kid,))
    b.depo.x("DELETE FROM kisiler WHERE id=?", (kid,))
    await b.yayinla({"tur": "kisiler"})
    return web.json_response({"ok": True})


async def y_deneme(req):
    """Seçilen kişiden gelmiş gibi bir deneme sesi ekler (hoparlör ve ekran testi)."""
    yonetici(req)
    b = kutu(req)
    k = b.depo.kisi(int(req.match_info["kid"]))
    if not k or k["durum"] != 1:
        raise web.HTTPNotFound()
    mid = b.depo.mesaj_ekle(k["id"], "gelen", "alindi")
    hedef = b.medya / f"gelen_{mid}.ogg"
    await deneme_sesi(hedef)
    b.depo.mesaj_guncelle(mid, dosya=hedef.name, sure=await sure_olc(hedef))
    b.budama(k["id"])
    await b.yayinla({"tur": "mesaj", "kisi": k["id"], "yon": "gelen"})
    return web.json_response({"id": mid})


async def y_ayarlar(req):
    yonetici(req)
    b = kutu(req)
    if req.method == "POST":
        veri = await req.json()
        temiz = {}
        try:
            for k, v in veri.items():
                temiz[k] = ayar_dogrula(k, v)
        except ValueError as e:
            raise web.HTTPBadRequest(text=str(e))
        for k, v in temiz.items():
            if k == "sessiz_elle" and v == "1" and b.ayar("sessiz_elle") != "1":
                b.depo.meta("sessiz_elle_zaman", int(time.time()))
            b.ayar_yaz(k, v)
        log.info("ayarlar güncellendi: %s", temiz)
        if "ekran_yonu" in temiz:
            asyncio.create_task(ekran_yonu_uygula())
        if temiz.keys() & {"parlaklik", "gece_parlaklik", "gece_otomatik", "gece_baslangic", "gece_bitis", "sessiz_elle"}:
            b.parlaklik_uygula()
        await b.yayinla({"tur": "ayarlar"})
    return web.json_response(b.ayarlar_json())


# ---------------------------------------------------------- donanım ve sistem
async def komut(*args, sure=15):
    """Komutu çalıştırır, (çıkış kodu, çıktı) döndürür. Program yoksa 127."""
    if not shutil.which(args[0]):
        return 127, f"{args[0]} bulunamadı"
    env = dict(os.environ)
    env.setdefault("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    p = await asyncio.create_subprocess_exec(*args, stdout=asyncio.subprocess.PIPE,
                                             stderr=asyncio.subprocess.STDOUT, env=env)
    try:
        out, _ = await asyncio.wait_for(p.communicate(), sure)
    except asyncio.TimeoutError:
        p.kill()
        return 124, "zaman aşımı"
    return p.returncode, out.decode(errors="replace").strip()


async def ses_seviyesi(hedef):
    kod, out = await komut("wpctl", "get-volume", hedef)
    m = re.search(r"Volume:\s*([\d.]+)", out)
    return round(float(m[1]) * 100) if kod == 0 and m else None


async def ses_durumu():
    kod, out = await komut("pw-dump")
    if kod != 0:
        return {"var": False, "hata": "Ses sistemi (PipeWire) bulunamadı"}
    try:
        nesneler = json.loads(out)
    except ValueError:
        return {"var": False, "hata": "Ses aygıtları okunamadı"}
    cihaz = {"Audio/Sink": [], "Audio/Source": []}
    varsayilan = {}
    for o in nesneler:
        if o.get("type") == "PipeWire:Interface:Node":
            pr = (o.get("info") or {}).get("props") or {}
            if pr.get("media.class") in cihaz:
                cihaz[pr["media.class"]].append({"id": o["id"], "isim": pr.get("node.name"),
                                                 "ad": pr.get("node.description") or pr.get("node.nick") or pr.get("node.name")})
        elif o.get("type") == "PipeWire:Interface:Metadata" and (o.get("props") or {}).get("metadata.name") == "default":
            for m in o.get("metadata") or []:
                deger = m.get("value")
                if isinstance(deger, str):
                    try:
                        deger = json.loads(deger)
                    except ValueError:
                        deger = {}
                if m.get("key") in ("default.audio.sink", "default.audio.source") and isinstance(deger, dict):
                    varsayilan[m["key"]] = deger.get("name")

    def sec(liste, anahtar):
        for c in liste:
            if c["isim"] == varsayilan.get(anahtar):
                return c["id"]
        return liste[0]["id"] if liste else None

    hop, mik = cihaz["Audio/Sink"], cihaz["Audio/Source"]
    return {"var": True, "hoparlorler": hop, "mikrofonlar": mik,
            "hoparlor": sec(hop, "default.audio.sink"), "mikrofon": sec(mik, "default.audio.source"),
            "ses": await ses_seviyesi("@DEFAULT_AUDIO_SINK@"), "mik_ses": await ses_seviyesi("@DEFAULT_AUDIO_SOURCE@")}


def arka_isik():
    for d in sorted(pathlib.Path("/sys/class/backlight").glob("*")):
        if (d / "brightness").exists():
            return d
    return None


def parlaklik_durumu():
    d = arka_isik()
    if not d:
        return {"var": False}
    try:
        mx = int((d / "max_brightness").read_text())
        return {"var": True, "deger": round(int((d / "brightness").read_text()) * 100 / mx),
                "yazilabilir": os.access(d / "brightness", os.W_OK)}
    except (OSError, ValueError, ZeroDivisionError):
        return {"var": False}


def parlaklik_yaz(yuzde):
    d = arka_isik()
    if not d:
        return False
    try:
        mx = int((d / "max_brightness").read_text())
        (d / "brightness").write_text(str(max(0, min(mx, round(mx * yuzde / 100)))))
        return True
    except (OSError, ValueError):
        return False


def wayland_ortami():
    calisma = pathlib.Path(os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}")
    soketler = sorted(calisma.glob("wayland-[0-9]"))
    if not soketler:
        return None
    return {"XDG_RUNTIME_DIR": str(calisma), "WAYLAND_DISPLAY": soketler[0].name,
            "DBUS_SESSION_BUS_ADDRESS": f"unix:path={calisma}/bus"}


async def ekran_yonu_uygula():
    """kiosk.sh --dondur: yönü sunucudan okuyup ekrana ve dokunmatiğe uygular."""
    ortam = wayland_ortami()
    if not ortam:
        return False, "Masaüstü oturumu açık değil; bir sonraki açılışta uygulanacak"
    env = dict(os.environ, **ortam)
    p = await asyncio.create_subprocess_exec("bash", str(BASE / "sistem" / "kiosk.sh"), "--dondur",
                                             stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT, env=env)
    out, _ = await p.communicate()
    log.info("ekran yönü: %s", out.decode(errors="replace").strip())
    return p.returncode == 0, out.decode(errors="replace").strip()


def depo_klasoru():
    r = pathlib.Path(os.environ.get("MESAJKUTUSU_REPO") or pathlib.Path.home() / "raspberrytime")
    return r if (r / ".git").exists() else None


def yeniden_baslat_sonra(saniye=1.0):
    """Yanıt gönderildikten sonra kendini kapatır; systemd (Restart=always) yeniden başlatır."""
    asyncio.get_running_loop().call_later(saniye, os.kill, os.getpid(), signal.SIGTERM)


async def y_ses(req):
    yonetici(req)
    if req.method == "POST":
        veri = await req.json()
        try:
            if veri.get("hoparlor") is not None:
                await komut("wpctl", "set-default", str(int(veri["hoparlor"])))
            if veri.get("mikrofon") is not None:
                await komut("wpctl", "set-default", str(int(veri["mikrofon"])))
            for anahtar, hedef in (("ses", "@DEFAULT_AUDIO_SINK@"), ("mik_ses", "@DEFAULT_AUDIO_SOURCE@")):
                if veri.get(anahtar) is not None:
                    x = max(0, min(100, int(veri[anahtar])))
                    kod, out = await komut("wpctl", "set-volume", hedef, f"{x / 100:.2f}")
                    if kod != 0:
                        raise web.HTTPBadRequest(text="Ses ayarlanamadı: " + out[:120])
        except (TypeError, ValueError):
            raise web.HTTPBadRequest(text="Geçersiz değer")
    return web.json_response(await ses_durumu())


async def y_zil(req):
    yonetici(req)
    await kutu(req).yayinla({"tur": "zil_dene"})
    return web.json_response({"ok": True})


async def y_ekran(req):
    yonetici(req)
    if req.method == "POST":
        veri = await req.json()
        if veri.get("yonu_uygula"):
            ok, mesaj = await ekran_yonu_uygula()
            return web.json_response({"ok": ok, "mesaj": mesaj, **parlaklik_durumu()})
    return web.json_response(parlaklik_durumu())


async def ekran_bildirim(req):
    """Çocuk ekranı uykuya geçince/uyanınca haber verir (arka ışık kısılır/açılır)."""
    yerel_mi(req)
    b = kutu(req)
    veri = await req.json()
    b.uykuda = bool(veri.get("uyku"))
    b.parlaklik_uygula()
    return web.json_response({"ok": True})


async def y_guvenlik(req):
    yonetici(req)
    b = kutu(req)
    if req.method == "POST":
        veri = await req.json()
        if "pin" in veri:
            pin = str(veri["pin"]).strip()
            if not re.fullmatch(r"\d{4,12}", pin):
                raise web.HTTPBadRequest(text="PIN 4–12 rakam olmalı")
            b.depo.meta("gizli_pin", pin)
            b.pin = pin
            log.info("yönetici PIN'i değiştirildi")
        if "bot_token" in veri:
            tok = str(veri["bot_token"]).strip()
            if tok:
                if not re.fullmatch(r"\d{5,}:[A-Za-z0-9_-]{30,}", tok):
                    raise web.HTTPBadRequest(text="Anahtar 123456789:AAH... biçiminde olmalı")
                try:
                    async with ClientSession(connector=TCPConnector(resolver=ThreadedResolver())) as o:
                        async with o.get(f"{b.cfg['TELEGRAM_API'].rstrip('/')}/bot{tok}/getMe",
                                         timeout=ClientTimeout(total=15)) as r:
                            sonuc = await r.json()
                except Exception:
                    raise web.HTTPBadRequest(text="Telegram'a ulaşılamadı, anahtar denenemedi")
                if not sonuc.get("ok"):
                    raise web.HTTPBadRequest(text="Telegram bu anahtarı kabul etmedi")
                b.depo.meta("gizli_bot_token", tok)
            else:
                b.depo.x("DELETE FROM meta WHERE k='gizli_bot_token'")
            log.info("bot anahtarı değiştirildi, yeniden başlatılıyor")
            yeniden_baslat_sonra(1.5)
            return web.json_response({"ok": True, "yeniden_basliyor": True})
    tok = b.token or ""
    return web.json_response({
        "token_var": bool(tok), "token_maske": (tok[:6] + "…" + tok[-4:]) if len(tok) > 16 else ("••••" if tok else ""),
        "token_kaynak": "panel" if b.depo.meta("gizli_bot_token") else ("dosya" if b.cfg["BOT_TOKEN"] else ""),
        "pin_kaynak": "panel" if b.depo.meta("gizli_pin") else ("dosya" if b.cfg["YONETICI_PIN"] else "otomatik"),
    })


async def sistem_bilgisi(b):
    d = {"ad": socket.gethostname()}
    kod, out = await komut("hostname", "-I")
    d["ip"] = out.split()[:2] if kod == 0 else []
    try:
        d["sicaklik"] = round(int(pathlib.Path("/sys/class/thermal/thermal_zone0/temp").read_text()) / 1000, 1)
    except (OSError, ValueError):
        d["sicaklik"] = None
    try:
        d["acik_sure"] = float(pathlib.Path("/proc/uptime").read_text().split()[0])
    except (OSError, ValueError):
        d["acik_sure"] = None
    du = shutil.disk_usage(b.veri)
    d["disk_bos"], d["disk_toplam"] = round(du.free / 1e9, 1), round(du.total / 1e9, 1)
    try:
        mi = dict(re.findall(r"^(\w+):\s+(\d+)", pathlib.Path("/proc/meminfo").read_text(), re.M))
        d["bellek_bos"], d["bellek_toplam"] = round(int(mi["MemAvailable"]) / 1e6, 1), round(int(mi["MemTotal"]) / 1e6, 1)
    except (OSError, KeyError):
        pass
    repo = depo_klasoru()
    d["depo"] = bool(repo)
    if repo:
        kod, out = await komut("git", "-C", str(repo), "log", "-1", "--format=%h|%cd|%s", "--date=format:%d.%m.%Y %H:%M")
        if kod == 0 and out.count("|") >= 2:
            d["surum"], d["surum_tarih"], d["surum_not"] = out.split("|", 2)
    gl = b.veri / "guncelleme.log"
    if gl.exists():
        d["guncelleme_log"] = "\n".join(gl.read_text(errors="replace").splitlines()[-12:])
    return d


async def y_sistem(req):
    yonetici(req)
    b = kutu(req)
    if req.method == "POST":
        islem = (await req.json()).get("islem")
        repo = depo_klasoru()
        if islem == "denetle":
            if not repo:
                raise web.HTTPBadRequest(text="Depo yok: Pi'de bir kez 'git clone https://github.com/ekremcet/raspberrytime ~/raspberrytime' çalıştır")
            kod, out = await komut("git", "-C", str(repo), "fetch", "--quiet", "origin", sure=40)
            if kod != 0:
                raise web.HTTPBadRequest(text="GitHub'a ulaşılamadı: " + out[:120])
            kod, out = await komut("git", "-C", str(repo), "log", "--format=%s", "HEAD..@{u}")
            yeniler = [x for x in out.splitlines() if x.strip()] if kod == 0 else []
            return web.json_response({**await sistem_bilgisi(b), "yeniler": yeniler})
        if islem == "guncelle":
            if not repo:
                raise web.HTTPBadRequest(text="Depo yok")
            gl = b.veri / "guncelleme.log"
            gl.write_text(f"{datetime.now():%d.%m.%Y %H:%M} güncelleme başladı\n")
            kod, out = await komut("systemd-run", "--user", "--collect", "--quiet", f"--unit=mesajkutusu-guncelle-{int(time.time())}",
                                   "bash", "-c", f"bash '{repo}/yazilim/guncelle.sh' >> '{gl}' 2>&1")
            if kod != 0:
                raise web.HTTPBadRequest(text="Güncelleme başlatılamadı: " + out[:120])
            return web.json_response({"ok": True, "mesaj": "Güncelleme başladı; kutu 1 dakika içinde yeniden açılır"})
        if islem == "uygulama":
            yeniden_baslat_sonra()
            return web.json_response({"ok": True, "mesaj": "Uygulama yeniden başlatılıyor"})
        if islem in ("yeniden_baslat", "kapat"):
            eylem = "reboot" if islem == "yeniden_baslat" else "poweroff"
            kod, out = await komut("systemctl", eylem, "--no-wall")
            if kod != 0:
                kod, out = await komut("sudo", "-n", "/usr/bin/systemctl", eylem)
            if kod != 0:
                raise web.HTTPBadRequest(text="İzin yok. Pi'de bir kez uzak kabuktan 'bash ~/raspberrytime/yazilim/guncelle.sh' çalıştırıp şifreni gir.")
            return web.json_response({"ok": True, "mesaj": "Cihaz " + ("yeniden başlatılıyor" if islem == "yeniden_baslat" else "kapanıyor")})
        raise web.HTTPBadRequest(text="bilinmeyen işlem")
    return web.json_response(await sistem_bilgisi(b))


def statik(ad):
    async def h(req):
        return web.FileResponse(BASE / "static" / ad, headers={"Cache-Control": "no-cache"})
    return h


async def baslangic(app):
    b = app["kutu"]
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        log.error("ffmpeg bulunamadı! Kurulum: sudo apt install ffmpeg  (Mac: brew install ffmpeg)")
    if b.demo:
        log.warning("BOT_TOKEN yok: DEMO modunda çalışıyor (Telegram'a bağlanmıyor).")
    else:
        app["oturum"] = ClientSession(connector=TCPConnector(resolver=ThreadedResolver()))
        b.tg = Telegram(b.token, b.cfg["TELEGRAM_API"].rstrip("/"), app["oturum"])
        b.gorevler.append(asyncio.create_task(b.dinleme_dongusu()))
        b.gorevler.append(asyncio.create_task(b.yeniden_deneme_dongusu()))
        for m in b.depo.q("SELECT id FROM mesajlar WHERE yon='giden' AND durum IN ('bekliyor','hata')"):
            b.gorevler.append(asyncio.create_task(b.teslim_et(m["id"])))
    b.gorevler.append(asyncio.create_task(b.parlaklik_dongusu()))
    port = b.cfg["PORT"]
    log.info("Çocuk ekranı:  http://localhost:%s/", port)
    log.info("Yönetim:       http://<bu-cihazın-adresi>:%s/yonetim   PIN: %s", port, b.pin)


async def kapanis(app):
    b = app["kutu"]
    for g in b.gorevler:
        g.cancel()
    for sock in list(b.wslar):
        await sock.close()
    if "oturum" in app:
        await app["oturum"].close()


def uygulama(cfg=None):
    cfg = cfg or ayarlari_oku()
    app = web.Application(client_max_size=20 * 1024 * 1024)
    app["kutu"] = Kutu(cfg)
    app.add_routes([
        web.get("/", statik("index.html")),
        web.get("/yonetim", statik("yonetim.html")),
        web.static("/static", BASE / "static"),
        web.get("/api/saglik", saglik),
        web.get("/api/durum", durum),
        web.get("/api/mesajlar/{kid}", mesajlar),
        web.post("/api/gonder", gonder),
        web.post("/api/dinlendi/{mid}", dinlendi),
        web.get("/medya/{ad}", medya),
        web.get("/ws", ws),
        web.get("/api/yonetim/bilgi", y_bilgi),
        web.get("/api/yonetim/kisiler", y_kisiler),
        web.post("/api/yonetim/kisi/{kid}", y_kisi_guncelle),
        web.post("/api/yonetim/foto/{kid}", y_foto),
        web.post("/api/yonetim/sira", y_sira),
        web.delete("/api/yonetim/kisi/{kid}", y_sil),
        web.post("/api/yonetim/deneme/{kid}", y_deneme),
        web.get("/api/yonetim/ayarlar", y_ayarlar),
        web.post("/api/yonetim/ayarlar", y_ayarlar),
        web.get("/api/yonetim/ses", y_ses),
        web.post("/api/yonetim/ses", y_ses),
        web.post("/api/yonetim/zil", y_zil),
        web.get("/api/yonetim/ekran", y_ekran),
        web.post("/api/yonetim/ekran", y_ekran),
        web.get("/api/yonetim/guvenlik", y_guvenlik),
        web.post("/api/yonetim/guvenlik", y_guvenlik),
        web.get("/api/yonetim/sistem", y_sistem),
        web.post("/api/yonetim/sistem", y_sistem),
        web.post("/api/ekran", ekran_bildirim),
    ])
    app.on_startup.append(baslangic)
    app.on_cleanup.append(kapanis)
    return app


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    c = ayarlari_oku()
    web.run_app(uygulama(c), host="0.0.0.0", port=int(c["PORT"]), print=None, access_log=None, shutdown_timeout=2)
