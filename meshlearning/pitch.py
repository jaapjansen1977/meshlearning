"""Original keyframed pitch design, without motion-capture or third-party assets.

The thorax-humerus functional convention is explicitly defined here; it is not
an ISB-validated joint coordinate system nor the Movalytics calibration.
"""

import csv
import json
from pathlib import Path

import numpy as np

from .motion import rotation

VERSION = "designed-pitch-v1"
MIRROR = np.diag([-1.0, 1.0, 1.0])
NAMES = ["pelvis", "thorax", "neck", "head"]
PARENTS = [None, "pelvis", "thorax", "neck"]
RADII = [0.15, 0.17, 0.045, 0.095]
for side in ("R", "L"):
    NAMES.extend(
        f"{part}_{side}"
        for part in (
            "clavicle",
            "scapula",
            "deltoid",
            "humerus",
            "forearm",
            "hand",
            "thigh",
            "shank",
            "foot",
        )
    )
    PARENTS.extend(
        [
            "thorax",
            f"clavicle_{side}",
            f"scapula_{side}",
            f"deltoid_{side}",
            f"humerus_{side}",
            f"forearm_{side}",
            "pelvis",
            f"thigh_{side}",
            f"shank_{side}",
        ]
    )
    RADII.extend([0.035, 0.04, 0.075, 0.055, 0.043, 0.037, 0.082, 0.054, 0.052])
INDEX = {name: i for i, name in enumerate(NAMES)}
PHASES = [
    (0.0, "Voorbereiding"),
    (0.4, "Beenheffing"),
    (0.8, "Uitstap"),
    (1.0, "Voetcontact / cocking"),
    (1.1, "Max. ontworpen exorotatie"),
    (1.175, "Nominaal loslaatmoment"),
    (1.45, "Afremmen / uitzwaai"),
    (1.9, "Herstel"),
    (2.1, "Eindstand"),
]


def rz(angle):
    return rotation([0, 0, angle])


def functional_rotation(plane_deg, elevation_deg, axial_deg, side="R"):
    r = rz(plane_deg) @ rotation([0, -elevation_deg, 0]) @ rz(axial_deg)
    return r if side == "R" else MIRROR @ r @ MIRROR


def functional_angles(thorax_world, humerus_world, side="R"):
    """Recover elevation, plane and signed axial rotation geometrically.

    R_HT = Rz(plane) Ry(-elevation) Rz(axial). Positive axial is internally
    directed in the designed right arm. Left uses sagittal mirror conjugation.
    Plane and axial are undefined at elevation 0/180; return NaN plus validity.
    No assertion of ISB or equivalence to a clinical maximum-ER angle.
    """
    r = np.asarray(thorax_world).T @ np.asarray(humerus_world)
    if side == "L":
        r = MIRROR @ r @ MIRROR
    if (
        not np.isfinite(r).all()
        or not np.allclose(r.T @ r, np.eye(3), atol=1e-8)
        or not np.isclose(np.linalg.det(r), 1, atol=1e-8)
    ):
        raise ValueError("Invalid segment orientation")
    direction = r @ np.array([0.0, 0.0, -1.0])
    horizontal = np.hypot(direction[0], direction[1])
    elevation = np.rad2deg(np.arctan2(horizontal, -direction[2]))
    if horizontal < 1e-7:
        return elevation, np.nan, np.nan, False
    plane = np.rad2deg(np.arctan2(direction[1], direction[0]))
    no_twist = rz(plane) @ rotation([0, -elevation, 0])
    twist = no_twist.T @ r
    axial = np.rad2deg(np.arctan2(twist[1, 0], twist[0, 0]))
    return float(elevation), float(plane), float(axial), True


