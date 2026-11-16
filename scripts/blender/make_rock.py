"""
make_rock.py - erzeugt prozedural einen Test-Felsblock fuer das Kletterspiel.

Aufruf (aus dem Projektordner):
    blender --background --factory-startup --python scripts/blender/make_rock.py

Ergebnis:
    assets-src/walls/test_rock.blend   (Quelldatei)
    public/assets/test_rock.glb        (fuer Three.js, Y-up)
    previews/test_rock.png             (Eevee-Vorschau, 1280x720)
"""
import json
import math
import os
import random
import sys
import traceback

import bmesh
import bpy
from mathutils import Vector

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
BLEND_PATH = os.path.join(ROOT, "assets-src", "walls", "test_rock.blend")
GLB_PATH = os.path.join(ROOT, "public", "assets", "test_rock.glb")
PNG_PATH = os.path.join(ROOT, "previews", "test_rock.png")
REPORT_PATH = os.path.join(ROOT, "scripts", "blender", "make_rock_report.json")

SEED = 42
TARGET_TRIS = 6500        # Ziel fuer das sichtbare Mesh
VOXEL_SIZE = 0.018        # Remesh-Aufloesung in Metern
TEX_SIZE = 2048           # Bake-Aufloesung
TEX_DIR = os.path.join(ROOT, "assets-src", "walls", "textures")
IMAGE_FORMAT = "WEBP"     # Texturen in der GLB (klein, von three.js unterstuetzt)
COL_MAX_TRIS = 400        # Obergrenze fuer das Kollisions-Mesh

report = {"blender": bpy.app.version_string, "steps": []}


def log(msg):
    print("[make_rock]", msg, flush=True)
    report["steps"].append(msg)


def tri_count(mesh):
    return sum(len(p.vertices) - 2 for p in mesh.polygons)


# ---------------------------------------------------------------- Szene
def clear_scene():
    for coll in (bpy.data.objects, bpy.data.meshes, bpy.data.materials, bpy.data.textures,
                 bpy.data.images, bpy.data.cameras, bpy.data.lights,
                 bpy.data.worlds):
        for block in list(coll):
            coll.remove(block)
    log("Szene geleert")


def apply_all_modifiers(obj):
    """Wendet alle Modifier an (ueber den ausgewerteten Depsgraph, ohne Operator)."""
    dg = bpy.context.evaluated_depsgraph_get()
    eval_obj = obj.evaluated_get(dg)
    new_mesh = bpy.data.meshes.new_from_object(eval_obj, preserve_all_data_layers=True,
                                               depsgraph=dg)
    old = obj.data
    name = old.name
    obj.modifiers.clear()
    obj.data = new_mesh
    bpy.data.meshes.remove(old)
    new_mesh.name = name          # Namen ohne .001-Suffix behalten


def make_texture(name, kind, size, **props):
    tex = bpy.data.textures.new(name, type=kind)
    tex.noise_scale = size
    for k, v in props.items():
        if hasattr(tex, k):
            try:
                setattr(tex, k, v)
            except Exception as e:  # Enum-Wert in dieser Version nicht vorhanden
                log(f"Textur {name}: {k}={v} uebersprungen ({e})")
    return tex


def add_displace(obj, tex, strength, mid=0.5):
    mod = obj.modifiers.new(f"Displace_{tex.name}", "DISPLACE")
    mod.texture = tex
    mod.texture_coords = "LOCAL"
    mod.strength = strength
    mod.mid_level = mid
    return mod


