"""Render our exact lifting arrays with an original continuous torso surface.
Run: blender -b -t 4 --python scripts/render_lifting.py -- --data ... --out ...
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector

p = argparse.ArgumentParser()
p.add_argument("--data", type=Path, required=True)
p.add_argument("--out", type=Path, required=True)
p.add_argument("--preview", action="store_true")
p.add_argument("--step", type=int, default=6)
a = p.parse_args(sys.argv[sys.argv.index("--") + 1 :])
bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)
scene = bpy.context.scene
scene.render.engine = "CYCLES"
scene.cycles.samples = 8
scene.cycles.use_denoising = False
scene.render.resolution_x = 384
scene.render.resolution_y = 384
scene.render.resolution_percentage = 100
scene.world.color = (0.45, 0.45, 0.45)
scene.view_settings.view_transform = "Standard"


def material(name, color):
    m = bpy.data.materials.new(name)
    m.diffuse_color = (*color, 1)
    m.use_nodes = True
    m.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (
        *color,
        1,
    )
    m.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.8
    return m


blue = material("Original blue mannequin", (0.09, 0.43, 0.64))
skin = material("Head and hands", (0.64, 0.43, 0.28))
orange = material("Five lumbar model links", (0.96, 0.41, 0.06))
boxmat = material("Unweighted demonstration box", (0.54, 0.32, 0.10))
gray = material("Floor and raised support", (0.42, 0.46, 0.49))
green = material("Pelvis axis", (0.08, 0.8, 0.2))


def sphere(name, mat):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=16, ring_count=8)
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(mat)
    for poly in obj.data.polygons:
        poly.use_smooth = True
    return obj


def link(obj, start, end, radius):
    d = Vector(end - start)
    obj.location = (start + end) / 2
    obj.rotation_mode = "QUATERNION"
    obj.rotation_quaternion = d.to_track_quat("Z", "Y")
    obj.scale = (radius, radius, d.length / 2 + radius * 0.25)


bpy.ops.mesh.primitive_plane_add(size=200)
floor = bpy.context.object
floor.data.materials.append(gray)
bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0.40, 0.215))
support = bpy.context.object
support.scale = (0.32, 0.25, 0.43)
support.data.materials.append(gray)
bpy.ops.mesh.primitive_cube_add(size=1)
box = bpy.context.object
box.scale = (0.38, 0.24, 0.22)
box.data.materials.append(boxmat)
bpy.ops.object.light_add(type="AREA", location=(3, -3, 6))
bpy.context.object.data.energy = 600
bpy.context.object.data.shape = "DISK"
bpy.context.object.data.size = 5
bpy.ops.object.camera_add()
camera = bpy.context.object
camera.data.type = "ORTHO"
camera.data.ortho_scale = 2.1
scene.camera = camera


def view(position):
    camera.location = position
    camera.rotation_euler = (
        (Vector((0, 0.1, 0.90)) - camera.location).to_track_quat("-Z", "Y").to_euler()
    )


objects = {}
for name in ["neck", "head"] + [
    f"{part}_{s}"
    for s in ["R", "L"]
    for part in ["thigh", "shank", "foot", "humerus", "forearm", "hand"]
]:
    objects[name] = sphere(
        name, skin if name == "head" or name.startswith("hand") else blue
    )
# Curved lumbar axis is visible on the posterior surface, separate from the
# actual centerline saved in the NPZ. It is a review overlay, not vertebral anatomy.
markers = [sphere(f"lumbar review marker {i}", orange) for i in range(6)]
axis = sphere("Pelvis anterior direction review overlay", green)
mesh = bpy.data.meshes.new("Continuous original torso rings")
torso = bpy.data.objects.new("Curved torso", mesh)
scene.collection.objects.link(torso)
mesh.materials.append(blue)
N = 24
faces = []
for j in range(8):
    for k in range(N):
        faces.append(
            (j * N + k, j * N + (k + 1) % N, (j + 1) * N + (k + 1) % N, (j + 1) * N + k)
        )
faces.extend([tuple(reversed(range(N))), tuple(8 * N + k for k in range(N))])
mesh.from_pydata([(0, 0, 0)] * (9 * N), [], faces)
for poly in mesh.polygons:
    poly.use_smooth = True

manifest = {}
for folder in sorted(a.data.iterdir()):
    if not (folder / "motion.npz").exists():
        continue
    data = np.load(folder / "motion.npz", allow_pickle=False)
    names = list(data["joint_names"])
    ix = {n: i for i, n in enumerate(names)}
    frames = [108] if a.preview else list(range(0, len(data["time_s"]), a.step))
    manifest[folder.name] = {
        "motion_sha256": hashlib.sha256(
            (folder / "motion.npz").read_bytes()
        ).hexdigest(),
        "source_frames": frames,
        "source_fps": int(data["source_fps"]),
    }
    for f in frames:
        p0 = data["joint_positions_world"][f]
        e = data["endpoints_world"][f]
        r = data["global_rots"][f]
        for name, obj in objects.items():
            link(obj, p0[ix[name]], e[ix[name]], float(data["radii"][ix[name]]))
        centers = [p0[ix["pelvis"]], e[ix["pelvis"]]] + [
            e[ix[f"lumbar_{i}"]] for i in range(1, 6)
        ]
        centers += [
            p0[ix["thorax"]] + (e[ix["thorax"]] - p0[ix["thorax"]]) * 0.60,
            e[ix["thorax"]],
        ]
        frames_r = (
            [r[ix["pelvis"]], r[ix["pelvis"]]]
            + [r[ix[f"lumbar_{i}"]] for i in range(1, 6)]
            + [r[ix["thorax"]]] * 2
        )
        widths = [0.145, 0.145, 0.135, 0.128, 0.128, 0.132, 0.145, 0.185, 0.195]
        depths = [0.095, 0.100, 0.100, 0.100, 0.102, 0.106, 0.110, 0.115, 0.095]
        verts = []
        for c, rr, w, d in zip(centers, frames_r, widths, depths):
            for k in range(N):
                t = 2 * np.pi * k / N
                verts.append(c + rr @ np.array([w * np.cos(t), d * np.sin(t), 0]))
        for vertex, co in zip(mesh.vertices, verts):
            vertex.co = co
        mesh.update()
        for j, marker in enumerate(markers):
            rr = frames_r[j + 1]
            marker.location = centers[j + 1] + rr @ np.array(
                [0, -depths[j + 1] - 0.008, 0]
            )
            marker.scale = (0.014, 0.014, 0.014)
        pp = p0[ix["pelvis"]]
        link(
            axis,
            pp + r[ix["pelvis"]] @ np.array([0.16, 0, 0]),
            pp + r[ix["pelvis"]] @ np.array([0.16, 0.18, 0]),
            0.008,
        )
        held = 1.8 <= data["time_s"][f] <= 4.7
        hand = e[ix["hand_R"]]
        box.location = (
            0,
            hand[1] if held else 0.40,
            float(data["box_handle_height_m"][f]) - 0.11,
        )
        for v, pos in (
            [("side", (4, -0.1, 1.15)), ("oblique", (3, 4, 2))]
            if a.preview
            else [("side", (4, -0.1, 1.15))]
        ):
            view(pos)
            target = a.out / folder.name / v
            target.mkdir(parents=True, exist_ok=True)
            scene.render.filepath = str((target / f"{f:04d}.png").resolve())
            bpy.ops.render.render(write_still=True)
(a.out / "render-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
print("Lifting renders complete")
