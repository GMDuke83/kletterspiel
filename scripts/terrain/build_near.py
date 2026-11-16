"""
Hochaufgeloester Nahbereich um die Kletterwand (nach build_terrain.py ausfuehren):

    python -I scripts/terrain/build_near.py

Eingabe:  assets-src/terrain/raw/alti_05/<E>-<N>.tif   (swissALTI3D 0,5 m)
          assets-src/terrain/raw/image_010/<E>-<N>.tif (SWISSIMAGE 10 cm)
          src/routes/dufourspitze.json                 (Wandstandort aus build_terrain.py)
Ausgabe:  public/assets/dufourspitze_near.glb   Netz 1,2 m, Luftbild 3600 px (entschattet)
          assets-src/walls/dufour_wall_depth.npy + .json   Felsoberflaeche im Wand-Koordinatensystem
                                                            (fuer make_wall.py --dufour)
          src/routes/dufourspitze.json  (ergaenzt: near, wallFrame, rockColor)

Wand-Koordinaten: x = entlang der Wand (rechts), z = hoch (ab Wandfuss), d = in den Berg hinein.
Geodaten (c) swisstopo.
"""
import io
import json
import math
import os

import numpy as np
from PIL import Image, ImageFilter

import build_terrain as bt

Image.MAX_IMAGE_PIXELS = None
ROOT = bt.ROOT
RAW = bt.RAW
NEAR_GLB = os.path.join(ROOT, "public", "assets", "dufourspitze_near.glb")
NEAR_LOW_GLB = os.path.join(ROOT, "public", "assets", "dufourspitze_near_low.glb")
DEPTH_NPY = os.path.join(ROOT, "assets-src", "walls", "dufour_wall_depth.npy")
DEPTH_META = os.path.join(ROOT, "assets-src", "walls", "dufour_wall_depth.json")

STEP = 1.2            # Netz-Abstand im Nahbereich (m)
STEP_LOW = 3.6        # Variante fuer Qualitaet "niedrig"
IMG_PX = 0.1          # SWISSIMAGE 10 cm
WALL_W, WALL_H = 8.0, 13.0
WALL_STEP = 0.05      # Raster der Wand-Tiefenkarte (m)
HOLE_MARGIN = 0.7     # so weit innerhalb des Wandrands wird das Gelaende ausgeschnitten


def blur(a, r=2, passes=3):
    """Weichzeichnen fuer Float-Arrays (wiederholter Kastenfilter ~ Gauss), Raender gespiegelt."""
    a = a.astype(np.float32)
    k = 2 * r + 1
    for _ in range(passes):
        for ax in (0, 1):
            p = np.pad(a, [(r, r) if i == ax else (0, 0) for i in range(2)], mode="edge")
            c = np.cumsum(p, axis=ax, dtype=np.float64)
            c = np.concatenate([np.zeros_like(np.take(c, [0], axis=ax)), c], axis=ax)
            a = ((np.take(c, range(k, c.shape[ax]), axis=ax) - np.take(c, range(0, c.shape[ax] - k), axis=ax)) / k).astype(np.float32)
    return a


def load_tile(kind, e, n):
    return Image.open(os.path.join(RAW, kind, f"{e}-{n}.tif"))


