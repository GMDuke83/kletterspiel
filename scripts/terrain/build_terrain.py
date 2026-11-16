"""
Baut aus swissALTI3D (2 m) + SWISSIMAGE (2 m) ein Gelaende-GLB fuer three.js.

    python -I scripts/terrain/build_terrain.py

Eingabe:  assets-src/terrain/raw/{alti,image}/<E>-<N>.tif   (fetch_swisstopo.py)
Ausgabe:  public/assets/dufourspitze_terrain.glb
          src/routes/dufourspitze.json   (Koordinaten, Wandposition, Quellenangabe)

Koordinaten im Spiel (Meter, 1:1):  x = E - E0,  y = Hoehe ueber Meer,  z = -(N - N0)
mit (E0, N0) = Dufourspitze-Gipfel (LV95).  Norden = -z.
Detailstufen: 500-m-Bloecke, nahe der Kletterwand fein (4 m), mittel 14 m, aussen 40 m.
Bloecke haben "Schuerzen" (senkrechte Raender nach unten), damit keine Spalten sichtbar sind.

Geodaten (c) swisstopo (Open Government Data, freie Nutzung mit Quellenangabe).
Benutzt nur numpy + Pillow (keine weiteren Pakete).
"""
import glob
import io
import json
import math
import os
import struct

import numpy as np
from PIL import Image

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
RAW = os.path.join(ROOT, "assets-src", "terrain", "raw")
GLB_OUT = os.path.join(ROOT, "public", "assets", "dufourspitze_terrain.glb")
JSON_OUT = os.path.join(ROOT, "src", "routes", "dufourspitze.json")

PX = 2.0                      # Rasterweite der Daten (m)
TILE = 500                    # Pixel je 1-km-Kachel
CHUNK = 500.0                 # Blockgroesse (m)
NEAR_R, MID_R = 300.0, 1800.0  # Radien der Detailstufen um die Wand
STEPS = (4.0, 14.0, 40.0)
TEX_QUALITY = 86


# ---------------------------------------------------------------- Mosaik
def load_mosaic():
    files = glob.glob(os.path.join(RAW, "alti", "*.tif"))
    keys = [tuple(map(int, os.path.basename(f)[:-4].split("-"))) for f in files]
    e0, e1 = min(k[0] for k in keys), max(k[0] for k in keys) + 1
    n0, n1 = min(k[1] for k in keys), max(k[1] for k in keys) + 1
    W, H = (e1 - e0) * TILE, (n1 - n0) * TILE
    dem = np.full((H, W), np.nan, np.float32)
    img = np.zeros((H, W, 3), np.uint8)
    have = np.zeros((H, W), bool)
    for (e, n) in keys:
        r0 = (n1 - 1 - n) * TILE   # Zeile 0 = Norden
        c0 = (e - e0) * TILE
        a = np.array(Image.open(os.path.join(RAW, "alti", f"{e}-{n}.tif")), np.float32)
        a[a < -1000] = np.nan
        dem[r0:r0 + TILE, c0:c0 + TILE] = a
        ip = os.path.join(RAW, "image", f"{e}-{n}.tif")
        if os.path.exists(ip):
            im = Image.open(ip).convert("RGB")
            if im.size != (TILE, TILE):
                im = im.resize((TILE, TILE), Image.BILINEAR)
            img[r0:r0 + TILE, c0:c0 + TILE] = np.array(im)
            have[r0:r0 + TILE, c0:c0 + TILE] = True
    missing = [f"{e}-{n}" for e in range(e0, e1) for n in range(n0, n1) if (e, n) not in keys]
    return dem, img, have, (e0 * 1000, n0 * 1000, e1 * 1000, n1 * 1000), missing


def fill_gaps(dem, img, have):
    """Fehlende Bereiche: Hoehe per wiederholtem Weichzeichnen auffuellen, Bild mit Fels-/Schneegrau."""
    mask = np.isnan(dem)
    if mask.any():
        filled = np.where(mask, np.nanmean(dem), dem)
        for _ in range(400):
            blur = (np.roll(filled, 1, 0) + np.roll(filled, -1, 0) + np.roll(filled, 1, 1) + np.roll(filled, -1, 1)) / 4
            filled[mask] = blur[mask]
        dem[:] = filled
    if (~have).any():
        lum = np.clip((dem - 3000) / 1500, 0, 1)[..., None]
        fill = (np.array([110, 105, 100]) * (1 - lum) + np.array([225, 228, 235]) * lum).astype(np.uint8)
        img[~have] = fill[~have]
    return mask


