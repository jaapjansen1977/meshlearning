"""Blender-only reuse of our original review scene with exported exact motion."""

import bpy
import numpy as np
from mathutils import Matrix

from .pitch import INDEX, NAMES, PARENTS


def animate_values(obj, path, values, frames, action):
    for channel in range(values.shape[1]):
        curve = action.fcurves.new(data_path=path, index=channel)
        curve.keyframe_points.add(len(frames))
        curve.keyframe_points.foreach_set(
            "co", np.column_stack([frames, values[:, channel]]).ravel()
        )
        for key in curve.keyframe_points:
            key.interpolation = "LINEAR"
        curve.update()


def animate_location(obj, locations, frames):
    obj.animation_data_clear()
    obj.animation_data_create()
    action = bpy.data.actions.new(obj.name + " motion")
    obj.animation_data.action = action
    animate_values(obj, "location", locations, frames, action)


def replace_motion(scene, rig, data):
    """Bulk-create curves, preserving the original rest rig and vertex weights."""
    if data["joint_names"].tolist() != NAMES:
        raise ValueError("Matching original rig joint names required")
    frames = np.arange(len(data["time_s"])) + 1
    rest = np.tile(np.eye(4), (len(NAMES), 1, 1))
    rest[:, :3, :3] = data["rest_global_rots"]
    rest[:, :3, 3] = data["rest_positions_world"]
    bone_rest = np.array([rig.data.bones[name].matrix_local for name in NAMES])
    wanted = np.tile(np.eye(4), (len(frames), len(NAMES), 1, 1))
    wanted[:, :, :3, :3] = data["global_rots"]
    wanted[:, :, :3, 3] = data["joint_positions_world"]
    desired = wanted @ np.linalg.inv(rest)[None] @ bone_rest[None]
    rig.animation_data_clear()
    rig.animation_data_create()
    action = bpy.data.actions.new("Exact exported motion")
    rig.animation_data.action = action
    for j, name in enumerate(NAMES):
        basis = (
            np.linalg.inv(bone_rest[j]) @ desired[:, j]
            if PARENTS[j] is None
            else (
                np.linalg.inv(bone_rest[j])
                @ bone_rest[INDEX[PARENTS[j]]]
                @ np.linalg.inv(desired[:, INDEX[PARENTS[j]]])
                @ desired[:, j]
            )
        )
        decomposed = [Matrix(matrix.tolist()).decompose() for matrix in basis]
        locations = np.array([x[0] for x in decomposed])
        quaternions = np.array([x[1] for x in decomposed])
        scales = np.array([x[2] for x in decomposed])
        for f in range(1, len(frames)):
            if quaternions[f] @ quaternions[f - 1] < 0:
                quaternions[f] *= -1
        bone = rig.pose.bones[name]
        bone.rotation_mode = "QUATERNION"
        for path, values in (
            ("location", locations),
            ("rotation_quaternion", quaternions),
            ("scale", scales),
        ):
            animate_values(rig, bone.path_from_id(path), values, frames, action)
    for sign in (-1, 1):
        eye = bpy.data.objects.get(
            "Procedural eye marker" if sign == -1 else "Procedural eye marker.001"
        )
        if eye:
            j = INDEX["head"]
            locations = data["joint_positions_world"][:, j] + (
                data["global_rots"][:, j] @ np.array([sign * 0.033, 0.079, 0.125])
            )
            animate_location(eye, locations, frames)
    old_ball = bpy.data.objects.get("Ball possession marker")
    if old_ball:
        old_ball.animation_data_clear()
        old_ball.hide_render = True
        old_ball.hide_viewport = True
    if "ball_positions_world" in data:
        # Ground is Z=0 in the kick data; use a shadow-receiving material so
        # planted foot and grounded ball can be judged visually.
        for obj in bpy.data.objects:
            if obj.type != "MESH":
                continue
            for mat in obj.data.materials:
                if mat and mat.name.startswith("Studio floor"):
                    obj.location.z = 0
                    mat.node_tree.nodes.clear()
                    output = mat.node_tree.nodes.new("ShaderNodeOutputMaterial")
                    shader = mat.node_tree.nodes.new("ShaderNodeBsdfPrincipled")
                    shader.inputs["Base Color"].default_value = (0.20, 0.22, 0.25, 1)
                    shader.inputs["Roughness"].default_value = 1
                    mat.node_tree.links.new(
                        shader.outputs["BSDF"], output.inputs["Surface"]
                    )
        bpy.ops.mesh.primitive_ico_sphere_add(
            subdivisions=3, radius=float(data["ball_radius_m"])
        )
        ball = bpy.context.object
        ball.name = "Original football contact marker"
        for name, color in (
            ("Football white", (0.9, 0.9, 0.86, 1)),
            ("Football dark", (0.025, 0.035, 0.045, 1)),
        ):
            mat = bpy.data.materials.new(name)
            mat.diffuse_color = color
            mat.use_nodes = True
            mat.node_tree.nodes["Principled BSDF"].inputs[
                "Base Color"
            ].default_value = color
            ball.data.materials.append(mat)
        for poly in ball.data.polygons:
            poly.use_smooth = True
            poly.material_index = 1 if poly.index % 9 in (0, 1) else 0
        animate_location(ball, data["ball_positions_world"], frames)
    scene.render.fps = int(data["source_fps"])
    scene.frame_end = len(frames)
    scene.timeline_markers.clear()
    for time, label in zip(data["phase_times_s"], data["phase_names"]):
        scene.timeline_markers.new(
            str(label), frame=round(float(time) * scene.render.fps) + 1
        )
    scene.frame_set(1)
