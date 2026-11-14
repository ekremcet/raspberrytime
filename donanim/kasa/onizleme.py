import numpy as np, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.path import Path
from matplotlib.patches import PathPatch, Patch
from kasa import *

def patch(ax, cs, fc, ec="#2b2b2b", lw=0.5, alpha=1, z=1):
    polys = cs.to_polygons()
    verts, codes = [], []
    for p in polys:
        p = np.asarray(p)
        if len(p) < 3: continue
        verts += list(p) + [p[0]]
        codes += [Path.MOVETO] + [Path.LINETO]*(len(p)-1) + [Path.CLOSEPOLY]
    if verts:
        ax.add_patch(PathPatch(Path(verts, codes), fc=fc, ec=ec, lw=lw, alpha=alpha, zorder=z))

fr, sh, st = on_cerceve(), arka_kapak(), stant()
d = dummies()
COL = dict(fr="#F2EEE6", sh="#C9D3DF", st="#8FA3B8", ekran="#1E2430", kamera="#2E9E5B", hoparlor="#E08A00", pi="#B23B3B")

fig = plt.figure(figsize=(15, 6.4), dpi=130)
gs = fig.add_gridspec(1, 3, width_ratios=[1.05, 1.05, 1.0], wspace=0.18)

# 1) ön görünüm
ax = fig.add_subplot(gs[0])
patch(ax, box(DW-2*OVERLAP+2, DH-2*OVERLAP+2, 1, PCX, PCY, 0).project(), "#1E2430", z=0)
patch(ax, fr.project(), COL["fr"])
ax.text(PCX, PCY, "7\" dokunmatik ekran", color="white", ha="center", va="center", fontsize=11)
ax.annotate("kamera", (0, CAM_LENS_Y), (-60, H/2+12), fontsize=9, arrowprops=dict(arrowstyle="->", lw=.7))
ax.annotate("mikrofon", (MIC_HOLES_X, MIC_Y), (55, H/2+12), fontsize=9, arrowprops=dict(arrowstyle="->", lw=.7))
ax.annotate("USB hoparlör ızgarası", (30, SPK_Y), (35, -H/2-16), fontsize=9, arrowprops=dict(arrowstyle="->", lw=.7))
ax.set_title(f"Önden  ({W:.0f} × {H:.0f} mm)", fontsize=12)
ax.set_xlim(-W/2-8, W/2+8); ax.set_ylim(-H/2-26, H/2+24); ax.set_aspect("equal"); ax.axis("off")

# 2) yan kesit (stantla birlikte, X=0 düzlemi)
ax = fig.add_subplot(gs[1])
P = np.array([[0,1,0,0],[0,0,1,0],[1,0,0,0]], float)
def side(man, col, z=1):
    patch(ax, man.transform(P).slice(0.3), col, z=z)
side(stand_world(st), COL["st"])
side(world_xform(sh), COL["sh"])
side(world_xform(fr), COL["fr"])
side(world_xform(d["ekran"]), COL["ekran"], 2)
side(world_xform(d["kamera"]), COL["kamera"], 2)
side(world_xform(d["hoparlor"]), COL["hoparlor"], 2)
side(world_xform(d["pi_yigini"]), COL["pi"], 0)
ax.axhline(0, color="#666", lw=1)
ax.text(-75, -6, "masa", fontsize=9, color="#555")
ax.set_title("Yandan kesit (stant üzerinde, 18° eğim)", fontsize=12)
ax.set_xlim(-80, 105); ax.set_ylim(-12, 212); ax.set_aspect("equal"); ax.axis("off")

# 3) arkadan görünüm
ax = fig.add_subplot(gs[2])
patch(ax, sh.mirror((1,0,0)).project(), COL["sh"])
# stant izdüşümü (arka yüz düzleminde, yaklaşık)
ax.add_patch(plt.Rectangle((-CW/2, -H/2), CW, SUP_L, fc=COL["st"], ec="#2b2b2b", lw=.5, alpha=.55, zorder=2))
ax.text(0, -H/2+40, "stant", ha="center", fontsize=9, zorder=3)
ax.annotate("güç kablosu", (-W/2, -70), (-W/2-4, -H/2-16), fontsize=9, ha="left", arrowprops=dict(arrowstyle="->", lw=.7))
ax.set_title("Arkadan (havalandırma)", fontsize=12)
ax.set_xlim(-W/2-8, W/2+8); ax.set_ylim(-H/2-26, H/2+24); ax.set_aspect("equal"); ax.axis("off")

fig.legend(handles=[Patch(fc=COL["fr"], ec="#333", label="Ön çerçeve"), Patch(fc=COL["sh"], ec="#333", label="Arka kapak"),
                    Patch(fc=COL["st"], ec="#333", label="Stant"), Patch(fc=COL["ekran"], label="Ekran"),
                    Patch(fc=COL["kamera"], label="Camera Module 3"), Patch(fc=COL["hoparlor"], label="Hoparlör"),
                    Patch(fc=COL["pi"], label="Pi 5 + aktif soğutucu (tahmini)")],
           loc="lower center", ncol=7, fontsize=9, frameon=False, bbox_to_anchor=(0.5, -0.02))
import os; plt.savefig(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "gorseller", "kasa_onizleme.png"), bbox_inches="tight")
print("ok")
