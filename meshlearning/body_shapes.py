"""Original adult surface variants; skeleton, weights and motion remain fixed."""

import numpy as np

from .pitch import NAMES

PROFILES = {
    "slender": {"torso_width": 0.86, "torso_depth": 0.78, "limb_radius": 0.82},
    "baseline": {"torso_width": 1.0, "torso_depth": 1.0, "limb_radius": 1.0},
    "fuller": {"torso_width": 1.13, "torso_depth": 1.42, "limb_radius": 1.22},
}


def shape_vertices(vertices, weights, positions, rotations, profile):
    """Blend radial rest-surface offsets using the unchanged baseline skin weights.

    Longitudinal segment coordinates are preserved by each individual transform.
    No age, BMI, clinical morphology or population coverage is asserted.
    """
    params = PROFILES[profile]
    vertices = np.asarray(vertices, dtype=float)
    offsets = np.zeros_like(vertices)
    for j, name in enumerate(NAMES):
        if name in ("pelvis", "thorax"):
            scale = np.array([params["torso_width"], params["torso_depth"], 1.0])
            delta = (vertices - positions[j]) * (scale - 1)
        elif name.startswith(("humerus", "forearm", "thigh", "shank", "deltoid")):
            local = (vertices - positions[j]) @ rotations[j]
            local[:, :2] *= params["limb_radius"] - 1
            local[:, 2] = 0
            delta = local @ rotations[j].T
        else:
            continue
        offsets += weights[:, j, None] * delta
    result = vertices + offsets
    if not np.isfinite(result).all():
        raise ValueError("Non-finite shape vertices")
    return result
