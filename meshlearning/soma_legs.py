"""Explicit template-based lower-limb registration, not an anatomical fit."""

import numpy as np

from .frames import unit
from .pitch import INDEX, down_frame
from .soma_bridge import proper_rotation, template_registration

SEGMENTS = {
    "Hips": "pelvis",
    "RightLeg": "thigh_R",
    "RightShin": "shank_R",
    "RightFoot": "foot_R",
    "LeftLeg": "thigh_L",
    "LeftShin": "shank_L",
    "LeftFoot": "foot_L",
}
PAIRS = (
    ("Hips", "RightLeg"),
    ("RightLeg", "RightShin"),
    ("RightShin", "RightFoot"),
    ("Hips", "LeftLeg"),
    ("LeftLeg", "LeftShin"),
    ("LeftShin", "LeftFoot"),
)


def leg_registration(rig):
    g = np.array(template_registration(rig)["world_model_to_soma"])
    names = rig["joint_names"]
    t = rig["t_pose_world"]
    records = {}
    model_toe = unit(np.array([0.0, 0.18, -0.035]))
    toe_basis = np.column_stack([[1, 0, 0], model_toe, np.cross([1, 0, 0], model_toe)])
    for name in SEGMENTS:
        if name not in names:
            raise ValueError(f"Missing required segment {name}")
        idx = names.index(name)
        soma_r = proper_rotation(t[idx, :3, :3])
        if name == "Hips":
            model_r = np.eye(3)
        elif name.endswith("Foot"):
            toe = name.replace("Foot", "ToeBase")
            forward = unit(g.T @ (t[names.index(toe), :3, 3] - t[idx, :3, 3]))
            right = unit(np.cross(forward, [0, 0, 1]))
            foot_basis = np.column_stack([right, forward, np.cross(right, forward)])
            # Preserve the exact rest toe vector of our renderer, not a silent
            # replacement of it by the SOMA Foot->ToeBase vector.
            model_r = foot_basis @ toe_basis.T
        else:
            distal = (
                name.replace("Leg", "Shin")
                if name.endswith("Leg")
                else name.replace("Shin", "Foot")
            )
            direction = g.T @ (t[names.index(distal), :3, 3] - t[idx, :3, 3])
            model_r = down_frame(direction, np.array([0, 1, 0]))
        b = proper_rotation(model_r.T @ g.T @ soma_r)
        if not np.allclose(g @ model_r @ b, soma_r, atol=1e-8):
            raise ValueError("Reference template reconstruction failed")
        records[name] = {
            "model_reference_rotation": model_r.tolist(),
            "soma_reference_rotation": soma_r.tolist(),
            "segment_registration": b.tolist(),
        }
    return {
        "world_model_to_soma": g.tolist(),
        "segments": records,
        "rig_sha256": rig["sha256"],
        "status": "template-based lower-limb convention; no measured ASIS/PSIS, femoral epicondylar or malleolar axes",
        "assumptions": [
            "Pelvis reference aligned with subject right/anterior/superior",
            "Leg/shin long axes from template joint centres; zero twist from projected subject anterior",
            "Foot reference from Foot->ToeBase and subject up, preserving our [0,.18,-.035] toe vector",
            "No angles, signs, axes or calibration weights fitted to output",
        ],
    }


def map_legs(global_rots, registration):
    source = np.asarray(global_rots)
    names = list(SEGMENTS)
    g = np.array(registration["world_model_to_soma"])
    b = {
        n: np.array(registration["segments"][n]["segment_registration"]) for n in names
    }
    mapped = np.stack([g @ source[:, INDEX[SEGMENTS[n]]] @ b[n] for n in names], axis=1)
    error = 0.0
    for parent, child in PAIRS:
        local = (
            mapped[:, names.index(parent)].swapaxes(-1, -2)
            @ mapped[:, names.index(child)]
        )
        recovered = b[parent] @ local @ b[child].T
        expected = (
            source[:, INDEX[SEGMENTS[parent]]].swapaxes(-1, -2)
            @ source[:, INDEX[SEGMENTS[child]]]
        )
        error = max(error, float(np.max(np.abs(recovered - expected))))
    if error > 1e-8:
        raise ValueError("Lower-limb inverse registration failed")
    return {
        "global_rots": mapped,
        "joint_names": np.array(names),
        "rest_global_rots": np.tile(np.eye(3), (len(names), 1, 1)),
        "template_rest_global_rots": np.array(
            [registration["segments"][n]["soma_reference_rotation"] for n in names]
        ),
    }, error
