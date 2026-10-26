"""SOMA template metadata reader and exact-rotation diagnostics.

No identity-model meshes or model weights are loaded. The pinned USD checksum
is mandatory for the real workflow. Template-based registration remains an
explicit neutral/twist-reference convention, not measured anatomical validation.
"""

import hashlib
from pathlib import Path

import numpy as np

from .frames import map_registered_frames, unit
from .pitch import INDEX, down_frame, functional_angles

SOMA_COMMIT = "86632764684281dc98f31ab9c4aac36a4cdbc428"
RIG_SHA256 = "79f02176534ebc0671c76bf09203bbee8e1621f8b6d34cc63aec69b73460bba2"
RIG_BYTES = 344934193
MOVALYTICS_COMMIT = "887de80c8966c1afcd35c5c685b8c59625bf6682"
REQUIRED = ("Hips", "Chest", "RightArm", "LeftArm", "RightForeArm", "LeftForeArm")


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def proper_rotation(matrix):
    matrix = np.asarray(matrix, dtype=float)
    if (
        matrix.shape != (3, 3)
        or not np.isfinite(matrix).all()
        or not np.allclose(matrix.T @ matrix, np.eye(3), atol=2e-5, rtol=0)
        or not np.isclose(np.linalg.det(matrix), 1, atol=2e-5)
    ):
        raise ValueError(
            "Rig orientation is not a proper rotation; scale/shear must be investigated"
        )
    # Only remove representation roundoff, not substantive scale/shear.
    u, _, v = np.linalg.svd(matrix)
    return u @ v


def read_rig(path, expected_sha256=RIG_SHA256):
    path = Path(path)
    with path.open("rb") as source:
        prefix = source.read(150)
    if prefix.startswith(b"version https://git-lfs.github.com/spec"):
        raise ValueError(
            "This is a Git LFS pointer, not the SOMA rig. Obtain the verified LFS asset first."
        )
    digest = sha256_file(path)
    if digest != expected_sha256:
        raise ValueError("SOMA rig SHA256 does not match the selected revision")
    from pxr import Usd, UsdGeom, UsdSkel

    stage = Usd.Stage.Open(str(path.resolve()), load=Usd.Stage.LoadNone)
    if stage is None:
        raise ValueError("Cannot read USD stage")
    candidates = []
    for prim in stage.Traverse():
        if prim.IsA(UsdSkel.Skeleton):
            skel = UsdSkel.Skeleton(prim)
            paths = [str(p) for p in skel.GetJointsAttr().Get() or []]
            names = [p.rsplit("/", 1)[-1] for p in paths]
            if set(REQUIRED).issubset(names):
                candidates.append((skel, paths, names))
    if len(candidates) != 1:
        raise ValueError("Exactly one skeleton with the required SOMA joints is needed")
    skeleton, paths, names = candidates[0]
    if len(names) != len(set(names)):
        raise ValueError("Ambiguous duplicate joint leaf names")
    rest_raw = skeleton.GetRestTransformsAttr().Get()
    bind_raw = skeleton.GetBindTransformsAttr().Get()
    if (
        rest_raw is None
        or bind_raw is None
        or len(rest_raw) != len(names)
        or len(bind_raw) != len(names)
    ):
        raise ValueError("Matching explicit rest and bind transforms are required")
    # Match the pinned soma/io.py loader: transpose USD row-vector matrices,
    # then accumulate rest transforms in skeleton space. Do not silently add
    # scene-prim xforms which the SOMA loader itself does not apply.
    rest = np.asarray(rest_raw, dtype=float).transpose(0, 2, 1)
    bind = np.asarray(bind_raw, dtype=float).transpose(0, 2, 1)
    indices = {p: i for i, p in enumerate(paths)}
    parents = [indices.get(p.rsplit("/", 1)[0], -1) if "/" in p else -1 for p in paths]
    world = np.zeros_like(rest)
    for j, parent in enumerate(parents):
        if parent >= j:
            raise ValueError("Skeleton must be parent-before-child")
        world[j] = rest[j] if parent < 0 else world[parent] @ rest[j]
    # SOMA includes deformation-helper joints with scale. They are not the
    # anatomical measurement segments. Never normalize or use those helpers
    # as a substitute for the required rigid Chest/Arm/ForeArm/Hips frames.
    for name in REQUIRED:
        proper_rotation(world[names.index(name), :3, :3])
    nonrigid_helpers = []
    for name, matrix in zip(names, world):
        r = matrix[:3, :3]
        if not np.allclose(r.T @ r, np.eye(3), atol=2e-5, rtol=0) or not np.isclose(
            np.linalg.det(r), 1, atol=2e-5
        ):
            nonrigid_helpers.append(name)
    return {
        "sha256": digest,
        "nonrigid_auxiliary_joints": nonrigid_helpers,
        "file_bytes": path.stat().st_size,
        "skeleton_path": str(skeleton.GetPath()),
        "joint_names": names,
        "parents": parents,
        "t_pose_world": world,
        "bind_pose_world": bind,
        "up_axis": str(UsdGeom.GetStageUpAxis(stage)),
        "meters_per_unit": float(UsdGeom.GetStageMetersPerUnit(stage)),
        "matrix_policy": "SOMA loader skeleton-space, USD matrices transposed; scene prim xforms not applied",
    }


