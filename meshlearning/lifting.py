"""Original bilateral sagittal lifting model with five lumbar bending links.

Frames X right, Y anterior, Z up. Positive pelvis tilt is anterior;
positive lumbar angle is flexion relative to pelvis, not a clinical L1-S1
measurement. No motion capture, learned calibration or external body assets.
"""

import csv
import json
from pathlib import Path

import numpy as np

from .motion import rotation

VARIANTS = {
    "hip_hinge": {
        "label": "Heupdominant",
        "pelvis": 65.0,
        "lumbar": 5.0,
        "shank": 5.0,
        "thigh": 20.0,
    },
    "mixed_stoop": {
        "label": "Gemengde stoop",
        "pelvis": 40.0,
        "lumbar": 30.0,
        "shank": 8.0,
        "thigh": 25.0,
    },
    "lumbar_dominant": {
        "label": "Rugdominant",
        "pelvis": -8.0,
        "lumbar": 60.0,
        "shank": 20.0,
        "thigh": 45.0,
    },
    "squat": {
        "label": "Squat",
        "pelvis": 15.0,
        "lumbar": 10.0,
        "shank": 30.0,
        "thigh": 65.0,
    },
}


def up(degrees, length):
    a = np.deg2rad(degrees)
    return np.array([0.0, length * np.sin(a), length * np.cos(a)])


def signed_x(matrix):
    return float(np.rad2deg(np.arctan2(matrix[2, 1], matrix[1, 1])))


def arm_elbow(shoulder, wrist):
    """Exact 0.32/0.29 m two-link reach; elbow bends posteriorly."""
    d = wrist - shoulder
    distance = np.linalg.norm(d)
    if not 0.030001 < distance < 0.609999:
        raise ValueError(f"Unreachable hand target: {distance}")
    direction = d / distance
    bend = np.array([0.0, -1.0, 0.0])
    bend -= direction * np.dot(bend, direction)
    bend /= np.linalg.norm(bend)
    along = (0.32**2 - 0.29**2 + distance**2) / (2 * distance)
    return shoulder + along * direction + np.sqrt(0.32**2 - along**2) * bend


