"""CPU Blender review renderer with original procedural continuous skinned mesh.

No external avatar, texture, motion file, add-on or human model is loaded.
"""

import argparse
import json
import sys
from pathlib import Path

import bpy
import numpy as np
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Matrix, Vector

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from meshlearning.binding import weights_for_vertices
from meshlearning.pitch import INDEX, NAMES, PARENTS, PHASES

parser = argparse.ArgumentParser()
parser.add_argument("--data", required=True)
parser.add_argument("--out", required=True)
parser.add_argument("--views", default="front,side,rear")
parser.add_argument("--sample-frames", default="")
parser.add_argument("--size", type=int, default=512)
parser.add_argument("--samples", type=int, default=8)
args = parser.parse_args(sys.argv[sys.argv.index("--") + 1 :])
data = np.load(args.data, allow_pickle=False)
if "phase_times_s" in data:
    PHASES = list(zip(data["phase_times_s"], data["phase_names"]))
source_fps = int(data["source_fps"]) if "source_fps" in data else 240
release_time = (
    float(data["nominal_release_time_s"]) if "nominal_release_time_s" in data else 1.175
)
out = Path(args.out)
out.mkdir(parents=True, exist_ok=True)
selected = (
    np.array([int(f) for f in args.sample_frames.split(",")])
    if args.sample_frames
    else data["render_frames"]
)
if (
    len(set(selected)) != len(selected)
    or np.any(selected < 0)
    or np.any(selected >= len(data["time_s"]))
):
    raise ValueError("Unique valid source frame indices required")
rest_p = data["rest_positions_world"]
rest_r = data["rest_global_rots"]
rest_e = data["rest_endpoints_world"]
radii = data["radii"]
bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)
scene = bpy.context.scene
scene.render.engine = "CYCLES"
scene.cycles.device = "CPU"
scene.cycles.samples = args.samples
scene.cycles.use_denoising = False
scene.render.resolution_x = args.size
scene.render.resolution_y = args.size
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
scene.render.fps = source_fps
scene.frame_start = 1
scene.frame_end = len(data["time_s"])
scene.world.use_nodes = True
scene.world.node_tree.nodes["Background"].inputs[0].default_value = (
    0.32,
    0.36,
    0.42,
    1,
)
scene.world.node_tree.nodes["Background"].inputs[1].default_value = 0.65
scene.view_settings.view_transform = "Standard"


def material(name, color, roughness=0.6):
    m = bpy.data.materials.new(name)
    m.diffuse_color = color
    m.use_nodes = True
    node = m.node_tree.nodes.get("Principled BSDF")
    node.inputs["Base Color"].default_value = color
    node.inputs["Roughness"].default_value = roughness
    return m


blue = material("Original tight suit", (0.055, 0.24, 0.42, 1))
skin = material("Original skin surface", (0.65, 0.40, 0.25, 1))
sleeve = material("Throwing arm sleeve", (0.72, 0.15, 0.07, 1))
stripe = material("Anterior orientation stripe", (0.98, 0.68, 0.06, 1))
dark = material("Cap and shoes", (0.035, 0.055, 0.08, 1))
white = material("Ball marker", (0.93, 0.93, 0.88, 1))
floor = material("Studio floor", (0.18, 0.20, 0.23, 1))
floor_nodes = floor.node_tree.nodes
floor_nodes.clear()
floor_output = floor_nodes.new("ShaderNodeOutputMaterial")
floor_emission = floor_nodes.new("ShaderNodeEmission")
floor_emission.inputs[0].default_value = (0.18, 0.20, 0.23, 1)
floor.node_tree.links.new(floor_emission.outputs[0], floor_output.inputs["Surface"])
parts = []


def ellipsoid(center, scale, orientation=None):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=20, ring_count=12, location=center)
    obj = bpy.context.object
    obj.scale = scale
    if orientation is not None:
        obj.rotation_euler = Matrix(orientation.tolist()).to_euler()
    parts.append(obj)
    return obj