def template_registration(rig):
    names = rig["joint_names"]
    t = rig["t_pose_world"]
    idx = {n: names.index(n) for n in REQUIRED}
    up = np.eye(3)[{"X": 0, "Y": 1, "Z": 2}[rig["up_axis"]]]
    if np.dot(t[idx["Chest"], :3, 3] - t[idx["Hips"], :3, 3], up) <= 0:
        raise ValueError(
            "Chest is not superior to Hips in the declared stage-up direction"
        )
    right = t[idx["RightArm"], :3, 3] - t[idx["LeftArm"], :3, 3]
    right = unit(right - up * np.dot(right, up))
    anterior = unit(np.cross(up, right))
    up = unit(np.cross(right, anterior))
    g = np.column_stack([right, anterior, up])
    registrations = {}
    reference = {}
    for segment in ("Chest", "RightArm", "LeftArm"):
        soma_r = proper_rotation(t[idx[segment], :3, :3])
        if segment == "Chest":
            model_r = np.eye(3)
        else:
            elbow = "RightForeArm" if segment == "RightArm" else "LeftForeArm"
            direction = g.T @ (t[idx[elbow], :3, 3] - t[idx[segment], :3, 3])
            model_r = down_frame(direction, np.array([0.0, 1, 0]))
        registrations[segment] = proper_rotation(model_r.T @ g.T @ soma_r)
        reconstructed = g @ model_r @ registrations[segment]
        if not np.allclose(reconstructed, soma_r, atol=1e-8):
            raise RuntimeError("Template reference reconstruction failed")
        side = "R" if segment == "RightArm" else "L"
        reference[segment] = {
            "model_rotation": model_r.tolist(),
            "soma_rotation": soma_r.tolist(),
            "model_functional_angles": list(
                functional_angles(np.eye(3), model_r, side)[:3]
            )
            if segment != "Chest"
            else None,
        }
    return {
        "world_model_to_soma": g.tolist(),
        "registrations": {k: v.tolist() for k, v in registrations.items()},
        "reference": reference,
        "status": "template-matched convention; not measured epicondylar/anatomical registration",
        "assumptions": [
            "World superior uses the USD stage-up axis; subject right uses the projected LeftArm-to-RightArm direction",
            "Thorax anterior is the right-handed cross-product direction; confirm against actual character facing",
            "Upper-arm zero twist uses projected thorax anterior in the template pose; not a measured epicondylar axis",
        ],
        "rig_sha256": rig["sha256"],
        "rig_metadata": {
            "skeleton_path": rig["skeleton_path"],
            "joint_count": len(rig["joint_names"]),
            "up_axis": rig["up_axis"],
            "meters_per_unit": rig["meters_per_unit"],
            "matrix_policy": rig["matrix_policy"],
            "nonrigid_auxiliary_joints_not_used": rig.get(
                "nonrigid_auxiliary_joints", []
            ),
        },
        "soma_commit": SOMA_COMMIT,
    }


def map_motion(motion, registration):
    names = ["Chest", "RightArm", "LeftArm"]
    g = np.array(registration["world_model_to_soma"])
    b = {k: np.array(v) for k, v in registration["registrations"].items()}
    frames = len(motion["frame_idx"])
    rotations = np.empty((frames, 3, 3, 3))
    errors = []
    for f in range(frames):
        tr = motion["global_rots"][f, INDEX["thorax"]]
        rotations[f, 0] = g @ tr @ b["Chest"]
        for j, (side, name) in enumerate(
            [("R", "RightArm"), ("L", "LeftArm")], start=1
        ):
            hr = motion["global_rots"][f, INDEX[f"humerus_{side}"]]
            rotations[f, j] = g @ hr @ b[name]
            local = map_registered_frames(tr, hr, b["Chest"], b[name])
            if not np.allclose(local, rotations[f, 0].T @ rotations[f, j], atol=1e-9):
                raise RuntimeError("Local registration invariant failed")
            recovered = b["Chest"] @ local @ b[name].T
            errors.append(float(np.max(np.abs(recovered - tr.T @ hr))))
    return {
        "frame_idx": motion["frame_idx"],
        "joint_names": np.array(names),
        "global_rots": rotations,
        "rest_global_rots": np.tile(np.eye(3), (3, 1, 1)),
    }, max(errors)