# ---------------------------------------------------------------- Fels
def make_rock():
    random.seed(SEED)
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=7, radius=1.0)
    mesh = bpy.data.meshes.new("rock_mesh")
    bm.to_mesh(mesh)
    bm.free()
    rock = bpy.data.objects.new("rock", mesh)
    bpy.context.scene.collection.objects.link(rock)

    # Grundform: etwas breiter als hoch, unten leicht abgeflacht -> ca. 2 m
    for v in mesh.vertices:
        co = v.co
        co.x *= 1.05
        co.y *= 0.85
        co.z *= 0.80
        if co.z < -0.35:                     # flacher Boden, damit er aufliegt
            co.z = -0.35 + (co.z + 0.35) * 0.25

    # Kantige Bruchflaechen: an zufaelligen Ebenen weich abflachen
    for _ in range(14):
        n = Vector((random.uniform(-1, 1), random.uniform(-1, 1), random.uniform(-0.6, 1)))
        n.normalize()
        d = random.uniform(0.55, 0.78)
        for v in mesh.vertices:
            dist = v.co.dot(n)
            if dist > d:
                v.co -= n * (dist - d) * 0.9

    # Displace in mehreren Skalen: grob (Form), mittel (Kanten), fein (Struktur)
    t_big = make_texture("rock_big", "CLOUDS", 1.1, noise_depth=2,
                         noise_basis="ORIGINAL_PERLIN")
    t_facet = make_texture("rock_facets", "VORONOI", 0.55,
                           distance_metric="DISTANCE", color_mode="INTENSITY",
                           weight_1=1.0, weight_2=0.0, noise_intensity=1.0)
    try:
        t_mid = make_texture("rock_mid", "MUSGRAVE", 0.35, musgrave_type="RIDGED_MULTIFRACTAL",
                             octaves=4.0, noise_basis="IMPROVED_PERLIN")
    except Exception as e:
        log(f"MUSGRAVE nicht verfuegbar ({e}), nehme DISTORTED_NOISE")
        t_mid = make_texture("rock_mid", "DISTORTED_NOISE", 0.35, distortion=1.5)
    t_fine = make_texture("rock_fine", "CLOUDS", 0.08, noise_depth=3,
                          noise_type="HARD_NOISE")

    add_displace(rock, t_big, 0.28)
    add_displace(rock, t_facet, 0.06)
    add_displace(rock, t_mid, 0.045)
    add_displace(rock, t_fine, 0.008)
    apply_all_modifiers(rock)
    log(f"Hochaufloesendes Mesh: {tri_count(rock.data)} Dreiecke")

    # Auf ca. 2 m groesste Ausdehnung normieren und auf den Boden stellen
    xs = [v.co for v in rock.data.vertices]
    mn = Vector((min(c.x for c in xs), min(c.y for c in xs), min(c.z for c in xs)))
    mx = Vector((max(c.x for c in xs), max(c.y for c in xs), max(c.z for c in xs)))
    size = mx - mn
    s = 2.0 / max(size)
    center = (mn + mx) / 2
    for v in rock.data.vertices:
        p = (v.co - center) * s
        p.z += size.z * s / 2       # Unterkante auf z = 0
        v.co = p
    rock.data.update()

    # Voxel-Remesh: entfernt Ueberhang-Splitter und Selbstdurchdringungen,
    # danach leicht glaetten, damit keine Voxel-Treppen bleiben
    rem = rock.modifiers.new("Remesh", "REMESH")
    rem.mode = "VOXEL"
    rem.voxel_size = VOXEL_SIZE
    rem.adaptivity = 0.0
    sm = rock.modifiers.new("Smooth", "SMOOTH")
    sm.factor = 0.5
    sm.iterations = 3
    apply_all_modifiers(rock)
    log(f"Nach Voxel-Remesh ({VOXEL_SIZE} m): {tri_count(rock.data)} Dreiecke")

    # Hochaufloesende Kopie fuer das Textur-Baken behalten
    high = rock.copy()
    high.data = rock.data.copy()
    high.name = "rock_high"
    high.data.name = "rock_high_mesh"
    bpy.context.scene.collection.objects.link(high)

    # Decimate auf Zielanzahl
    cur = tri_count(rock.data)
    dec = rock.modifiers.new("Decimate", "DECIMATE")
    dec.decimate_type = "COLLAPSE"
    dec.ratio = min(1.0, TARGET_TRIS / cur)
    dec.use_collapse_triangulate = True
    apply_all_modifiers(rock)
    log(f"Nach Decimate: {tri_count(rock.data)} Dreiecke")

    # Glatt schattieren, harte Kanten ab ~40 Grad (Ersatz fuer das alte Auto-Smooth)
    bpy.context.view_layer.objects.active = rock
    rock.select_set(True)
    rock.data.shade_smooth()
    try:
        bpy.ops.object.shade_smooth_by_angle(angle=math.radians(40), keep_sharp_edges=True)
        log("Smooth by Angle (40 Grad) gesetzt")
    except Exception as e:
        log(f"shade_smooth_by_angle fehlgeschlagen: {e}")
    rock.select_set(False)
    return rock, high