def interpolate(times, values, query):
    """Shape-preserving cubic Hermite interpolation (C1), no SciPy dependency."""
    t = np.asarray(times, dtype=float)
    y = np.asarray(values, dtype=float)
    q = np.asarray(query, dtype=float)
    if t.ndim != 1 or y.shape != t.shape or len(t) < 2 or not np.all(np.diff(t) > 0):
        raise ValueError("Matching finite increasing knots required")
    if (
        not np.isfinite(t).all()
        or not np.isfinite(y).all()
        or not np.isfinite(q).all()
        or np.any(q < t[0])
        or np.any(q > t[-1])
    ):
        raise ValueError("Nonfinite or out-of-range interpolation")
    h = np.diff(t)
    secants = np.diff(y) / h
    slopes = np.zeros_like(y)
    if len(t) == 2:
        slopes[:] = secants[0]
    else:
        for i in range(1, len(t) - 1):
            if secants[i - 1] * secants[i] > 0:
                w1 = 2 * h[i] + h[i - 1]
                w2 = h[i] + 2 * h[i - 1]
                slopes[i] = (w1 + w2) / (w1 / secants[i - 1] + w2 / secants[i])
        for edge, a, b, ha, hb in (
            (0, secants[0], secants[1], h[0], h[1]),
            (-1, secants[-1], secants[-2], h[-1], h[-2]),
        ):
            candidate = ((2 * ha + hb) * a - ha * b) / (ha + hb)
            if candidate * a <= 0:
                candidate = 0.0
            elif a * b < 0 and abs(candidate) > 3 * abs(a):
                candidate = 3 * a
            slopes[edge] = candidate
    i = np.clip(np.searchsorted(t, q, side="right") - 1, 0, len(t) - 2)
    u = (q - t[i]) / h[i]
    return (
        (2 * u**3 - 3 * u**2 + 1) * y[i]
        + (u**3 - 2 * u**2 + u) * h[i] * slopes[i]
        + (-2 * u**3 + 3 * u**2) * y[i + 1]
        + (u**3 - u**2) * h[i] * slopes[i + 1]
    )


def down_frame(direction, anterior):
    """Frame with local -Z along the segment and local Y towards anterior."""
    d = np.asarray(direction, dtype=float)
    z = -d / np.linalg.norm(d)
    y = np.asarray(anterior, dtype=float) - z * np.dot(anterior, z)
    if np.linalg.norm(y) < 1e-8:
        y = np.array([1.0, 0, 0]) - z * z[0]
    y /= np.linalg.norm(y)
    x = np.cross(y, z)
    return np.column_stack([x, y, z])


def leg_ik(hip, ankle, forward):
    """Two 0.45 m links; flag unreachable requests rather than silently claim contact."""
    vector = ankle - hip
    distance = np.linalg.norm(vector)
    clipped = np.clip(distance, 0.001, 0.8999)
    direction = vector / distance
    bend = np.asarray(forward) - direction * np.dot(forward, direction)
    if np.linalg.norm(bend) < 1e-8:
        bend = np.array([0.0, 1, 0]) - direction * direction[1]
    bend /= np.linalg.norm(bend)
    knee = hip + direction * clipped / 2 + bend * np.sqrt(0.45**2 - (clipped / 2) ** 2)
    actual_ankle = hip + direction * clipped
    return knee, actual_ankle, float(abs(distance - clipped))


