"""Separate provable calibration range limits from provisional anatomical mapping.

Never refits calibration or edits the external Movalytics checkout. Random
SO(3) controls deliberately bypass all anatomical registration assumptions.
"""

import argparse
import csv
import json
import os
import subprocess
import sys
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/tmp/meshlearning-matplotlib")
os.environ.setdefault("XDG_CACHE_HOME", "/tmp/meshlearning-review-cache")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.spatial.transform import Rotation

from meshlearning.soma_bridge import MOVALYTICS_COMMIT, sha256_file

p = argparse.ArgumentParser()
p.add_argument("--movalytics", type=Path, required=True)
p.add_argument("--sweep", type=Path, required=True)
p.add_argument("--out", type=Path, required=True)
a = p.parse_args()
if a.out.exists() and any(a.out.iterdir()):
    p.error("Use a new empty directory")
root = a.movalytics.resolve()
if (
    subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "HEAD"], text=True
    ).strip()
    != MOVALYTICS_COMMIT
):
    raise ValueError("Wrong revision")
sys.path.insert(0, str(root / "src"))
import movalytics
from movalytics import extract_clinical_angles, load_mapping
from movalytics.kinematics import extract_motion_matrices_per_joint
from movalytics.kinematics.decompose import decompose_swing_twist

if Path(movalytics.__file__).resolve().parent != root / "src/movalytics":
    raise ValueError("Wrong import")
contract = json.loads(
    (
        Path(__file__).resolve().parents[1] / "docs/pitch-v2/frame-contract.json"
    ).read_text()
)["movalytics"]
cal = root / "calibrations/soma_gemx_v14.json"
if (
    sha256_file(cal) != contract["calibration_sha256"]
    or sha256_file(root / "src/movalytics/kinematics/extract.py")
    != contract["source_sha256"]
):
    raise ValueError("Changed source or calibration")
mapping = load_mapping(cal)
a.out.mkdir(parents=True, exist_ok=True)
report = {
    "movalytics_commit": MOVALYTICS_COMMIT,
    "calibration_sha256": sha256_file(cal),
    "calibration_modified": False,
    "gemx_executed": False,
    "filter": "disabled; bounds concern raw outputs only",
    "scope": "proven algebraic limits of this public calibration, not a reproduction of the private/working app",
    "bounds": {},
    "random_seed": 20261026,
    "random_rotations": 10000,
}
rng = np.random.default_rng(report["random_seed"])
random_r = Rotation.random(report["random_rotations"], random_state=rng)
mats = random_r.as_matrix()
# Actual public API, with Chest=I and both arm matrices equal to each test R.
# Consequently R_motion=R, independently of SOMA/anatomical frame choices.
globals_r = np.tile(np.eye(3), (len(mats), 3, 1, 1))
globals_r[:, 1] = mats
globals_r[:, 2] = mats
api = extract_clinical_angles(
    globals_r,
    np.tile(np.eye(3), (3, 1, 1)),
    ["Chest", "RightArm", "LeftArm"],
    fps=60,
    mapping=mapping,
    apply_lowpass_filter=False,
)
quaternion_errors = []
formula_errors = []
bound_rows = []
for side in ("R", "L"):
    jm = mapping.joints[f"shoulder_{side}"]
    e = np.array(jm.axes)
    e /= np.linalg.norm(e, axis=1)[:, None]
    axis, b, c = e
    raw = np.degrees(decompose_swing_twist(mats, *np.array(jm.axes)))
    # Independent quaternion projection onto the twist axis, rather than the
    # production algorithm's rotated-axis cross product and residual matrix.
    q = random_r.as_quat()
    projection = q[:, :3] @ axis
    twist_q = np.column_stack([projection[:, None] * axis, q[:, 3]])
    norm = np.linalg.norm(twist_q, axis=1)
    if np.any(norm < 1e-8):
        raise ValueError("Random test hit undefined twist")
    twist_q /= norm[:, None]
    twist = Rotation.from_quat(twist_q)
    swing_vector = (random_r * twist.inv()).as_rotvec()
    twist_angle = np.rad2deg(2 * np.arctan2(projection, q[:, 3]))
    twist_error = (raw[:, 0] - twist_angle + 180) % 360 - 180
    independent_swing = np.rad2deg(
        np.column_stack([swing_vector @ b, swing_vector @ c])
    )
    quaternion_errors.extend(
        [
            float(np.max(np.abs(twist_error))),
            float(np.max(np.abs(raw[:, 1:] - independent_swing))),
        ]
    )
    report["bounds"][side] = {}
    for dof in jm.dofs:
        suffix = {"adduction": "abd", "flexion": "flex", "rotation": "rot"}[dof.name]
        w = np.array(dof.weights)
        # c0 is in [-180,180]; swing vector s is perpendicular to axis
        # and ||s|| <=180. Weighted swing = s dot (w1*b+w2*c).
        vector = w[1] * b + w[2] * c
        perpendicular = vector - axis * (axis @ vector)
        half_width = 180 * (abs(w[0]) + np.linalg.norm(perpendicular))
        lower, upper = dof.offset - half_width, dof.offset + half_width
        simple_half_width = 180 * np.abs(w).sum()
        pred = dof.sign * (raw @ w) + dof.offset
        actual = api[f"shoulder_{side}"][f"shoulder_{suffix}_deg"].to_numpy()
        valid = np.isfinite(actual)
        if not np.any(valid):
            raise ValueError("No valid API results")
        formula_errors.append(float(np.max(np.abs(pred[valid] - actual[valid]))))
        if np.any(pred < lower - 1e-7) or np.any(pred > upper + 1e-7):
            raise ValueError("Analytical range bound violated")
        item = {
            "channel": suffix,
            "weights": w.tolist(),
            "sign": dof.sign,
            "offset_deg": dof.offset,
            "raw_lower_bound_deg": float(lower),
            "raw_upper_bound_deg": float(upper),
            "simple_componentwise_lower_bound_deg": float(
                dof.offset - simple_half_width
            ),
            "simple_componentwise_upper_bound_deg": float(
                dof.offset + simple_half_width
            ),
            "random_observed_min_deg": float(pred.min()),
            "random_observed_max_deg": float(pred.max()),
            "valid_public_api_samples": int(valid.sum()),
        }
        report["bounds"][side][suffix] = item
        bound_rows.append(
            {"side": side, **{k: v for k, v in item.items() if k != "weights"}}
        )
