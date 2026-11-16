"""
make_wall.py - erzeugt eine Test-Kletterwand (ca. 6 m breit, 12 m hoch) fuer den Prototyp.

Aufruf (aus dem Projektordner):
    scripts\\blender\\make_wall.cmd
    (= blender --background --factory-startup --python scripts/blender/make_wall.py)

Ergebnis:
    assets-src/walls/test_wall.blend
    assets-src/walls/textures/test_wall_*.png
    public/assets/test_wall.glb   (Y-up; Wand zeigt in three.js nach +Z)
    previews/test_wall.png

Koordinaten in Blender: X = Breite, Z = Hoehe, die Kletterseite schaut nach -Y.
Griffe: Empties grip_<typ>_<nr> mit Extras grip_type, start, summit.
Kollision: col_wall (grobes Gitter, nur Form ohne Feindetail).
"""
import json
import math
import os
import random
import sys
import traceback

import bmesh
import bpy
from mathutils import Matrix, Vector, noise

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
BLEND_PATH = os.path.join(ROOT, "assets-src", "walls", "test_wall.blend")
TEX_DIR = os.path.join(ROOT, "assets-src", "walls", "textures")
GLB_PATH = os.path.join(ROOT, "public", "assets", "test_wall.glb")
PNG_PATH = os.path.join(ROOT, "previews", "test_wall.png")
REPORT_PATH = os.path.join(ROOT, "scripts", "blender", "make_wall_report.json")

SEED = 7
WIDTH, HEIGHT = 6.0, 12.0

# --dufour: Wandform aus dem echten Gelaende (Tiefenkarte von scripts/terrain/build_near.py)
ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
DUFOUR = "--dufour" in ARGS
REAL_DEPTH = None
ROCK_RGB = (0.42, 0.40, 0.37)
if DUFOUR:
    import numpy as np
    _meta = json.load(open(os.path.join(ROOT, "assets-src", "walls", "dufour_wall_depth.json"), encoding="utf-8"))
    REAL_DEPTH = np.load(os.path.join(ROOT, "assets-src", "walls", "dufour_wall_depth.npy"))
    REAL_STEP = _meta["step"]
    WIDTH, HEIGHT = _meta["width"], _meta["height"]
    ROCK_RGB = tuple(_meta["rock_rgb"])
    BLEND_PATH = os.path.join(ROOT, "assets-src", "walls", "dufour_wall.blend")
    GLB_PATH = os.path.join(ROOT, "public", "assets", "dufour_wall.glb")
    PNG_PATH = os.path.join(ROOT, "previews", "dufour_wall_blender.png")
    REPORT_PATH = os.path.join(ROOT, "scripts", "blender", "make_wall_report.json")
TOP = HEIGHT - 1.0        # oberster Griff (Gipfelgriff) knapp unter der Oberkante
HIGH_STEP = 0.03          # Rasterabstand des hochaufgeloesten Meshes (m)
TARGET_TRIS = 22000       # sichtbares Wand-Mesh (Griffe sind jetzt Teil der Geometrie)
COL_STEP = 0.5            # Rasterabstand des Kollisions-Meshes
TEX_W, TEX_H = 2048, 4096 # Bake-Aufloesung (Seitenverhaeltnis wie die Wand)

report = {"blender": bpy.app.version_string, "steps": []}


def log(msg):
    print("[make_wall]", msg, flush=True)
    report["steps"].append(msg)


def tri_count(mesh):
    return sum(len(p.vertices) - 2 for p in mesh.polygons)


def smoothstep(a, b, x):
    t = min(1.0, max(0.0, (x - a) / (b - a)))
    return t * t * (3 - 2 * t)


# ---------------------------------------------------------------- Wandform
def profile_y(z):
    """Grundneigung: positiv = von der Kletterin weg (geneigt), negativ = zu ihr hin (Ueberhang).
    0-6 m leicht geneigt, 6-8 m kleiner Ueberhang (~20 Grad), darueber wieder senkrecht/geneigt."""
    y = 0.10 * z                                   # ~6 Grad geneigt
    y -= 0.95 * smoothstep(6.0, 8.2, z)            # Bauch nach vorne = Ueberhang
    y += 0.06 * max(0.0, z - 8.2)
    return y