def pose(parameters, shoulder_motion=True):
    p = {}
    r = {}
    e = {}
    leg_errors = {}
    root = np.array([parameters["root_x"], parameters["root_y"], parameters["root_z"]])
    p["pelvis"] = root
    r["pelvis"] = rz(parameters["pelvis_yaw"])
    e["pelvis"] = root + r["pelvis"] @ np.array([0, 0, 0.11])
    p["thorax"] = e["pelvis"]
    r["thorax"] = rz(parameters["thorax_yaw"]) @ rotation(
        [parameters["trunk_lean"], parameters["trunk_side"], 0]
    )
    e["thorax"] = p["thorax"] + r["thorax"] @ np.array([0, 0, 0.36])
    p["neck"] = e["thorax"]
    r["neck"] = r["thorax"] @ rotation(
        [-parameters["trunk_lean"] * 0.45, 0, -parameters["thorax_yaw"] * 0.6]
    )
    e["neck"] = p["neck"] + r["neck"] @ np.array([0, 0, 0.08])
    p["head"] = e["neck"]
    r["head"] = r["neck"]
    e["head"] = p["head"] + r["head"] @ np.array([0, 0, 0.20])
    for side, sign in [("R", 1), ("L", -1)]:
        elevation = parameters[f"{side}_elevation"]
        plane = parameters[f"{side}_plane"]
        axial = parameters[f"{side}_axial"]
        clav_elevation = min(16, max(0, elevation * 0.12)) if shoulder_motion else 0
        scap_up = max(0, elevation - 25) * 0.35 if shoulder_motion else 0
        protraction = float(np.clip(plane * 0.2, -12, 25)) if shoulder_motion else 0
        p[f"clavicle_{side}"] = p["thorax"] + r["thorax"] @ np.array([0, 0.01, 0.30])
        r[f"clavicle_{side}"] = (
            r["thorax"]
            @ rz(sign * protraction * 0.5)
            @ rotation([0, -sign * clav_elevation, 0])
        )
        e[f"clavicle_{side}"] = p[f"clavicle_{side}"] + r[
            f"clavicle_{side}"
        ] @ np.array([sign * 0.16, 0, 0])
        p[f"scapula_{side}"] = e[f"clavicle_{side}"]
        r[f"scapula_{side}"] = (
            r["thorax"]
            @ rz(sign * protraction)
            @ rotation(
                [4 + elevation * 0.04 if shoulder_motion else 0, -sign * scap_up, 0]
            )
        )
        shoulder = p[f"scapula_{side}"] + r[f"scapula_{side}"] @ np.array(
            [sign * 0.045, 0, -0.012]
        )
        e[f"scapula_{side}"] = shoulder
        p[f"deltoid_{side}"] = shoulder
        r[f"deltoid_{side}"] = r["thorax"] @ functional_rotation(
            plane, elevation, axial * 0.3, side
        )
        e[f"deltoid_{side}"] = shoulder + r[f"deltoid_{side}"] @ np.array([0, 0, -0.09])
        p[f"humerus_{side}"] = shoulder
        r[f"humerus_{side}"] = r["thorax"] @ functional_rotation(
            plane, elevation, axial, side
        )
        e[f"humerus_{side}"] = shoulder + r[f"humerus_{side}"] @ np.array([0, 0, -0.30])
        p[f"forearm_{side}"] = e[f"humerus_{side}"]
        r[f"forearm_{side}"] = r[f"humerus_{side}"] @ rotation(
            [parameters[f"{side}_elbow"], 0, sign * parameters[f"{side}_pronation"]]
        )
        e[f"forearm_{side}"] = p[f"forearm_{side}"] + r[f"forearm_{side}"] @ np.array(
            [0, 0, -0.26]
        )
        p[f"hand_{side}"] = e[f"forearm_{side}"]
        r[f"hand_{side}"] = r[f"forearm_{side}"] @ rotation(
            [parameters[f"{side}_wrist"], 0, 0]
        )
        e[f"hand_{side}"] = p[f"hand_{side}"] + r[f"hand_{side}"] @ np.array(
            [0, 0, -0.14]
        )
        hip = root + r["pelvis"] @ np.array([sign * 0.095, 0, -0.035])
        ankle = np.array(
            [
                parameters[f"{side}_ankle_x"],
                parameters[f"{side}_ankle_y"],
                parameters[f"{side}_ankle_z"],
            ]
        )
        knee, actual_ankle, leg_errors[side] = leg_ik(
            hip, ankle, r["pelvis"] @ np.array([0.0, 1, 0])
        )
        p[f"thigh_{side}"] = hip
        r[f"thigh_{side}"] = down_frame(knee - hip, r["pelvis"] @ np.array([0.0, 1, 0]))
        e[f"thigh_{side}"] = knee
        p[f"shank_{side}"] = knee
        r[f"shank_{side}"] = down_frame(
            actual_ankle - knee, r["pelvis"] @ np.array([0.0, 1, 0])
        )
        e[f"shank_{side}"] = actual_ankle
        p[f"foot_{side}"] = actual_ankle
        r[f"foot_{side}"] = rz(parameters[f"{side}_foot_yaw"]) @ rotation(
            [parameters[f"{side}_heel_raise"], 0, 0]
        )
        e[f"foot_{side}"] = actual_ankle + r[f"foot_{side}"] @ np.array(
            [0, 0.18, -0.035]
        )
    return (
        np.array([p[n] for n in NAMES]),
        np.array([r[n] for n in NAMES]),
        np.array([e[n] for n in NAMES]),
        leg_errors,
    )


