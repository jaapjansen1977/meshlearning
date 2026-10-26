"""Explicit model-landmark frame construction and a guarded SOMA frame contract.

Virtual landmark placement is a design assumption, not anatomical validation.
ISB-oriented X anterior / Y superior / Z right; shoulder Y-X-Y representation.
"""

import numpy as np

# Columns express the ISB-oriented model axes in our segment coordinates.
MODEL_FROM_ISB = np.array([[0.0, 0.0, 1.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])


def unit(v):
    v = np.asarray(v, dtype=float)
    length = np.linalg.norm(v)
    if not np.isfinite(v).all() or length < 1e-9:
        raise ValueError("Degenerate anatomical landmark geometry")
    return v / length


def thorax_frame(ij, c7, px, t8):
    upper = (np.asarray(ij) + c7) / 2
    lower = (np.asarray(px) + t8) / 2
    y = unit(upper - lower)
    z0 = unit(np.cross(np.asarray(c7) - ij, lower - ij))
    x = unit(np.cross(y, z0))
    z = unit(np.cross(x, y))
    return np.column_stack([x, y, z])


def humerus_frame(gh, el, em, side):
    if side not in ("R", "L"):
        raise ValueError("R or L required")
    y = unit(np.asarray(gh) - (np.asarray(el) + em) / 2)
    z0 = (np.asarray(el) - em) * (1 if side == "R" else -1)
    x = unit(np.cross(y, z0))
    z = unit(np.cross(x, y))
    return np.column_stack([x, y, z])


def virtual_landmarks(thorax_origin, thorax_rotation, gh, humerus_rotation, side):
    origin = np.asarray(thorax_origin)
    tr = np.asarray(thorax_rotation)
    hr = np.asarray(humerus_rotation)
    d = {
        "IJ": origin + tr @ np.array([0, 0.08, 0.32]),
        "C7": origin + tr @ np.array([0, -0.08, 0.32]),
        "PX": origin + tr @ np.array([0, 0.08, 0.05]),
        "T8": origin + tr @ np.array([0, -0.08, 0.05]),
        "GH": np.asarray(gh),
    }
    elbow = np.asarray(gh) + hr @ np.array([0, 0, -0.30])
    offset = hr @ np.array([0.035 * (1 if side == "R" else -1), 0, 0])
    d["EL"] = elbow + offset
    d["EM"] = elbow - offset
    return d


def landmark_yxy(landmarks, side):
    t = thorax_frame(*(landmarks[k] for k in ("IJ", "C7", "PX", "T8")))
    h = humerus_frame(*(landmarks[k] for k in ("GH", "EL", "EM")), side)
    r = t.T @ h
    sign = 1 if side == "R" else -1
    beta = -sign * np.arccos(np.clip(r[1, 1], -1, 1))
    if abs(np.sin(beta)) < 1e-7:
        return np.array([np.nan, beta, np.nan]), False
    alpha = np.arctan2(r[0, 1] / np.sin(beta), r[2, 1] / np.sin(beta))
    gamma = np.arctan2(r[1, 0] / np.sin(beta), -r[1, 2] / np.sin(beta))
    return np.rad2deg([alpha, beta, gamma]), True


def map_registered_frames(thorax, humerus, thorax_registration, humerus_registration):
    """Registration B_s expresses SOMA segment axes in our model segment frame.

    R_soma_s = G @ R_model_s @ B_s; common world transform G cancels locally.
    Never substitute guessed registrations into the actual Movalytics calibration.
    """
    if thorax_registration is None or humerus_registration is None:
        raise ValueError(
            "Measured/verified Chest and Arm registrations required; no identity fallback"
        )
    for b in (thorax_registration, humerus_registration):
        if (
            np.asarray(b).shape != (3, 3)
            or not np.isfinite(b).all()
            or not np.allclose(np.asarray(b).T @ b, np.eye(3), atol=1e-8)
            or not np.isclose(np.linalg.det(b), 1, atol=1e-8)
        ):
            raise ValueError("Registration must be a proper rotation")
    return (
        np.asarray(thorax_registration).T
        @ np.asarray(thorax).T
        @ humerus
        @ humerus_registration
    )
