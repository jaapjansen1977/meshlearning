"""Anatomically restricted procedural skin weights, not nearest-bone-only binding."""

import numpy as np

from .pitch import INDEX, NAMES


def smoothstep(value):
    t = np.clip(value, 0, 1)
    return t * t * (3 - 2 * t)


def weights_for_vertices(vertices, positions, rotations, endpoints, radii):
    vertices = np.asarray(vertices, dtype=float)
    distances = []
    for j in range(len(NAMES)):
        delta = endpoints[j] - positions[j]
        u = np.clip(((vertices - positions[j]) @ delta) / np.dot(delta, delta), 0, 1)
        distances.append(
            np.maximum(
                np.linalg.norm(vertices - (positions[j] + u[:, None] * delta), axis=1)
                - radii[j] * 0.45,
                0,
            )
        )
    distances = np.array(distances).T
    # Initial binding is retained for legs/head, then torso and arms get ownership constraints.
    nearest = np.argsort(distances, axis=1)[:, :4]
    raw = np.exp(-(np.take_along_axis(distances, nearest, axis=1) ** 2) / 0.065**2)
    weights = np.zeros((len(vertices), len(NAMES)))
    np.put_along_axis(weights, nearest, raw / raw.sum(axis=1, keepdims=True), axis=1)
    root_z = positions[INDEX["pelvis"], 2]
    chest_top = positions[INDEX["neck"], 2] + 0.01
    torso = (
        (vertices[:, 2] > root_z + 0.04)
        & (vertices[:, 2] < chest_top)
        & (np.abs(vertices[:, 0]) < 0.24)
    )
    blend = smoothstep((vertices[:, 2] - (root_z + 0.07)) / 0.17)
    weights[torso] = 0
    weights[torso, INDEX["pelvis"]] = 1 - blend[torso]
    weights[torso, INDEX["thorax"]] = blend[torso]
    region = np.full(len(vertices), "other", dtype="<U24")
    region[torso] = "torso"
    for side, sign in [("R", 1), ("L", -1)]:
        shoulder = positions[INDEX[f"humerus_{side}"]]
        direction = (endpoints[INDEX[f"humerus_{side}"]] - shoulder) / 0.30
        t = (vertices - shoulder) @ direction
        radial = np.linalg.norm(vertices - (shoulder + t[:, None] * direction), axis=1)
        arm = (
            (sign * vertices[:, 0] > 0.17) & (t > -0.03) & (t < 0.76) & (radial < 0.115)
        )
        amount = smoothstep((sign * vertices[:, 0] - 0.17) / 0.08) * smoothstep(
            (t + 0.005) / 0.085
        )
        arm_weights = np.zeros_like(weights)
        # Only adjacent segments blend near joints; the forearm shaft is rigid.
        elbow = smoothstep((t - 0.275) / 0.05)
        wrist = smoothstep((t - 0.535) / 0.05)
        proximal = 1 - smoothstep((t - 0.035) / 0.08)
        arm_weights[:, INDEX[f"deltoid_{side}"]] = (1 - elbow) * proximal
        arm_weights[:, INDEX[f"humerus_{side}"]] = (1 - elbow) * (1 - proximal)
        arm_weights[:, INDEX[f"forearm_{side}"]] = elbow * (1 - wrist)
        arm_weights[:, INDEX[f"hand_{side}"]] = elbow * wrist
        # Small shoulder transition onto a thorax-owned surface, no distant arm influence.
        weights[arm] = (1 - amount[arm, None]) * weights[arm] + amount[
            arm, None
        ] * arm_weights[arm]
        rigid = arm & (t >= 0.325) & (t <= 0.535) & (amount > 0.999)
        region[arm] = f"arm_{side}"
        region[rigid] = f"rigid_forearm_{side}"
    # Protected interior chest must not be dragged outward by any shoulder/arm bone.
    core = torso & (np.abs(vertices[:, 0]) < 0.17)
    weights[core] = 0
    weights[core, INDEX["pelvis"]] = 1 - blend[core]
    weights[core, INDEX["thorax"]] = blend[core]
    region[core] = "protected_torso"
    if (
        not np.isfinite(weights).all()
        or np.any(weights < 0)
        or not np.allclose(weights.sum(axis=1), 1, atol=1e-12)
    ):
        raise ValueError("Invalid constrained skin weights")
    return weights, region
