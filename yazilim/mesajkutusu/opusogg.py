"""ffmpeg olmadan ses işleri (saf Python).

- webm_to_ogg: Tarayıcının MediaRecorder kaydını (WebM/Matroska içinde Opus) yeniden kodlamadan
  Telegram sesli notu biçimine (Ogg içinde Opus) taşır. Ses verisine dokunulmaz, yalnızca kap değişir.
- ogg_sure: Ogg/Opus dosyasının süresi (son sayfanın granül konumundan).
- melodi_wav: Hoparlör denemesi için kısa bir WAV melodisi.

Tablette (Android) ffmpeg yok; Pi'de ffmpeg varsa sunucu onu kullanmaya devam eder.
"""
import io
import math
import struct
import wave

# --------------------------------------------------------------------------- Ogg CRC (poli 0x04C11DB7, yansımasız)
_CRC = []
for _i in range(256):
    _r = _i << 24
    for _ in range(8):
        _r = ((_r << 1) ^ 0x04C11DB7) if _r & 0x80000000 else (_r << 1)
    _CRC.append(_r & 0xFFFFFFFF)


def _ogg_crc(veri):
    crc = 0
    for b in veri:
        crc = ((crc << 8) & 0xFFFFFFFF) ^ _CRC[((crc >> 24) & 0xFF) ^ b]
    return crc


class OpusHatasi(ValueError):
    pass


# --------------------------------------------------------------------------- EBML / Matroska okuma
_ICINE_GIR = {
    0x18538067,  # Segment
    0x1654AE6B,  # Tracks
    0xAE,        # TrackEntry
    0xE1,        # Audio
    0x1F43B675,  # Cluster
    0xA0,        # BlockGroup
}
_BILINMEYEN_BOY = -1


def _vint(veri, i, kimlik=False):
    """EBML değişken uzunluklu tamsayı. kimlik=True ise işaret biti korunur (Element ID)."""
    if i >= len(veri):
        raise IndexError
    ilk = veri[i]
    uzunluk = 1
    maske = 0x80
    while uzunluk <= 8 and not (ilk & maske):
        maske >>= 1
        uzunluk += 1
    if uzunluk > 8:
        raise OpusHatasi("bozuk EBML")
    if i + uzunluk > len(veri):
        raise IndexError
    deger = ilk if kimlik else (ilk & (maske - 1))
    hepsi_bir = deger == (maske - 1)
    for j in range(1, uzunluk):
        deger = (deger << 8) | veri[i + j]
        hepsi_bir = hepsi_bir and veri[i + j] == 0xFF
    if not kimlik and hepsi_bir:
        deger = _BILINMEYEN_BOY
    return deger, i + uzunluk


def _uint(b):
    return int.from_bytes(b, "big") if b else 0


def webm_opus_oku(veri):
    """WebM'den (opus_head, paketler, codec_delay_ns) çıkarır."""
    i, n = 0, len(veri)
    izler = {}            # iz no -> {"codec": .., "ozel": .., "gecikme": .., "kanal": ..}
    gecerli = None        # okunan TrackEntry
    paketler = []         # (iz_no, bayt)
    while i < n:
        try:
            kimlik, j = _vint(veri, i, kimlik=True)
            boy, j = _vint(veri, j)
        except IndexError:
            break         # kayıt yarıda kesilmiş olabilir: okunabilen kadarını kullan
        if kimlik in _ICINE_GIR:
            if kimlik == 0xAE:
                gecerli = {}
                izler.setdefault("_sira", []).append(gecerli)
            i = j
            continue
        if boy == _BILINMEYEN_BOY:
            raise OpusHatasi("boyutu bilinmeyen öğe: %x" % kimlik)
        son = min(j + boy, n)
        icerik = veri[j:son]
        if gecerli is not None:
            if kimlik == 0xD7:
                gecerli["no"] = _uint(icerik)
            elif kimlik == 0x86:
                gecerli["codec"] = icerik.decode("ascii", "ignore")
            elif kimlik == 0x63A2:
                gecerli["ozel"] = bytes(icerik)
            elif kimlik == 0x56AA:
                gecerli["gecikme"] = _uint(icerik)
            elif kimlik == 0x9F:
                gecerli["kanal"] = _uint(icerik)
        if kimlik in (0xA3, 0xA1):          # SimpleBlock / Block
            iz, k = _vint(icerik, 0)
            bayrak = icerik[k + 2]
            govde = bytes(icerik[k + 3:])
            lacing = (bayrak >> 1) & 0x03
            if lacing == 0:
                paketler.append((iz, govde))
            elif lacing == 2:                # sabit boy
                adet = govde[0] + 1
                parca = (len(govde) - 1) // adet
                for a in range(adet):
                    paketler.append((iz, govde[1 + a * parca:1 + (a + 1) * parca]))
            else:
                raise OpusHatasi("desteklenmeyen lacing")
        i = son
    opus_iz = next((t for t in izler.get("_sira", []) if t.get("codec") == "A_OPUS"), None)
    if not opus_iz:
        raise OpusHatasi("WebM içinde Opus ses izi yok")
    no = opus_iz.get("no", 1)
    secili = [p for t, p in paketler if t == no and p]
    if not secili:
        raise OpusHatasi("ses verisi yok")
    return opus_iz.get("ozel"), secili, opus_iz.get("gecikme", 0), opus_iz.get("kanal", 1)


