"""Reuse an original baseline pitch scene to review adult surface variants on CPU.

Run inside Blender. No downloaded body assets are used. The scene must have been
created by render_pitch.py with the baseline profile and the supplied motion.
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Matrix, Vector

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from meshlearning.binding import weights_for_vertices
from meshlearning.body_shapes import PROFILES, shape_vertices
from meshlearning.pitch import INDEX, NAMES

parser = argparse.ArgumentParser()
parser.add_argument("--scene", required=True)
parser.add_argument("--data", required=True)
parser.add_argument("--out", required=True)
parser.add_argument("--step", type=int, default=12)
parser.add_argument("--size", type=int, default=320)
args = parser.parse_args(sys.argv[sys.argv.index("--") + 1 :])
if args.step < 1:
    raise ValueError("Positive sample step required")
bpy.ops.wm.open_mainfile(filepath=str(Path(args.scene).resolve()))
scene = bpy.context.scene
scene.cycles.device = "CPU"
scene.cycles.samples = 4
scene.render.resolution_x = scene.render.resolution_y = args.size
body = bpy.data.objects["Original continuous review mannequin"]
rig = bpy.data.objects["Designed pitch rig - not an anatomical ISB skeleton"]
data = np.load(args.data, allow_pickle=False)
p, r, e = (
    data[k]
    for k in ("rest_positions_world", "rest_global_rots", "rest_endpoints_world")
)
base = np.array([v.co[:] for v in body.data.vertices])
weights, regions = weights_for_vertices(base, p, r, e, data["radii"])
# Reject a template whose existing binding differs from the supplied rest data.
actual_weights = np.zeros_like(weights)
for v in body.data.vertices:
    for group in v.groups:
        actual_weights[v.index, INDEX[body.vertex_groups[group.group].name]] = (
            group.weight
        )
if not np.allclose(weights, actual_weights, atol=1e-6):
    raise ValueError("Template is not the matching baseline binding")
frames = list(range(0, len(data["time_s"]), args.step))
out = Path(args.out)
out.mkdir(parents=True, exist_ok=True)
report = {
    "scope": "original adult thickness variants; no age/BMI or clinical validation",
    "motion_sha256": hashlib.sha256(Path(args.data).read_bytes()).hexdigest(),
    "template_sha256": hashlib.sha256(Path(args.scene).read_bytes()).hexdigest(),
    "source_frames": frames,
    "time_s": data["time_s"][frames].tolist(),
    "source_fps": int(data["source_fps"]),
    "sample_fps": float(data["source_fps"]) / args.step,
    "binding_weights_sha256": hashlib.sha256(actual_weights.tobytes()).hexdigest(),
    "profiles": {},
}
for profile in PROFILES:
    verts = shape_vertices(base, weights, p, r, profile)
    for v, point in zip(body.data.vertices, verts):
        v.co = point
    body.data.update()
    max_rig_error = 0.0
    max_surface_error = 0.0
    folder = out / profile
    folder.mkdir(exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str((folder / "review.blend").resolve()))
    for view in ("front", "side"):
        scene.camera = bpy.data.objects["Review " + view]
        (folder / view).mkdir(exist_ok=True)
        for k, f in enumerate(frames):
            scene.frame_set(f + 1)
            bpy.context.view_layer.update()
            for j, name in enumerate(NAMES):
                rest = Matrix(r[j].tolist()).to_4x4()
                rest.translation = Vector(p[j])
                t = (
                    rig.pose.bones[name].matrix
                    @ rig.data.bones[name].matrix_local.inverted()
                    @ rest
                )
                error = max(
                    np.max(np.abs(np.array(t.to_3x3()) - data["global_rots"][f, j])),
                    np.max(
                        np.abs(
                            np.array(t.translation)
                            - data["joint_positions_world"][f, j]
                        )
                    ),
                )
                max_rig_error = max(max_rig_error, float(error))
            sub = body.modifiers["Smooth review surface"]
            sub.show_viewport = False
            bpy.context.view_layer.update()
            evaluated = body.evaluated_get(bpy.context.evaluated_depsgraph_get())
            mesh = evaluated.to_mesh()
            deformed = np.array([v.co[:] for v in mesh.vertices])
            evaluated.to_mesh_clear()
            sub.show_viewport = True
            for region, segment in (
                ("protected_torso", "thorax"),
                ("rigid_forearm_R", "forearm_R"),
                ("rigid_forearm_L", "forearm_L"),
            ):
                j = INDEX[segment]
                mask = (regions == region) & (weights[:, j] > 0.999999)
                if not np.any(mask):
                    raise ValueError("Missing verification region")
                expected = (
                    data["global_rots"][f, j] @ r[j].T @ (verts[mask] - p[j]).T
                ).T + data["joint_positions_world"][f, j]
                max_surface_error = max(
                    max_surface_error,
                    float(np.max(np.linalg.norm(deformed[mask] - expected, axis=1))),
                )
            if max_rig_error > 1e-4 or max_surface_error > 1e-4:
                raise ValueError("Motion or skin ownership changed")
            scene.render.filepath = str(folder / view / f"{k:04d}.png")
            bpy.ops.render.render(write_still=True)
    report["profiles"][profile] = {
        "parameters": PROFILES[profile],
        "vertices": len(verts),
        "rest_surface_sha256": hashlib.sha256(verts.tobytes()).hexdigest(),
        "max_rig_export_error": max_rig_error,
        "max_protected_surface_error_m": max_surface_error,
    }
(out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
