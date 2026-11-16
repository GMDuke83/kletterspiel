"""
make_climber.py - baut eine eigene, stilisierte Kletterfigur (1,75 m) mit Skelett.
Keine fremden Assets: Koerper per Skin-Modifier aus einem Gelenk-Graphen, eigene Gewichte.

Aufruf:  blender --background --factory-startup --python scripts/blender/make_climber.py
Ausgabe: assets-src/characters/climber.blend, public/assets/climber.glb, previews/climber_blender.png

Konventionen (Blender): Figur steht auf z = 0, schaut nach -Y (im glTF/three.js: nach +Z),
".L" = linke Koerperseite der Figur = +X.  Knochen zeigen entlang ihrer lokalen +Y-Achse.
Knochen: hips, spine, chest, neck, head, shoulder.L/R, upper_arm.L/R, forearm.L/R, hand.L/R,
         thigh.L/R, shin.L/R, foot.L/R
"""
import json
import math
import os
import sys
import traceback

import bmesh
import bpy
from mathutils import Vector

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
BLEND = os.path.join(ROOT, "assets-src", "characters", "climber.blend")
GLB = os.path.join(ROOT, "public", "assets", "climber.glb")
PNG = os.path.join(ROOT, "previews", "climber_blender.png")
REPORT = os.path.join(ROOT, "scripts", "blender", "make_climber_report.json")
report = {"steps": []}


def log(m):
    print("[make_climber]", m, flush=True)
    report["steps"].append(m)


V = Vector
# ------------------------------------------------------------- Gelenke (m)
J = {
    "pelvis": V((0, 0, 0.97)), "spine": V((0, 0.01, 1.15)), "chest": V((0, 0.0, 1.33)),
    "neck": V((0, 0.01, 1.50)), "head": V((0, 0, 1.60)), "head_top": V((0, 0, 1.75)),
}
for s, x in (("L", 1), ("R", -1)):
    J[f"clav.{s}"] = V((0.05 * x, 0.0, 1.43))
    J[f"shoulder.{s}"] = V((0.19 * x, 0.01, 1.43))
    J[f"elbow.{s}"] = V((0.29 * x, 0.03, 1.16))
    J[f"wrist.{s}"] = V((0.37 * x, 0.0, 0.92))
    J[f"hand_end.{s}"] = V((0.40 * x, -0.01, 0.83))
    J[f"hip.{s}"] = V((0.095 * x, 0.0, 0.93))
    J[f"knee.{s}"] = V((0.105 * x, -0.03, 0.51))
    J[f"ankle.{s}"] = V((0.11 * x, 0.02, 0.09))
    J[f"toe.{s}"] = V((0.12 * x, -0.13, 0.03))

BONES = [  # name, head, tail, parent
    ("hips", "pelvis", "spine", None), ("spine", "spine", "chest", "hips"),
    ("chest", "chest", "neck", "spine"), ("neck", "neck", "head", "chest"),
    ("head", "head", "head_top", "neck"),
]
for s in ("L", "R"):
    BONES += [
        (f"shoulder.{s}", f"clav.{s}", f"shoulder.{s}", "chest"),
        (f"upper_arm.{s}", f"shoulder.{s}", f"elbow.{s}", f"shoulder.{s}"),
        (f"forearm.{s}", f"elbow.{s}", f"wrist.{s}", f"upper_arm.{s}"),
        (f"hand.{s}", f"wrist.{s}", f"hand_end.{s}", f"forearm.{s}"),
        (f"thigh.{s}", f"hip.{s}", f"knee.{s}", "hips"),
        (f"shin.{s}", f"knee.{s}", f"ankle.{s}", f"thigh.{s}"),
        (f"foot.{s}", f"ankle.{s}", f"toe.{s}", f"shin.{s}"),
    ]

