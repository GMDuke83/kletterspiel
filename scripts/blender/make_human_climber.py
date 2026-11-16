"""
make_human_climber.py - realistische Kletterfigur mit MPFB 2 (MakeHuman fuer Blender).

Voraussetzung: Blender-Erweiterung MPFB 2 installiert (GPL; die erzeugte Figur und die
verwendeten MakeHuman-System-Assets sind CC0) und
assets-src/mpfb/makehuman_system_assets_cc0.zip vorhanden (nicht im Repo).

Aufruf:  blender --background --python scripts/blender/make_human_climber.py
Ausgabe: assets-src/characters/human_climber.blend, public/assets/climber_human.glb,
         previews/climber_human_blender.png

Es werden nur die benoetigten Assets aus dem Zip in MPFBs Benutzerdaten entpackt (Platz sparen).
Figur: junger Mann, athletisch, ~1,78 m; Haut, Augen, Brauen, Wimpern, Kurzhaar;
Kleidung: Oberteil (rot eingefaerbt) + Hose, Bergstiefel; dazu eigene Teile:
Helm, Klettergurt, Rucksack. Skelett: MPFB "game_engine" (inkl. Finger).
"""
import io
import json
import math
import os
import sys
import traceback
import zipfile

import bmesh
import bpy
from mathutils import Matrix, Vector

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ZIP = os.path.join(ROOT, "assets-src", "mpfb", "makehuman_system_assets_cc0.zip")
BLEND = os.path.join(ROOT, "assets-src", "characters", "human_climber.blend")
GLB = os.path.join(ROOT, "public", "assets", "climber_human.glb")
PNG = os.path.join(ROOT, "previews", "climber_human_blender.png")
REPORT = os.path.join(ROOT, "scripts", "blender", "make_human_report.json")
report = {"steps": []}

NEEDED = ("packs/", "skins/young_caucasian_male/", "clothes/male_casualsuit02/", "clothes/shoes03/",
          "hair/short02/", "eyebrows/eyebrow001/", "eyelashes/eyelashes01/", "eyes/")
SKIN = "skins/young_caucasian_male/young_caucasian_male.mhmat"
CLOTHES = ["clothes/male_casualsuit02/male_casualsuit02.mhclo", "clothes/shoes03/shoes03.mhclo"]
# Haare, Brauen, Wimpern haben Alpha-Texturen: im Spiel mit alphaTest (Ausstanzen) statt Transparenz
BODYPARTS = {
    "Hair": "hair/short02/short02.mhclo",
    "Eyebrows": "eyebrows/eyebrow001/eyebrow001.mhclo",
    "Eyelashes": "eyelashes/eyelashes01/eyelashes01.mhclo",
}
ALPHA_PARTS = ("hair", "short02", "eyebrow", "eyelash")
TEX_MAX = 1024   # Texturen fuers Web verkleinern


def log(m):
    print("[make_human]", m, flush=True)
    report["steps"].append(m)


def mpfb():
    """Module der installierten MPFB-Erweiterung finden."""
    import addon_utils
    name = next(m.__name__ for m in addon_utils.modules() if m.__name__.endswith(".mpfb"))
    addon_utils.enable(name, default_set=True)
    import importlib
    return name, importlib


def install_assets(user_data):
    """Nur benoetigte Ordner aus dem System-Asset-Zip entpacken (falls noch nicht vorhanden)."""
    marker = os.path.join(user_data, "packs", "makehuman_system_assets.json")
    if os.path.exists(os.path.join(user_data, SKIN)) and os.path.exists(marker):
        return
    with zipfile.ZipFile(ZIP) as z:
        members = [n for n in z.namelist() if n.startswith(NEEDED)]
        for n in members:
            dst = os.path.join(user_data, n)
            if n.endswith("/"):
                os.makedirs(dst, exist_ok=True)
                continue
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            with open(dst, "wb") as f:
                f.write(z.read(n))
    log(f"{len(members)} Asset-Dateien nach {user_data} entpackt")


