"""
Bereitet die CC0-Fels-Fototextur von Poly Haven ("Rock Face 03", polyhaven.com, Lizenz CC0)
fuer das Spiel auf:

    python -I scripts/terrain/prep_photo_textures.py

Eingabe:  assets-src/textures/polyhaven/rock_face_03_{diffuse,nor_gl,rough}_2k.jpg
          (nicht im Repo; Download ueber https://api.polyhaven.com/files/rock_face_03 -> 2k/jpg)
Ausgabe:  public/assets/rock_detail.jpg   Helligkeit um 50 % (Farbe entfernt, wird multipliziert)
          public/assets/rock_normal.jpg   Normal-Map (OpenGL), 1024 px
          public/assets/rock_rough.jpg    Rauheit, 1024 px

Nur die Struktur wird uebernommen, die Farbe kommt weiter aus dem Luftbild bzw. der Wand,
damit der Fels zum echten (grauen) Gestein der Dufourspitze passt.
"""
import os

import numpy as np
from PIL import Image

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SRC = os.path.join(ROOT, "assets-src", "textures", "polyhaven")
OUT = os.path.join(ROOT, "public", "assets")
SIZE = 1024


def load(name):
    return Image.open(os.path.join(SRC, name)).resize((SIZE, SIZE), Image.LANCZOS)


def main():
    rgb = np.array(load("rock_face_03_diffuse_2k.jpg").convert("RGB"), np.float32) / 255
    lum = rgb @ np.array([0.299, 0.587, 0.114], np.float32)
    # sehr grossflaechige Helligkeitsunterschiede entfernen (sonst sieht man die Kachel)
    big = np.array(Image.fromarray((lum * 255).astype(np.uint8)).resize((16, 16), Image.BILINEAR)
                   .resize((SIZE, SIZE), Image.BICUBIC), np.float32) / 255
    detail = lum / np.maximum(big, 0.05) * 0.5
    detail = 0.5 + (detail - 0.5) * 1.15          # etwas mehr Kontrast
    detail = np.clip(detail, 0.1, 0.9)
    Image.fromarray((detail * 255).astype(np.uint8), "L").save(os.path.join(OUT, "rock_detail.jpg"), quality=88)
    load("rock_face_03_nor_gl_2k.jpg").convert("RGB").save(os.path.join(OUT, "rock_normal.jpg"), quality=90)
    load("rock_face_03_rough_2k.jpg").convert("L").save(os.path.join(OUT, "rock_rough.jpg"), quality=88)
    for f in ("rock_detail.jpg", "rock_normal.jpg", "rock_rough.jpg"):
        print(f, os.path.getsize(os.path.join(OUT, f)) // 1024, "KB")


if __name__ == "__main__":
    main()