def plates(x, z):
    """Voronoi-Platten: jede Zelle bekommt eine eigene Hoehe, Kanten leicht gefast."""
    # leicht gedreht und verzerrt, damit keine Raster-Ausrichtung sichtbar ist
    q = Vector((x * 0.8 + 0.3 * z, z * 1.1 - 0.2 * x, 0.37))
    q += noise.noise_vector(q * 0.6) * 0.35
    dist, pts = noise.voronoi(q, distance_metric="DISTANCE")
    h1 = noise.cell(pts[0] * 3.7)
    h2 = noise.cell(pts[1] * 3.7)
    t = smoothstep(0.0, 0.07, dist[1] - dist[0])
    return (h1 + h2) / 2 * (1 - t) + h1 * t


def detail(x, z, fine=True):
    """Felsrelief entlang -Y (zur Kletterseite hin). Mehrere Skalen + Kanten."""
    p = Vector((x, z * 0.9, 0.0))
    big = noise.fractal(p * 0.35, 1.0, 2.0, 3, noise_basis="PERLIN_ORIGINAL") * 0.30
    # gestufte Platten (unregelmaessige Voronoi-Zellen mit eigener Hoehe) -> kantige Absaetze
    cell = plates(x, z) * 0.11
    ridge = noise.ridged_multi_fractal(p * 1.3, 1.0, 2.0, 4, 1.0, 2.0,
                                       noise_basis="PERLIN_ORIGINAL") * 0.035
    d = big + cell + ridge
    if fine:
        d += noise.fractal(p * 6.0, 0.8, 2.0, 3, noise_basis="PERLIN_ORIGINAL") * 0.012
    # Raender zur Seite hin etwas zuruecknehmen
    edge = smoothstep(WIDTH / 2, WIDTH / 2 - 0.6, abs(x))
    return d * (0.4 + 0.6 * edge)


def real_depth(x, z):
    """bilineare Tiefe des echten Felsens hinter der Wandebene (m)."""
    rows, cols = REAL_DEPTH.shape
    c = min(max((x + WIDTH / 2) / REAL_STEP, 0), cols - 1.001)
    r = min(max(z / REAL_STEP, 0), rows - 1.001)
    c0, r0 = int(c), int(r)
    fc, fr = c - c0, r - r0
    d = REAL_DEPTH
    return float((d[r0, c0] * (1 - fc) + d[r0, c0 + 1] * fc) * (1 - fr)
                 + (d[r0 + 1, c0] * (1 - fc) + d[r0 + 1, c0 + 1] * fc) * fr)


def edge_fade(x, z):
    """1 in der Wandmitte, 0 am Rand: dort laeuft die Wand in das echte Gelaende aus."""
    return (smoothstep(WIDTH / 2, WIDTH / 2 - 0.9, abs(x))
            * smoothstep(0.0, 0.5, z) * smoothstep(HEIGHT, HEIGHT - 0.9, z))


# Griffe und Tritte als Felsformen (werden in surface_point eingerechnet)
HOLDS = []          # dicts: x, z, type, w (Breite)
HOLD_BINS = {}      # Hoehen-Raster 0.5 m -> Liste der Griffe


def hold_shape(h, x, z):
    """Erhebung (m, zur Kletterseite) einer einzelnen Griff-/Trittform an (x, z)."""
    dx, dz = x - h["x"], z - h["z"]
    t, w = h["type"], h["w"]
    # unregelmaessige Kante: Hoehe der Kante und Breite schwanken entlang des Griffs
    wob = noise.noise(Vector((x * 9.0 + h["x"] * 3.1, h["z"] * 5.7, 1.3)))
    dz += 0.025 * wob
    w *= 1.0 + 0.25 * noise.noise(Vector((h["x"] * 7.3, h["z"] * 4.1, 2.9)))
    if t == "sloper":       # runder Buckel
        return 0.06 * math.exp(-((dx / (w * 0.5)) ** 2 + (dz / 0.09) ** 2) * 1.3)
    if abs(dx) > w / 2 + 0.03 or dz < -0.2 or dz > 0.14:
        return 0.0
    A, below, drop = {"jug": (0.10, 0.14, 0.035), "crimp": (0.04, 0.06, 0.018),
                      "foot": (0.04, 0.08, 0.012)}[t]
    lat = smoothstep(w / 2 + 0.03, w / 2 - 0.02, abs(dx))   # seitlich weich auslaufen
    if dz <= 0:
        prof = A * smoothstep(-below, 0.0, dz)                # Rampe von unten bis zur Kante
    else:
        prof = A * (1 - smoothstep(0.0, 0.03, dz))            # Kante bricht oben scharf ab
        if dz < 0.12:
            prof -= drop * math.sin(math.pi * dz / 0.12)      # kleine Mulde dahinter
    return prof * lat