def uv_region_masks(obj, w, h, waist_z):
    """Maske im Texturraum: welche Pixel gehoeren zum Oberteil (ueber der Taille), welche zur Hose."""
    import numpy as np
    dg = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(dg)
    me = ev.to_mesh()
    uv = me.uv_layers.active.data
    top = np.zeros((h, w), bool)
    bottom = np.zeros((h, w), bool)
    mw = ev.matrix_world
    for poly in me.polygons:
        z = (mw @ poly.center).z
        target = top if z > waist_z else bottom
        loops = list(poly.loop_indices)
        pts = [uv[i].uv for i in loops]
        for k in range(1, len(pts) - 1):                 # Faecher-Triangulierung
            tri = [pts[0], pts[k], pts[k + 1]]
            xs = [p.x * (w - 1) for p in tri]
            ys = [(1 - p.y) * (h - 1) for p in tri]
            x0, x1 = int(max(0, min(xs))), int(min(w - 1, max(xs) + 1))
            y0, y1 = int(max(0, min(ys))), int(min(h - 1, max(ys) + 1))
            if x1 < x0 or y1 < y0:
                continue
            gx, gy = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
            (ax, bx, cx), (ay, by, cy) = xs, ys
            d = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
            if abs(d) < 1e-9:
                continue
            l1 = ((by - cy) * (gx - cx) + (cx - bx) * (gy - cy)) / d
            l2 = ((cy - ay) * (gx - cx) + (ax - cx) * (gy - cy)) / d
            inside = (l1 >= -0.01) & (l2 >= -0.01) & (1 - l1 - l2 >= -0.01)
            target[y0:y1 + 1, x0:x1 + 1] |= inside
    ev.to_mesh_clear()
    return top, bottom


def recolor_suit(img, obj, waist_z):
    """Oberteil -> rot-orange Kletterjacke, Hose -> dunkelgraue Softshell (getrennt nach Texturbereich)."""
    import numpy as np
    w, h = img.size
    top, bottom = uv_region_masks(obj, w, h, waist_z)
    # Masken leicht vergroessern (Naehte), Bildzeilen: Blender-Pixel beginnen unten
    top = np.flipud(top)
    bottom = np.flipud(bottom)
    for _ in range(3):
        top |= np.roll(top, 1, 0) | np.roll(top, -1, 0) | np.roll(top, 1, 1) | np.roll(top, -1, 1)
        bottom |= np.roll(bottom, 1, 0) | np.roll(bottom, -1, 0) | np.roll(bottom, 1, 1) | np.roll(bottom, -1, 1)
    px = np.array(img.pixels[:], dtype=np.float32).reshape(h, w, 4)
    rgb = px[..., :3]
    lum = rgb @ np.array([0.3, 0.59, 0.11], np.float32)
    jacket = np.stack([lum * 2.1, lum * 0.5, lum * 0.22], -1)
    pants = np.stack([lum * 0.62, lum * 0.66, lum * 0.72], -1)
    only_top = top & ~bottom
    rgb[only_top] = np.clip(jacket[only_top], 0, 1)
    rgb[bottom] = np.clip(pants[bottom], 0, 1)
    px[..., :3] = rgb
    img.pixels[:] = px.reshape(-1)
    img.update()
    return int(only_top.sum()), int(bottom.sum())


def shrink_images():
    for img in bpy.data.images:
        if img.size[0] > TEX_MAX or img.size[1] > TEX_MAX:
            s = TEX_MAX / max(img.size)
            img.scale(int(img.size[0] * s), int(img.size[1] * s))
            img.pack()