# ---------------------------------------------------------------- Material
def make_material(rock):
    """Prozedurales Quellmaterial (liegt auf dem High-Poly und wird gebacken)."""
    mat = bpy.data.materials.new("rock_procedural")
    mat.use_nodes = True
    nt = mat.node_tree
    nodes, links = nt.nodes, nt.links
    bsdf = next(n for n in nodes if n.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Base Color"].default_value = (0.32, 0.31, 0.30, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.85

    texco = nodes.new("ShaderNodeTexCoord")
    noise = nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 4.0
    noise.inputs["Detail"].default_value = 8.0
    noise.inputs["Roughness"].default_value = 0.6
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.35
    ramp.color_ramp.elements[0].color = (0.18, 0.18, 0.17, 1)
    ramp.color_ramp.elements[1].position = 0.75
    ramp.color_ramp.elements[1].color = (0.46, 0.45, 0.43, 1)
    links.new(texco.outputs["Object"], noise.inputs["Vector"])
    links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])

    # Feine Oberflaechenstruktur per Bump
    fine = nodes.new("ShaderNodeTexNoise")
    fine.inputs["Scale"].default_value = 25.0
    fine.inputs["Detail"].default_value = 10.0
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.35
    links.new(texco.outputs["Object"], fine.inputs["Vector"])
    links.new(fine.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])

    # Leicht schwankende Rauheit um 0.85
    rmap = nodes.new("ShaderNodeMapRange")
    rmap.inputs["To Min"].default_value = 0.78
    rmap.inputs["To Max"].default_value = 0.92
    links.new(fine.outputs["Fac"], rmap.inputs["Value"])
    links.new(rmap.outputs["Result"], bsdf.inputs["Roughness"])

    rock.data.materials.append(mat)
    log("Prozedurales Material rock_procedural (Roughness ~0.85) zugewiesen")
    return mat


# ---------------------------------------------------------------- Bake
def smart_uv(obj):
    bpy.ops.object.select_all(action="DESELECT")
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=0.004)
    bpy.ops.object.mode_set(mode="OBJECT")
    log("UVs per Smart UV Project erzeugt")