# Torso profile and head are original parametric geometry.
pelvis = rest_p[INDEX["pelvis"]]
thorax = rest_p[INDEX["thorax"]]
ellipsoid(pelvis + np.array([0, 0, 0.015]), (0.155, 0.105, 0.15))
ellipsoid(pelvis + np.array([0, 0, 0.18]), (0.135, 0.09, 0.19))
ellipsoid(thorax + np.array([0, 0, 0.22]), (0.205, 0.112, 0.205))
for name in NAMES:
    if name in ("pelvis", "thorax") or name.startswith(
        ("clavicle", "scapula", "deltoid")
    ):
        continue
    j = INDEX[name]
    start = rest_p[j]
    end = rest_e[j]
    delta = end - start
    q = Vector(delta).to_track_quat("Z", "Y").to_matrix()
    radius = radii[j]
    if name == "head":
        ellipsoid((start + end) / 2, (0.087, 0.086, 0.12), rest_r[j])
        ellipsoid(
            start + rest_r[j] @ np.array([0, 0.083, 0.105]),
            (0.022, 0.032, 0.025),
            rest_r[j],
        )
    elif name.startswith("hand"):
        ellipsoid(
            (start + end) / 2,
            (0.045, 0.028, np.linalg.norm(delta) / 2 + 0.025),
            np.array(q),
        )
    elif name.startswith("foot"):
        ellipsoid(
            (start + end) / 2,
            (0.06, 0.044, np.linalg.norm(delta) / 2 + 0.04),
            np.array(q),
        )
    else:
        ellipsoid(
            (start + end) / 2,
            (radius, radius * 0.9, np.linalg.norm(delta) / 2 + radius * 0.5),
            np.array(q),
        )
        ellipsoid(start, (radius * 0.95,) * 3)
for side in ("R", "L"):
    shoulder = rest_p[INDEX[f"humerus_{side}"]]
    ellipsoid(shoulder, (0.077, 0.077, 0.084))

bpy.ops.object.select_all(action="DESELECT")
for obj in parts:
    obj.select_set(True)
bpy.context.view_layer.objects.active = parts[0]
bpy.ops.object.join()
body = bpy.context.object
body.name = "Original continuous review mannequin"
bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
# Join produces a local object origin; remesh then reset world transform for binding.
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
remesh = body.modifiers.new("Original geometry union", "REMESH")
remesh.mode = "VOXEL"
remesh.voxel_size = 0.018
remesh.use_smooth_shade = True
bpy.ops.object.modifier_apply(modifier=remesh.name)
smooth = body.modifiers.new("Surface smoothing", "SMOOTH")
smooth.factor = 0.7
smooth.iterations = 8
bpy.ops.object.modifier_apply(modifier=smooth.name)
for m in (blue, skin, sleeve, stripe, dark):
    body.data.materials.append(m)
verts = np.array([v.co[:] for v in body.data.vertices])
# Region-constrained weights prevent shoulder bones pulling the chest and
# keep the forearm shaft rigid, blending only near elbow and wrist.
weights, binding_regions = weights_for_vertices(verts, rest_p, rest_r, rest_e, radii)

bpy.ops.object.armature_add(enter_editmode=True, location=(0, 0, 0))
rig = bpy.context.object
rig.name = "Designed pitch rig - not an anatomical ISB skeleton"
for bone in list(rig.data.edit_bones):
    rig.data.edit_bones.remove(bone)
for j, name in enumerate(NAMES):
    bone = rig.data.edit_bones.new(name)
    bone.head = rest_p[j]
    bone.tail = rest_e[j]
    if (Vector(bone.tail) - Vector(bone.head)).length < 0.005:
        bone.tail = bone.head + Vector((0, 0, 0.02))
    if PARENTS[j] is not None:
        bone.parent = rig.data.edit_bones[PARENTS[j]]
bpy.ops.object.mode_set(mode="OBJECT")
rig.show_in_front = True
for name in NAMES:
    body.vertex_groups.new(name=name)
for vertex, amounts in enumerate(weights):
    for index in np.flatnonzero(amounts > 1e-12):
        body.vertex_groups[int(index)].add([vertex], float(amounts[index]), "REPLACE")

armature = body.modifiers.new("Volume preserving shoulder deformation", "ARMATURE")
armature.object = rig
armature.use_deform_preserve_volume = True
subdivision = body.modifiers.new("Smooth review surface", "SUBSURF")
subdivision.levels = 1
subdivision.render_levels = 1
for poly in body.data.polygons:
    poly.use_smooth = True
    point = np.mean([verts[v] for v in poly.vertices], axis=0)
    head_local = rest_r[INDEX["head"]].T @ (point - rest_p[INDEX["head"]])
    if point[2] > rest_p[INDEX["head"], 2] - 0.015:
        poly.material_index = 4 if head_local[2] > 0.17 else 1
    for side in ("R", "L"):
        hand = INDEX[f"hand_{side}"]
        local = rest_r[hand].T @ (point - rest_p[hand])
        if -0.2 < local[2] < 0.01 and abs(local[0]) < 0.07 and abs(local[1]) < 0.06:
            poly.material_index = 1 if side == "R" else 4
        foot = INDEX[f"foot_{side}"]
        if (
            np.linalg.norm(point - (rest_p[foot] + rest_e[foot]) / 2) < 0.16
            and point[2] < 0.16
        ):
            poly.material_index = 4
    for segment in ("humerus_R", "forearm_R"):
        j = INDEX[segment]
        local = rest_r[j].T @ (point - rest_p[j])
        if -0.29 < local[2] < -0.015 and np.hypot(local[0], local[1]) < 0.08:
            poly.material_index = 3 if local[1] > 0.025 and abs(local[0]) < 0.026 else 2

