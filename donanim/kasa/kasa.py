"""
Sesli Mesaj Hub - 3D baskı kasa (parametrik)

Parçalar (baskı yönünde STL):
  on_cerceve.stl  Ön çerçeve: ekran yuvası, kamera penceresi, USB hoparlör yuvası + ızgara,
                  BOYA BY-M100UA mikrofon yatağı ve ön yüzde mikrofon delikleri (kapalı ses odası)
  arka_kapak.stl  Arka kapak: Pi 5 + AI HAT+ 2 için 44 mm derinlik, havalandırma, kablo çıkışı
  stant.stl       Masa standı v2 (18° geriye eğim), tek parça dolu profil -> ipliklenmez

Koordinatlar (cihaz): x = genişlik, y = yukarı, z = ön yüzden arkaya (ön yüz z=0)

Ölçü kaynakları:
  Touch Display 2 (7"): 189.32 x 120.24 mm, ~14.92 mm kalınlık, aktif alan 155 x 88
  Camera Module 3 (resmi çizim): 25 x 23.862 mm kart, Ø2.2 delikler kenarlardan 2.0 mm (21 x 12.5),
  lens merkezi yatayda ortada, üst kenardan 14.4 mm (alt vida çiftiyle aynı hizada); lens modülü 10.8 x 10.8 mm, FOV 66° x 41°
  USB hoparlör (Robotistan / Adafruit 3369 tipi): 84 x 43 x 32 mm; sürücülerin 84x43 yüzde olduğu varsayıldı
  BOYA BY-M100UA USB mikrofon: Ø18 x 75 mm (USB-A fiş dahil), kapsül uçta, çok yönlü
"""
import math
import numpy as np
import manifold3d as m3
import trimesh

SEG = 72

# ---------------- ölçüler ----------------
DW, DH, DT = 189.32, 120.24, 14.92     # ekran
CLR = 0.3
PW, PH = DW + 2 * CLR, DH + 2 * CLR    # ekran yuvası
SIDE, TOP, CHIN = 10.0, 30.0, 52.0     # çerçeve bantları
W = PW + 2 * SIDE
H = PH + TOP + CHIN
R_OUT = 16.0
WALL = 2.4
LIP = 2.0                              # ön dudak kalınlığı
OVERLAP = 4.0                          # dudağın camın üstüne bindiği pay
Z_RIM = 19.0                           # çerçeve-kapak birleşim düzlemi
SHELL_D = 44.0                         # arka kapak derinliği
Z_BACK = Z_RIM + SHELL_D               # arka yüz
BACK_T = 2.4

PY0 = -H / 2 + CHIN                    # ekran yuvası alt kenarı
PY1 = PY0 + PH                         # üst kenar
PCX, PCY = 0.0, (PY0 + PY1) / 2        # yuva merkezi
# Not: DW/DH/PW/PH/PY1/PCY kasanın dış ölçüsünü ve arka kapağı belirler (v4 ile aynı kalır).

# ---- v5: kullanılan ekran = ilk Raspberry Pi 7" Touch Display (800x480)
# resmi: assembly module 192.96 x 110.76 mm, aktif alan 154.08 x 85.92 mm, 20 mm (standoff'lar dahil)
EW, EH = 192.96, 110.76
E_CLR = 0.5                            # PLA çekmesi için yanlarda daha fazla pay
EPW, EPH = EW + 2 * E_CLR, EH + 2 * E_CLR
EPY0 = PY0                             # yuva alt kenarı v4 ile aynı (hoparlör yuvasının hemen üstü)
EPY1 = EPY0 + EPH
EPCY = (EPY0 + EPY1) / 2
E_WALL_TOP = 17.0                      # yuva duvarı üst kotu (arka kapağın dayama kolonlarına çarpmasın)

# kamera
CAM_W, CAM_H = 25.0, 23.862          # CM3 resmi çizim (RP-008153-DS-1)
CAM_TOP = H / 2 - WALL - 0.8           # kart üst kenarı
CAM_LENS_Y = CAM_TOP - 14.4           # v6: lens merkezi ÜST kenardan 14.4 (alt vida sırasıyla aynı hizada; baskıda doğrulandı)
CAM_HOLES = [(sx * 10.5, CAM_TOP - dy) for sx in (-1, 1) for dy in (2.0, 14.5)]
CAM_STANDOFF = 11.0                    # dudak arkasından kart ön yüzüne
CAM_WIN_D = 13.0