def bake_textures(low, high):
    """Backt Farbe, Normalen und Rauheit vom High-Poly auf das Low-Poly-Mesh."""
    os.makedirs(TEX_DIR, exist_ok=True)
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 8
    bk = scene.render.bake
    bk.use_selected_to_active = True
    bk.cage_extrusion = 0.04
    bk.max_ray_distance = 0.12
    bk.margin = 16

    mat = bpy.data.materials.new("rock_baked")
    mat.use_nodes = True
    mat.use_backface_culling = True       # glTF: einseitig (doubleSided = false)
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = next(n for n in nodes if n.type == "BSDF_PRINCIPLED")
    low.data.materials.clear()
    low.data.materials.append(mat)

    def new_image(suffix, non_color):
        img = bpy.data.images.new(f"test_rock_{suffix}", TEX_SIZE, TEX_SIZE, alpha=False)
        if non_color:
            img.colorspace_settings.name = "Non-Color"
        node = nodes.new("ShaderNodeTexImage")
        node.image = img
        return img, node

    col_img, col_node = new_image("basecolor", False)
    nrm_img, nrm_node = new_image("normal", True)
    rgh_img, rgh_node = new_image("roughness", True)

    bpy.ops.object.select_all(action="DESELECT")
    high.select_set(True)
    low.select_set(True)
    bpy.context.view_layer.objects.active = low

    for img, node, btype, extra in (
        (col_img, col_node, "DIFFUSE", {"pass_filter": {"COLOR"}}),
        (nrm_img, nrm_node, "NORMAL", {}),
        (rgh_img, rgh_node, "ROUGHNESS", {}),
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

    # Gebackene Bilder ins Material einhaengen (glTF-tauglich)
    links.new(col_node.outputs["Color"], bsdf.inputs["Base Color"])
    links.new(rgh_node.outputs["Color"], bsdf.inputs["Roughness"])
    nmap = nodes.new("ShaderNodeNormalMap")
    links.new(nrm_node.outputs["Color"], nmap.inputs["Color"])
    links.new(nmap.outputs["Normal"], bsdf.inputs["Normal"])

    # High-Poly wird nicht mehr gebraucht
    hm = high.data
    bpy.data.objects.remove(high)
    bpy.data.meshes.remove(hm)
    log("Material rock_baked (Base Color + Normal + Roughness, 2K) zugewiesen")


# ---------------------------------------------------------------- Griffe
def add_grips(rock):
    """Schiesst Strahlen von aussen auf den Fels und setzt Empties auf die Treffer."""
    dg = bpy.context.evaluated_depsgraph_get()
    center = Vector((0, 0, 0.55))
    dirs = [Vector((0.9, -0.6, 0.35)), Vector((-0.4, -1.0, 0.1)), Vector((0.2, -0.7, 0.9))]
    grips = []
    for i, d in enumerate(dirs, start=1):
        d.normalize()
        origin = center + d * 5.0
        hit, loc, normal, _idx = rock.ray_cast(origin, -d, depsgraph=dg)
        if not hit:
            log(f"Griff {i}: kein Treffer, nehme Ersatzposition")
            loc, normal = center + d, d
        e = bpy.data.objects.new(f"grip_jug_{i:03d}", None)
        e.empty_display_type = "ARROWS"
        e.empty_display_size = 0.15
        e.location = loc + normal * 0.01
        # lokale Z-Achse zeigt von der Oberflaeche weg
        e.rotation_euler = normal.to_track_quat("Z", "Y").to_euler()
        e["grip_type"] = "jug"
        bpy.context.scene.collection.objects.link(e)
        e.parent = rock
        grips.append(e)
        log(f"{e.name} bei {tuple(round(c, 3) for c in loc)}")
    return grips


# ---------------------------------------------------------------- Kollision
def make_collision(rock):
    bm = bmesh.new()
    bm.from_mesh(rock.data)
    hull = bmesh.ops.convex_hull(bm, input=bm.verts[:])
    # alles entfernen, was nicht zur Huelle gehoert
    keep = set(hull["geom"])
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if v not in keep], context="VERTS")
    bmesh.ops.triangulate(bm, faces=bm.faces[:])
    mesh = bpy.data.meshes.new("col_rock_mesh")
    bm.to_mesh(mesh)
    bm.free()
    col = bpy.data.objects.new("col_rock", mesh)
    bpy.context.scene.collection.objects.link(col)
    log(f"Konvexe Huelle roh: {tri_count(mesh)} Dreiecke")

    if tri_count(mesh) > COL_MAX_TRIS:
        dec = col.modifiers.new("Decimate", "DECIMATE")
        dec.ratio = COL_MAX_TRIS / tri_count(mesh) * 0.9
        apply_all_modifiers(col)
        # erneut konvex machen (Decimate kann kleine Dellen erzeugen)
        bm = bmesh.new()
        bm.from_mesh(col.data)
        hull = bmesh.ops.convex_hull(bm, input=bm.verts[:])
        keep = set(hull["geom"])
        bmesh.ops.delete(bm, geom=[v for v in bm.verts if v not in keep], context="VERTS")
        bmesh.ops.triangulate(bm, faces=bm.faces[:])
        bm.to_mesh(col.data)
        bm.free()

    col.display_type = "WIRE"
    col.hide_render = True
    col["collider"] = "convex"
    col.parent = rock
    log(f"col_rock: {tri_count(col.data)} Dreiecke")
    return col


# ---------------------------------------------------------------- Licht/Kamera
def setup_world_and_camera():
    scene = bpy.context.scene
    world = bpy.data.worlds.new("sky")
    scene.world = world
    world.use_nodes = True
    wn = world.node_tree.nodes
    bg = next(n for n in wn if n.type == "BACKGROUND")
    sky = wn.new("ShaderNodeTexSky")
    # Sky-Typ je nach Version waehlen (Nishita bis 4.x, neue Namen ab 5.0)
    types = [i.identifier for i in sky.bl_rna.properties["sky_type"].enum_items]
    log(f"Sky-Typen verfuegbar: {types}")
    for pref in ("MULTIPLE_SCATTERING", "SINGLE_SCATTERING", "NISHITA", "HOSEK_WILKIE", "PREETHAM"):
        if pref in types:
            sky.sky_type = pref
            break
    for attr, val in (("sun_elevation", math.radians(35)), ("sun_rotation", math.radians(140))):
        if hasattr(sky, attr):
            setattr(sky, attr, val)
    world.node_tree.links.new(sky.outputs["Color"], bg.inputs["Color"])
    bg.inputs["Strength"].default_value = 0.12

    sun_data = bpy.data.lights.new("sun", "SUN")
    sun_data.energy = 3.0
    sun_data.angle = math.radians(1.5)
    sun = bpy.data.objects.new("sun", sun_data)
    sun.rotation_euler = (math.radians(55), 0, math.radians(140 - 90))
    scene.collection.objects.link(sun)

    cam_data = bpy.data.cameras.new("camera")
    cam_data.lens = 55
    cam = bpy.data.objects.new("camera", cam_data)
    cam.location = (3.6, -4.0, 2.2)
    scene.collection.objects.link(cam)
    target = bpy.data.objects.new("cam_target", None)
    target.location = (0, 0, 0.5)
    scene.collection.objects.link(target)
    c = cam.constraints.new("TRACK_TO")
    c.target = target
    c.track_axis = "TRACK_NEGATIVE_Z"
    c.up_axis = "UP_Y"
    scene.camera = cam
    return cam, sun, target


