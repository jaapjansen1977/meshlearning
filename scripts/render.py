"""Run inside Blender; no external meshes, textures or add-ons."""

import argparse
import json
import sys
from pathlib import Path

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Matrix, Vector

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np

from meshlearning.motion import BONES

p = argparse.ArgumentParser()
p.add_argument("--data", required=True)
p.add_argument("--out", required=True)
p.add_argument("--fps", type=int, default=24)
p.add_argument("--size", type=int, default=256)
a = p.parse_args(sys.argv[sys.argv.index("--") + 1 :])
data = np.load(a.data, allow_pickle=False)
out = Path(a.out)
out.mkdir(parents=True, exist_ok=True)
bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)
s = bpy.context.scene
s.render.engine = "CYCLES"
s.cycles.device = "CPU"
s.cycles.samples = 8
s.cycles.use_denoising = False
s.render.resolution_x = a.size
s.render.resolution_y = a.size
s.render.resolution_percentage = 100
s.render.image_settings.file_format = "PNG"
s.render.fps = a.fps
s.world.color = (0.22, 0.22, 0.22)
mat = bpy.data.materials.new("original_procedural_surface")
mat.diffuse_color = (0.16, 0.46, 0.65, 1)
segments = []
joints = []
target_marker = None
if "case" in data:
    target_name = str(data["case"]).split(".")[0]
    marker_material = bpy.data.materials.new("orientation_marker")
    marker_material.diffuse_color = (1, 0.65, 0.03, 1)
    bpy.ops.mesh.primitive_uv_sphere_add(segments=12, ring_count=8, radius=0.018)
    target_marker = bpy.context.object
    target_marker.data.materials.append(marker_material)
    s.render.use_stamp = True
    for flag in (
        "date",
        "time",
        "render_time",
        "frame",
        "filename",
        "scene",
        "camera",
        "hostname",
    ):
        setattr(s.render, "use_stamp_" + flag, False)
    s.render.use_stamp_note = True
    s.render.stamp_font_size = 10
for name, parent, offset, end, radius in BONES:
    bpy.ops.mesh.primitive_uv_sphere_add(segments=12, ring_count=8)
    o = bpy.context.object
    o.name = name
    o.data.materials.append(mat)
    segments.append(o)
    bpy.ops.mesh.primitive_uv_sphere_add(segments=12, ring_count=8, radius=radius * 0.9)
    o = bpy.context.object
    o.data.materials.append(mat)
    joints.append(o)
bpy.ops.object.light_add(type="AREA", location=(2, 3, 5))
bpy.context.object.data.energy = 650
bpy.context.object.data.shape = "DISK"
bpy.context.object.data.size = 4
bpy.ops.object.camera_add()
cam = bpy.context.object
s.camera = cam
cam.data.lens = 48
metadata = {
    "schema_version": 1,
    "label_status": "engineering_reference_not_validated_ISB",
    "visibility": "in_frame only; no occlusion classification",
    "cameras": {},
}
for camera, loc in [("front", (0, 4, 2.0)), ("oblique", (3, 3, 2.0))]:
    cam.location = loc
    cam.rotation_euler = (
        (Vector((0, 0, 1.0)) - cam.location).to_track_quat("-Z", "Y").to_euler()
    )
    bpy.context.view_layer.update()
    folder = out / camera
    folder.mkdir(exist_ok=True)
    views = []
    for f, (positions, ends, rots) in enumerate(
        zip(data["joint_positions_world"], data["endpoints_world"], data["global_rots"])
    ):
        for j, (start, end) in enumerate(zip(positions, ends)):
            v = Vector(end - start)
            o = segments[j]
            o.location = Vector((start + end) / 2)
            o.rotation_euler = (
                Matrix(rots[j].tolist()).to_quaternion()
                @ Vector(BONES[j][3]).to_track_quat("Z", "Y")
            ).to_euler()
            o.scale = (
                BONES[j][4],
                BONES[j][4] * 0.75,
                v.length / 2 + BONES[j][4] * 0.3,
            )
            joints[j].location = start
        if target_marker is not None:
            target_index = next(
                i for i, bone in enumerate(BONES) if bone[0] == target_name
            )
            target_marker.location = Vector(
                (positions[target_index] + ends[target_index]) / 2
            ) + Matrix(rots[target_index].tolist()) @ Vector(
                (0, BONES[target_index][4], 0)
            )
            s.render.stamp_note_text = f"{data['case']!s} | expected {data['expected_deg'][f]:+.1f} | recovered {data['calculated_deg'][f]:+.1f} deg"
        bpy.context.view_layer.update()
        points = []
        for start in positions:
            q = world_to_camera_view(s, cam, Vector(start))
            points.append(
                {
                    "xy_px": [q.x * a.size, (1 - q.y) * a.size],
                    "depth_camera": q.z,
                    "in_frame": bool(q.z > 0 and 0 <= q.x <= 1 and 0 <= q.y <= 1),
                }
            )
        views.append({"frame_idx": f, "joints": points})
        s.render.filepath = str(folder / f"{f:05d}.png")
        bpy.ops.render.render(write_still=True)
    metadata["cameras"][camera] = {
        "world_from_camera": [list(row) for row in cam.matrix_world],
        "projection_matrix": [
            list(row)
            for row in cam.calc_matrix_camera(
                bpy.context.evaluated_depsgraph_get(), x=a.size, y=a.size
            )
        ],
        "image_size": [a.size, a.size],
        "frames": views,
    }
(out / "camera_labels.json").write_text(json.dumps(metadata, indent=2))