# mikrofon (BOYA BY-M100UA): üst bantta yatay, ucu sağa bakar; uç kapalı bir ses odasında,
# oda öndeki 7 deliğe açılır. USB uzatmanın dişi ucu kameranın arkasından sola geçer.
MIC_R, MIC_L, MIC_PLUG_L = 9.0, 75.0, 12.0   # fiş boyu tahmini
MIC_Y, MIC_Z = 85.0, 24.8                     # eksen (ön yüzü kamera kartının arkasında)
MIC_TIP = 86.0                                # kapsül ucu (x)
MIC_END = MIC_TIP - MIC_L                     # fişin ucu (x)
CH_X0, CH_X1 = 78.0, 88.0                     # ses odası iç sınırları (x)
MIC_HOLES_X = 83.0
EXT_L, EXT_W, EXT_T = 40.0, 16.0, 8.5         # USB uzatma dişi ucu (tahmini)
# v7: mikrofon SÜNGERİYLE (resmi Ø18) arkadan geçmeli bir kaba oturur.
# Kap ~250° sarar; sünger ağızdan sıkışarak geçer, içeride açılır. Ucu sağdaki kapalı duvara dayanır.
CUP_X0 = 66.0                                 # kabın sol ağzı (x); lastik halka (~uçtan 26 mm) kabın dışında kalır
CUP_BORE = 17.6                               # iç çap (Ø18 süngeri hafif sıkar)
CUP_T = 2.0                                   # kap et kalınlığı
CUP_OPEN = 15.0                               # arkadaki ağız genişliği (süngersiz kafa ~Ø14-15 rahat geçer)

# hoparlör
SPK_W, SPK_H, SPK_D = 84.0, 43.0, 32.0
SPK_Y = (-H / 2 + WALL + PY0 - 2) / 2
SPK_CLR = 0.3                                 # v7: hap biçimli yuva, kenar boşluğu
SPK_WALL_TOP = LIP + 12.0                     # yuva duvarı üst kotu (arka kapak eteğine değmez)

# vidalar
SCREWS = [(sx * 94.0, sy * 82.0) for sx in (-1, 1) for sy in (-1, 1)]
STAND_SCREWS = [(-40.0, -70.0), (40.0, -70.0)]

THETA = math.radians(18)


def cyl(h, r, z0=0.0, r2=None, x=0.0, y=0.0):
    return m3.Manifold.cylinder(h, r, r if r2 is None else r2, SEG).translate((x, y, z0))


def ycyl(y0, y1, r, x=0.0, z=0.0):
    """y ekseni boyunca silindir"""
    return m3.Manifold.cylinder(y1 - y0, r, r, SEG).rotate((-90, 0, 0)).translate((x, y0, z))


def xcyl(x0, x1, r, y=0.0, z=0.0):
    """x ekseni boyunca silindir"""
    return m3.Manifold.cylinder(x1 - x0, r, r, SEG).rotate((0, 90, 0)).translate((x0, y, z))


def box(sx, sy, sz, cx=0.0, cy=0.0, z0=0.0):
    return m3.Manifold.cube((sx, sy, sz), True).translate((cx, cy, z0 + sz / 2))


def rrect(w, h, r, z0, z1, cx=0.0, cy=0.0):
    r = max(0.2, min(r, w / 2 - 0.01, h / 2 - 0.01))
    pts = [cyl(z1 - z0, r, z0, x=cx + sx * (w / 2 - r), y=cy + sy * (h / 2 - r)) for sx in (-1, 1) for sy in (-1, 1)]
    return m3.Manifold.batch_hull(pts)


def U(parts):
    return m3.Manifold.batch_boolean([p for p in parts if p is not None], m3.OpType.Add)