# --------------------------------------------------------------------------- Opus paket süresi (48 kHz örnek)
def opus_ornek(paket):
    if not paket:
        return 0
    toc = paket[0]
    yapi = toc >> 3
    if yapi < 12:
        ms10 = (10, 20, 40, 60)[yapi % 4] * 10
    elif yapi < 16:
        ms10 = (10, 20)[yapi % 2] * 10
    else:
        ms10 = (25, 50, 100, 200)[yapi % 4]
    c = toc & 3
    if c == 0:
        cerceve = 1
    elif c in (1, 2):
        cerceve = 2
    else:
        cerceve = (paket[1] & 0x3F) if len(paket) > 1 else 1
    return cerceve * ms10 * 48 // 10      # ms10: 0,1 ms birimi -> 48 örnek/ms


# --------------------------------------------------------------------------- Ogg yazma
def _sayfa(seri, sira, granul, paketler_bolum, bayrak):
    """paketler_bolum: [(bayt, son_parca_mi)] tek sayfaya sığan bölümler."""
    segmentler = []
    govde = b""
    for parca, bitti in paketler_bolum:
        govde += parca
        kalan = len(parca)
        while kalan >= 255:
            segmentler.append(255)
            kalan -= 255
        if bitti:
            segmentler.append(kalan)
        elif kalan:
            raise OpusHatasi("iç hata: bölüm 255'in katı olmalı")
    baslik = struct.pack("<4sBBqIIIB", b"OggS", 0, bayrak, granul, seri, sira, 0, len(segmentler)) + bytes(segmentler)
    sayfa = bytearray(baslik + govde)
    struct.pack_into("<I", sayfa, 22, _ogg_crc(sayfa))
    return bytes(sayfa)


def ogg_opus_yaz(opus_head, paketler, seri=0x4B555455):
    cikti = io.BytesIO()
    cikti.write(_sayfa(seri, 0, 0, [(opus_head, True)], 0x02))
    etiket = b"OpusTags" + struct.pack("<I", 11) + b"mesajkutusu" + struct.pack("<I", 0)
    cikti.write(_sayfa(seri, 1, 0, [(etiket, True)], 0x00))
    sira, granul = 2, 0
    on_atlama = struct.unpack_from("<H", opus_head, 10)[0]
    bekleyen, seg_sayisi, onceki_granul = [], 0, 0
    for idx, p in enumerate(paketler):
        granul += opus_ornek(p)
        gerek = len(p) // 255 + 1
        if seg_sayisi + gerek > 255 or len(bekleyen) >= 50:
            cikti.write(_sayfa(seri, sira, onceki_granul, bekleyen, 0x00))
            sira += 1
            bekleyen, seg_sayisi = [], 0
        bekleyen.append((p, True))
        seg_sayisi += gerek
        onceki_granul = granul
    if bekleyen:
        cikti.write(_sayfa(seri, sira, granul, bekleyen, 0x04))
    sure = max(0.0, (granul - on_atlama) / 48000)
    return cikti.getvalue(), sure


def _opus_head(kanal=1, on_atlama=312, hiz=48000):
    return b"OpusHead" + struct.pack("<BBHIhB", 1, kanal, on_atlama, hiz, 0, 0)


def webm_to_ogg(veri):
    """WebM/Opus baytları -> (Ogg/Opus baytları, süre saniye)."""
    ozel, paketler, gecikme_ns, kanal = webm_opus_oku(memoryview(veri).tobytes())
    if ozel and ozel.startswith(b"OpusHead") and len(ozel) >= 19:
        head = ozel
    else:
        head = _opus_head(kanal or 1, round(gecikme_ns * 48000 / 1e9) if gecikme_ns else 312)
    return ogg_opus_yaz(head, paketler)


def ogg_sure(veri):
    """Ogg/Opus süresi (saniye); bulunamazsa 0."""
    on_atlama = 0
    h = veri.find(b"OpusHead")
    if h >= 0 and len(veri) >= h + 12:
        on_atlama = struct.unpack_from("<H", veri, h + 10)[0]
    son = veri.rfind(b"OggS")
    while son >= 0:
        if len(veri) >= son + 14:
            granul = struct.unpack_from("<q", veri, son + 6)[0]
            if granul > 0:
                return round(max(0.0, (granul - on_atlama) / 48000), 1)
        son = veri.rfind(b"OggS", 0, son)
    return 0.0


def melodi_wav(saniye=3, hiz=24000):
    """Do-Mi-Sol, yumuşak başlangıç/bitişli kısa bir WAV (hoparlör denemesi)."""
    notalar = (523.25, 659.25, 783.99)
    parca = int(hiz * saniye / len(notalar))
    ornekler = bytearray()
    for f in notalar:
        for k in range(parca):
            zarf = min(1.0, k / 400, (parca - k) / 1200)
            v = 0.35 * zarf * (math.sin(2 * math.pi * f * k / hiz) + 0.25 * math.sin(4 * math.pi * f * k / hiz))
            ornekler += struct.pack("<h", int(max(-1, min(1, v)) * 32000))
    b = io.BytesIO()
    with wave.open(b, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(hiz)
        w.writeframes(bytes(ornekler))
    return b.getvalue()