# ---------------------------------------------------------------- Abtasten
class Field:
    def __init__(self, dem, bounds):
        self.dem = dem
        self.E0, self.N0, self.E1, self.N1 = bounds

    def h(self, E, N):
        """bilineare Hoehe an LV95-Koordinaten (Arrays)."""
        c = (E - self.E0) / PX - 0.5
        r = (self.N1 - N) / PX - 0.5
        H, W = self.dem.shape
        c = np.clip(c, 0, W - 1.001)
        r = np.clip(r, 0, H - 1.001)
        c0, r0 = np.floor(c).astype(int), np.floor(r).astype(int)
        fc, fr = c - c0, r - r0
        d = self.dem
        return ((d[r0, c0] * (1 - fc) + d[r0, c0 + 1] * fc) * (1 - fr)
                + (d[r0 + 1, c0] * (1 - fc) + d[r0 + 1, c0 + 1] * fc) * fr)

    def normal(self, E, N, s):
        """Flaechennormale in Spielkoordinaten (x=E, y=oben, z=-N)."""
        dx = (self.h(E + s, N) - self.h(E - s, N)) / (2 * s)
        dn = (self.h(E, N + s) - self.h(E, N - s)) / (2 * s)
        n = np.stack([-dx, np.ones_like(dx), dn], -1)    # dz = -dN
        return n / np.linalg.norm(n, axis=-1, keepdims=True)


# ---------------------------------------------------------------- Wand-Standort
def find_wall_site(field, summit):
    """Echte Felswand fuer die 12-m-Testwand: nach W/N schauend, 100-700 m vom Gipfel.
    Bedingung: hinter dem Wandfuss steigt der Fels auf 3-14 m Abstand um mindestens die
    Wandhoehe an (die Wand lehnt also am Berg und steht nicht frei auf einem Grat),
    und ueber die ganze Wandbreite ist es aehnlich steil. Unter den Kandidaten: moeglichst hoch."""
    sE, sN = summit
    best = None
    one = lambda v: np.array([v])
    for r in np.arange(100, 701, 8):
        for a in np.radians(np.arange(0, 360, 3)):
            E, N = sE + r * math.sin(a), sN + r * math.cos(a)
            n = field.normal(one(E), one(N), 6.0)[0]
            slope = math.degrees(math.acos(n[1]))
            az = math.degrees(math.atan2(n[0], -n[2])) % 360   # Blickrichtung der Flaeche (0 = Norden)
            if not (58 <= slope <= 85) or not (240 <= az <= 360 or az <= 30):
                continue
            hd = np.array([n[0], -n[2]])                       # horizontal "aus der Wand" in (E, N)
            hd /= np.linalg.norm(hd)
            side = np.array([hd[1], -hd[0]])
            ok = True
            base = None
            for off in (-3.0, 0.0, 3.0):                       # ueber die Wandbreite pruefen
                pE, pN = E + side[0] * off, N + side[1] * off
                h0 = float(field.h(one(pE), one(pN))[0])
                h_back = float(field.h(one(pE - hd[0] * 9), one(pN - hd[1] * 9))[0])
                h_front = float(field.h(one(pE + hd[0] * 4), one(pN + hd[1] * 4))[0])
                if h_back - h0 < 12.5 or h0 - h_front < 2.0:
                    ok = False
                    break
                base = h0 if base is None else min(base, h0)
            if not ok:
                continue
            score = base - 0.15 * r
            if best is None or score > best[0]:
                best = (score, E, N, base, slope, az, n)
    return best