# =====================================================================
def on_cerceve():
    # dış gövde, ön kenarı 1.2 mm pahlı
    body = m3.Manifold.batch_hull([rrect(W - 2.4, H - 2.4, R_OUT - 1.2, 0, 0.01), rrect(W, H, R_OUT, 1.2, Z_RIM)])
    body = body - rrect(W - 2 * WALL, H - 2 * WALL, R_OUT - WALL, LIP, Z_RIM + 1)

    # ekran penceresi (ön kenarı pahlı)
    ww, wh = EPW - 2 * OVERLAP, EPH - 2 * OVERLAP
    win = rrect(ww, wh, 3.0, -1, LIP + 1, PCX, EPCY)
    win_ch = m3.Manifold.batch_hull([rrect(ww + 2.4, wh + 2.4, 4.2, -0.01, 0, PCX, EPCY), rrect(ww, wh, 3.0, 1.2, 1.21, PCX, EPCY)])
    body = body - win - win_ch

    # ekran yuvası duvarları
    pocket = rrect(EPW + 4, EPH + 4, 3, LIP, E_WALL_TOP, PCX, EPCY) - rrect(EPW, EPH, 1, LIP - 0.01, E_WALL_TOP + 1, PCX, EPCY)
    # kamera kablosu için üst duvarda çentik
    pocket = pocket - box(22, 6, 12, 0, EPY1 + 1, 8)
    # ekran tellerinin / FPC'nin geçmesi için alt duvarda da çentik (orta)
    pocket = pocket - box(40, 6, 12, 0, EPY0 - 1, 8)
    body = body + pocket

    # kamera: 4 M2 çıkıntı + lens penceresi (dışa doğru genişleyen)
    for (x, y) in CAM_HOLES:
        body = body + cyl(CAM_STANDOFF, 2.2, LIP, x=x, y=y)
        body = body - cyl(8.5, 0.9, LIP + CAM_STANDOFF - 8.5 + 0.01, x=x, y=y)
    body = body - cyl(LIP + 2, CAM_WIN_D / 2, -1, x=0, y=CAM_LENS_Y)
    body = body - cyl(LIP + 0.01, 9.0, -0.005, CAM_WIN_D / 2, x=0, y=CAM_LENS_Y)

    # hoparlör yuvası (v7: hap biçimi, ezilme kaburgalı) + ızgara
    sw, sh = SPK_W + 2 * SPK_CLR, SPK_H + 2 * SPK_CLR
    cradle = rrect(sw + 3.2, sh + 3.2, sh / 2 + 1.6, LIP, SPK_WALL_TOP, 0, SPK_Y) - \
        rrect(sw, sh, sh / 2, LIP - 0.01, SPK_WALL_TOP + 1, 0, SPK_Y)
    ribs = []
    rib_z0 = LIP - 0.01                       # lipten başlar: sarkma yok
    rib_h = SPK_WALL_TOP - 1.0 - rib_z0          # üstte 1 mm giriş payı
    for x in (-18.0, 0.0, 18.0):
        for sy in (-1, 1):
            ribs.append(cyl(rib_h, 0.6, rib_z0, x=x, y=SPK_Y + sy * (sh / 2 + 0.1)))
    for sx in (-1, 1):
        ribs.append(cyl(rib_h, 0.6, rib_z0, x=sx * (sw / 2 + 0.1), y=SPK_Y))
    body = body + cradle + U(ribs)
    holes = []
    pitch = 3.6
    rr = sh / 2 - 3.5                              # ızgara hap içinde kalsın
    for j in range(-6, 7):
        for i in range(-12, 13):
            x = i * pitch + (pitch / 2 if j % 2 else 0)
            y = j * pitch * 0.866
            cx = max(-(sw / 2 - sh / 2), min(sw / 2 - sh / 2, x))
            if math.hypot(x - cx, y) <= rr:
                holes.append(cyl(LIP + 2, 1.1, -1, x=x, y=SPK_Y + y))
    body = body - U(holes)

    # ---- mikrofon (v7): süngerli kafayı saran, arkadan geçmeli kap ----
    rb = CUP_BORE / 2
    ro = rb + CUP_T
    x1 = CH_X1 + 1.2                                    # kapalı sağ duvarın dışı
    cup = box(x1 - CUP_X0, 2 * ro, MIC_Z - LIP, (CUP_X0 + x1) / 2, MIC_Y, LIP) + xcyl(CUP_X0, x1, ro, MIC_Y, MIC_Z)
    cup = cup - xcyl(CUP_X0 - 1, CH_X1, rb, MIC_Y, MIC_Z)             # kafa yatağı (sol ucu açık)
    cup = cup - box(x1 - CUP_X0 + 2, CUP_OPEN, 20, (CUP_X0 + x1) / 2, MIC_Y, MIC_Z)   # arka ağız
    # giriş pahı: ağız kenarları 45° açılır, sünger kolay girer
    cup = cup - m3.Manifold.batch_hull([box(x1 - CUP_X0 + 2, CUP_OPEN, 0.01, (CUP_X0 + x1) / 2, MIC_Y, MIC_Z + rb * 0.55),
                                        box(x1 - CUP_X0 + 2, CUP_OPEN + 6, 0.01, (CUP_X0 + x1) / 2, MIC_Y, MIC_Z + ro + 1)])
    # ses kanalı: ön deliklerden kafaya
    cup = cup - box(CH_X1 - 66.5, 10.0, MIC_Z - LIP + 0.01, (66.5 + CH_X1) / 2, MIC_Y, LIP - 0.01)
    body = body + cup
    for i, x in enumerate([68.0, 71.5, 75.0, 78.5, 82.0, 85.5]):
        for dy in ((-2.6, 2.6) if i % 2 else (-3.9, 0.0, 3.9)):
            body = body - cyl(LIP + 2, 0.8, -1, x=x - 0.5, y=MIC_Y + dy)

    # arka kapak vida çıkıntıları (M3 vida plastiğe kendi diş açar: Ø2.6 pilot)
    for (x, y) in SCREWS:
        body = body + cyl(Z_RIM - LIP, 4.0, LIP, x=x, y=y)
        body = body - cyl(Z_RIM - 4 + 0.01, 1.3, 4, x=x, y=y)
    return body