def add_gear(rig, body):
    """Helm, Klettergurt, Rucksack: eigene Meshes, starr an Knochen gebunden."""
    pb = {b.name: b for b in rig.data.bones}

    def head_pos(name):
        return rig.matrix_world @ pb[name].head_local

    def tail_pos(name):
        return rig.matrix_world @ pb[name].tail_local

    mats = {}
    for key, col, rough in (("helmet", (0.85, 0.72, 0.04), 0.35), ("harness", (0.02, 0.08, 0.32), 0.6),
                            ("pack", (0.04, 0.14, 0.07), 0.75), ("buckle", (0.6, 0.6, 0.62), 0.3),
                            ("rope", (0.55, 0.05, 0.03), 0.8), ("black", (0.02, 0.02, 0.025), 0.5),
                            ("lens", (0.15, 0.25, 0.35), 0.1), ("lamp", (0.9, 0.9, 0.85), 0.3),
                            ("steel", (0.55, 0.57, 0.6), 0.35), ("axe_shaft", (0.1, 0.2, 0.55), 0.4)):
        m = bpy.data.materials.new(f"gear_{key}")
        m.use_nodes = True
        p = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
        p.inputs["Base Color"].default_value = (*col, 1)
        p.inputs["Roughness"].default_value = rough
        if key in ("buckle", "steel"):
            p.inputs["Metallic"].default_value = 1.0
        mats[key] = m

    objs = []

    def finish(bm, name, mat, bone):
        me = bpy.data.meshes.new(name)
        bm.to_mesh(me)
        bm.free()
        me.materials.append(mats[mat])
        for poly in me.polygons:
            poly.use_smooth = True
        o = bpy.data.objects.new(name, me)
        bpy.context.scene.collection.objects.link(o)
        vg = o.vertex_groups.new(name=bone)
        vg.add(list(range(len(me.vertices))), 1.0, "REPLACE")
        mod = o.modifiers.new("Armature", "ARMATURE")
        mod.object = rig
        o.parent = rig
        objs.append(o)

    # Helm: Schale, die Stirn, Schlaefen und Hinterkopf umschliesst, mit Rand
    head = head_pos("head")
    top = tail_pos("head")
    up = (top - head).normalized()
    hl = (top - head).length
    c = head + up * (hl * 0.48)
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=32, v_segments=16, radius=1.0)
    # vorne hoeher abschneiden (Gesicht frei), hinten tiefer (Hinterkopf bedeckt)
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if v.co.z < (-0.05 if v.co.y < 0 else -0.45)], context="VERTS")
    rx, ry, rz = 0.105, 0.125, 0.105
    for v in bm.verts:
        v.co = Vector((v.co.x * rx, v.co.y * ry + 0.005, v.co.z * rz)) + c
    # Wandstaerke: Schale nach aussen extrudieren
    ret = bmesh.ops.solidify(bm, geom=list(bm.faces), thickness=0.012)
    finish(bm, "helmet", "helmet", "head")

    fwd = Vector((0, -1, 0))   # Figur schaut nach -Y

    def box(center, size, mat, bone, name, bevel=0.0):
        bm = bmesh.new()
        ret = bmesh.ops.create_cube(bm, size=1.0)
        for v in ret["verts"]:
            v.co = Vector((v.co.x * size[0], v.co.y * size[1], v.co.z * size[2])) + center
        if bevel:
            bmesh.ops.bevel(bm, geom=list(bm.edges), offset=bevel, segments=2, affect="EDGES")
        finish(bm, name, mat, bone)

    def ring(center, radius, minor, axis, mat, bone, name, seg=20):
        bm = bmesh.new()
        ret = bmesh.ops.create_cone(bm, cap_ends=False, segments=seg, radius1=radius, radius2=radius, depth=minor)
        if axis == "x":
            bmesh.ops.rotate(bm, verts=ret["verts"], cent=Vector(), matrix=Matrix.Rotation(math.pi / 2, 3, "Y"))
        elif axis == "y":
            bmesh.ops.rotate(bm, verts=ret["verts"], cent=Vector(), matrix=Matrix.Rotation(math.pi / 2, 3, "X"))
        bmesh.ops.translate(bm, verts=ret["verts"], vec=center)
        finish(bm, name, mat, bone)

    # Stirnlampe vorne am Helm + Gummiband
    front = c + fwd * (ry + 0.012) + up * 0.01
    box(front, (0.045, 0.022, 0.03), "black", "head", "headlamp", 0.004)
    box(front + fwd * 0.012, (0.028, 0.004, 0.02), "lamp", "head", "headlamp_lens")
    ring(c + up * 0.005, rx + 0.006, 0.014, "z", "black", "head", "headlamp_band", 28)
    # Gletscherbrille auf dem Helm (hochgeschoben)
    for sx in (-0.03, 0.03):
        box(c + fwd * (ry * 0.75) + up * (rz * 0.72) + Vector((sx, 0, 0)), (0.045, 0.012, 0.028), "lens", "head", f"goggle_{sx > 0}", 0.004)

    # Gurt: Hueftring + zwei Beinschlaufen
    pelvis = head_pos("pelvis")
    bm = bmesh.new()
    for (cx, cz, rx, ry, depth) in ((0.0, -0.035, 0.2, 0.145, 0.045),):
        ret = bmesh.ops.create_cone(bm, cap_ends=False, segments=28, radius1=1, radius2=1, depth=depth)
        for v in ret["verts"]:
            v.co = Vector((cx + v.co.x * rx, v.co.y * ry, v.co.z)) + pelvis + Vector((0, 0.005, cz))
    finish(bm, "harness_waist", "harness", "pelvis")
    for side in ("l", "r"):
        th = head_pos(f"thigh_{side}")
        kn = head_pos(f"calf_{side}")
        p = th + (kn - th) * 0.16
        bm = bmesh.new()
        ret = bmesh.ops.create_cone(bm, cap_ends=False, segments=24, radius1=1, radius2=1, depth=0.035)
        for v in ret["verts"]:
            v.co = Vector((v.co.x * 0.11, v.co.y * 0.115, v.co.z)) + p
        finish(bm, f"harness_leg_{side}", "harness", f"thigh_{side}")
    # Karabiner/Expressen an den Materialschlaufen + Sicherungsgeraet vorne
    for i, ang in enumerate((-2.2, -1.9, 1.9, 2.2)):
        p = pelvis + Vector((math.sin(ang) * 0.2, -math.cos(ang) * 0.15, -0.075))
        ring(p, 0.022, 0.006, "y", "steel", "pelvis", f"carabiner_{i}", 10)
    box(pelvis + Vector((0, -0.165, -0.06)), (0.04, 0.02, 0.05), "steel", "pelvis", "belay_device", 0.005)
    ring(pelvis + Vector((0, -0.16, -0.1)), 0.025, 0.012, "y", "rope", "pelvis", "rope_tiein", 12)

    # Rucksack direkt am Ruecken (Figur schaut nach -Y -> Ruecken bei +Y), mit Volumen und Traegern.
    # Rueckenflaeche: hinterster Punkt des Koerpers auf Brusthoehe
    sp = head_pos("spine_03")
    back_y = max((body.matrix_world @ v.co).y for v in body.data.vertices
                 if abs((body.matrix_world @ v.co).z - sp.z) < 0.08 and abs((body.matrix_world @ v.co).x) < 0.12)
    depth = 0.16
    bm = bmesh.new()
    ret = bmesh.ops.create_cube(bm, size=1.0)
    for v in ret["verts"]:
        v.co = Vector((v.co.x * 0.28, v.co.y * depth, v.co.z * 0.42)) + Vector((0, back_y + 0.015 + depth / 2, sp.z - 0.06))
    bmesh.ops.bevel(bm, geom=list(bm.edges), offset=0.065, segments=5, affect="EDGES")
    finish(bm, "backpack", "pack", "spine_03")
    pack_c = Vector((0, back_y + 0.015 + depth / 2, sp.z - 0.06))
    # Seilpuppe oben auf dem Rucksack
    for k in range(3):
        ring(pack_c + Vector((0, 0.0, 0.25 + k * 0.012)), 0.15 - k * 0.004, 0.012, "z", "rope", "spine_03", f"rope_coil_{k}", 24)
    # Eispickel aussen am Rucksack (Schaft schraeg, Haue oben)
    shaft_c = pack_c + Vector((0.06, depth / 2 + 0.015, 0.02))
    bm = bmesh.new()
    ret = bmesh.ops.create_cone(bm, cap_ends=True, segments=10, radius1=0.013, radius2=0.013, depth=0.55)
    bmesh.ops.rotate(bm, verts=ret["verts"], cent=Vector(), matrix=Matrix.Rotation(math.radians(12), 3, "Y"))
    bmesh.ops.translate(bm, verts=ret["verts"], vec=shaft_c)
    finish(bm, "ice_axe_shaft", "axe_shaft", "spine_03")
    box(shaft_c + Vector((0.06, 0, 0.27)), (0.2, 0.012, 0.03), "steel", "spine_03", "ice_axe_head", 0.004)
    for sx in (-0.085, 0.085):
        bm = bmesh.new()
        ret = bmesh.ops.create_cube(bm, size=1.0)
        front_y = min((body.matrix_world @ v.co).y for v in body.data.vertices
                      if abs((body.matrix_world @ v.co).z - sp.z) < 0.08 and abs((body.matrix_world @ v.co).x - sx) < 0.03)
        # Traeger vorne: von der Schulter bis knapp unter die Brust
        for v in ret["verts"]:
            v.co = Vector((v.co.x * 0.035, v.co.y * 0.012, v.co.z * 0.24)) + Vector((sx, front_y - 0.012, sp.z + 0.1))
        finish(bm, f"strap_{'l' if sx > 0 else 'r'}", "pack", "spine_03")
    log("Ausruestung: Helm mit Stirnlampe und Gletscherbrille, Gurt mit Karabinern, Rucksack mit Seil und Eispickel")
    return objs


