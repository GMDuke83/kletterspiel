"""
Erzeugt kachelbare Fels-Detailtexturen (prozedural, eigene Arbeit, keine fremden Assets):

    python -I scripts/terrain/make_detail_textures.py

public/assets/detail_rock.jpg    Graustufen-Helligkeit um 50 % (wird im Shader multipliziert)
(Die Detail-Normalen berechnet der Shader per Bump direkt aus dieser Textur.)

Methode: periodisches Rauschen ueber FFT (1/f-Spektrum) -> nahtlos kachelbar,
dazu kantige "Platten" aus periodischem Voronoi fuer Felsbruch-Struktur.
"""
import os

import numpy as np
from PIL import Image

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUT = os.path.join(ROOT, "public", "assets")
N = 1024
rng = np.random.default_rng(11)


def spectral_noise(beta, lo=2, hi=None):
    """periodisches Rauschen mit Leistungsspektrum ~ 1/f^beta"""
    f = np.fft.fftfreq(N) * N
    fx, fy = np.meshgrid(f, f)
    r = np.hypot(fx, fy)
    r[0, 0] = 1
    amp = r ** (-beta / 2)
    amp[r < lo] = 0
    if hi:
        amp[r > hi] = 0
    phase = rng.uniform(0, 2 * np.pi, (N, N))
    z = np.real(np.fft.ifft2(amp * np.exp(1j * phase)))
    return (z - z.mean()) / z.std()


def periodic_voronoi(cells):
    """F2-F1 einer periodischen Voronoi-Zerlegung (Bruchkanten) und Zell-ID-Hoehen."""
    pts = rng.uniform(0, N, (cells, 2))
    hts = rng.uniform(-1, 1, cells)
    y, x = np.mgrid[0:N, 0:N].astype(np.float32)
    d1 = np.full((N, N), 1e9, np.float32)
    d2 = np.full((N, N), 1e9, np.float32)
    h1 = np.zeros((N, N), np.float32)
    for (px, py), h in zip(pts, hts):
        dx = np.abs(x - px); dx = np.minimum(dx, N - dx)
        dy = np.abs(y - py); dy = np.minimum(dy, N - dy)
        d = np.hypot(dx, dy)
        closer = d < d1
        d2 = np.where(closer, d1, np.minimum(d2, d))
        h1 = np.where(closer, h, h1)
        d1 = np.where(closer, d, d1)
    return d2 - d1, h1


def main():
    base = spectral_noise(2.2, lo=2)
    fine = spectral_noise(1.4, lo=40)
    edge, plates = periodic_voronoi(60)
    crack = np.exp(-edge / 4.0)                      # schmale Fugen zwischen Platten
    height = 0.55 * base + 0.35 * plates + 0.18 * fine - 0.9 * crack

    # Helligkeit: Fugen dunkel, Plattenkanten etwas heller, feine Koernung
    alb = 0.5 + 0.13 * base + 0.015 * fine + 0.07 * plates - 0.2 * crack
    alb = np.clip(alb, 0.15, 0.85)
    Image.fromarray((alb * 255).astype(np.uint8), "L").save(os.path.join(OUT, "detail_rock.jpg"), quality=88)

    for f in ("detail_rock.jpg",):
        print(f, os.path.getsize(os.path.join(OUT, f)) // 1024, "KB")


if __name__ == "__main__":
    main()
