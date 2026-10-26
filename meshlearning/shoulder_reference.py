"""Landmark-defined thorax--humerus reference, with no learned calibration.

Frames: X anterior, Y superior/proximal, Z subject right. Intrinsic Y-X-Y:
R_right = Ry(plane) Rx(-elevation) Ry(axial). Left anatomical directions use
sagittal mirror conjugation. Published values retain the physical raw YXY
triplet as well as the bilateral clinical-direction convention.

This implements an explicit ISB-style model convention, not clinical validation
of real landmarks or a registration of arbitrary SOMA segment frames.
"""

from dataclasses import asdict, dataclass

import numpy as np

from .controls import validate_rotation
from .frames import humerus_frame, thorax_frame

DEFINITION_VERSION = "thorax-humerus-landmark-yxy-v1"
SAGITTAL_MIRROR = np.diag([1.0, 1.0, -1.0])
SINGULAR_SINE_TOL = 1e-8
NEAR_SINGULAR_DEG = 2.0


def wrap_degrees(value):
    return float((value + 180.0) % 360.0 - 180.0)


@dataclass(frozen=True)
class ShoulderAngles:
    side: str
    plane_of_elevation_deg: float | None
    elevation_deg: float
    axial_yxy_deg: float | None
    raw_yxy_deg: tuple[float | None, float, float | None]
    frontal_swing_component_deg: float | None
    sagittal_swing_component_deg: float | None
    minimal_swing_twist_deg: float | None
    yxy_valid: bool
    singularity: str | None
    near_singularity: bool
    definition_version: str = DEFINITION_VERSION

    def to_dict(self):
        return asdict(self)


def frames_from_landmarks(landmarks, side):
    """Require explicit IJ, C7, PX, T8, GH, EL and EM world positions.

    GH is a joint centre; using a visible skin point instead requires validation.
    No camera/world-axis defaults or inferred anatomical registrations are used.
    """
    if side not in ("R", "L"):
        raise ValueError("Side must be R or L")
    points = {}
    for name in ("IJ", "C7", "PX", "T8", "GH", "EL", "EM"):
        if name not in landmarks:
            raise ValueError(f"Missing anatomical landmark {name}")
        point = np.asarray(landmarks[name], dtype=float)
        if point.shape != (3,) or not np.isfinite(point).all():
            raise ValueError(f"Invalid landmark {name}")
        points[name] = point
    t = thorax_frame(*(points[k] for k in ("IJ", "C7", "PX", "T8")))
    h = humerus_frame(*(points[k] for k in ("GH", "EL", "EM")), side)
    return validate_rotation(t), validate_rotation(h)


def angles_from_frames(thorax_world, humerus_world, side):
    """Extract angles from anatomical frames (columns are axes in world).

    R = R_thorax.T R_humerus. Do not subtract an arbitrary rig rest rotation:
    registration to the anatomical frames must happen BEFORE this function.
    At elevation 0/180 plane and axial YXY are non-unique and returned as None.
    At arm-down only, their combined twist is still identifiable.
    """
    if side not in ("R", "L"):
        raise ValueError("Side must be R or L")
    t, h = validate_rotation(thorax_world), validate_rotation(humerus_world)
    r = t.T @ h
    if side == "L":
        r = SAGITTAL_MIRROR @ r @ SAGITTAL_MIRROR
    proximal = r[:, 1]
    sine = float(np.hypot(proximal[0], proximal[2]))
    cosine = float(np.clip(proximal[1], -1, 1))
    elevation = float(np.rad2deg(np.arctan2(sine, cosine)))
    valid = sine > SINGULAR_SINE_TOL
    near = min(elevation, 180 - elevation) < NEAR_SINGULAR_DEG
    if not valid:
        up = cosine < 0
        twist = None if up else wrap_degrees(np.rad2deg(np.arctan2(r[0, 2], r[0, 0])))
        return ShoulderAngles(
            side=side,
            plane_of_elevation_deg=None,
            elevation_deg=elevation,
            axial_yxy_deg=None,
            raw_yxy_deg=(None, elevation if side == "L" else -elevation, None),
            frontal_swing_component_deg=None if up else 0.0,
            sagittal_swing_component_deg=None if up else 0.0,
            minimal_swing_twist_deg=twist,
            yxy_valid=False,
            singularity="arm_up" if up else "arm_down",
            near_singularity=True,
        )
    # Direct entries of Ry(alpha) Rx(beta) Ry(gamma), beta=-elevation.
    plane = wrap_degrees(np.rad2deg(np.arctan2(-r[0, 1], -r[2, 1])))
    axial = wrap_degrees(np.rad2deg(np.arctan2(-r[1, 0], r[1, 2])))
    # Independently construct the shortest swing carrying proximal Y to R Y.
    # The residual is a pure rotation about proximal Y in neutral coordinates.
    a = np.array([0.0, 1.0, 0.0])
    axis = np.cross(a, proximal) / sine
    x, y, z = axis
    k = np.array([[0, -z, y], [z, 0, -x], [-y, x, 0]])
    swing = np.eye(3) + sine * k + (1 - cosine) * (k @ k)
    residual = swing.T @ r
    twist = wrap_degrees(np.rad2deg(np.arctan2(residual[0, 2], residual[0, 0])))
    sign = 1 if side == "R" else -1
    return ShoulderAngles(
        side=side,
        plane_of_elevation_deg=plane,
        elevation_deg=elevation,
        axial_yxy_deg=axial,
        raw_yxy_deg=(
            wrap_degrees(sign * plane),
            -sign * elevation,
            wrap_degrees(sign * axial),
        ),
        frontal_swing_component_deg=float(elevation * np.cos(np.deg2rad(plane))),
        sagittal_swing_component_deg=float(elevation * np.sin(np.deg2rad(plane))),
        minimal_swing_twist_deg=twist,
        yxy_valid=True,
        singularity=None,
        near_singularity=near,
    )


def angles_from_landmarks(landmarks, side):
    return angles_from_frames(*frames_from_landmarks(landmarks, side), side)


def angles_from_registered_segments(
    thorax_segment_world,
    humerus_segment_world,
    thorax_anatomical_in_segment,
    humerus_anatomical_in_segment,
    side,
):
    """Use explicit fixed anatomical-axis registrations, with no fallback.

    B contains anatomical axes expressed in a technical segment's coordinates:
    R_anatomical_world = R_technical_world @ B. These B matrices must come from
    known landmarks/rig metadata, never from fitting the angle outputs.
    """
    t = validate_rotation(thorax_segment_world)
    h = validate_rotation(humerus_segment_world)
    bt = validate_rotation(thorax_anatomical_in_segment)
    bh = validate_rotation(humerus_anatomical_in_segment)
    return angles_from_frames(t @ bt, h @ bh, side)