# Ball is only a possession marker; hidden after the nominal release, no flight claim.
bpy.ops.mesh.primitive_uv_sphere_add(segments=16, ring_count=10, radius=0.033)
ball = bpy.context.object
ball.name = "Ball possession marker"
ball.data.materials.append(white)
eyes = []
for sign in (-1, 1):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=12, ring_count=8, radius=0.007)
    eye = bpy.context.object
    eye.name = "Procedural eye marker"
    eye.data.materials.append(dark)
    eyes.append((eye, sign))

rest_transforms = []
bone_rest = []
for j, name in enumerate(NAMES):
    t = Matrix(rest_r[j].tolist()).to_4x4()
    t.translation = Vector(rest_p[j])
    rest_transforms.append(t)
    bone_rest.append(rig.data.bones[name].matrix_local.copy())
for f in range(len(data["time_s"])):
    desired = []
    for j, name in enumerate(NAMES):
        t = Matrix(data["global_rots"][f, j].tolist()).to_4x4()
        t.translation = Vector(data["joint_positions_world"][f, j])
        desired.append(t @ rest_transforms[j].inverted() @ bone_rest[j])
    for j, name in enumerate(NAMES):
        bone = rig.pose.bones[name]
        parent = PARENTS[j]
        basis = (
            bone_rest[j].inverted() @ desired[j]
            if parent is None
            else bone_rest[j].inverted()
            @ bone_rest[INDEX[parent]]
            @ desired[INDEX[parent]].inverted()
            @ desired[j]
        )
        bone.rotation_mode = "QUATERNION"
        bone.matrix_basis = basis
        bone.keyframe_insert("location", frame=f + 1)
        bone.keyframe_insert("rotation_quaternion", frame=f + 1)
        bone.keyframe_insert("scale", frame=f + 1)
    hand = INDEX["hand_R"]
    ball.location = Vector(data["endpoints_world"][f, hand]) + Matrix(
        data["global_rots"][f, hand].tolist()
    ) @ Vector((0, 0.025, 0.02))
    ball.hide_render = bool(data["time_s"][f] > release_time)
    ball.hide_viewport = ball.hide_render
    ball.keyframe_insert("location", frame=f + 1)
    ball.keyframe_insert("hide_render", frame=f + 1)
    ball.keyframe_insert("hide_viewport", frame=f + 1)
    for eye, sign in eyes:
        j = INDEX["head"]
        eye.location = Vector(data["joint_positions_world"][f, j]) + Matrix(
            data["global_rots"][f, j].tolist()
        ) @ Vector((sign * 0.033, 0.079, 0.125))
        eye.keyframe_insert("location", frame=f + 1)
if rig.animation_data and rig.animation_data.action:
    for curve in rig.animation_data.action.fcurves:
        for key in curve.keyframe_points:
            key.interpolation = "LINEAR"

bpy.ops.mesh.primitive_plane_add(size=200, location=(0, 0, -0.018))
bpy.context.object.data.materials.append(floor)
for loc, energy, size in [
    ((3, 4, 6), 650, 5),
    ((-3, 1, 4), 400, 4),
    ((0, -4, 4), 450, 3),
]:
    bpy.ops.object.light_add(type="AREA", location=loc)
    light = bpy.context.object
    light.data.energy = energy
    light.data.shape = "DISK"
    light.data.size = size
    light.rotation_euler = (
        (Vector((0, 0.35, 1)) - light.location).to_track_quat("-Z", "Y").to_euler()
    )
# Ground arrow denotes the intended throwing direction (+Y).
arrow_mesh = bpy.data.meshes.new("Forward arrow")
arrow_mesh.from_pydata(
    [
        (-0.06, 1.25, -0.015),
        (0.06, 1.25, -0.015),
        (0.06, 1.65, -0.015),
        (0.15, 1.65, -0.015),
        (0, 1.87, -0.015),
        (-0.15, 1.65, -0.015),
        (-0.06, 1.65, -0.015),
    ],
    [],
    [(0, 1, 2, 3, 4, 5, 6)],
)
arrow_obj = bpy.data.objects.new("Intended throwing direction +Y", arrow_mesh)
bpy.context.collection.objects.link(arrow_obj)
arrow_obj.data.materials.append(stripe)