report["max_independent_quaternion_component_error_deg"] = max(quaternion_errors)
report["max_formula_vs_public_api_error_deg"] = max(formula_errors)
if max(quaternion_errors) > 1e-7 or max(formula_errors) > 1e-7:
    raise ValueError("Independent algebra verification failed")
# Attribute the previous geometric sweep to the three terms plus intercept.
sweep = np.load(a.sweep / "inputs.npz", allow_pickle=False)
trace = []
neutral = []
for movement in ("abduction", "anteflexion"):
    for heading in (0, 60):
        global_rots = sweep[f"{movement}_heading{heading}_global_rots"]
        for mode, rest_key in (
            ("runner_identity", "runner_rest"),
            ("template_rest_sensitivity", "template_rest"),
        ):
            motions = extract_motion_matrices_per_joint(
                global_rots, sweep[rest_key], sweep["joint_names"].tolist(), fps=60
            )
            tables = extract_clinical_angles(
                global_rots,
                sweep[rest_key],
                sweep["joint_names"].tolist(),
                fps=60,
                mapping=mapping,
                apply_lowpass_filter=False,
            )
            for side in ("R", "L"):
                joint = f"shoulder_{side}"
                jm = mapping.joints[joint]
                m = (
                    motions[joint][[f"r{i}{j}" for i in range(3) for j in range(3)]]
                    .to_numpy()
                    .reshape(-1, 3, 3)
                )
                raw = np.degrees(decompose_swing_twist(m, *np.array(jm.axes)))
                if movement == "abduction" and heading == 0:
                    neutral.append(
                        {
                            "side": side,
                            "rest_mode": mode,
                            "neutral_R_motion_magnitude_deg": float(
                                np.rad2deg(Rotation.from_matrix(m[0]).magnitude())
                            ),
                            "neutral_components_deg": raw[0].tolist(),
                        }
                    )
                for f, theta in enumerate(sweep["angle_deg"]):
                    for dof in jm.dofs:
                        suffix = {
                            "adduction": "abd",
                            "flexion": "flex",
                            "rotation": "rot",
                        }[dof.name]
                        terms = dof.sign * np.array(dof.weights) * raw[f]
                        value = float(terms.sum() + dof.offset)
                        actual = float(tables[joint].iloc[f][f"shoulder_{suffix}_deg"])
                        lock = int(tables[joint].iloc[f]["shoulder_lock_flag"])
                        if not lock and abs(value - actual) > 1e-7:
                            raise ValueError("Sweep attribution mismatch")
                        trace.append(
                            {
                                "movement": movement,
                                "heading_deg": heading,
                                "side": side,
                                "rest_mode": mode,
                                "input_elevation_deg": float(theta),
                                "channel": suffix,
                                "raw_twist_deg": float(raw[f, 0]),
                                "raw_swing1_deg": float(raw[f, 1]),
                                "raw_swing2_deg": float(raw[f, 2]),
                                "twist_contribution_deg": float(terms[0]),
                                "swing1_contribution_deg": float(terms[1]),
                                "swing2_contribution_deg": float(terms[2]),
                                "offset_deg": dof.offset,
                                "unmasked_formula_deg": value,
                                "public_api_deg": actual,
                                "lock_flag": lock,
                            }
                        )