# ---------------------------------------------------------------- Export
def export_glb(rock):
    bpy.ops.object.select_all(action="DESELECT")
    rock.select_set(True)
    for ch in rock.children:
        ch.select_set(True)
    bpy.context.view_layer.objects.active = rock
    bpy.ops.export_scene.gltf(
        filepath=GLB_PATH,
        export_format="GLB",
        use_selection=True,          # nur Fels, Griffe, Kollision (keine Kamera/Hilfsobjekte)
        export_yup=True,
        export_apply=True,
        export_extras=True,          # grip_type / collider als glTF extras
        export_cameras=False,
        export_lights=False,
        export_image_format=IMAGE_FORMAT,
        export_jpeg_quality=90,
    )
    log(f"GLB exportiert: {GLB_PATH}")


def render_preview():
    scene = bpy.context.scene
    # Hilfsboden nur fuer das Vorschaubild (wird nicht gespeichert/exportiert)
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=12)
    gmesh = bpy.data.meshes.new("preview_ground")
    bm.to_mesh(gmesh)
    bm.free()
    gmat = bpy.data.materials.new("preview_ground")
    gmat.use_nodes = True
    gb = next(n for n in gmat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    gb.inputs["Base Color"].default_value = (0.25, 0.22, 0.18, 1)
    gb.inputs["Roughness"].default_value = 0.95
    gmesh.materials.append(gmat)
    ground = bpy.data.objects.new("preview_ground", gmesh)
    scene.collection.objects.link(ground)

    engines = [i.identifier for i in scene.render.bl_rna.properties["engine"].enum_items]
    log(f"Render-Engines: {engines}")
    eevee = "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in engines else "BLENDER_EEVEE"
    scene.render.resolution_x = 1280
    scene.render.resolution_y = 720
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = PNG_PATH
    try:
        scene.view_settings.view_transform = "AgX"
        scene.view_settings.exposure = -2.0
    except Exception:
        pass

    try:
        scene.render.engine = eevee
        try:
            scene.eevee.taa_render_samples = 64
        except Exception:
            pass
        bpy.ops.render.render(write_still=True)
        report["render_engine"] = eevee
    except Exception as e:
        log(f"Eevee-Render fehlgeschlagen ({e}), versuche Cycles (CPU)")
        scene.render.engine = "CYCLES"
        scene.cycles.device = "CPU"
        scene.cycles.samples = 64
        bpy.ops.render.render(write_still=True)
        report["render_engine"] = "CYCLES (Fallback)"
    log(f"Vorschau gerendert mit {report['render_engine']}: {PNG_PATH}")


# ---------------------------------------------------------------- main
def main():
    clear_scene()
    rock, high = make_rock()
    make_material(high)
    smart_uv(rock)
    bake_textures(rock, high)
    add_grips(rock)
    col = make_collision(rock)
    setup_world_and_camera()

    report["rock_tris"] = tri_count(rock.data)
    report["col_tris"] = tri_count(col.data)
    dims = rock.dimensions
    report["rock_dimensions_m"] = [round(d, 3) for d in dims]

    bpy.context.preferences.filepaths.save_version = 0   # keine .blend1-Backups
    bpy.ops.wm.save_as_mainfile(filepath=BLEND_PATH)
    log(f"Blend gespeichert: {BLEND_PATH}")
    export_glb(rock)
    render_preview()      # nach dem Speichern, damit der Hilfsboden nicht im .blend landet


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
