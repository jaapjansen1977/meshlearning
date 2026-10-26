"""Exact single-axis shoulder sweeps through frozen Movalytics, without images.

These are geometric model-frame controls, not a claim of validated ISB ground
truth. No axes, signs, offsets or calibration weights are fitted to the result.
"""

import argparse
import csv
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
from scipy.spatial.transform import Rotation

from meshlearning.controls import rodrigues
from meshlearning.pitch import INDEX, NAMES
from meshlearning.soma_bridge import (
    MOVALYTICS_COMMIT,
    map_motion,
    read_rig,
    sha256_file,
    template_registration,
)

parser = argparse.ArgumentParser()
parser.add_argument("--movalytics", type=Path, required=True)
parser.add_argument("--rig", type=Path, required=True)
parser.add_argument("--out", type=Path, required=True)
a = parser.parse_args()
if a.out.exists() and any(a.out.iterdir()):
    parser.error("Use a new empty output directory")
root = a.movalytics.resolve()
commit = subprocess.check_output(
    ["git", "-C", str(root), "rev-parse", "HEAD"], text=True
).strip()
if commit != MOVALYTICS_COMMIT:
    raise ValueError("Wrong Movalytics revision")
sys.path.insert(0, str(root / "src"))
import movalytics
from movalytics import extract_clinical_angles, load_mapping

if Path(movalytics.__file__).resolve().parent != root / "src/movalytics":
    raise ValueError("Unexpected import")
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
    raise ValueError("Pinned source or calibration changed")
mapping = load_mapping(cal)
registration = template_registration(read_rig(a.rig))
a.out.mkdir(parents=True, exist_ok=True)
(a.out / "registration.json").write_text(json.dumps(registration, indent=2) + "\n")
angles = np.arange(0.0, 161.0, 10.0)
names = ["Chest", "RightArm", "LeftArm"]
true_rest = np.array(
    [registration["reference"][name]["soma_rotation"] for name in names]
)
rows = []
max_inverse_error = 0.0
max_reference_error = 0.0
inputs = {}
for movement in ("abduction", "anteflexion"):
    for heading in (0, 60):
        world = rodrigues([0, 0, 1], heading)
        model = np.tile(np.eye(3), (len(angles), len(NAMES), 1, 1))
        for f, angle in enumerate(angles):
            model[f, INDEX["thorax"]] = world
            for side in ("R", "L"):
                axis = (
                    np.array([0.0, -1.0 if side == "R" else 1.0, 0.0])
                    if movement == "abduction"
                    else np.array([1.0, 0.0, 0.0])
                )
                local = rodrigues(axis, angle)
                # Independently check rotation magnitude/axis and the arm direction.
                vector = Rotation.from_matrix(local).as_rotvec()
                max_reference_error = max(
                    max_reference_error,
                    float(np.max(np.abs(vector - axis * np.deg2rad(angle)))),
                )
                direction = local @ np.array([0.0, 0.0, -1.0])
                elevation = np.rad2deg(np.arccos(np.clip(-direction[2], -1, 1)))
                max_reference_error = max(
                    max_reference_error, abs(float(elevation - angle))
                )
                forbidden_component = (
                    direction[1] if movement == "abduction" else direction[0]
                )
                if abs(forbidden_component) > 1e-12:
                    raise ValueError("Reference left the requested movement plane")
                model[f, INDEX[f"humerus_{side}"]] = world @ local
        mapped, error = map_motion(
            {"frame_idx": np.arange(len(angles)), "global_rots": model}, registration
        )
        max_inverse_error = max(max_inverse_error, error)
        inputs[f"{movement}_heading{heading}_global_rots"] = mapped["global_rots"]
        for rest_mode, rest in (
            ("runner_identity", mapped["rest_global_rots"]),
            ("template_rest_sensitivity", true_rest),
        ):
            tables = extract_clinical_angles(
                mapped["global_rots"],
                rest,
                names,
                fps=60,
                mapping=mapping,
                apply_lowpass_filter=False,
            )
            for side in ("R", "L"):
                table = tables[f"shoulder_{side}"]
                for f, angle in enumerate(angles):
                    row = {
                        "movement": movement,
                        "side": side,
                        "common_world_heading_deg": heading,
                        "rest_mode": rest_mode,
                        "sample_index": f,
                        "reference_elevation_deg": float(angle),
                        "reference_abduction_control_deg": float(angle)
                        if movement == "abduction"
                        else 0.0,
                        "reference_anteflexion_control_deg": float(angle)
                        if movement == "anteflexion"
                        else 0.0,
                        "reference_added_axial_twist_deg": 0.0,
                        "movalytics_abd_deg": float(table.iloc[f]["shoulder_abd_deg"]),
                        "movalytics_flex_deg": float(
                            table.iloc[f]["shoulder_flex_deg"]
                        ),
                        "movalytics_rot_deg": float(table.iloc[f]["shoulder_rot_deg"]),
                        "lock_flag": int(table.iloc[f]["shoulder_lock_flag"]),
                    }
                    rows.append(row)