def hold_offset(x, z):
    best = 0.0
    for h in HOLD_BINS.get(int(z / 0.5), ()):
        v = hold_shape(h, x, z)
        if abs(v) > abs(best):
            best = v
    return best


def chalk_amount(x, z):
    """Kreidespuren auf den Handgriffen (0..1)."""
    c = 0.0
    for h in HOLD_BINS.get(int(z / 0.5), ()):
        if h["type"] == "foot":
            continue
        dx, dz = x - h["x"], z - h["z"]
        # nur auf der Griffkante und knapp darunter, mit unregelmaessigem Rand
        ragged = 0.75 + 0.25 * noise.noise(Vector((x * 40, z * 40, 0.3)))
        c = max(c, ragged * math.exp(-((dx / (h["w"] * 0.42)) ** 2 + ((dz + 0.005) / 0.04) ** 2)))
    return c


def surface_point(x, z, fine=True, holds=True):
    hold = hold_offset(x, z) if (fine and holds and HOLDS) else 0.0
    if DUFOUR:
        # echter Fels + eigenes Relief zur Kletterseite hin; am Rand knapp hinter das Gelaende
        f = edge_fade(x, z)
        inner = max(0.12, 0.16 + 0.8 * detail(x, z, fine))   # sicher vor dem Gelaendenetz
        off = f * inner - (1 - f) * 0.06
        return Vector((x, real_depth(x, z) - off - hold, z))
    return Vector((x, profile_y(z) - detail(x, z, fine) - hold, z))


def surface_normal(x, z, holds=False):
    e = 0.02
    px = surface_point(x + e, z, holds=holds) - surface_point(x - e, z, holds=holds)
    pz = surface_point(x, z + e, holds=holds) - surface_point(x, z - e, holds=holds)
    n = px.cross(pz)           # X x Z = -Y -> zeigt zur Kletterseite
    n.normalize()
    return n


def grid_mesh(name, step, fine):
    nx = int(round(WIDTH / step))
    nz = int(round(HEIGHT / step))
    verts, faces = [], []
    for j in range(nz + 1):
        z = j * step
        for i in range(nx + 1):
            x = -WIDTH / 2 + i * step
            verts.append(surface_point(x, z, fine))
    for j in range(nz):
        for i in range(nx):
            a = j * (nx + 1) + i
            faces.append((a, a + 1, a + nx + 2, a + nx + 1))
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata([tuple(v) for v in verts], [], faces)
    mesh.update()
    return mesh


def planar_uv(mesh):
    uv = mesh.uv_layers.new(name="UVMap")
    for loop in mesh.loops:
        co = mesh.vertices[loop.vertex_index].co
        uv.data[loop.index].uv = ((co.x + WIDTH / 2) / WIDTH, co.z / HEIGHT)


def apply_all_modifiers(obj):
    dg = bpy.context.evaluated_depsgraph_get()
    new_mesh = bpy.data.meshes.new_from_object(obj.evaluated_get(dg), depsgraph=dg)
    old = obj.data
    name = old.name
    obj.modifiers.clear()
    obj.data = new_mesh
    bpy.data.meshes.remove(old)
    new_mesh.name = name