report["previous_sweep_neutral_trace"] = neutral
report["pure_e1_160deg_change"] = {}
for side in ("R", "L"):
    report["pure_e1_160deg_change"][side] = {
        dof.name: float(dof.sign * dof.weights[0] * 160)
        for dof in mapping.joints[f"shoulder_{side}"].dofs
    }
# A constant held matrix cannot lose amplitude because of the 6 Hz filter.
held = np.repeat(globals_r[123:124], 180, axis=0)
held_outputs = [
    extract_clinical_angles(
        held,
        np.tile(np.eye(3), (3, 1, 1)),
        ["Chest", "RightArm", "LeftArm"],
        fps=60,
        mapping=mapping,
        apply_lowpass_filter=filtered,
    )
    for filtered in (False, True)
]
filter_error = 0.0
for joint in held_outputs[0]:
    for column in held_outputs[0][joint]:
        if column.endswith("_deg"):
            filter_error = max(
                filter_error,
                float(
                    np.max(
                        np.abs(
                            held_outputs[0][joint][column].to_numpy()
                            - held_outputs[1][joint][column].to_numpy()
                        )
                    )
                ),
            )
report["constant_180_frame_hold_max_filter_difference_deg"] = filter_error
if filter_error > 1e-7:
    raise ValueError("Constant hold filter control failed")
report["trace_rows"] = len(trace)
report["trace_160deg"] = [
    r for r in trace if r["input_elevation_deg"] == 160 and r["heading_deg"] == 0
]
for filename, rows in (("bounds.csv", bound_rows), ("stage-trace.csv", trace)):
    with (a.out / filename).open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
(a.out / "report.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
fig, axes = plt.subplots(1, 2, figsize=(11, 4.5), constrained_layout=True)
for ax, side in zip(axes, ("R", "L")):
    jm = mapping.joints[f"shoulder_{side}"]
    angles = np.linspace(-179, 179, 359)
    rots = Rotation.from_rotvec(
        np.deg2rad(angles)[:, None]
        * (np.array(jm.axes[0]) / np.linalg.norm(jm.axes[0]))
    ).as_matrix()
    raw = np.degrees(decompose_swing_twist(rots, *np.array(jm.axes)))
    for dof in jm.dofs:
        ax.plot(
            angles,
            dof.sign * (raw @ np.array(dof.weights)) + dof.offset,
            label=dof.name,
        )
    ax.set(
        title=f"Pure rotation about calibration e1, {side}",
        xlabel="Known frame-space rotation (deg)",
        ylabel="Calibrated output (deg)",
    )
    ax.axhline(0, color="grey", lw=0.5)
    ax.grid(alpha=0.2)
    ax.legend()
fig.suptitle("Calibration gain control; not anatomical abduction or axial rotation")
fig.savefig(a.out / "gain-control.png", dpi=140)
plt.close(fig)
print(
    json.dumps(
        {
            "abd_bounds": report["bounds"]["R"]["abd"],
            "quaternion_error_deg": max(quaternion_errors),
            "formula_error_deg": max(formula_errors),
            "neutral": neutral,
        },
        indent=2,
    )
)