# =====================================================================
def arka_kapak():
    outer = m3.Manifold.batch_hull([rrect(W, H, R_OUT, Z_RIM, Z_BACK - 1.2), rrect(W - 2.4, H - 2.4, R_OUT - 1.2, Z_BACK - 0.01, Z_BACK)])
    shell = outer - rrect(W - 2 * WALL, H - 2 * WALL, R_OUT - WALL, Z_RIM - 1, Z_BACK - BACK_T)

    # hizalama eteği: çerçevenin içine 3 mm girer
    sk_o = (W - 2 * WALL - 0.4, H - 2 * WALL - 0.4, R_OUT - WALL - 0.2)
    sk_i = (sk_o[0] - 2.4, sk_o[1] - 2.4, sk_o[2] - 1.2)
    skirt = rrect(*sk_o, Z_RIM - 3, Z_RIM + 0.5) - rrect(*sk_i, Z_RIM - 4, Z_RIM + 1)
    # kamera çıkıntıları ve mikrofon kanalının hizasında etek boşluğu gerekmez (z farklı); yine de kamera bölgesini aç
    shell = shell + skirt

    # vida kolonları + havşa
    for (x, y) in SCREWS:
        shell = shell + cyl(Z_BACK - BACK_T - Z_RIM + 0.01, 4.0, Z_RIM, x=x, y=y)
        shell = shell - cyl(Z_BACK - Z_RIM + 2, 1.7, Z_RIM - 1, x=x, y=y)
        shell = shell - cyl(Z_BACK - (Z_RIM + 8) + 1, 3.3, Z_RIM + 8, x=x, y=y)

    # ekranı yerinde tutan dayama kolonları (uçlarına 1-2 mm köpük bant)
    z_disp_back = LIP + DT
    for (x, y) in [(sx * 86.7, PY1 - 8) for sx in (-1, 1)] + [(sx * 86.7, PY0 + 8) for sx in (-1, 1)]:
        shell = shell + cyl(Z_BACK - BACK_T - (z_disp_back + 0.5) + 0.01, 4.0, z_disp_back + 0.5, x=x, y=y)
    # hoparlörü bastıran kolon
    z_spk_back = LIP + SPK_D
    shell = shell + cyl(Z_BACK - BACK_T - (z_spk_back + 0.4) + 0.01, 6.0, z_spk_back + 0.4, x=0, y=SPK_Y)

    # stant vida çıkıntıları (içeride), pilot arkadan açık
    for (x, y) in STAND_SCREWS:
        shell = shell + cyl(8.0 + 0.01, 4.5, Z_BACK - BACK_T - 8.0, x=x, y=y)
        shell = shell - cyl(10.0 + 0.01, 1.3, Z_BACK - 10.0, x=x, y=y)

    # arka havalandırma (üst bölge, iki sütun)
    vents = []
    for k in range(11):
        y = 14 + k * 7
        for cx in (-42, 42):
            vents.append(rrect(60, 3.4, 1.7, Z_BACK - BACK_T - 1, Z_BACK + 1, cx, y))
    # üst duvar havalandırması
    for k in range(-7, 8):
        vents.append(rrect(3.2, WALL * 3, 1.0, Z_RIM + 8, Z_RIM + 34, k * 8.0, H / 2 - WALL / 2))
    # yan duvarlarda alt hava girişleri
    for k in range(5):
        y = -50 + k * 7
        for sx in (-1, 1):
            vents.append(box(WALL * 3, 3.2, 22, sx * (W / 2 - WALL / 2), y, Z_RIM + 9))
    shell = shell - U(vents)

    # güç kablosu çıkışı (sağ yan duvar)
    cable = rrect(14, 9, 3, -6, 6).rotate((0, 90, 0)).translate((W / 2 - WALL / 2, -70, Z_RIM + 22))
    shell = shell - cable
    return shell


