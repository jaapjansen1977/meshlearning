"""Right-handed world: X right, Y anterior, Z up; metres and degrees.

Local active rotations are Rx(x_control) @ Ry(y_control) @ Rz(z_control).
These are engineering controls, NOT validated ISB anatomical angles.
"""

import numpy as np

# name, parent, rest offset, segment endpoint, radius
BONES = [
    ("pelvis", None, (0, 0, 1.0), (0, 0, 0.15), 0.14),
    ("trunk", "pelvis", (0, 0, 0.15), (0, 0, 0.37), 0.16),
    ("neck", "trunk", (0, 0, 0.37), (0, 0, 0.10), 0.055),
    ("head", "neck", (0, 0, 0.10), (0, 0, 0.19), 0.10),
]
for side, sign in [("L", -1), ("R", 1)]:
    BONES += [
        (f"clavicle_{side}", "trunk", (0, 0, 0.32), (sign * 0.20, 0, 0), 0.045),
        (
            f"upperarm_{side}",
            f"clavicle_{side}",
            (sign * 0.20, 0, 0),
            (0, 0, -0.29),
            0.055,
        ),
        (f"forearm_{side}", f"upperarm_{side}", (0, 0, -0.29), (0, 0, -0.25), 0.043),
        (f"hand_{side}", f"forearm_{side}", (0, 0, -0.25), (0, 0, -0.13), 0.042),
        (f"thigh_{side}", "pelvis", (sign * 0.095, 0, 0), (0, 0, -0.43), 0.075),
        (f"shank_{side}", f"thigh_{side}", (0, 0, -0.43), (0, 0, -0.43), 0.052),
        (f"foot_{side}", f"shank_{side}", (0, 0, -0.43), (0, 0.19, -0.045), 0.055),
    ]
NAMES = [b[0] for b in BONES]


def rotation(angles):
    x, y, z = np.deg2rad(angles)
    cx, sx = np.cos(x), np.sin(x)
    cy, sy = np.cos(y), np.sin(y)
    cz, sz = np.cos(z), np.sin(z)
    return (
        np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]])
        @ np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
        @ np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]])
    )


def decompose(r):
    """Inverse of the control convention, valid away from +/-90 degree Y singularity."""
    return np.rad2deg(
        [
            np.arctan2(-r[1, 2], r[2, 2]),
            np.arcsin(np.clip(r[0, 2], -1, 1)),
            np.arctan2(-r[0, 1], r[0, 0]),
        ]
    )


def forward(controls, scale=1.0):
    positions = []
    rotations = []
    ends = []
    for i, (name, parent, offset, end, _) in enumerate(BONES):
        pr = np.eye(3) if parent is None else rotations[NAMES.index(parent)]
        pp = np.zeros(3) if parent is None else positions[NAMES.index(parent)]
        p = pp + pr @ (np.array(offset) * scale)
        r = pr @ rotation(controls[i])
        positions.append(p)
        rotations.append(r)
        ends.append(p + r @ (np.array(end) * scale))
    return np.array(positions), np.array(rotations), np.array(ends)


def generate(frames=48, fps=24, scale=1.0):
    if frames < 2 or fps <= 0 or scale <= 0:
        raise ValueError("frames >= 2, fps > 0 and scale > 0 required")
    # Deterministic smooth, deliberately broad controls. Not a physiological ROM prescription.
    amplitudes = {
        "pelvis": (4, 4, 12),
        "trunk": (18, 15, 25),
        "neck": (12, 12, 20),
        "head": (8, 8, 10),
        "clavicle": (4, 4, 6),
        "upperarm": (85, 40, 65),
        "forearm": (65, 0, 45),
        "hand": (25, 15, 10),
        "thigh": (65, 25, 60),
        "shank": (60, 0, 0),
        "foot": (20, 10, 8),
    }
    controls = np.zeros((frames, len(BONES), 3))
    for j, name in enumerate(NAMES):
        a = np.array(amplitudes[name.split("_")[0]])
        for axis in range(3):
            controls[:, j, axis] = a[axis] * np.sin(
                np.linspace(0, 2 * np.pi, frames) + j * 0.37 + axis * 0.8
            )
    # Start at neutral, useful for detecting frame alignment and rest-pose errors.
    controls[0] = 0
    # Smoothly blend away from neutral over first quarter of the sequence.
    ramp = np.minimum(np.arange(frames) / max(1, frames // 4), 1)
    ramp = ramp * ramp * (3 - 2 * ramp)
    controls *= ramp[:, None, None]
    p, r, e = zip(*(forward(c, scale) for c in controls))
    return {
        "frame_idx": np.arange(frames),
        "time_s": np.arange(frames) / fps,
        "joint_names": np.array(NAMES),
        "controls_deg": controls,
        "joint_positions_world": np.array(p),
        "global_rots": np.array(r),
        "endpoints_world": np.array(e),
        "rest_global_rots": np.tile(np.eye(3), (len(BONES), 1, 1)),
    }