cameras = {}
for name, loc in [
    ("front", (0, 5.7, 2.0)),
    ("side", (5.4, 0.45, 2.0)),
    ("rear", (-3.8, -4.2, 2.6)),
]:
    bpy.ops.object.camera_add(location=loc)
    camera = bpy.context.object
    camera.name = "Review " + name
    camera.rotation_euler = (
        (Vector((0, 0.4, 0.95)) - camera.location).to_track_quat("-Z", "Y").to_euler()
    )
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = 2.55
    cameras[name] = camera
for time, label in PHASES:
    scene.timeline_markers.new(label, frame=round(time * source_fps) + 1)
scene.camera = cameras["side"]
scene.frame_set(round(PHASES[4][0] * source_fps) + 1)
bpy.ops.wm.save_as_mainfile(filepath=str((out / "pitch_review.blend").resolve()))
metadata = {
    "schema_version": 1,
    "model_status": "original procedural review mannequin; not anatomically validated",
    "source_fps": source_fps,
    "views": {},
    "mesh_vertices": len(body.data.vertices),
    "binding_profile": "region-constrained-v2",
    "rigid_forearm_vertex_counts": {
        side: int(np.sum(binding_regions == f"rigid_forearm_{side}"))
        for side in ("R", "L")
    },
    "skin_weight_sum_max_error": float(np.max(np.abs(weights.sum(axis=1) - 1))),
}
for name in args.views.split(","):
    camera = cameras[name]
    scene.camera = camera
    folder = out / name
    folder.mkdir(exist_ok=True)
    frames = []
    for k, f in enumerate(selected):
        scene.frame_set(int(f) + 1)
        bpy.context.view_layer.update()
        points = []
        for j, point in enumerate(data["joint_positions_world"][f]):
            v = world_to_camera_view(scene, camera, Vector(point))
            points.append([float(v.x * args.size), float((1 - v.y) * args.size)])
        # Independently verify the evaluated Blender pose matches exported segment transforms.
        max_bone_error = 0.0
        for j, segment in enumerate(NAMES):
            t = (
                rig.pose.bones[segment].matrix
                @ bone_rest[j].inverted()
                @ rest_transforms[j]
            )
            max_bone_error = max(
                max_bone_error,
                float(np.max(np.abs(np.array(t.to_3x3()) - data["global_rots"][f, j]))),
                float(
                    np.max(
                        np.abs(
                            np.array(t.translation)
                            - data["joint_positions_world"][f, j]
                        )
                    )
                ),
            )
        if max_bone_error > 1e-4:
            raise RuntimeError(f"Rig/export mismatch {max_bone_error} at frame {f}")
        # Verify actual deformed surface vertices before subdivision, not only bones.
        subdivision.show_viewport = False
        bpy.context.view_layer.update()
        evaluated = body.evaluated_get(bpy.context.evaluated_depsgraph_get())
        evaluated_mesh = evaluated.to_mesh()
        deformed = np.array([v.co[:] for v in evaluated_mesh.vertices])
        evaluated.to_mesh_clear()
        subdivision.show_viewport = True
        surface_errors = {}
        for region, segment in [
            ("rigid_forearm_R", "forearm_R"),
            ("rigid_forearm_L", "forearm_L"),
            ("protected_torso", "thorax"),
        ]:
            j = INDEX[segment]
            mask = (binding_regions == region) & (weights[:, j] > 0.999999)
            if not np.any(mask):
                raise RuntimeError(f"No verification vertices in {region}")
            expected = (
                data["global_rots"][f, j] @ rest_r[j].T @ (verts[mask] - rest_p[j]).T
            ).T + data["joint_positions_world"][f, j]
            surface_errors[region] = float(
                np.max(np.linalg.norm(deformed[mask] - expected, axis=1))
            )
        if max(surface_errors.values()) > 1e-4:
            raise RuntimeError(f"Surface ownership mismatch: {surface_errors}")
        bpy.context.view_layer.update()
        phase = next(
            label
            for start, label in reversed(PHASES)
            if data["time_s"][f] >= start - 1e-8
        )
        scene.render.filepath = str(folder / f"{k:04d}.png")
        bpy.ops.render.render(write_still=True)
        frames.append(
            {
                "review_frame": k,
                "source_frame": int(f),
                "source_time_s": float(data["time_s"][f]),
                "phase": phase,
                "joint_xy_px": points,
                "max_rig_export_error": max_bone_error,
                "surface_ownership_error_m": surface_errors,
            }
        )
    metadata["views"][name] = {
        "world_from_camera": [list(row) for row in camera.matrix_world],
        "projection_matrix": [
            list(row)
            for row in camera.calc_matrix_camera(
                bpy.context.evaluated_depsgraph_get(), x=args.size, y=args.size
            )
        ],
        "image_size": [args.size, args.size],
        "frames": frames,
    }
(out / "render_metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