# ---------------------------------------------------------------- Mesh
def build_mesh(field, bounds, wall_EN, origin):
    E0, N0, E1, N1 = bounds
    oE, oN = origin
    pos, nor, uv, idx = [], [], [], []
    count = 0
    stats = {s: 0 for s in STEPS}
    Wm, Hm = E1 - E0, N1 - N0
    for cy in np.arange(N0, N1, CHUNK):
        for cx in np.arange(E0, E1, CHUNK):
            ccE, ccN = cx + CHUNK / 2, cy + CHUNK / 2
            # Abstand Block -> Wand (naechster Punkt des Blocks)
            dE = max(cx - wall_EN[0], 0, wall_EN[0] - (cx + CHUNK))
            dN = max(cy - wall_EN[1], 0, wall_EN[1] - (cy + CHUNK))
            d = math.hypot(dE, dN)
            s = STEPS[0] if d < NEAR_R else STEPS[1] if d < MID_R else STEPS[2]
            n = int(round(CHUNK / s))
            es = cx + np.arange(n + 1) * s
            ns = cy + CHUNK - np.arange(n + 1) * s          # Zeile 0 = Norden
            EE, NN = np.meshgrid(es, ns)
            EE = np.clip(EE, E0 + 1, E1 - 1)
            NN = np.clip(NN, N0 + 1, N1 - 1)
            HH = field.h(EE, NN)
            NRM = field.normal(EE, NN, max(s, 4.0))
            P = np.stack([EE - oE, HH, -(NN - oN)], -1).reshape(-1, 3)
            UV = np.stack([(EE - E0) / Wm, (N1 - NN) / Hm], -1).reshape(-1, 2)
            NRM = NRM.reshape(-1, 3)
            pos.append(P); nor.append(NRM); uv.append(UV)
            loc = np.arange((n + 1) * (n + 1)).reshape(n + 1, n + 1)
            base = count
            g = loc + base
            a, b, c_, d_ = g[:-1, :-1], g[:-1, 1:], g[1:, :-1], g[1:, 1:]
            # Zeile 0 = Norden (z klein), Spalte = Osten: Dreiecke gegen den Uhrzeigersinn von oben
            tri = np.stack([a, c_, b, b, c_, d_], -1).reshape(-1, 3)
            idx.append(tri)
            count += (n + 1) * (n + 1)
            stats[s] += len(tri)
            # Schuerzen an allen vier Raendern (Aussenrand des Gebiets tief, damit keine Luecke sichtbar ist)
            edges = (
                (loc[0, :], cy + CHUNK >= N1),       # Nordrand
                (loc[-1, ::-1], cy <= N0),           # Suedrand
                (loc[::-1, 0], cx <= E0),            # Westrand
                (loc[:, -1], cx + CHUNK >= E1),      # Ostrand
            )
            for edge, is_outer in edges:
                low = P[edge].copy()
                low[:, 1] -= 600 if is_outer else 1.5 * s + 2   # nur so tief wie noetig (sonst helle Streifen)
                pos.append(low); nor.append(NRM[edge]); uv.append(UV[edge])
                top = edge + base
                lo = np.arange(len(edge)) + count
                count += len(edge)
                t1 = np.stack([top[:-1], lo[:-1], top[1:]], -1)
                t2 = np.stack([top[1:], lo[:-1], lo[1:]], -1)
                idx.append(np.concatenate([t1, t2]))
                stats[s] += 2 * (len(edge) - 1)
    P = np.concatenate(pos).astype(np.float32)
    N = np.concatenate(nor).astype(np.float32)
    T = np.concatenate(uv).astype(np.float32)
    I = np.concatenate(idx).astype(np.uint32).reshape(-1)
    return P, N, T, I, stats


# ---------------------------------------------------------------- GLB
def write_glb(path, P, N, T, I, jpeg_bytes):
    bufs, views, accessors = [], [], []
    offset = 0

    def add(data, target=None):
        nonlocal offset
        b = data.tobytes() if hasattr(data, "tobytes") else data
        pad = (-len(b)) % 4
        views.append({"buffer": 0, "byteOffset": offset, "byteLength": len(b), **({"target": target} if target else {})})
        bufs.append(b + b"\0" * pad)
        offset += len(b) + pad
        return len(views) - 1

    vp = add(P, 34962); vn = add(N, 34962); vt = add(T, 34962); vi = add(I, 34963)
    vimg = add(jpeg_bytes)
    accessors = [
        {"bufferView": vp, "componentType": 5126, "count": len(P), "type": "VEC3",
         "min": P.min(0).tolist(), "max": P.max(0).tolist()},
        {"bufferView": vn, "componentType": 5126, "count": len(N), "type": "VEC3"},
        {"bufferView": vt, "componentType": 5126, "count": len(T), "type": "VEC2"},
        {"bufferView": vi, "componentType": 5125, "count": len(I), "type": "SCALAR"},
    ]
    gltf = {
        "asset": {"version": "2.0", "generator": "kletterspiel build_terrain.py",
                  "copyright": "Geodaten (c) swisstopo"},
        "scene": 0, "scenes": [{"nodes": [0]}],
        "nodes": [{"name": "terrain", "mesh": 0}],
        "meshes": [{"name": "terrain", "primitives": [{
            "attributes": {"POSITION": 0, "NORMAL": 1, "TEXCOORD_0": 2}, "indices": 3, "material": 0}]}],
        "materials": [{"name": "terrain_orthophoto", "pbrMetallicRoughness": {
            "baseColorTexture": {"index": 0}, "metallicFactor": 0, "roughnessFactor": 1}}],
        "textures": [{"source": 0, "sampler": 0}],
        "samplers": [{"magFilter": 9729, "minFilter": 9987, "wrapS": 33071, "wrapT": 33071}],
        "images": [{"bufferView": vimg, "mimeType": "image/jpeg"}],
        "accessors": accessors, "bufferViews": views,
        "buffers": [{"byteLength": offset}],
    }
    js = json.dumps(gltf, separators=(",", ":")).encode()
    js += b" " * ((-len(js)) % 4)
    binb = b"".join(bufs)
    with open(path, "wb") as f:
        f.write(struct.pack("<III", 0x46546C67, 2, 12 + 8 + len(js) + 8 + len(binb)))
        f.write(struct.pack("<II", len(js), 0x4E4F534A)); f.write(js)
        f.write(struct.pack("<II", len(binb), 0x004E4942)); f.write(binb)