# Koerper-Graph fuer den Skin-Modifier: (Gelenk, Radius x, Radius y)
SKIN = {
    "pelvis": (0.15, 0.11), "spine": (0.14, 0.10), "chest": (0.17, 0.115), "neck": (0.055, 0.055),
    "head": (0.05, 0.05),
}
for s in ("L", "R"):
    SKIN.update({
        f"clav.{s}": (0.07, 0.07), f"shoulder.{s}": (0.06, 0.06), f"elbow.{s}": (0.045, 0.045),
        f"wrist.{s}": (0.035, 0.03), f"hand_end.{s}": (0.04, 0.02),
        f"hip.{s}": (0.085, 0.085), f"knee.{s}": (0.058, 0.058), f"ankle.{s}": (0.045, 0.045),
        f"toe.{s}": (0.045, 0.03),
    })
EDGES = [("pelvis", "spine"), ("spine", "chest"), ("chest", "neck"), ("neck", "head")]
for s in ("L", "R"):
    EDGES += [("chest", f"clav.{s}"), (f"clav.{s}", f"shoulder.{s}"), (f"shoulder.{s}", f"elbow.{s}"),
              (f"elbow.{s}", f"wrist.{s}"), (f"wrist.{s}", f"hand_end.{s}"),
              ("pelvis", f"hip.{s}"), (f"hip.{s}", f"knee.{s}"), (f"knee.{s}", f"ankle.{s}"),
              (f"ankle.{s}", f"toe.{s}")]

COLORS = {  # Basisfarbe (linear), Rauheit
    "jacket": ((0.62, 0.09, 0.03), 0.65),   # rot-orange Hardshell
    "pants": ((0.035, 0.045, 0.06), 0.85),  # dunkle Hose
    "shoe": ((0.03, 0.03, 0.03), 0.7),
    "skin": ((0.58, 0.36, 0.25), 0.6),
    "helmet": ((0.85, 0.75, 0.05), 0.35),   # gelber Helm
    "harness": ((0.02, 0.1, 0.35), 0.6),    # blauer Gurt
    "glove": ((0.12, 0.12, 0.12), 0.8),
    "pack": ((0.05, 0.16, 0.08), 0.75),     # kleiner gruener Rucksack (zeigt, wo hinten ist)
}
BONE_MAT = {"hips": "pants", "spine": "jacket", "chest": "jacket", "neck": "skin", "head": "skin"}
for s in ("L", "R"):
    BONE_MAT.update({f"shoulder.{s}": "jacket", f"upper_arm.{s}": "jacket", f"forearm.{s}": "jacket",
                     f"hand.{s}": "glove", f"thigh.{s}": "pants", f"shin.{s}": "pants", f"foot.{s}": "shoe"})


def seg_dist(p, a, b):
    ab = b - a
    t = max(0.0, min(1.0, (p - a).dot(ab) / ab.length_squared))
    return (a + ab * t - p).length


def apply_mods(obj):
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(obj.evaluated_get(dg), depsgraph=dg)
    old = obj.data
    obj.modifiers.clear()
    obj.data = me
    bpy.data.meshes.remove(old)


