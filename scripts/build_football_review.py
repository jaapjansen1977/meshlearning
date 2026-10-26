"""Build football review videos, phase panels, plots and original source bundle."""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/tmp/meshlearning-matplotlib")
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

p = argparse.ArgumentParser()
p.add_argument("--renders", type=Path, required=True)
p.add_argument("--motion-dir", type=Path, required=True)
p.add_argument("--out", type=Path, required=True)
a = p.parse_args()
renders = json.loads((a.renders / "report.json").read_text())
if (
    hashlib.sha256((a.motion_dir / "motion.npz").read_bytes()).hexdigest()
    != renders["motion_sha256"]
):
    raise ValueError("Motion and render sources differ")
subprocess.run(
    [
        sys.executable,
        str(Path(__file__).with_name("build_body_shape_review.py")),
        "--renders",
        str(a.renders),
        "--out",
        str(a.out),
        "--phase-times",
        "0,.8,1.2,1.45,2.4",
    ],
    check=True,
)
shutil.copyfile(a.motion_dir / "report.json", a.out / "motion-checks.json")
shutil.copyfile(a.motion_dir / "angles.csv", a.out / "angles.csv")
shutil.copyfile(a.motion_dir / "design.json", a.out / "design.json")
with zipfile.ZipFile(
    a.out / "football-source-data.zip", "w", compression=zipfile.ZIP_DEFLATED
) as bundle:
    for name in ("motion.npz", "design.json", "angles.csv", "report.json"):
        bundle.write(a.motion_dir / name, name)
angles = np.genfromtxt(
    a.motion_dir / "angles.csv", delimiter=",", names=True, encoding="utf-8", dtype=None
)
fig, axes = plt.subplots(2, 1, figsize=(10, 7), sharex=True, constrained_layout=True)
for channel, label in (
    ("calculated_model_hip_flexion_deg", "Right hip: model flexion"),
    ("calculated_model_knee_flexion_deg", "Right knee: model flexion"),
    ("calculated_model_ankle_dorsiflexion_deg", "Right ankle: model dorsiflexion (+)"),
):
    axes[0].plot(angles["time_s"], angles[channel], label=label)
for channel, label in (
    ("pelvis_yaw_world_control_deg", "Pelvis yaw"),
    ("thorax_yaw_world_control_deg", "Thorax yaw"),
    ("thorax_extension_control_deg", "Trunk extension (+) / flexion (-)"),
):
    axes[1].plot(angles["time_s"], angles[channel], label=label)
for ax in axes:
    ax.axvline(1.2, color="black", ls="--", label="Nominal ball contact")
    ax.set_ylabel("Model control / calculated angle (deg)")
    ax.grid(alpha=0.2)
    ax.legend(fontsize=9)
axes[-1].set_xlabel("Original time (s)")
fig.suptitle(
    "Original football kick: exact model controls, not validated ISB hip/knee labels"
)
fig.savefig(a.out / "motion-controls.png", dpi=140)
plt.close(fig)
print(
    json.dumps(
        {
            "motion": renders["motion_kind"],
            "frames_per_view": len(renders["source_frames"]),
            "fps": renders["sample_fps"],
            "profiles": list(renders["profiles"]),
        }
    )
)