def deshadow(img):
    """Blaue Schlagschatten im Luftbild aufhellen (Schnee im Schatten ist blaeulich und dunkel)."""
    a = img.astype(np.float32)
    r, g, b = a[..., 0] + 1, a[..., 1], a[..., 2]
    lum = 0.3 * r + 0.59 * g + 0.11 * b
    blue = b / r
    m = np.clip((blue - 1.03) / 0.12, 0, 1) * np.clip((232 - lum) / 40, 0, 1)
    m = np.array(Image.fromarray((m * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(6)), np.float32) / 255
    lit = (lum > 215) & (blue < 1.05)
    sh = (m > 0.8) & (lum > 90)
    if lit.sum() > 1000 and sh.sum() > 1000:
        gain = a[lit].mean(0) / a[sh].mean(0)
    else:
        gain = np.array([1.5, 1.4, 1.2])
    gl = float(np.mean(gain))
    gain = gl + 0.45 * (gain - gl)          # Farbstich nur teilweise korrigieren (sonst gelb/violett)
    gain = np.clip(gain, 1.0, 1.75)
    out = a * (1 + (gain - 1) * m[..., None])
    # leichte lokale Kontrastanhebung, Gesamtbild etwas waermer
    out = np.clip(out * np.array([1.02, 1.0, 0.97]), 0, 255).astype(np.uint8)
    return out, gain.tolist(), float(m.mean())


def main():
    route = json.load(open(bt.JSON_OUT, encoding="utf-8"))
    oE, oN = route["origin"]["E"], route["origin"]["N"]
    wE, wN = route["wall"]["E"], route["wall"]["N"]
    yaw = route["wall"]["yaw"]
    e, n = int(wE // 1000), int(wN // 1000)

    dem = np.array(load_tile("alti_05", e, n), np.float32)
    field = bt.Field(dem, (e * 1000, n * 1000, e * 1000 + 1000, n * 1000 + 1000), px=0.5)

    # ------------------------------------------------ Wand-Rahmen (Spielkoordinaten)
    out = np.array([math.sin(yaw), 0, math.cos(yaw)])           # aus der Wand heraus
    side = np.array([math.cos(yaw), 0, -math.sin(yaw)])         # lokale +x (rechts von der Kletterin aus? s.u.)
    xs = np.linspace(-WALL_W / 2, WALL_W / 2, 17)
    Eb = wE + xs * side[0]
    Nb = wN - xs * side[2]
    base_y = float(field.h(Eb, Nb).min()) - 0.3

    # ------------------------------------------------ Tiefenkarte d(x, z): Abstand Wandebene -> Fels
    gx = np.arange(-WALL_W / 2, WALL_W / 2 + 1e-6, WALL_STEP)
    gz = np.arange(0, WALL_H + 1e-6, WALL_STEP)
    X, Z = np.meshgrid(gx, gz)                                  # Zeilen = Hoehe
    ds = np.arange(-8, 20, 0.05)
    depth = np.full(X.shape, np.nan, np.float32)
    for k, d in enumerate(ds):
        # Punkt = Wandfuss + side*x + up*z - out*d
        Ep = wE + X * side[0] - d * out[0]
        Np = wN - (X * side[2] - d * out[2])
        inside = field.h(Ep, Np) >= base_y + Z
        newly = inside & np.isnan(depth)
        depth[newly] = d
    depth[np.isnan(depth)] = ds[-1]
    depth = blur(depth, 1)
    os.makedirs(os.path.dirname(DEPTH_NPY), exist_ok=True)
    np.save(DEPTH_NPY, depth)

    # ------------------------------------------------ Nahbereich-Netz
    H = bt.NEAR_HALF
    E0, E1, N0, N1 = wE - H, wE + H, wN - H, wN + H
    # Hoehe des groben 4-m-Netzes (build_terrain.py) fuer einen nahtlosen Rand
    dem2, img2, have2, bounds2, _ = bt.load_mosaic()
    bt.fill_gaps(dem2, img2, have2)
    coarse_field = bt.Field(dem2, bounds2)
    cs = bt.STEPS[0]

    def coarse_h(E, N):
        gE0, gN0 = bounds2[0], bounds2[1]
        i = np.floor((E - gE0) / cs)
        j = np.floor((N - gN0) / cs)
        e0, n0 = gE0 + i * cs, gN0 + j * cs
        fe, fn = (E - e0) / cs, (N - n0) / cs
        h00 = coarse_field.h(e0, n0)
        h10 = coarse_field.h(e0 + cs, n0)
        h01 = coarse_field.h(e0, n0 + cs)
        h11 = coarse_field.h(e0 + cs, n0 + cs)
        return (h00 * (1 - fe) + h10 * fe) * (1 - fn) + (h01 * (1 - fe) + h11 * fe) * fn

    BLEND = 14.0   # Meter am Rand, ueber die das feine Netz in das grobe uebergeht

    def patch_mesh(step, cut=True):
        """Gitter mit Loch unter der Wand (cut) und Schuerze am Rand."""
        cnt = int(round(2 * H / step))
        es = E0 + np.arange(cnt + 1) * step
        ns = N1 - np.arange(cnt + 1) * step
        EE, NN = np.meshgrid(es, ns)
        HH = field.h(EE, NN)
        edge = np.minimum(np.minimum(EE - E0, E1 - EE), np.minimum(NN - N0, N1 - NN))
        w = np.clip(1 - edge / BLEND, 0, 1)
        w = w * w * (3 - 2 * w)
        HH = HH * (1 - w) + coarse_h(EE, NN) * w
        NRM = field.normal(EE, NN, step).reshape(-1, 3)
        P = np.stack([EE - oE, HH, -(NN - oN)], -1).reshape(-1, 3)
        UV = np.stack([(EE - E0) / (2 * H), (N1 - NN) / (2 * H)], -1).reshape(-1, 2)
        g = np.arange((cnt + 1) ** 2).reshape(cnt + 1, cnt + 1)
        a, b, c, d_ = g[:-1, :-1], g[:-1, 1:], g[1:, :-1], g[1:, 1:]
        tri = np.stack([a, c, b, b, c, d_], -1).reshape(-1, 3)
        # Loch, wo die Kletterwand sitzt (Wand-Koordinaten des Dreieck-Schwerpunkts)
        base_pt = np.array([wE - oE, base_y, -(wN - oN)])
        cen = P[tri].mean(1) - base_pt
        lx = cen @ side
        lz = cen[:, 1]
        ld = -(cen @ out)
        in_wall = ((np.abs(lx) < WALL_W / 2 - HOLE_MARGIN) & (lz > HOLE_MARGIN) & (lz < WALL_H - HOLE_MARGIN)
                   & (ld > -3) & (ld < 8))
        if cut:
            tri = tri[~in_wall]
        # Schuerze am Aussenrand
        pos, nor, uv, idx = [P], [NRM], [UV], [tri]
        count = len(P)
        for edge in (g[0, :], g[-1, ::-1], g[::-1, 0], g[:, -1]):
            low = P[edge].copy()
            low[:, 1] -= 8
            pos.append(low); nor.append(NRM[edge]); uv.append(UV[edge])
            lo = np.arange(len(edge)) + count
            count += len(edge)
            idx.append(np.concatenate([np.stack([edge[:-1], lo[:-1], edge[1:]], -1),
                                       np.stack([edge[1:], lo[:-1], lo[1:]], -1)]))
        P = np.concatenate(pos).astype(np.float32)
        N = np.concatenate(nor).astype(np.float32)
        T = np.concatenate(uv).astype(np.float32)
        I = np.concatenate(idx).astype(np.uint32).reshape(-1)

        return P, N, T, I

    P, N, T, I = patch_mesh(STEP, cut=False)   # kein Loch: die Wand liegt vor dem Gelaende, Raender tauchen darunter

    # ------------------------------------------------ Luftbild 10 cm, entschattet
    im = load_tile("image_010", e, n)
    px0 = int(round((E0 - e * 1000) / IMG_PX))
    py0 = int(round((n * 1000 + 1000 - N1) / IMG_PX))
    size = int(round(2 * H / IMG_PX))
    crop = np.array(im.crop((px0, py0, px0 + size, py0 + size)).convert("RGB"))
    fixed, gain, shadow_frac = deshadow(crop)
    buf = io.BytesIO()
    Image.fromarray(fixed).save(buf, "JPEG", quality=82, optimize=True, progressive=True)
    bt.write_glb(NEAR_GLB, P, N, T, I, buf.getvalue())

    # leichte Variante fuer Qualitaet "niedrig": grobes Netz, kleines Bild (fuellt das Loch im Grobgelaende)
    Pl, Nl, Tl, Il = patch_mesh(STEP_LOW, cut=False)   # grobes Netz: ohne Loch, sonst Luecken am Wandrand
    buf = io.BytesIO()
    Image.fromarray(fixed).resize((900, 900), Image.LANCZOS).save(buf, "JPEG", quality=80, optimize=True)
    bt.write_glb(NEAR_LOW_GLB, Pl, Nl, Tl, Il, buf.getvalue())
    print(f"Nahbereich niedrig: {len(Il) // 3} Dreiecke, GLB {os.path.getsize(NEAR_LOW_GLB) / 1e6:.1f} MB")

    # Felsfarbe rund um die Wand (fuer das Wandmaterial in Blender)
    cx = int((wE - E0) / IMG_PX)
    cy = int((N1 - wN) / IMG_PX)
    patch = fixed[cy - 150:cy + 150, cx - 150:cx + 150].reshape(-1, 3).astype(np.float32)
    lum = patch.mean(1)
    rock = patch[(lum > 40) & (lum < 170)]
    rock_rgb = (rock.mean(0) / 255).tolist() if len(rock) > 100 else [0.42, 0.40, 0.37]

    meta = {
        "step": WALL_STEP, "width": WALL_W, "height": WALL_H,
        "x0": -WALL_W / 2, "z0": 0.0, "shape": list(depth.shape),
        "rock_rgb": rock_rgb,
        "note": "depth[z_index, x_index] = Abstand von der Wandebene in den Berg (m); "
                "Blender: X = x, Y = depth, Z = z (Kletterseite schaut nach -Y)",
    }
    json.dump(meta, open(DEPTH_META, "w", encoding="utf-8"), indent=2)

    route["near"] = {
        "file": "assets/dufourspitze_near.glb",
        "fileLow": "assets/dufourspitze_near_low.glb",
        "bounds": {"E0": E0, "N0": N0, "E1": E1, "N1": N1},
        "meshStep": STEP, "imagePx": IMG_PX, "triangles": int(len(I) // 3),
        "deshadowGain": [round(v, 3) for v in gain], "shadowFraction": round(shadow_frac, 3),
    }
    route["wall"]["position"] = [round(wE - oE, 3), round(base_y, 3), round(-(wN - oN), 3)]
    route["wall"]["file"] = "assets/dufour_wall.glb"
    route["wall"]["size"] = [WALL_W, WALL_H]
    route["rockColor"] = [round(v, 3) for v in rock_rgb]
    json.dump(route, open(bt.JSON_OUT, "w", encoding="utf-8"), indent=2, ensure_ascii=False)

    print(f"Nahbereich: {len(I) // 3} Dreiecke, Textur {size}x{size}, GLB {os.path.getsize(NEAR_GLB) / 1e6:.1f} MB")
    print(f"Entschattung: Verstaerkung {np.round(gain, 2)}, Schattenanteil {shadow_frac:.0%}")
    print(f"Wandfuss {base_y:.1f} m, Tiefenkarte {depth.shape}, Tiefe {depth.min():.1f}..{depth.max():.1f} m")
    print(f"Felsfarbe {np.round(rock_rgb, 3)}")


if __name__ == "__main__":
    main()
