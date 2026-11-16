"""
Laedt swissALTI3D (2 m) und SWISSIMAGE (2 m) Kacheln fuer einen LV95-Ausschnitt
ueber die offizielle STAC-API von data.geo.admin.ch.

    python scripts/terrain/fetch_swisstopo.py 2630 2636 1084 1090

Argumente: E_min E_max N_min N_max in km (LV95, Kachelraster 1 km).
Ziel: assets-src/terrain/raw/{alti,image}/   (per .gitignore nicht im Repo)
Geodaten (c) swisstopo - freie Nutzung mit Quellenangabe (OGD).
"""
import json
import os
import sys
import urllib.request

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
RAW = os.path.join(ROOT, "assets-src", "terrain", "raw")
API = "https://data.geo.admin.ch/api/stac/v0.9/collections/{}/items/{}"
COLLECTIONS = {
    "alti": ("ch.swisstopo.swissalti3d", "swissalti3d", 2.0),
    "image": ("ch.swisstopo.swissimage-dop10", "swissimage-dop10", 2.0),
}


def get_json(url):
    with urllib.request.urlopen(url, timeout=60) as r:
        return json.load(r)


def find_item(coll, prefix, e, n):
    """Neueste Ausgabe einer Kachel suchen (Item-IDs: <prefix>_<jahr>_<E>-<N>)."""
    url = (f"https://data.geo.admin.ch/api/stac/v0.9/collections/{coll}/items"
           f"?bbox={lv95_corner_to_wgs(e, n)}&limit=100")
    items = get_json(url)["features"]
    tag = f"_{e}-{n}"
    cands = [i for i in items if i["id"].endswith(tag)]
    cands.sort(key=lambda i: i["id"])
    return cands[-1] if cands else None


def lv95_to_wgs(E, N):
    """Naeherungsformel swisstopo (Genauigkeit ~1 m)."""
    y = (E - 2600000) / 1e6
    x = (N - 1200000) / 1e6
    lon = 2.6779094 + 4.728982 * y + 0.791484 * y * x + 0.1306 * y * x * x - 0.0436 * y ** 3
    lat = 16.9023892 + 3.238272 * x - 0.270978 * y * y - 0.002528 * x * x - 0.0447 * y * y * x - 0.0140 * x ** 3
    return lon * 100 / 36, lat * 100 / 36


def lv95_corner_to_wgs(e, n):
    # kleine BBox in der Kachelmitte
    lon, lat = lv95_to_wgs(e * 1000 + 500, n * 1000 + 500)
    d = 0.001
    return f"{lon - d},{lat - d},{lon + d},{lat + d}"


def main():
    e0, e1, n0, n1 = map(int, sys.argv[1:5])
    log = []
    for kind, (coll, prefix, gsd) in COLLECTIONS.items():
        out_dir = os.path.join(RAW, kind)
        os.makedirs(out_dir, exist_ok=True)
        for e in range(e0, e1):
            for n in range(n0, n1):
                item = find_item(coll, prefix, e, n)
                if not item:
                    log.append(f"{kind} {e}-{n}: keine Kachel")
                    print(log[-1], flush=True)
                    continue
                asset = next((a for a in item["assets"].values()
                              if a.get("eo:gsd") == gsd and a["href"].endswith(".tif")), None)
                if not asset:
                    log.append(f"{kind} {e}-{n}: kein {gsd} m GeoTIFF")
                    continue
                dst = os.path.join(out_dir, f"{e}-{n}.tif")
                if not os.path.exists(dst):
                    urllib.request.urlretrieve(asset["href"], dst)
                log.append(f"{kind} {e}-{n}: {item['id']} ({os.path.getsize(dst) // 1024} KB)")
                print(log[-1], flush=True)
    with open(os.path.join(RAW, "download_log.txt"), "w", encoding="utf-8") as f:
        f.write("Geodaten (c) swisstopo\n" + "\n".join(log) + "\n")


if __name__ == "__main__":
    main()