# ---------------------------------------------------------------- Material
def make_source_material():
    """Prozedurales Fels-Material fuer das High-Poly (wird gebacken)."""
    mat = bpy.data.materials.new("wall_procedural")
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = next(n for n in nodes if n.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Roughness"].default_value = 0.85

    texco = nodes.new("ShaderNodeTexCoord")
    noise_n = nodes.new("ShaderNodeTexNoise")
    noise_n.inputs["Scale"].default_value = 1.2
    noise_n.inputs["Detail"].default_value = 10.0
    noise_n.inputs["Roughness"].default_value = 0.62
    base_ramp = nodes.new("ShaderNodeValToRGB")
    e = base_ramp.color_ramp.elements
    lin = [c ** 2.2 for c in ROCK_RGB]   # Felsfarbe aus dem Luftbild (sRGB -> linear)
    e[0].position, e[0].color = 0.32, (lin[0] * 0.45, lin[1] * 0.45, lin[2] * 0.45, 1)
    e[1].position, e[1].color = 0.72, (lin[0] * 1.35, lin[1] * 1.35, lin[2] * 1.35, 1)
    links.new(texco.outputs["Object"], noise_n.inputs["Vector"])
    links.new(noise_n.outputs["Fac"], base_ramp.inputs["Fac"])

    # leichte Gesteinsschichten (horizontale Baender)
    wave = nodes.new("ShaderNodeTexWave")
    wave.wave_type = "BANDS"
    wave.bands_direction = "Z"
    wave.inputs["Scale"].default_value = 0.9
    wave.inputs["Distortion"].default_value = 6.0
    wave.inputs["Detail"].default_value = 3.0
    links.new(texco.outputs["Object"], wave.inputs["Vector"])
    band_mix = nodes.new("ShaderNodeMix")
    band_mix.data_type = "RGBA"
    band_mix.blend_type = "MULTIPLY"
    band_mix.inputs["Factor"].default_value = 0.18
    links.new(base_ramp.outputs["Color"], band_mix.inputs["A"])
    links.new(wave.outputs["Color"], band_mix.inputs["B"])

    # Hoehlungen dunkler, Kanten heller (Pointiness, nur Cycles - perfekt zum Baken)
    geo = nodes.new("ShaderNodeNewGeometry")
    cav = nodes.new("ShaderNodeValToRGB")
    c = cav.color_ramp.elements
    c[0].position, c[0].color = 0.44, (0.45, 0.45, 0.45, 1)
    c[1].position, c[1].color = 0.56, (1.15, 1.15, 1.15, 1)
    links.new(geo.outputs["Pointiness"], cav.inputs["Fac"])
    cav_mix = nodes.new("ShaderNodeMix")
    cav_mix.data_type = "RGBA"
    cav_mix.blend_type = "MULTIPLY"
    cav_mix.inputs["Factor"].default_value = 1.0
    links.new(band_mix.outputs["Result"], cav_mix.inputs["A"])
    links.new(cav.outputs["Color"], cav_mix.inputs["B"])
    # Kreidespuren (Farbattribut "chalk" am High-Poly)
    chalk_attr = nodes.new("ShaderNodeAttribute")
    chalk_attr.attribute_name = "chalk"
    chalk_fac = nodes.new("ShaderNodeMath")
    chalk_fac.operation = "MULTIPLY"
    chalk_fac.inputs[1].default_value = 0.75
    links.new(chalk_attr.outputs["Fac"], chalk_fac.inputs[0])
    chalk_mix = nodes.new("ShaderNodeMix")
    chalk_mix.data_type = "RGBA"
    chalk_mix.inputs["B"].default_value = (0.8, 0.79, 0.77, 1)
    links.new(chalk_fac.outputs["Value"], chalk_mix.inputs["Factor"])
    links.new(cav_mix.outputs["Result"], chalk_mix.inputs["A"])
    links.new(chalk_mix.outputs["Result"], bsdf.inputs["Base Color"])

    fine = nodes.new("ShaderNodeTexNoise")
    fine.inputs["Scale"].default_value = 30.0
    fine.inputs["Detail"].default_value = 12.0
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.45
    links.new(texco.outputs["Object"], fine.inputs["Vector"])
    links.new(fine.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def bake(low, high):
    os.makedirs(TEX_DIR, exist_ok=True)
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 8
    bk = scene.render.bake
    bk.use_selected_to_active = True
    bk.cage_extrusion = 0.06
    bk.max_ray_distance = 0.2
    bk.margin = 8

    mat = bpy.data.materials.new("wall_baked")
    mat.use_nodes = True
    mat.use_backface_culling = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = next(n for n in nodes if n.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Roughness"].default_value = 0.85
    low.data.materials.clear()
    low.data.materials.append(mat)

    def new_image(suffix, non_color):
        img = bpy.data.images.new(f"{'dufour_wall' if DUFOUR else 'test_wall'}_{suffix}", TEX_W, TEX_H, alpha=False)
        if non_color:
            img.colorspace_settings.name = "Non-Color"
        node = nodes.new("ShaderNodeTexImage")
        node.image = img
        return img, node

    col_img, col_node = new_image("basecolor", False)
    nrm_img, nrm_node = new_image("normal", True)

    bpy.ops.object.select_all(action="DESELECT")
    high.select_set(True)
    low.select_set(True)
    bpy.context.view_layer.objects.active = low
    for img, node, btype, extra in (
        (col_img, col_node, "DIFFUSE", {"pass_filter": {"COLOR"}}),
        (nrm_img, nrm_node, "NORMAL", {}),
    ):
        for n in nodes:
            n.select = False
        node.select = True
        nodes.active = node
        bpy.ops.object.bake(type=btype, **extra)
        img.filepath_raw = os.path.join(TEX_DIR, img.name + ".png")
        img.file_format = "PNG"
        img.save()
        log(f"Gebacken: {btype} -> {img.filepath_raw}")

    links.new(col_node.outputs["Color"], bsdf.inputs["Base Color"])
    nmap = nodes.new("ShaderNodeNormalMap")
    links.new(nrm_node.outputs["Color"], nmap.inputs["Color"])
    links.new(nmap.outputs["Normal"], bsdf.inputs["Normal"])


# ---------------------------------------------------------------- Griffe


def pick_type(z, rnd):
    if z < 4.0:
        w = {"jug": 0.7, "crimp": 0.2, "sloper": 0.1}
    elif 5.8 < z < 8.4:      # Ueberhang: mehr Henkel, sonst unfair
        w = {"jug": 0.5, "crimp": 0.25, "sloper": 0.25}
    else:
        w = {"jug": 0.35, "crimp": 0.35, "sloper": 0.30}
    r = rnd.random()
    for k, v in w.items():
        r -= v
        if r <= 0:
            return k
    return "jug"


def route_center(z):
    """Mittellinie der Route: schlaengelt sich sanft (max. ~0.9 m zur Seite)."""
    return 0.9 * math.sin((z - 1.6) * 0.38)


def layout_grips():
    """Erzeugt eine kletterbare Route: Reihen alle ~0.5 m, Mittellinie schlaengelt sich."""
    rnd = random.Random(SEED)
    grips = [
        {"x": -0.32, "z": 1.65, "type": "jug", "start": 1},
        {"x": 0.32, "z": 1.65, "type": "jug", "start": 1},
    ]
    z, row = 2.1, 0
    while z < TOP - 0.45:
        cx = route_center(z)
        a = {"x": cx + rnd.uniform(-0.4, -0.12), "z": z + rnd.uniform(-0.06, 0.06)}
        b = {"x": cx + rnd.uniform(0.12, 0.4), "z": z + rnd.uniform(-0.06, 0.06)}
        a["type"] = "jug" if row % 4 == 0 else pick_type(z, rnd)
        b["type"] = pick_type(z, rnd)
        grips += [a, b]
        if rnd.random() < 0.5:   # Seitengriff als Alternative
            side = rnd.choice((-1, 1))
            c = {"x": cx + side * rnd.uniform(0.7, 1.1), "z": z + rnd.uniform(-0.15, 0.15)}
            lim = WIDTH / 2 - (1.2 if DUFOUR else 0.4)
            c["x"] = max(-lim, min(lim, c["x"]))
            c["type"] = pick_type(z, rnd)
            grips.append(c)
        z += rnd.uniform(0.38, 0.5)
        row += 1
    # sicherer Ausstieg: zwei Henkel knapp unter dem Gipfelgriff
    cx = route_center(TOP)
    for side in (-1, 1):
        grips.append({"x": cx + side * 0.25, "z": TOP - 0.42, "type": "jug"})
    grips.append({"x": cx, "z": TOP, "type": "jug", "summit": 1})
    return grips


HOLD_WIDTH = {"jug": 0.17, "crimp": 0.13, "sloper": 0.22, "foot": 0.12}


def layout_feet(grips):
    """Tritte fuer die Fuesse: kleine Absaetze entlang der Route, nicht auf Handgriffen."""
    rnd = random.Random(SEED + 1)
    feet = []
    z = 0.3
    while z < TOP - 1.2:
        cx = route_center(z + 1.0)
        for side in (-1, 1):
            x = cx + side * rnd.uniform(0.15, 0.35)
            zz = z + rnd.uniform(-0.06, 0.06)
            if all(math.hypot(x - g["x"], zz - g["z"]) > 0.22 for g in grips):
                feet.append({"x": x, "z": zz, "type": "foot"})
        z += rnd.uniform(0.28, 0.36)
    return feet


def register_holds(grips, feet):
    rnd = random.Random(SEED + 2)
    HOLDS.clear()
    HOLD_BINS.clear()
    for g in grips + feet:
        h = {"x": g["x"], "z": g["z"], "type": g["type"],
             "w": HOLD_WIDTH[g["type"]] * rnd.uniform(0.85, 1.2)}
        HOLDS.append(h)
        b = int(h["z"] / 0.5)
        for k in (b - 1, b, b + 1):
            HOLD_BINS.setdefault(k, []).append(h)


def make_empties(grips, feet):
    """Logikpunkte: grip_* (Haende) und foot_* (Fuesse) auf der Felsform, Ausrichtung = Wandnormale."""
    empties = []
    counters = {}
    for g in grips + feet:
        t = g["type"]
        counters[t] = counters.get(t, 0) + 1
        x, z = g["x"], g["z"]
        n = surface_normal(x, z)                  # Normale der Wand ohne Griff (fuer die Mechanik)
        p = surface_point(x, z)                   # Punkt auf der Griffkante
        zx = n
        xx = Vector((1, 0, 0))
        yx = zx.cross(xx).normalized()
        xx = yx.cross(zx).normalized()
        rot = Matrix((xx, yx, zx)).transposed()
        if t == "foot":
            name = f"foot_{counters[t]:03d}"
        else:
            name = "grip_summit" if g.get("summit") else f"grip_{t}_{counters[t]:03d}"
        e = bpy.data.objects.new(name, None)
        e.empty_display_type = "ARROWS"
        e.empty_display_size = 0.1
        e.matrix_world = Matrix.Translation(p + n * 0.02) @ rot.to_4x4()
        if t == "foot":
            e["foot"] = 1
        else:
            e["grip_type"] = t
            e["start"] = int(g.get("start", 0))
            e["summit"] = int(g.get("summit", 0))
        bpy.context.scene.collection.objects.link(e)
        empties.append(e)
    log(f"{len(empties)} Punkte gesetzt: " + ", ".join(f"{k}={v}" for k, v in counters.items()))
    return empties


# ---------------------------------------------------------------- Szene
def setup_preview_scene():
    scene = bpy.context.scene
    world = bpy.data.worlds.new("sky")
    scene.world = world
    world.use_nodes = True
    wn = world.node_tree.nodes
    bg = next(n for n in wn if n.type == "BACKGROUND")
    sky = wn.new("ShaderNodeTexSky")
    types = [i.identifier for i in sky.bl_rna.properties["sky_type"].enum_items]
    for pref in ("MULTIPLE_SCATTERING", "SINGLE_SCATTERING", "NISHITA", "HOSEK_WILKIE"):
        if pref in types:
            sky.sky_type = pref
            break
    for attr, val in (("sun_elevation", math.radians(35)), ("sun_rotation", math.radians(200))):
        if hasattr(sky, attr):
            setattr(sky, attr, val)
    world.node_tree.links.new(sky.outputs["Color"], bg.inputs["Color"])
    bg.inputs["Strength"].default_value = 0.12

    sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
    sun.data.energy = 3.0
    sun.rotation_euler = (math.radians(55), 0, math.radians(-25))
    scene.collection.objects.link(sun)

    cam = bpy.data.objects.new("camera", bpy.data.cameras.new("camera"))
    cam.data.lens = 28
    cam.location = (6.5, -14.0, 3.0)
    scene.collection.objects.link(cam)
    tgt = bpy.data.objects.new("cam_target", None)
    tgt.location = (0, 0, 6.0)
    scene.collection.objects.link(tgt)
    c = cam.constraints.new("TRACK_TO")
    c.target = tgt
    c.track_axis = "TRACK_NEGATIVE_Z"
    c.up_axis = "UP_Y"
    scene.camera = cam


def render_preview():
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x, scene.render.resolution_y = 1280, 720
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = PNG_PATH
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.exposure = -2.0
    bpy.ops.render.render(write_still=True)
    log(f"Vorschau: {PNG_PATH}")


# ---------------------------------------------------------------- main
def main():
    for coll in (bpy.data.objects, bpy.data.meshes, bpy.data.materials, bpy.data.images,
                 bpy.data.cameras, bpy.data.lights, bpy.data.worlds):
        for block in list(coll):
            coll.remove(block)

    grips = layout_grips()
    feet = layout_feet(grips)
    register_holds(grips, feet)

    high = bpy.data.objects.new("wall_high", grid_mesh("wall_high_mesh", HIGH_STEP, True))
    bpy.context.scene.collection.objects.link(high)
    chalk = high.data.color_attributes.new(name="chalk", type="FLOAT_COLOR", domain="POINT")
    for v in high.data.vertices:
        c = chalk_amount(v.co.x, v.co.z)
        chalk.data[v.index].color = (c, c, c, 1.0)
    high.data.materials.append(make_source_material())
    log(f"High-Poly: {tri_count(high.data)} Dreiecke")

    low = bpy.data.objects.new("wall", high.data.copy())
    low.data.name = "wall_mesh"
    bpy.context.scene.collection.objects.link(low)
    dec = low.modifiers.new("Decimate", "DECIMATE")
    dec.ratio = TARGET_TRIS / tri_count(low.data)
    dec.use_collapse_triangulate = True
    apply_all_modifiers(low)
    planar_uv(low.data)
    for poly in low.data.polygons:
        poly.use_smooth = True
    log(f"Wand (low): {tri_count(low.data)} Dreiecke")

    bake(low, high)
    hm = high.data
    bpy.data.objects.remove(high)
    bpy.data.meshes.remove(hm)

    empties = make_empties(grips, feet)

    col = bpy.data.objects.new("col_wall", grid_mesh("col_wall_mesh", COL_STEP, False))
    bpy.context.scene.collection.objects.link(col)
    bm = bmesh.new()
    bm.from_mesh(col.data)
    bmesh.ops.triangulate(bm, faces=bm.faces[:])
    bm.to_mesh(col.data)
    bm.free()
    col.display_type = "WIRE"
    col.hide_render = True
    col["collider"] = "mesh"
    log(f"col_wall: {tri_count(col.data)} Dreiecke")

    for o in [col] + empties:
        o.parent = low

    setup_preview_scene()
    report.update(wall_tris=tri_count(low.data), col_tris=tri_count(col.data),
                  grips=len(grips), feet=len(feet))

    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=BLEND_PATH)
    log(f"Blend gespeichert: {BLEND_PATH}")

    bpy.ops.object.select_all(action="DESELECT")
    for o in [low, col] + empties:
        o.select_set(True)
    bpy.context.view_layer.objects.active = low
    bpy.ops.export_scene.gltf(
        filepath=GLB_PATH, export_format="GLB", use_selection=True, export_yup=True,
        export_apply=True, export_extras=True, export_cameras=False, export_lights=False,
        export_image_format="WEBP",
    )
    log(f"GLB exportiert: {GLB_PATH}")
    render_preview()


if __name__ == "__main__":
    ok = True
    try:
        main()
    except Exception:
        ok = False
        report["error"] = traceback.format_exc()
        print(report["error"], flush=True)
    report["ok"] = ok
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    sys.exit(0 if ok else 1)