# ---------------------------------------------------------------- main
def main():
    dem, img, have, bounds, missing = load_mosaic()
    gap_mask = fill_gaps(dem, img, have)
    field = Field(dem, bounds)
    E0, N0, E1, N1 = bounds

    r, c = np.unravel_index(np.nanargmax(dem), dem.shape)
    summit = (E0 + (c + 0.5) * PX, N1 - (r + 0.5) * PX)
    summit_h = float(dem[r, c])
    print(f"Gipfel: E {summit[0]:.0f} N {summit[1]:.0f} H {summit_h:.1f} m")

    site = find_wall_site(field, summit)
    if site is None:
        raise SystemExit("Keine passende Wandstelle gefunden")
    _, wE, wN, wH, slope, az, n = site
    print(f"Wand: E {wE:.0f} N {wN:.0f} H {wH:.0f} m, Neigung {slope:.0f} Grad, Blick nach {az:.0f} Grad")

    P, Nm, T, I, stats = build_mesh(field, bounds, (wE, wN), summit)
    tris = len(I) // 3
    print(f"Dreiecke: {tris} ({', '.join(f'{int(s)} m: {v}' for s, v in stats.items())})")

    buf = io.BytesIO()
    Image.fromarray(img).save(buf, "JPEG", quality=TEX_QUALITY, optimize=True, progressive=True)
    write_glb(GLB_OUT, P, Nm, T, I, buf.getvalue())
    print(f"GLB: {GLB_OUT} ({os.path.getsize(GLB_OUT) / 1e6:.1f} MB, Textur {img.shape[1]}x{img.shape[0]}, "
          f"JPEG {len(buf.getvalue()) / 1e6:.1f} MB)")

    # Wand im Spiel: Fuss auf dem Gelaende, Wandflaeche schaut horizontal in Richtung der Hangnormale
    yaw = math.atan2(float(n[0]), float(n[2]))            # three.js: Wand schaut lokal nach +Z
    # tiefster Gelaendepunkt unter der Wandbreite, damit die Wand nicht schwebt
    side = np.array([math.cos(yaw), -math.sin(yaw)])      # lokale x-Achse in (x, z)
    xs = np.linspace(-3, 3, 13)
    Es = wE + xs * side[0]
    Ns = wN - xs * side[1]
    base = float(field.h(Es, Ns).min()) - 0.4
    os.makedirs(os.path.dirname(JSON_OUT), exist_ok=True)
    route = {
        "name": "Dufourspitze",
        "attribution": "Geodaten © swisstopo",
        "crs": "EPSG:2056 (LV95)",
        "origin": {"E": round(summit[0], 1), "N": round(summit[1], 1),
                   "note": "Spielkoordinaten: x = E - E0, y = Hoehe (m ueber Meer), z = -(N - N0)"},
        "summit": {"E": round(summit[0], 1), "N": round(summit[1], 1), "H": round(summit_h, 1)},
        "bounds": {"E0": E0, "N0": N0, "E1": E1, "N1": N1},
        "missingTiles": missing,
        "filledArea": round(float(gap_mask.mean()), 4),
        "wall": {
            "E": round(wE, 1), "N": round(wN, 1),
            "position": [round(wE - summit[0], 2), round(base, 2), round(-(wN - summit[1]), 2)],
            "yaw": round(yaw, 4),
            "slopeDeg": round(slope, 1), "facingDeg": round(az, 1),
        },
        "terrain": {"file": "assets/dufourspitze_terrain.glb", "triangles": tris,
                    "lodSteps": list(STEPS), "lodRadii": [NEAR_R, MID_R]},
    }
    with open(JSON_OUT, "w", encoding="utf-8") as f:
        json.dump(route, f, indent=2, ensure_ascii=False)
    print(f"Route: {JSON_OUT}")


if __name__ == "__main__":
    main()