def main():
    for c in (bpy.data.objects, bpy.data.meshes, bpy.data.materials, bpy.data.armatures):
        for b in list(c):
            c.remove(b)
    scene = bpy.context.scene

    # ------------------------------------------------ Skelett
    arm_data = bpy.data.armatures.new("climber_rig")
    rig = bpy.data.objects.new("climber_rig", arm_data)
    scene.collection.objects.link(rig)
    bpy.context.view_layer.objects.active = rig
    rig.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    eb = {}
    for name, h, t, parent in BONES:
        b = arm_data.edit_bones.new(name)
        b.head, b.tail = J[h], J[t]
        if parent:
            b.parent = eb[parent]
            b.use_connect = False
        eb[name] = b
    # Roll so, dass lokale Z-Achsen grob nach vorne (-Y) zeigen -> ruhige Verdrehung
    for b in arm_data.edit_bones:
        b.align_roll(V((0, -1, 0)))
    bpy.ops.object.mode_set(mode="OBJECT")
    segs = {name: (J[h], J[t]) for name, h, t, _ in BONES}
    log(f"Skelett: {len(BONES)} Knochen")

    # ------------------------------------------------ Koerper (Skin-Modifier)
    names = list(SKIN.keys())
    me = bpy.data.meshes.new("body")
    me.from_pydata([J[n] for n in names], [(names.index(a), names.index(b)) for a, b in EDGES], [])
    body = bpy.data.objects.new("climber_body", me)
    scene.collection.objects.link(body)
    skin_mod = body.modifiers.new("Skin", "SKIN")
    sv = me.skin_vertices[0].data
    for i, n in enumerate(names):
        sv[i].radius = SKIN[n]
        sv[i].use_root = (n == "pelvis")
    sub = body.modifiers.new("Sub", "SUBSURF")
    sub.levels = 2
    apply_mods(body)

    # Kopf: eigene Kugel (runder als der Skin-Graph), Helm, Gurt
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=24, v_segments=16, radius=1.0)
    for v in bm.verts:
        v.co = V((v.co.x * 0.085, v.co.y * 0.10, v.co.z * 0.115)) + V((0, -0.005, 1.635))
    head_mesh = bpy.data.meshes.new("head")
    bm.to_mesh(head_mesh)
    bm.free()

    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=24, v_segments=12, radius=1.0)
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if v.co.z < -0.15], context="VERTS")
    for v in bm.verts:
        v.co = V((v.co.x * 0.105, v.co.y * 0.12, v.co.z * 0.10)) + V((0, 0.0, 1.67))
    helmet_mesh = bpy.data.meshes.new("helmet")
    bm.to_mesh(helmet_mesh)
    bm.free()

    bm = bmesh.new()
    bmesh.ops.create_circle(bm, segments=1, radius=0.0)  # nur um bm zu initialisieren
    bm.clear()
    harness_parts = [((0, 0.0, 0.93), 0.155, 0.11), ((0.095, 0.0, 0.84), 0.085, 0.085), ((-0.095, 0.0, 0.84), 0.085, 0.085)]
    for (cx, cy, cz), rx, ry in harness_parts:
        ret = bmesh.ops.create_cone(bm, cap_ends=False, segments=20, radius1=1.0, radius2=1.0, depth=0.045)
        for v in ret["verts"]:
            v.co = V((cx + v.co.x * rx * 1.07, cy + v.co.y * ry * 1.07, cz + v.co.z))
    harness_mesh = bpy.data.meshes.new("harness")
    bm.to_mesh(harness_mesh)
    bm.free()

    bm = bmesh.new()
    ret = bmesh.ops.create_cube(bm, size=1.0)
    for v in ret["verts"]:
        v.co = V((v.co.x * 0.25, v.co.y * 0.11, v.co.z * 0.34)) + V((0, 0.165, 1.27))
    bmesh.ops.bevel(bm, geom=list(bm.edges), offset=0.03, segments=3, affect="EDGES")
    pack_mesh = bpy.data.meshes.new("pack")
    bm.to_mesh(pack_mesh)
    bm.free()

    # Alles in ein Objekt, Materialien je Teil
    mats = {}
    for key, (col, rough) in COLORS.items():
        m = bpy.data.materials.new(f"climber_{key}")
        m.use_nodes = True
        p = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
        p.inputs["Base Color"].default_value = (*col, 1)
        p.inputs["Roughness"].default_value = rough
        mats[key] = m
    order = list(COLORS.keys())
    for key in order:
        body.data.materials.append(mats[key])

    def bone_of(p):
        return min(segs, key=lambda n: seg_dist(p, *segs[n]))

    for poly in body.data.polygons:
        c = poly.center
        name = bone_of(c)
        # saubere Saeume: nach Hoehe statt nach Knochen (ausser Haende/Fuesse)
        if name.startswith("hand"):
            key = "glove"
        elif name.startswith("foot") or c.z < 0.11:
            key = "shoe"
        elif c.z > 1.485 and abs(c.x) < 0.09:
            key = "skin"
        elif c.z > 0.955 or name.startswith(("upper_arm", "forearm", "shoulder")):
            key = "jacket"
        else:
            key = "pants"
        poly.material_index = order.index(key)
        poly.use_smooth = True

    extra = []
    for mesh, key in ((head_mesh, "skin"), (helmet_mesh, "helmet"), (harness_mesh, "harness"), (pack_mesh, "pack")):
        o = bpy.data.objects.new(mesh.name, mesh)
        scene.collection.objects.link(o)
        mesh.materials.append(mats[key])
        for poly in mesh.polygons:
            poly.use_smooth = True
        extra.append(o)
    bpy.ops.object.select_all(action="DESELECT")
    for o in [body] + extra:
        o.select_set(True)
    bpy.context.view_layer.objects.active = body
    bpy.ops.object.join()
    # Materialindizes der angehaengten Teile auf die gemeinsame Liste abbilden
    log(f"Koerper: {sum(len(p.vertices) - 2 for p in body.data.polygons)} Dreiecke")

    # ------------------------------------------------ Gewichte (eigene, nach Abstand zu den Knochen)
    groups = {n: body.vertex_groups.new(name=n) for n in segs}
    for v in body.data.vertices:
        p = v.co
        if p.z > 1.56:                       # Kopf, Helm: starr am Kopf
            groups["head"].add([v.index], 1.0, "REPLACE")
            continue
        if p.y > 0.12 and 1.08 < p.z < 1.46 and abs(p.x) < 0.15:   # Rucksack starr an der Brust
            groups["chest"].add([v.index], 1.0, "REPLACE")
            continue
        d = sorted(((seg_dist(p, *segs[n]), n) for n in segs))
        near = [(dd, n) for dd, n in d[:3] if dd < d[0][0] * 1.7 + 0.015]
        w = [(1.0 / (dd + 0.01) ** 4, n) for dd, n in near]
        tot = sum(x for x, _ in w)
        for x, n in w:
            groups[n].add([v.index], x / tot, "REPLACE")
    mod = body.modifiers.new("Armature", "ARMATURE")
    mod.object = rig
    body.parent = rig
    log("Gewichte gesetzt (max. 3 Knochen je Punkt)")

    # ------------------------------------------------ Speichern, Export, Vorschau
    os.makedirs(os.path.dirname(BLEND), exist_ok=True)
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=BLEND)
    bpy.ops.object.select_all(action="DESELECT")
    rig.select_set(True)
    body.select_set(True)
    bpy.context.view_layer.objects.active = rig
    bpy.ops.export_scene.gltf(filepath=GLB, export_format="GLB", use_selection=True, export_yup=True,
                              export_skins=True, export_animations=False, export_apply=False)
    report["triangles"] = sum(len(p.vertices) - 2 for p in body.data.polygons)
    log(f"GLB: {GLB} ({os.path.getsize(GLB) // 1024} KB)")

    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    cam.location = (1.6, -3.2, 1.3)
    cam.rotation_euler = (math.radians(86), 0, math.radians(27))
    scene.collection.objects.link(cam)
    scene.camera = cam
    sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
    sun.rotation_euler = (math.radians(50), 0, math.radians(30))
    scene.collection.objects.link(sun)
    world = bpy.data.worlds.new("w")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.6, 0.65, 0.7, 1)
    scene.world = world
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x, scene.render.resolution_y = 800, 800
    scene.render.filepath = PNG
    bpy.ops.render.render(write_still=True)
    log(f"Vorschau: {PNG}")


if __name__ == "__main__":
    ok = True
    try:
        main()
    except Exception:
        ok = False
        report["error"] = traceback.format_exc()
        print(report["error"], flush=True)
    report["ok"] = ok
    json.dump(report, open(REPORT, "w", encoding="utf-8"), indent=2)
    sys.exit(0 if ok else 1)