def main():
    for c in (bpy.data.objects, bpy.data.meshes, bpy.data.materials, bpy.data.armatures, bpy.data.images):
        for b in list(c):
            c.remove(b)
    pkg, importlib = mpfb()
    LocationService = importlib.import_module(pkg + ".services.locationservice").LocationService
    HumanService = importlib.import_module(pkg + ".services.humanservice").HumanService
    TargetService = importlib.import_module(pkg + ".services.targetservice").TargetService
    AssetService = importlib.import_module(pkg + ".services.assetservice").AssetService

    user_data = LocationService.get_user_data()
    install_assets(user_data)
    AssetService.update_all_asset_lists()

    macro = TargetService.get_default_macro_info_dict()
    macro.update({"gender": 1.0, "age": 0.5, "muscle": 0.72, "weight": 0.48, "height": 0.56,
                  "proportions": 0.6})
    body = HumanService.create_human(macro_detail_dict=macro, feet_on_ground=True, scale=0.1)
    log(f"Mensch erzeugt: {body.name}, Hoehe {body.dimensions.z:.2f} m")

    rig = HumanService.add_builtin_rig(body, "game_engine", import_weights=True)
    log(f"Skelett game_engine: {len(rig.data.bones)} Knochen")

    def asset(rel):
        return os.path.join(user_data, rel)

    HumanService.set_character_skin(asset(SKIN), body, skin_type="MAKESKIN")
    for kind, rel in BODYPARTS.items():
        HumanService.add_mhclo_asset(asset(rel), body, asset_type=kind, subdiv_levels=0, material_type="MAKESKIN")
    # Augen
    eyes = [p for p in AssetService.list_mhclo_assets("eyes")]
    if eyes:
        HumanService.add_mhclo_asset(str(eyes[0]), body, asset_type="Eyes", subdiv_levels=0, material_type="MAKESKIN")
    for rel in CLOTHES:
        HumanService.add_mhclo_asset(asset(rel), body, asset_type="Clothes", subdiv_levels=0, material_type="MAKESKIN")
    log("Haut, Haare, Augen, Kleidung angelegt")

    # Oberteil/Hose umfaerben (Taille: Kopf des Beckenknochens)
    waist_z = (rig.matrix_world @ rig.data.bones["pelvis"].head_local).z + 0.04
    suit = next((o for o in bpy.context.scene.objects if o.type == "MESH" and "casualsuit02" in o.name.lower()), None)
    for img in bpy.data.images:
        if "casualsuit02_diffuse" in img.name and suit:
            s, j = recolor_suit(img, suit, waist_z)
            img.pack()
            log(f"Kleidung eingefaerbt ({s} px Jacke, {j} px Hose)")

    gear = add_gear(rig, body)
    shrink_images()
    for m in bpy.data.materials:
        if not m.use_nodes:
            continue
        for n in m.node_tree.nodes:
            if n.type == "BSDF_PRINCIPLED":
                if any(k in m.name.lower() for k in ALPHA_PARTS):
                    continue          # Alpha behalten (wird im Spiel ausgestanzt)
                a = n.inputs["Alpha"]
                for l in list(a.links):
                    m.node_tree.links.remove(l)
                a.default_value = 1.0
                if not m.name.startswith("gear_"):
                    n.inputs["Roughness"].default_value = 0.85
                    for l in list(n.inputs["Roughness"].links):
                        m.node_tree.links.remove(l)
                    if "Specular IOR Level" in n.inputs:
                        n.inputs["Specular IOR Level"].default_value = 0.3
        try:
            m.surface_render_method = "DITHERED"
        except Exception:
            pass
    log("Materialien undurchsichtig und matt gesetzt")

    # Dreiecke zaehlen (mit Masken-Modifiern ausgewertet)
    dg = bpy.context.evaluated_depsgraph_get()
    tris = 0
    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    for o in meshes:
        me = o.evaluated_get(dg).to_mesh()
        tris += sum(len(p.vertices) - 2 for p in me.polygons)
        o.evaluated_get(dg).to_mesh_clear()
    report["triangles"] = tris
    log(f"Dreiecke gesamt: {tris}")

    os.makedirs(os.path.dirname(BLEND), exist_ok=True)
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=BLEND)

    bpy.ops.object.select_all(action="DESELECT")
    rig.select_set(True)
    for o in meshes:
        o.select_set(True)
    bpy.context.view_layer.objects.active = rig
    bpy.ops.export_scene.gltf(filepath=GLB, export_format="GLB", use_selection=True, export_yup=True,
                              export_skins=True, export_animations=False, export_apply=True,
                              export_image_format="JPEG", export_jpeg_quality=85)
    report["glb_kb"] = os.path.getsize(GLB) // 1024
    report["bones"] = [b.name for b in rig.data.bones]
    log(f"GLB: {GLB} ({report['glb_kb']} KB)")

    # Vorschau
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    cam.location = (1.4, -2.6, 1.2)
    cam.rotation_euler = (math.radians(84), 0, math.radians(28))
    bpy.context.scene.collection.objects.link(cam)
    bpy.context.scene.camera = cam
    sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
    sun.data.energy = 3
    sun.rotation_euler = (math.radians(50), 0, math.radians(30))
    bpy.context.scene.collection.objects.link(sun)
    world = bpy.data.worlds.new("w")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.55, 0.6, 0.66, 1)
    bpy.context.scene.world = world
    sc = bpy.context.scene
    sc.render.engine = "BLENDER_EEVEE"
    sc.render.resolution_x = sc.render.resolution_y = 900
    sc.render.filepath = PNG
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