def neutral_parameters():
    d = {
        "root_x": 0.0,
        "root_y": 0.0,
        "root_z": 0.96,
        "pelvis_yaw": 0.0,
        "thorax_yaw": 0.0,
        "trunk_lean": 0.0,
        "trunk_side": 0.0,
    }
    for side, sign in [("R", 1), ("L", -1)]:
        d.update(
            {
                f"{side}_elevation": 45.0,
                f"{side}_plane": 0.0,
                f"{side}_axial": 0.0,
                f"{side}_elbow": 0.0,
                f"{side}_pronation": 0.0,
                f"{side}_wrist": 0.0,
                f"{side}_ankle_x": sign * 0.095,
                f"{side}_ankle_y": 0.0,
                f"{side}_ankle_z": 0.075,
                f"{side}_foot_yaw": 0.0,
                f"{side}_heel_raise": 0.0,
            }
        )
    return d


def phase_definitions(config):
    labels = config.get("phase_labels", [label for _, label in PHASES])
    if len(labels) != len(config["key_times_s"]):
        raise ValueError("One phase label per key time required")
    return list(zip(config["key_times_s"], labels))


def generate(config_path, out):
    out = Path(out)
    if out.exists() and any(out.iterdir()):
        raise ValueError(
            "Output directory must be empty; preserve existing review results"
        )
    config = json.loads(Path(config_path).read_text())
    phases = phase_definitions(config)
    fps = config["source_fps"]
    duration = config["key_times_s"][-1]
    if fps <= 0 or duration <= 0:
        raise ValueError("Positive source fps/duration required")
    times = np.arange(round(duration * fps) + 1) / fps
    values = {
        name: interpolate(config["key_times_s"], knots, times)
        for name, knots in config["tracks"].items()
    }
    all_positions = []
    all_rots = []
    all_ends = []
    errors = []
    rows = []
    for f, time in enumerate(times):
        params = {name: float(track[f]) for name, track in values.items()}
        p, r, e, leg_errors = pose(params)
        all_positions.append(p)
        all_rots.append(r)
        all_ends.append(e)
        errors.append(list(leg_errors.values()))
        phase = next(label for start, label in reversed(phases) if time >= start - 1e-8)
        row = {"frame_idx": f, "time_s": float(time), "phase": phase}
        row.update(
            {
                "thorax_yaw_world_control_deg": params["thorax_yaw"],
                "pelvis_yaw_world_control_deg": params["pelvis_yaw"],
                "thorax_yaw_relative_pelvis_control_deg": params["thorax_yaw"]
                - params["pelvis_yaw"],
                "thorax_extension_control_deg": params["trunk_lean"],
                "thorax_lateral_control_deg": params["trunk_side"],
            }
        )
        for side in ("R", "L"):
            from .frames import landmark_yxy, virtual_landmarks

            lm = virtual_landmarks(
                p[INDEX["thorax"]],
                r[INDEX["thorax"]],
                p[INDEX[f"humerus_{side}"]],
                r[INDEX[f"humerus_{side}"]],
                side,
            )
            yxy, valid_yxy = landmark_yxy(lm, side)
            row.update(
                {
                    f"{side}_landmark_proxy_yxy_{axis}_deg": float(value)
                    for axis, value in zip(("alpha", "beta", "gamma"), yxy)
                }
            )
            row[f"{side}_landmark_proxy_valid"] = valid_yxy
            elevation, plane, axial, valid = functional_angles(
                r[INDEX["thorax"]], r[INDEX[f"humerus_{side}"]], side
            )
            row.update(
                {
                    f"{side}_elevation_deg": elevation,
                    f"{side}_plane_deg": plane,
                    f"{side}_axial_deg": axial,
                    f"{side}_valid": valid,
                    f"{side}_elbow_control_deg": params[f"{side}_elbow"],
                }
            )
        rows.append(row)
    all_positions = np.array(all_positions)
    all_rots = np.array(all_rots)
    all_ends = np.array(all_ends)
    rest_p, rest_r, rest_e, _ = pose(neutral_parameters())
    render_frames = np.arange(0, len(times), config["render_stride"], dtype=int)
    if render_frames[-1] != len(times) - 1:
        render_frames = np.append(render_frames, len(times) - 1)
    out.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        out / "motion.npz",
        source_fps=np.array(fps),
        phase_times_s=np.array([t for t, _ in phases]),
        phase_names=np.array([name for _, name in phases]),
        nominal_release_time_s=np.array(config["key_times_s"][5]),
        frame_idx=np.arange(len(times)),
        time_s=times,
        joint_names=np.array(NAMES),
        parents=np.array([p or "" for p in PARENTS]),
        radii=np.array(RADII),
        joint_positions_world=all_positions,
        global_rots=all_rots,
        endpoints_world=all_ends,
        rest_positions_world=rest_p,
        rest_global_rots=rest_r,
        rest_endpoints_world=rest_e,
        render_frames=render_frames,
    )
    with (out / "angles.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    expected = np.array(
        [
            [values[f"{s}_{key}"] for key in ("elevation", "plane", "axial")]
            for s in ("R", "L")
        ]
    ).transpose(2, 0, 1)
    calculated = np.array(
        [
            [
                [row[f"{s}_{key}_deg"] for key in ("elevation", "plane", "axial")]
                for s in ("R", "L")
            ]
            for row in rows
        ]
    )
    error = float(np.nanmax(np.abs(calculated - expected)))
    report = {
        "version": config.get("version", VERSION),
        "motion_source": "original authored numerical tracks; no recorded performer, mocap, copied animation or external mesh",
        "source_fps": fps,
        "duration_s": duration,
        "source_frames": len(times),
        "render_frames": len(render_frames),
        "render_source_fps": fps / config["render_stride"],
        "playback_fps": config["playback_fps"],
        "slowdown_factor": fps / config["render_stride"] / config["playback_fps"],
        "phases": [{"time_s": t, "name": name} for t, name in phases],
        "angle_definition": "R_HT = Rz(plane) @ Ry(-elevation) @ Rz(axial); L uses mirrored frame; positive axial internally directed",
        "angle_status": "functional engineering labels, NOT ISB validated; NOT Movalytics angles",
        "undefined_angles": "Plane/axial undefined when humerus is parallel to thorax Z; marked invalid/NaN",
        "max_label_roundtrip_error_deg": error,
        "max_leg_ik_target_error_m": float(np.max(errors)),
        "checks": {
            "finite_positions": bool(np.isfinite(all_positions).all()),
            "proper_rotations": bool(
                np.allclose(all_rots.swapaxes(-1, -2) @ all_rots, np.eye(3), atol=1e-8)
                and np.allclose(np.linalg.det(all_rots), 1, atol=1e-8)
            ),
            "labels_match_design": error < 1e-7,
            "leg_targets_reachable": float(np.max(errors)) < 1e-5,
        },
        "assumptions": [
            "Clavicle/scapula motion is heuristic, not measured or ISB calibrated",
            "Scapular frame is a simplified rig control, not a landmark-derived bone frame",
            "Deltoid helpers distribute deformation and are not anatomical segments",
            "No physical dynamics, collision/contact certification or muscle simulation",
            "Nominal release is an authored event, no ball flight simulation",
            "Continuous procedural surface is a review mannequin, not a population-valid human model",
            "No GEM-X, SOMA mapping, Movalytics or model training performed",
        ],
    }
    (out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    (out / "design.json").write_text(json.dumps(config, indent=2) + "\n")
    if not all(report["checks"].values()):
        raise RuntimeError(f"Pitch generation checks failed; inspect {out}/report.json")
    return report
