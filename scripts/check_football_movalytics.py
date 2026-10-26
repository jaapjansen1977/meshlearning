"""Frozen Movalytics lower-limb extraction on exact football rotations."""

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/tmp/meshlearning-matplotlib")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from meshlearning.soma_bridge import MOVALYTICS_COMMIT, read_rig, sha256_file
from meshlearning.soma_legs import leg_registration, map_legs

p = argparse.ArgumentParser()
p.add_argument("--movalytics", type=Path, required=True)
p.add_argument("--rig", type=Path, required=True)
p.add_argument("--motion-dir", type=Path, required=True)
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
    raise ValueError("Wrong Movalytics revision")
sys.path.insert(0, str(root / "src"))
import movalytics
from movalytics import extract_clinical_angles, load_mapping

if Path(movalytics.__file__).resolve().parent != root / "src/movalytics":
    raise ValueError("Wrong source import")
expected = json.loads(
    (
        Path(__file__).resolve().parents[1] / "docs/pitch-v2/frame-contract.json"
    ).read_text()
)["movalytics"]
cal = root / "calibrations/soma_gemx_v14.json"
if (
    sha256_file(cal) != expected["calibration_sha256"]
    or sha256_file(root / "src/movalytics/kinematics/extract.py")
    != expected["source_sha256"]
):
    raise ValueError("Changed calibration or extractor")