def sample(variant, time):
    """Six seconds: lower, grasp hold, lift, top hold, lower, release, rise."""
    spec = VARIANTS[variant]
    # Smoothstep, zero velocity at the deliberately slow phase boundaries.
    knots = [0.0, 1.4, 1.8, 3.0, 3.5, 4.7, 5.0, 6.0]
    bends = [0.0, 1.0, 1.0, 0.0, 0.0, 1.0, 1.0, 0.0]
    box_heights = [1.0, 0.65, 0.65, 1.0, 1.0, 0.65, 0.65, 1.0]
    # Hands descend to the stationary raised box before grasp; box only moves
    # during the grasp interval. On release the hands return independently.
    i = min(np.searchsorted(knots, time, side="right") - 1, len(knots) - 2)
    i = max(i, 0)
    u = np.clip((time - knots[i]) / (knots[i + 1] - knots[i]), 0, 1)
    s = u * u * (3 - 2 * u)
    bend = bends[i] * (1 - s) + bends[i + 1] * s
    handle_z = box_heights[i] * (1 - s) + box_heights[i + 1] * s
    held = 1.8 <= time <= 4.7
    box_z = handle_z if held else 0.65
    pelvis = spec["pelvis"] * bend
    lumbar = spec["lumbar"] * bend
    alpha = spec["shank"] * bend
    beta = 5.0 + (spec["thigh"] - 5.0) * bend
    points, rots, ends, names, parents, widths = [], [], [], [], [], []

    def add(name, parent, p, e, r, width):
        names.append(name)
        parents.append(parent)
        points.append(p.copy())
        ends.append(e.copy())
        rots.append(r.copy())
        widths.append(width)

    hip = np.array([0.0, 0.0, 0.08]) + up(alpha, 0.45) + up(-beta, 0.45)
    rp = rotation([-pelvis, 0, 0])
    pelvis_top = hip + up(pelvis, 0.10)
    add("pelvis", "", hip, pelvis_top, rp, 0.145)
    base = pelvis_top
    for j in range(5):
        # Each rigid link turns by lumbar/5; total end orientation exactly L.
        theta = pelvis + lumbar * (j + 1) / 5
        r = rotation([-theta, 0, 0])
        end = base + up(theta, 0.035)
        add(
            f"lumbar_{j + 1}",
            "pelvis" if j == 0 else f"lumbar_{j}",
            base,
            end,
            r,
            0.105,
        )
        base = end
    rt = rotation([-pelvis - lumbar, 0, 0])
    shoulder_mid = base + up(pelvis + lumbar, 0.23)
    add("thorax", "lumbar_5", base, shoulder_mid, rt, 0.17)
    neck_end = shoulder_mid + up((pelvis + lumbar) * 0.45, 0.08)
    rn = rotation([-(pelvis + lumbar) * 0.45, 0, 0])
    add("neck", "thorax", shoulder_mid, neck_end, rn, 0.045)
    add(
        "head",
        "neck",
        neck_end,
        neck_end + up((pelvis + lumbar) * 0.45, 0.18),
        rn,
        0.095,
    )
    for side, sign in [("R", 1), ("L", -1)]:
        h = hip + np.array([sign * 0.095, 0, 0])
        ankle = np.array([sign * 0.095, 0.0, 0.08])
        knee = ankle + up(alpha, 0.45)
        add(f"thigh_{side}", "pelvis", h, knee, rotation([beta, 0, 0]), 0.075)
        add(
            f"shank_{side}",
            f"thigh_{side}",
            knee,
            ankle,
            rotation([-alpha, 0, 0]),
            0.05,
        )
        add(
            f"foot_{side}",
            f"shank_{side}",
            ankle,
            ankle + [0, 0.20, -0.035],
            np.eye(3),
            0.05,
        )
        shoulder = shoulder_mid + np.array([sign * 0.195, 0.0, 0.0])
        hand = np.array([sign * 0.19, 0.30 + 0.10 * bend, handle_z])
        wrist = hand + np.array([0.0, 0.0, 0.10])
        elbow = arm_elbow(shoulder, wrist)
        from .pitch import down_frame

        add(
            f"humerus_{side}",
            "thorax",
            shoulder,
            elbow,
            down_frame(elbow - shoulder, [0, 1, 0]),
            0.052,
        )
        add(
            f"forearm_{side}",
            f"humerus_{side}",
            elbow,
            wrist,
            down_frame(wrist - elbow, [0, 1, 0]),
            0.04,
        )
        add(f"hand_{side}", f"forearm_{side}", wrist, hand, np.eye(3), 0.035)
    index = {n: i for i, n in enumerate(names)}
    rr = np.array(rots)
    calculated_hip = signed_x(rp.T @ rr[index["thigh_R"]])
    calculated_knee = -signed_x(rr[index["thigh_R"]].T @ rr[index["shank_R"]])
    calculated_lumbar = -signed_x(rp.T @ rt)
    row = {
        "time_s": float(time),
        "pelvis_anterior_tilt_deg": pelvis,
        "expected_hip_flexion_deg": pelvis + beta,
        "hip_flexion_deg": calculated_hip,
        "expected_knee_flexion_deg": alpha + beta,
        "knee_flexion_deg": calculated_knee,
        "expected_lumbar_flexion_deg": lumbar,
        "lumbar_flexion_deg": calculated_lumbar,
        "thorax_forward_tilt_deg": pelvis + lumbar,
        "handle_height_m": handle_z,
        "box_handle_height_m": box_z,
        "box_held": int(held),
    }
    return {
        "joint_names": np.array(names),
        "parents": np.array(parents),
        "joint_positions_world": np.array(points),
        "endpoints_world": np.array(ends),
        "global_rots": rr,
        "radii": np.array(widths),
        "row": row,
    }


def generate(out, fps=60):
    out = Path(out)
    if out.exists() and any(out.iterdir()):
        raise ValueError("Use a new empty output directory")
    out.mkdir(parents=True, exist_ok=True)
    report = {}
    for variant, spec in VARIANTS.items():
        target = out / variant
        target.mkdir()
        times = np.arange(6 * fps + 1) / fps
        frames = [sample(variant, t) for t in times]
        rows = [f["row"] for f in frames]
        err = max(
            abs(row[f"expected_{key}_deg"] - row[f"{key}_deg"])
            for row in rows
            for key in ["hip_flexion", "knee_flexion", "lumbar_flexion"]
        )
        data = {
            k: np.array([f[k] for f in frames])
            for k in ["joint_positions_world", "endpoints_world", "global_rots"]
        }
        for k in ["joint_names", "parents", "radii"]:
            data[k] = frames[0][k]
        lengths = np.linalg.norm(
            data["endpoints_world"] - data["joint_positions_world"], axis=-1
        )
        length_error = float(np.max(np.abs(lengths - lengths[0])))
        if err > 1e-9 or length_error > 1e-9:
            raise ValueError("Angle/length checks failed")
        np.savez_compressed(
            target / "motion.npz",
            **data,
            time_s=times,
            source_fps=np.array(fps),
            box_handle_height_m=np.array([r["box_handle_height_m"] for r in rows]),
        )
        with (target / "angles.csv").open("w") as f:
            writer = csv.DictWriter(f, fieldnames=rows[0])
            writer.writeheader()
            writer.writerows(rows)
        report[variant] = {
            "label": spec["label"],
            "max_angle_error_deg": err,
            "max_link_length_change_m": length_error,
            "bottom": rows[round(1.8 * fps)],
        }
    (out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    return report