# =====================================================================
# Stant: profil (a = arkaya, b = yukarı) X boyunca kalıplanır
S, C = math.sin(THETA), math.cos(THETA)
BASE_T = 6.0
B_PT = (0.0, BASE_T)                                      # cihazın arka-alt kenarı
F_PT = (-Z_BACK * C, BASE_T + Z_BACK * S)                 # cihazın ön-alt kenarı
SUP_L = 80.0
T_PT = (SUP_L * S, BASE_T + SUP_L * C)
TW = 5.0
T2_PT = (T_PT[0] + TW * C, T_PT[1] - TW * S)
LIP_TOP = (F_PT[0] + 5 * S, F_PT[1] + 5 * C)
LIP_FR = (LIP_TOP[0] - 4 * C, LIP_TOP[1] + 4 * S)
A_FRONT, A_BACK = F_PT[0] - 8, 55.0
CW = 140.0


def dev2world(p):
    """cihaz (y,z) -> dünya (a,b)"""
    y, z = p
    a0 = (-H / 2) * S + Z_BACK * C
    b0 = (-H / 2) * C - Z_BACK * S
    return (y * S + z * C - a0, y * C - z * S - b0 + BASE_T)


def poly_extrude(pts, x0, x1):
    cs = m3.CrossSection([pts], m3.FillRule.Positive)
    if cs.area() < 0:
        cs = m3.CrossSection([pts[::-1]], m3.FillRule.Positive)
    return m3.Manifold.extrude(cs, x1 - x0).translate((0, 0, x0))


def ccw(pts):
    a = 0
    for i in range(len(pts)):
        x1, y1 = pts[i]; x2, y2 = pts[(i + 1) % len(pts)]
        a += x1 * y2 - x2 * y1
    return pts if a > 0 else pts[::-1]


def stant():
    """v2: tek parça dolu profil, tüm genişlik boyunca. Baskıda her katman tek ada -> ipliklenme olmaz.
    İçinde profil boyunca açık bir hafifletme penceresi var (katmanda delik, ada değil)."""
    full = ccw([(A_FRONT, 0), (A_BACK, 0), (A_BACK, 10), T2_PT, T_PT, B_PT, F_PT, LIP_TOP, LIP_FR])
    cs = m3.CrossSection([full], m3.FillRule.Positive)
    # dış köşeleri yuvarlat (iç köşe = cihazın oturduğu köşe keskin kalır)
    cs = cs.offset(-2.0, m3.JoinType.Round).offset(2.0, m3.JoinType.Round)
    # hafifletme penceresi: cihaz yüzeylerinden 7 mm, tabandan 6 mm içeride
    inner = m3.CrossSection([full], m3.FillRule.Positive).offset(-7.0, m3.JoinType.Round)
    inner = inner - m3.CrossSection.square((400, 6.0)).translate((-200, 0))   # taban kalın kalsın
    inner = inner.offset(-0.01, m3.JoinType.Round).offset(0.01, m3.JoinType.Round)
    if inner.area() > 200:
        cs = cs - inner.offset(-3.0, m3.JoinType.Round).offset(3.0, m3.JoinType.Round)
    st = m3.Manifold.extrude(cs, CW).translate((0, 0, -CW / 2))
    # kenar pahı: uç yüzlerde 1 mm (fil ayağı ve keskin kenar olmasın)
    # cihaza bağlantı delikleri (cihazın z ekseni doğrultusunda), vida başı arkadan girer
    for (x, y) in STAND_SCREWS:
        a, b = dev2world((y, Z_BACK))
        h = m3.Manifold.cylinder(30, 1.7, 1.7, SEG).rotate((0, 90, 0))
        h = h.translate((-15, 0, 0)).rotate((0, 0, -math.degrees(THETA))).translate((a, b, x))
        st = st - h
        hd = m3.Manifold.cylinder(80, 3.4, 3.4, SEG).rotate((0, 90, 0))
        hd = hd.rotate((0, 0, -math.degrees(THETA)))
        off = TW + 0.01
        st = st - hd.translate((a + off * C, b - off * S, x))
    return st