mapping = load_mapping(cal)
registration = leg_registration(read_rig(a.rig))
motion = np.load(a.motion_dir / "motion.npz", allow_pickle=False)
mapped, error = map_legs(motion["global_rots"], registration)
reference = pd.read_csv(a.motion_dir / "angles.csv")
a.out.mkdir(parents=True, exist_ok=True)
(a.out / "registration.json").write_text(json.dumps(registration, indent=2) + "\n")
np.savez_compressed(
    a.out / "registered-leg-rotations.npz",
    **mapped,
    time_s=motion["time_s"],
    frame_idx=motion["frame_idx"],
    source_fps=motion["source_fps"],
)
metrics, contacts = [], []
world = np.array([[0.0, -1, 0], [1, 0, 0], [0, 0, 1]])
world_error = 0.0
for mode, rest in (
    ("runner_identity", mapped["rest_global_rots"]),
    ("template_rest_sensitivity", mapped["template_rest_global_rots"]),
):
    fig, axes = plt.subplots(
        3, 2, figsize=(12, 10), sharex=True, constrained_layout=True
    )
    for filtered in (False, True):
        outputs = extract_clinical_angles(
            mapped["global_rots"],
            rest,
            mapped["joint_names"].tolist(),
            fps=float(motion["source_fps"]),
            mapping=mapping,
            apply_lowpass_filter=filtered,
        )
        heading_outputs = extract_clinical_angles(
            world @ mapped["global_rots"],
            rest,
            mapped["joint_names"].tolist(),
            fps=float(motion["source_fps"]),
            mapping=mapping,
            apply_lowpass_filter=filtered,
        )
        folder = a.out / mode / ("filtered_6hz" if filtered else "raw")
        folder.mkdir(parents=True, exist_ok=True)
        for col, side in enumerate(("R", "L")):
            for row, joint in enumerate(("hip", "knee", "ankle")):
                table = outputs[f"{joint}_{side}"]
                other = heading_outputs[f"{joint}_{side}"]
                table.to_csv(folder / f"{joint}_{side}.csv", index=False)
                if not np.array_equal(table.isna(), other.isna()):
                    raise ValueError("World rotation changed validity")
                degree_columns = [c for c in table if c.endswith(("_deg", "_deg_info"))]
                for c in degree_columns:
                    diff = (table[c] - other[c]).abs().max()
                    if pd.notna(diff):
                        world_error = max(world_error, float(diff))
                actual = table[f"{joint}_flex_deg"].to_numpy()
                prefix = (
                    "hip_flexion"
                    if joint == "hip"
                    else "knee_flexion"
                    if joint == "knee"
                    else "ankle_dorsiflexion"
                )
                # Right is independently verified in football generator. Left
                # has no authored clinical reference here: do not fabricate one.
                expected_values = (
                    reference[f"expected_model_{prefix}_deg"].to_numpy()
                    if side == "R"
                    else None
                )
                metric = {
                    "rest_mode": mode,
                    "filtered": filtered,
                    "side": side,
                    "joint": joint,
                    "movalytics_min_deg": float(np.nanmin(actual)),
                    "movalytics_max_deg": float(np.nanmax(actual)),
                    "movalytics_rom_deg": float(np.nanmax(actual) - np.nanmin(actual)),
                    "locked_frames": int(table[f"{joint}_lock_flag"].sum()),
                    "finite_frames": int(np.isfinite(actual).sum()),
                }
                if expected_values is not None:
                    metric.update(
                        model_reference_min_deg=float(expected_values.min()),
                        model_reference_max_deg=float(expected_values.max()),
                        model_reference_rom_deg=float(np.ptp(expected_values)),
                        mean_absolute_difference_from_model_control_deg=float(
                            np.nanmean(np.abs(actual - expected_values))
                        ),
                    )
                    if not filtered:
                        combined = pd.DataFrame(
                            {
                                "source_frame_idx": motion["frame_idx"],
                                "time_s": motion["time_s"],
                                "model_reference_deg": expected_values,
                                "movalytics_flex_deg": actual,
                            }
                        )
                        for c in table:
                            if c not in ("time_s", f"{joint}_flex_deg"):
                                combined[c] = table[c]
                        combined.to_csv(
                            a.out / f"{mode}-{joint}-R-comparison.csv", index=False
                        )
                        axes[row, col].plot(
                            motion["time_s"],
                            expected_values,
                            "k--",
                            label="Known model control",
                        )
                axes[row, col].plot(
                    motion["time_s"],
                    actual,
                    label="Movalytics 6 Hz" if filtered else "Movalytics raw",
                )
                axes[row, col].set(title=f"{joint}, {side}", ylabel="Degrees")
                metrics.append(metric)
                if side == "R":
                    f = int(
                        np.argmin(
                            np.abs(
                                motion["time_s"]
                                - float(motion["nominal_contact_time_s"])
                            )
                        )
                    )
                    contacts.append(
                        {
                            "rest_mode": mode,
                            "filtered": filtered,
                            "joint": joint,
                            "time_s": float(motion["time_s"][f]),
                            "model_control_deg": float(expected_values[f]),
                            "movalytics_deg": float(actual[f]),
                        }
                    )
    for ax in axes.flat:
        ax.axvline(float(motion["nominal_contact_time_s"]), ls=":", color="grey")
        ax.grid(alpha=0.2)
        ax.legend(fontsize=8)
    for ax in axes[-1]:
        ax.set_xlabel("Original time (s)")
    fig.suptitle(
        f"Exact football rotations -> frozen Movalytics; {mode}; provisional registration"
    )
    fig.savefig(a.out / f"{mode}.png", dpi=130)
    plt.close(fig)
if world_error > 1e-6:
    raise ValueError("Common-world-rotation invariance failed")
report = {
    "movalytics_commit": MOVALYTICS_COMMIT,
    "calibration_sha256": sha256_file(cal),
    "rig_sha256": registration["rig_sha256"],
    "motion_sha256": hashlib.sha256(
        (a.motion_dir / "motion.npz").read_bytes()
    ).hexdigest(),
    "frames": len(motion["time_s"]),
    "source_fps": int(motion["source_fps"]),
    "gemx_executed": False,
    "calibration_modified": False,
    "max_inverse_registration_matrix_error": error,
    "max_common_world_rotation_difference_deg": world_error,
    "comparison_status": "Numerical differences from procedural sagittal controls; not validated clinical MAE or a working-app benchmark",
    "registration_status": registration["status"],
    "metrics": metrics,
    "contact_values": contacts,
}
(a.out / "report.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
pd.DataFrame(metrics).to_csv(a.out / "metrics.csv", index=False)
print(
    json.dumps(
        {
            "contact_values": contacts,
            "right_metrics_raw": [
                m for m in metrics if m["side"] == "R" and not m["filtered"]
            ],
        },
        indent=2,
    )
)
