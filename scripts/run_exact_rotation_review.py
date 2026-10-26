"""Prepare or run the pinned SOMA -> Movalytics exact-rotation review.

`--probes-only` is a frame-space software diagnostic, never a pitch assessment.
Real pitch execution requires the checksum-verified pinned SOMA USD file.
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
import numpy as np

from meshlearning.controls import rodrigues
from meshlearning.motion import rotation
from meshlearning.pitch import INDEX, NAMES, functional_angles, functional_rotation
from meshlearning.soma_bridge import (
    MOVALYTICS_COMMIT,
    map_motion,
    read_rig,
    sha256_file,
    template_registration,
)

p = argparse.ArgumentParser()
p.add_argument("--movalytics", type=Path, required=True)
p.add_argument("--rig", type=Path)
p.add_argument("--motion", type=Path)
p.add_argument("--out", type=Path, required=True)
p.add_argument("--probes-only", action="store_true")
p.add_argument("--audit-input-routes", action="store_true")
p.add_argument(
    "--video-samples",
    action="store_true",
    help="Use the original-time single-view video sample frames",
)
a = p.parse_args()
if a.out.exists() and any(a.out.iterdir()):
    p.error("Use a new empty output directory")
if not (a.probes_only or a.audit_input_routes) and (a.rig is None or a.motion is None):
    p.error("--rig and --motion required for pitch execution")
root = a.movalytics.resolve()
commit = subprocess.check_output(
    ["git", "-C", str(root), "rev-parse", "HEAD"], text=True
).strip()
if commit != MOVALYTICS_COMMIT:
    raise ValueError("Select the Movalytics revision pinned by this project")
sys.path.insert(0, str(root / "src"))
import movalytics
from movalytics import extract_clinical_angles, load_mapping

if Path(movalytics.__file__).resolve().parent != root / "src/movalytics":
    raise ValueError("Unexpected Movalytics import path")
calibration = root / "calibrations/soma_gemx_v14.json"
expected = json.loads(
    (
        Path(__file__).resolve().parents[1] / "docs/pitch-v2/frame-contract.json"
    ).read_text()
)["movalytics"]
if (
    sha256_file(calibration) != expected["calibration_sha256"]
    or sha256_file(root / "src/movalytics/kinematics/extract.py")
    != expected["source_sha256"]
):
    raise ValueError("Pinned calibration or extraction source changed")
mapping = load_mapping(calibration)
a.out.mkdir(parents=True, exist_ok=True)
if a.audit_input_routes:
    import tempfile

    from movalytics.kinematics import extract_motion_matrices_per_joint
    from movalytics.sources.gemx import read_npz

    local = rotation([35, 20, -40])
    g0 = np.eye(3)
    g1 = rotation([0, 0, 60])
    rotations = np.array([[g0, g0 @ local], [g1, g1 @ local]])
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "example.npz"
        np.savez(
            path,
            frame_idx=np.arange(2),
            joint_names=np.array(["Chest", "RightArm"]),
            global_rots=rotations,
            rest_global_rots=np.tile(np.eye(3), (2, 1, 1)),
        )
        rows = read_npz(path, 1, "frame_contract_probe", "Cam1")
        bundled = np.array(
            [[row[f"r{i}{j}"] for i in range(3) for j in range(3)] for row in rows]
        ).reshape(-1, 3, 3)
        runtime_table = extract_motion_matrices_per_joint(
            rotations, np.tile(np.eye(3), (2, 1, 1)), ["Chest", "RightArm"], fps=60
        )["shoulder_R"]
        runtime = (
            runtime_table[[f"r{i}{j}" for i in range(3) for j in range(3)]]
            .to_numpy()
            .reshape(-1, 3, 3)
        )

    def distance(x, y):
        return float(np.rad2deg(np.arccos(np.clip((np.trace(x.T @ y) - 1) / 2, -1, 1))))

    report = {
        "status": "Reproduced input-route difference; actual historical calibration data not established",
        "movalytics_commit": commit,
        "common_world_rotation_deg": 60,
        "expected_relative_shoulder_change_deg": 0,
        "bundle_adapter_matrix_change_deg": distance(bundled[0], bundled[1]),
        "runtime_relative_matrix_change_deg": distance(runtime[0], runtime[1]),
        "adapter_keeps_absolute_child_rotation": bool(
            np.allclose(bundled, rotations[:, 1])
        ),
        "runtime_keeps_parent_relative_rotation": bool(
            np.allclose(runtime, np.broadcast_to(local, runtime.shape))
        ),
        "pending_confirmation": "Which representation actually fed soma_gemx_v14 and the working application?",
    }
    if (
        not report["adapter_keeps_absolute_child_rotation"]
        or not report["runtime_keeps_parent_relative_rotation"]
    ):
        raise RuntimeError("Source routes changed; inspect before interpreting")
    (a.out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
elif a.probes_only:
    probes = []
    for side, joint in [("R", "shoulder_R"), ("L", "shoulder_L")]:
        jm = mapping.joints[joint]
        axis = np.array(jm.axes[0])
        axis /= np.linalg.norm(axis)
        angles = np.array([-120.0, -60.0, -30.0, 0.0, 30.0, 60.0, 120.0])
        rots = np.tile(np.eye(3), (len(angles), 3, 1, 1))
        arm = 1 if side == "R" else 2
        for f, angle in enumerate(angles):
            rots[f, arm] = rodrigues(axis, angle)
        tables = extract_clinical_angles(
            rots,
            np.tile(np.eye(3), (3, 1, 1)),
            ["Chest", "RightArm", "LeftArm"],
            fps=240,
            mapping=mapping,
            apply_lowpass_filter=False,
        )
        for dof in jm.dofs:
            suffix = {"flexion": "flex", "adduction": "abd", "rotation": "rot"}[
                dof.name
            ]
            column = f"shoulder_{suffix}_deg"
            values = tables[joint][column].to_numpy()
            for theta, value in zip(angles, values):
                expected_value = dof.sign * dof.weights[0] * theta + dof.offset
                probes.append(
                    {
                        "side": side,
                        "input_kind": "pure twist about calibration e1, NOT anatomical pose",
                        "input_parameter_deg": float(theta),
                        "channel": column,
                        "expected_deg": float(expected_value),
                        "movalytics_deg": float(value),
                        "difference_deg": float(value - expected_value),
                    }
                )
    with (a.out / "calibration-probes.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(probes[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(probes)
    if not np.isfinite([row["movalytics_deg"] for row in probes]).all():
        raise RuntimeError("Nonfinite calibration probe output")
    error = max(abs(row["difference_deg"]) for row in probes)
    report = {
        "status": "CPU calibration probes executed, no pitch or anatomical accuracy claim",
        "movalytics_commit": commit,
        "calibration_sha256": sha256_file(calibration),
        "rows": len(probes),
        "max_probe_difference_deg": error,
        "filter": "disabled to test exact matrix/calibration algebra",
        "passed": error < 1e-7,
        "pitch_executed": False,
    }
    (a.out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    if not report["passed"]:
        raise RuntimeError("Actual Movalytics probe failed")
else:
    rig = read_rig(a.rig)
    registration = template_registration(rig)
    (a.out / "registration.json").write_text(json.dumps(registration, indent=2) + "\n")
    with np.load(a.motion, allow_pickle=False) as motion:
        selection = (
            motion["render_frames"]
            if a.video_samples
            else np.arange(len(motion["frame_idx"]))
        )
        source_indices = motion["frame_idx"][selection]
        selected = {
            "frame_idx": np.arange(len(selection)),
            "global_rots": motion["global_rots"][selection],
        }
        mapped, error = map_motion(selected, registration)
        mapped["source_frame_idx"] = source_indices
        times = motion["time_s"][selection].copy()
        mapped["time_s"] = times
        fps = 1 / float(times[1] - times[0])
        reference = []
        for f, time in enumerate(times):
            tr = motion["global_rots"][selection[f], INDEX["thorax"]]
            for side in ("R", "L"):
                elevation, plane, axial, valid = functional_angles(
                    tr,
                    motion["global_rots"][selection[f], INDEX[f"humerus_{side}"]],
                    side,
                )
                reference.append(
                    {
                        "frame_idx": f,
                        "source_frame_idx": int(source_indices[f]),
                        "time_s": float(time),
                        "side": side,
                        "reference_elevation_deg": elevation,
                        "reference_plane_deg": plane,
                        "reference_axial_deg": axial,
                        "reference_valid": valid,
                        "comparison_status": "Different representations: no direct estimator MAE",
                    }
                )
    np.savez_compressed(a.out / "registered_rotations.npz", **mapped)
    for filtered, label in [(False, "raw"), (True, "filtered_6hz")]:
        results = extract_clinical_angles(
            mapped["global_rots"],
            mapped["rest_global_rots"],
            mapped["joint_names"].tolist(),
            fps=fps,
            mapping=mapping,
            apply_lowpass_filter=filtered,
        )
        if not filtered:
            raw_results = results
        directory = a.out / label
        directory.mkdir()
        for name, table in results.items():
            table.to_csv(directory / f"{name}.csv", index=False, lineterminator="\n")
    for row in reference:
        values = raw_results[f"shoulder_{row['side']}"].iloc[row["frame_idx"]]
        for column in (
            "shoulder_flex_deg",
            "shoulder_abd_deg",
            "shoulder_rot_deg",
            "shoulder_lock_flag",
        ):
            row["movalytics_raw_" + column] = float(values[column])
    with (a.out / "reference-vs-movalytics.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(reference[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(reference)
    # Recognizable independent reference poses; no filtering across discontinuous cases.
    poses = [
        ("near_down", 0, 5, 0),
        ("lateral90", 0, 90, 0),
        ("anterior90", 90, 90, 0),
        ("external60", 0, 90, -60),
        ("internal60", 0, 90, 60),
        ("combined", 30, 110, -100),
    ]
    checks = []
    rotations = []
    for name, plane, elevation, axial in poses:
        for variant in ("identity_world", "rotated_world"):
            tr = np.eye(3) if variant == "identity_world" else rotation([23, -17, 39])
            frame = np.tile(np.eye(3), (len(NAMES), 1, 1))
            frame[INDEX["thorax"]] = tr
            for side in ("R", "L"):
                frame[INDEX[f"humerus_{side}"]] = tr @ functional_rotation(
                    plane, elevation, axial, side
                )
            rotations.append(frame)
            checks.append((name, variant, plane, elevation, axial))
    probe_map, probe_error = map_motion(
        {"frame_idx": np.arange(len(rotations)), "global_rots": np.array(rotations)},
        registration,
    )
    tables = extract_clinical_angles(
        probe_map["global_rots"],
        probe_map["rest_global_rots"],
        probe_map["joint_names"].tolist(),
        fps=240,
        mapping=mapping,
        apply_lowpass_filter=False,
    )
    invariance = 0.0
    checked = 0
    pose_rows = []
    for side in ("R", "L"):
        table = tables[f"shoulder_{side}"]
        for f, (name, variant, plane, elevation, axial) in enumerate(checks):
            pose_rows.append(
                {
                    "case": name,
                    "world_variant": variant,
                    "side": side,
                    "reference_plane_deg": plane,
                    "reference_elevation_deg": elevation,
                    "reference_axial_deg": axial,
                    **{
                        key: float(value)
                        for key, value in table.iloc[f].to_dict().items()
                        if key != "time_s"
                    },
                }
            )
        for f in range(0, len(checks), 2):
            x = table.iloc[f].to_numpy(dtype=float)[1:]
            y = table.iloc[f + 1].to_numpy(dtype=float)[1:]
            if not np.array_equal(np.isfinite(x), np.isfinite(y)):
                raise RuntimeError("World rotation changed valid/locked channels")
            finite = np.isfinite(x) & np.isfinite(y)
            if finite.any():
                invariance = max(
                    invariance, float(np.max(np.abs(x[finite] - y[finite])))
                )
                checked += int(finite.sum())
    if checked == 0 or invariance > 1e-7:
        raise RuntimeError("Registered controlled-pose world invariance failed")
    with (a.out / "registration-pose-checks.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(pose_rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(pose_rows)
    (a.out / "registration-checks.json").write_text(
        json.dumps(
            {
                "reference_cases": len(poses),
                "world_variants": 2,
                "sides": 2,
                "finite_values_checked": checked,
                "world_invariance_max_difference_deg": invariance,
                "pose_inverse_registration_max_error": probe_error,
                "scope": "Matrix and software registration checks, not anatomical angle accuracy",
            },
            indent=2,
        )
        + "\n"
    )
    report = {
        "status": "Application-reference angles from known rotations through unchanged Movalytics; no image estimation",
        "input_sampling": "single-view original-time video frames"
        if a.video_samples
        else "dense design source frames",
        "application_reference_policy": "Compare future predicted rotations through the same unchanged calibration and sampling/filter policy; this measures application-convention estimation error, not clinical validity",
        "movalytics_commit": commit,
        "calibration_sha256": sha256_file(calibration),
        "rig_sha256": rig["sha256"],
        "frames": len(times),
        "fps": fps,
        "inverse_registration_max_matrix_error": error,
        "comparison_policy": "YXY plane/elevation/axial and Movalytics flex/abd/rotation are distinct representations; do not report their direct differences as estimator MAE",
        "registration_status": registration["status"],
        "video_inference_executed": False,
        "training_reference_ready": False,
        "pending_confirmation": "Registration twist reference and calibration/runtime input semantics must be confirmed before treating these values as training reference",
    }
    (a.out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps(report, indent=2))