# ---------------- montaj için dummy parçalar ----------------
def dummies():
    d = {}
    d["ekran"] = box(EW, EH, 12.0, PCX, EPCY, LIP)   # kalınlık tahmini (cam + LCD + metal çerçeve)
    cam = box(CAM_W, CAM_H, 1.0, 0, CAM_TOP - CAM_H / 2, LIP + CAM_STANDOFF) + \
        box(10.8, 10.8, CAM_STANDOFF - 0.5, 0, CAM_LENS_Y, LIP + 0.5)
    # M2 vida başları kartın arkasında (Ø4 x 1.6 mm)
    cam = cam + U([cyl(1.6, 2.0, LIP + CAM_STANDOFF + 1.0, x=x, y=y) for (x, y) in CAM_HOLES])
    d["kamera"] = cam
    d["hoparlor"] = rrect(SPK_W, SPK_H, SPK_H / 2, LIP, LIP + SPK_D, 0, SPK_Y)
    d["mikrofon"] = xcyl(MIC_END, MIC_TIP, MIC_R, MIC_Y, MIC_Z)
    d["usb_uzatma"] = box(EXT_L, EXT_W, EXT_T, MIC_END - EXT_L / 2, MIC_Y, MIC_Z - EXT_T / 2)
    d["pi_yigini"] = box(85, 56, 36, 0, PCY, LIP + DT)    # Pi 5 + soğutucu + AI HAT+ 2 (tahmini)
    return d


def world_xform(man):
    """cihaz (x,y,z) -> dünya (X, a, b) ; stant sistemiyle aynı"""
    a0 = (-H / 2) * S + Z_BACK * C
    b0 = (-H / 2) * C - Z_BACK * S
    M = np.array([[1, 0, 0, 0],
                  [0, S, C, -a0],
                  [0, C, -S, -b0 + BASE_T]], dtype=float)
    return man.transform(M)


def stand_world(st):
    # stant (a, b, X) -> (X, a, b)
    M = np.array([[0, 0, 1, 0], [1, 0, 0, 0], [0, 1, 0, 0]], dtype=float)
    return st.transform(M)


def to_tm(man):
    mesh = man.to_mesh()
    return trimesh.Trimesh(np.asarray(mesh.vert_properties)[:, :3], np.asarray(mesh.tri_verts), process=True)


def on_bed(man):
    bb = man.bounding_box()
    return man.translate((-(bb[0] + bb[3]) / 2, -(bb[1] + bb[4]) / 2, -bb[2]))


def deneme_parcasi(fr):
    """Ön çerçeveden 3 küçük test parçası: kamera penceresi, mikrofon kabı, hoparlör yuvası."""
    mic = fr ^ box(92 - 62, 98.5 - 72, 60, 77, (72 + 98.5) / 2, -1)
    sy0, sy1 = -98.75, SPK_Y + 25
    spk = fr ^ box(94, sy1 - sy0, 60, 0, (sy0 + sy1) / 2, -1)
    cam = fr ^ box(30, 30, 60, 0, CAM_TOP - 12, -1)
    return [on_bed(mic).translate((22, 32, 0)), on_bed(spk).translate((0, -14, 0)), on_bed(cam).translate((-25, 32, 0))]


if __name__ == "__main__":
    import os, json
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "stl")
    os.makedirs(out, exist_ok=True)
    fr, sh, st = on_cerceve(), arka_kapak(), stant()
    parts = {
        "on_cerceve": on_bed(fr),                              # ön yüz tablada
        "arka_kapak": on_bed(sh.mirror((0, 0, 1))),            # arka yüz tablada
        "stant": on_bed(st),                                   # yan profil yüzü tablada
    }
    info = {}
    for n, m in parts.items():
        t = to_tm(m)
        t.export(os.path.join(out, n + ".stl"))
        info[n] = dict(watertight=bool(t.is_watertight), olcu_mm=[round(float(v), 1) for v in t.extents],
                       hacim_cm3=round(float(t.volume) / 1000, 1))
    t = trimesh.util.concatenate([to_tm(p) for p in deneme_parcasi(fr)])
    t.export(os.path.join(out, "deneme_parcasi.stl"))
    info["deneme_parcasi"] = dict(olcu_mm=[round(float(v), 1) for v in t.extents], hacim_cm3=round(float(t.volume) / 1000, 1))
    info["cihaz_olcu"] = [round(W, 1), round(H, 1), Z_BACK]
    print(json.dumps(info, indent=1))