np.savez_compressed(
    a.out / "inputs.npz",
    **inputs,
    angle_deg=angles,
    joint_names=np.array(names),
    runner_rest=np.tile(np.eye(3), (3, 1, 1)),
    template_rest=true_rest,
)
with (a.out / "results.csv").open("w", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
for row in rows:
    values = np.array([row[f"movalytics_{c}_deg"] for c in ("abd", "flex", "rot")])
    if np.isinf(values).any() or (np.isnan(values).any() and not row["lock_flag"]):
        raise ValueError("Unexpected nonfinite output outside a declared lock")
max_heading_error = 0.0
for row in rows:
    if row["common_world_heading_deg"] == 0:
        other = next(
            r
            for r in rows
            if all(
                r[k] == row[k]
                for k in ("movement", "side", "rest_mode", "sample_index")
            )
            and r["common_world_heading_deg"] == 60
        )
        if row["lock_flag"] != other["lock_flag"]:
            raise ValueError("Heading changed lock status")
        for c in ("abd", "flex", "rot"):
            x, y = row[f"movalytics_{c}_deg"], other[f"movalytics_{c}_deg"]
            if np.isnan(x) and np.isnan(y):
                continue
            if not np.isfinite([x, y]).all():
                raise ValueError("Heading changed output validity")
            max_heading_error = max(max_heading_error, abs(x - y))

if max_heading_error > 1e-7 or max_inverse_error > 1e-8 or max_reference_error > 1e-8:
    raise ValueError("Reference or registration invariant failed")
endpoints = [
    r
    for r in rows
    if r["reference_elevation_deg"] in (0, 90, 160)
    and r["common_world_heading_deg"] == 0
]
report = {
    "status": "Executed exact geometric shoulder sweeps; clinical registration remains provisional",
    "movalytics_commit": commit,
    "calibration_sha256": sha256_file(cal),
    "source_sha256": sha256_file(root / "src/movalytics/kinematics/extract.py"),
    "rig_sha256": registration["rig_sha256"],
    "filter": "disabled; independent static poses, not a timed movement",
    "gemx_executed": False,
    "calibration_modified": False,
    "model_axes": "X subject right, Y anterior, Z superior; neutral arm points -Z",
    "reference_definition": "Abduction = pure rotation about -Y right / +Y left; anteflexion = pure +X rotation on both sides; no added long-axis twist. This is not the plane/elevation/axial Euler chart used for the pitch.",
    "registration_limit": registration["status"],
    "rest_modes": {
        "runner_identity": "Actual public GEM-X runner rest convention; primary result",
        "template_rest_sensitivity": "True template rest supplied to the same frozen calibration; sensitivity only, not a corrected or validated pipeline",
    },
    "rows": len(rows),
    "max_model_roundtrip_error": max_inverse_error,
    "max_reference_check_error": max_reference_error,
    "max_common_world_rotation_output_difference_deg": max_heading_error,
    "locked_rows": sum(r["lock_flag"] for r in rows),
    "endpoints": endpoints,
}
(a.out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
for mode in ("runner_identity", "template_rest_sensitivity"):
    fig, axes = plt.subplots(
        2, 2, figsize=(11, 8), sharex=True, constrained_layout=True
    )
    for col, movement in enumerate(("abduction", "anteflexion")):
        for row_index, side in enumerate(("R", "L")):
            ax = axes[row_index, col]
            subset = [
                r
                for r in rows
                if r["movement"] == movement
                and r["side"] == side
                and r["rest_mode"] == mode
                and r["common_world_heading_deg"] == 0
            ]
            for c, label in (
                ("abd", "Movalytics abd"),
                ("flex", "Movalytics flex"),
                ("rot", "Movalytics rot"),
            ):
                ax.plot(
                    angles,
                    [r[f"movalytics_{c}_deg"] for r in subset],
                    marker=".",
                    label=label,
                )
            ax.plot(angles, angles, "k--", label="reference elevation (geometric)")
            ax.axhline(0, color="grey", lw=0.6)
            ax.set(
                title=f"{movement}, {side}",
                xlabel="Known elevation (deg)",
                ylabel="Output (deg)",
            )
            ax.grid(alpha=0.2)
            ax.legend(fontsize=8)
    fig.suptitle(f"Frozen soma_gemx_v14; {mode}; provisional frame registration")
    fig.savefig(a.out / f"{mode}.png", dpi=140)
    plt.close(fig)
fig, axes = plt.subplots(1, 2, figsize=(8, 5), constrained_layout=True)
for ax, movement in zip(axes, ("abduction", "anteflexion")):
    for angle in (0, 90, 160):
        local = rodrigues([0, -1, 0] if movement == "abduction" else [1, 0, 0], angle)
        d = local @ np.array([0, 0, -1.0])
        horizontal = d[0] if movement == "abduction" else d[1]
        ax.plot([0, horizontal], [0, d[2]], "o-", label=f"{angle} deg")
    ax.plot([0, 0], [-1.1, 0.35], color="grey", alpha=0.3)
    ax.set(
        aspect="equal",
        xlim=(-0.3, 1.15),
        ylim=(-1.2, 1.15),
        title=movement,
        xlabel="Right / anterior",
        ylabel="Superior",
    )
    ax.legend()
fig.suptitle("Known right-arm directions relative to a fixed thorax")
fig.savefig(a.out / "reference-poses.png", dpi=140)
plt.close(fig)
print(
    json.dumps(
        {
            "rows": len(rows),
            "max_heading_error": max_heading_error,
            "160deg_primary": [
                r
                for r in endpoints
                if r["reference_elevation_deg"] == 160
                and r["rest_mode"] == "runner_identity"
            ],
        },
        indent=2,
    )
)
