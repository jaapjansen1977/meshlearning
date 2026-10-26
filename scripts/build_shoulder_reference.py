"""Independent SciPy verification and review of landmark shoulder reference.

The runtime reference uses NumPy and landmark frames only. This verification
script uses SciPy quaternion rotations/Euler decomposition as a separate oracle.
It imports no SOMA, GEM-X, Movalytics or learned calibration.
"""

import argparse
import csv
import hashlib
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/tmp/meshlearning-matplotlib")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import scipy
from scipy.spatial.transform import Rotation

from meshlearning.frames import virtual_landmarks
from meshlearning.pitch import INDEX
from meshlearning.shoulder_reference import (
    DEFINITION_VERSION,
    SAGITTAL_MIRROR,
    angles_from_frames,
    angles_from_landmarks,
    frames_from_landmarks,
)

p = argparse.ArgumentParser()
p.add_argument("--out", type=Path, required=True)
p.add_argument("--pitch", type=Path)
a = p.parse_args()
if a.out.exists() and any(a.out.iterdir()):
    p.error("Use a new empty directory")
a.out.mkdir(parents=True, exist_ok=True)


def wrap(x):
    return float((x + 180) % 360 - 180)


def angular_error(x, y):
    return abs(wrap(x - y))


def make_landmarks(thorax, humerus, side, translation):
    # Independent fixture landmarks in X anterior/Y superior/Z right world.
    gh = translation + thorax @ np.array([0, 0.26, 0.22 if side == "R" else -0.22])
    elbow = gh + humerus @ np.array([0, -0.30, 0])
    lateral = humerus @ np.array([0, 0, 0.035 if side == "R" else -0.035])
    return {
        "IJ": translation + thorax @ np.array([0.08, 0.32, 0]),
        "C7": translation + thorax @ np.array([-0.08, 0.32, 0]),
        "PX": translation + thorax @ np.array([0.08, 0.05, 0]),
        "T8": translation + thorax @ np.array([-0.08, 0.05, 0]),
        "GH": gh,
        "EL": elbow + lateral,
        "EM": elbow - lateral,
    }


def write_csv(path, rows):
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


definition = {
    "version": DEFINITION_VERSION,
    "joint": "thorax-humerus (humerothoracic); not isolated glenohumeral",
    "rotation_convention": "active column vectors; anatomical axes are columns of R_world",
    "axes": {
        "X": "anterior",
        "Y_thorax": "superior",
        "Y_humerus": "elbow midpoint to GH (proximal)",
        "Z": "subject right",
    },
    "thorax_landmarks": {
        "Y": "mid(IJ,C7)-mid(PX,T8)",
        "Z_seed": "cross(C7-IJ, mid(PX,T8)-IJ), rightward",
        "X": "Y cross Z; orthonormalized",
    },
    "humerus_landmarks": {
        "origin": "GH",
        "Y": "GH-mid(EL,EM)",
        "X": "normal to GH/EL/EM plane, anterior; left cross-order reversed",
        "Z": "X cross Y, subject right",
    },
    "relative_rotation": "R_thorax_world.T @ R_humerus_world",
    "registration_rule": "Technical frames require explicit anatomy-in-segment matrices B; R_anatomy=R_segment@B. No identity fallback and no fitted offset.",
    "right_intrinsic_yxy": "R=Ry(plane) Rx(-elevation) Ry(axial_yxy)",
    "left_raw_intrinsic_yxy": "R=Ry(-plane) Rx(+elevation) Ry(-axial_yxy); side-normalized reported values match mirrored right movement",
    "plane_zero": "frontal outward arm elevation",
    "plane_plus_90": "anterior arm elevation",
    "axial_yxy_positive": "internal direction, bilateral normalized convention",
    "neutral": "Anatomical frames aligned, arm down; YXY plane and third angle individually nonunique",
    "elevation_range_deg": [0, 180],
    "wrapped_angles_deg": "[-180,180)",
    "singularities": "At 0 and 180 degrees plane and YXY axial are None. At 0 minimal-swing twist remains identifiable; at 180 it is None.",
    "geometric_swing_components": "frontal=elevation*cos(plane), sagittal=elevation*sin(plane); supplementary, not independent ISB Euler flexion/abduction angles",
    "minimal_swing_twist": "Residual long-axis rotation after shortest swing from neutral; equals wrap(plane+axial_yxy) away from poles; supplementary, not the third ISB Euler coordinate",
    "near_singularity": "Within 2 degrees of either pole, warning flag; not automatically forced to zero",
    "calibration": "none",
    "filter": "none",
    "primary_reference_doi": "10.1016/j.jbiomech.2004.05.042",
    "status": "Explicit model convention, independently verified numerically; not validation of real anatomy or unknown SOMA frames",
}
(a.out / "definition.json").write_text(json.dumps(definition, indent=2) + "\n")
rows = []
inputs = []
max_frame_error = max_reconstruction_error = max_scipy_error = max_twist_error = 0.0
worlds = [Rotation.identity(), Rotation.from_rotvec(np.array([0.3, -0.4, 0.5]))]


def check_case(case_id, side, canonical, expected, world_index):
    global max_frame_error, max_reconstruction_error, max_scipy_error, max_twist_error
    world = worlds[world_index].as_matrix()
    local = canonical if side == "R" else SAGITTAL_MIRROR @ canonical @ SAGITTAL_MIRROR
    h = world @ local
    points = make_landmarks(world, h, side, np.array([2.1, -0.7, 3.2]) * world_index)
    t_frame, h_frame = frames_from_landmarks(points, side)
    max_frame_error = max(
        max_frame_error,
        float(np.max(np.abs(t_frame - world))),
        float(np.max(np.abs(h_frame - h))),
    )
    result = angles_from_landmarks(points, side)
    # Alternative source: direct known anatomical frames must agree as well.
    direct = angles_from_frames(world, h, side)
    if abs(direct.elevation_deg - result.elevation_deg) > 1e-7:
        raise ValueError("Landmark/frame disagreement")
    elevation_error = abs(result.elevation_deg - expected[1])
    plane_error = axial_error = twist_error = reconstruction_error = scipy_error = None
    if result.yxy_valid:
        plane_error = angular_error(result.plane_of_elevation_deg, expected[0])
        axial_error = angular_error(result.axial_yxy_deg, expected[2])
        twist_error = angular_error(result.minimal_swing_twist_deg, expected[3])
        reconstructed = Rotation.from_euler(
            "YXY", result.raw_yxy_deg, degrees=True
        ).as_matrix()
        reconstruction_error = float(np.max(np.abs(reconstructed - local)))
        # Independent SciPy intrinsic Euler branch: beta>=0; transform branch
        # for the right convention's negative beta before comparing angles.
        oracle = Rotation.from_matrix(local).as_euler("YXY", degrees=True)
        if side == "R":
            oracle = np.array(
                [wrap(oracle[0] + 180), -oracle[1], wrap(oracle[2] + 180)]
            )
        scipy_error = max(
            angular_error(x, y) for x, y in zip(result.raw_yxy_deg, oracle)
        )
        max_scipy_error = max(max_scipy_error, scipy_error)
        max_reconstruction_error = max(max_reconstruction_error, reconstruction_error)
        max_twist_error = max(max_twist_error, twist_error)
        if (
            max(elevation_error, plane_error, axial_error, twist_error, scipy_error)
            > 1e-7
            or reconstruction_error > 1e-8
        ):
            raise ValueError(f"Reference verification failed: {case_id}")
    elif elevation_error > 1e-7:
        raise ValueError("Singular elevation error")
    rows.append(
        {
            "case_id": case_id,
            "side": side,
            "world_index": world_index,
            "expected_plane_deg": expected[0] if result.yxy_valid else None,
            "expected_elevation_deg": expected[1],
            "expected_axial_yxy_deg": expected[2] if result.yxy_valid else None,
            "expected_minimal_twist_deg": expected[3]
            if result.singularity != "arm_up"
            else None,
            "plane_deg": result.plane_of_elevation_deg,
            "elevation_deg": result.elevation_deg,
            "axial_yxy_deg": result.axial_yxy_deg,
            "minimal_twist_deg": result.minimal_swing_twist_deg,
            "frontal_component_deg": result.frontal_swing_component_deg,
            "sagittal_component_deg": result.sagittal_swing_component_deg,
            "yxy_valid": result.yxy_valid,
            "singularity": result.singularity,
            "near_singularity": result.near_singularity,
            "elevation_error_deg": elevation_error,
            "plane_error_deg": plane_error,
            "axial_error_deg": axial_error,
            "minimal_twist_error_deg": twist_error,
            "scipy_yxy_error_deg": scipy_error,
            "matrix_reconstruction_error": reconstruction_error,
        }
    )
    inputs.append(
        (world, h, [points[k] for k in ("IJ", "C7", "PX", "T8", "GH", "EL", "EM")])
    )


# Physical single-axis movements use quaternion rotations around fixed axes.
for movement, axis, plane in (
    ("abduction", [-1, 0, 0], 0),
    ("anteflexion", [0, 0, 1], 90),
):
    for angle in range(0, 181, 10):
        canonical = Rotation.from_rotvec(np.array(axis) * np.deg2rad(angle)).as_matrix()
        for side in ("R", "L"):
            for w in range(2):
                check_case(
                    f"{movement}_{angle:03d}",
                    side,
                    canonical,
                    (plane, angle, -plane, 0),
                    w,
                )
# Minimal swings composed with independently authored long-axis twists.
for plane in (-90, -45, 0, 30, 45, 90, 135, 179):
    for elevation in (0.01, 1, 5, 30, 90, 125, 160, 179, 179.99):
        swing_axis = np.array(
            [-np.cos(np.deg2rad(plane)), 0, np.sin(np.deg2rad(plane))]
        )
        swing = Rotation.from_rotvec(swing_axis * np.deg2rad(elevation))
        for twist in (-120, -60, 0, 60, 120):
            canonical = (
                swing * Rotation.from_rotvec(np.array([0, 1, 0]) * np.deg2rad(twist))
            ).as_matrix()
            for side in ("R", "L"):
                for w in range(2):
                    check_case(
                        f"combined_p{plane}_e{elevation}_t{twist}",
                        side,
                        canonical,
                        (plane, elevation, wrap(twist - plane), twist),
                        w,
                    )
write_csv(a.out / "expected-vs-calculated.csv", rows)
np.savez_compressed(
    a.out / "reference-inputs.npz",
    case_id=np.array([r["case_id"] for r in rows]),
    side=np.array([r["side"] for r in rows]),
    world_index=np.array([r["world_index"] for r in rows]),
    thorax_world=np.array([x[0] for x in inputs]),
    humerus_world=np.array([x[1] for x in inputs]),
    landmark_names=np.array(["IJ", "C7", "PX", "T8", "GH", "EL", "EM"]),
    landmarks_world=np.array([x[2] for x in inputs]),
)
# Arbitrary orientation coverage; independent SciPy and rotation reconstruction.
rng = np.random.default_rng(20261026)
random_error = 0.0
random_count = 2000
for side in ("R", "L"):
    for local in Rotation.random(random_count, random_state=rng).as_matrix():
        result = angles_from_frames(np.eye(3), local, side)
        if not result.yxy_valid:
            raise ValueError("Unexpected random singular sample")
        reconstructed = Rotation.from_euler(
            "YXY", result.raw_yxy_deg, degrees=True
        ).as_matrix()
        random_error = max(random_error, float(np.max(np.abs(local - reconstructed))))
        oracle = Rotation.from_matrix(local).as_euler("YXY", degrees=True)
        if side == "R":
            oracle = [wrap(oracle[0] + 180), -oracle[1], wrap(oracle[2] + 180)]
        max_scipy_error = max(
            max_scipy_error,
            *(angular_error(x, y) for x, y in zip(result.raw_yxy_deg, oracle)),
        )
if max(random_error, max_frame_error) > 1e-8 or max_scipy_error > 1e-7:
    raise ValueError("Random reconstruction/frame check failed")
report = {
    "definition_version": DEFINITION_VERSION,
    "definition_sha256": hashlib.sha256(
        (a.out / "definition.json").read_bytes()
    ).hexdigest(),
    "reference_source_sha256": hashlib.sha256(
        (
            Path(__file__).resolve().parents[1] / "meshlearning/shoulder_reference.py"
        ).read_bytes()
    ).hexdigest(),
    "numpy_version": np.__version__,
    "scipy_version": scipy.__version__,
    "structured_cases": len(rows),
    "random_cases": 2 * random_count,
    "structured_singular_cases": sum(not r["yxy_valid"] for r in rows),
    "max_structured_elevation_error_deg": max(r["elevation_error_deg"] for r in rows),
    "max_structured_plane_error_deg": max(r["plane_error_deg"] or 0 for r in rows),
    "max_structured_axial_error_deg": max(r["axial_error_deg"] or 0 for r in rows),
    "max_minimal_twist_error_deg": max_twist_error,
    "max_independent_scipy_yxy_error_deg": max_scipy_error,
    "max_landmark_frame_error": max_frame_error,
    "max_structured_reconstruction_error": max_reconstruction_error,
    "max_random_reconstruction_error": random_error,
    "gemx_used": False,
    "movalytics_used": False,
    "learned_calibration_used": False,
    "clinical_validation": False,
    "soma_registration_validated": False,
    "passed": True,
    "160deg_examples": [
        r
        for r in rows
        if r["case_id"] in ("abduction_160", "anteflexion_160")
        and r["world_index"] == 0
    ],
}
if a.pitch:
    motion = np.load(a.pitch, allow_pickle=False)
    pitch_rows = []
    pitch_error = 0.0
    for f, time in enumerate(motion["time_s"]):
        for side in ("R", "L"):
            tr = motion["global_rots"][f, INDEX["thorax"]]
            hr = motion["global_rots"][f, INDEX[f"humerus_{side}"]]
            points = virtual_landmarks(
                motion["joint_positions_world"][f, INDEX["thorax"]],
                tr,
                motion["joint_positions_world"][f, INDEX[f"humerus_{side}"]],
                hr,
                side,
            )
            t, h = frames_from_landmarks(points, side)
            result = angles_from_frames(t, h, side)
            if result.yxy_valid:
                recovered = Rotation.from_euler(
                    "YXY", result.raw_yxy_deg, degrees=True
                ).as_matrix()
                pitch_error = max(
                    pitch_error, float(np.max(np.abs(recovered - t.T @ h)))
                )
            values = result.to_dict()
            values.pop("raw_yxy_deg")
            pitch_rows.append({"source_frame_idx": f, "time_s": float(time), **values})
    if pitch_error > 1e-8:
        raise ValueError("Pitch rotation reconstruction failed")
    write_csv(a.out / "pitch-reference.csv", pitch_rows)
    report["pitch"] = {
        "source_sha256": hashlib.sha256(a.pitch.read_bytes()).hexdigest(),
        "frames": len(motion["time_s"]),
        "rows": len(pitch_rows),
        "max_matrix_reconstruction_error": pitch_error,
        "anatomical_landmarks": "authored virtual model landmarks, not measured human landmarks",
    }
    fig, axes = plt.subplots(
        3, 1, figsize=(10, 8), sharex=True, constrained_layout=True
    )
    for ax, key, label in zip(
        axes,
        ("elevation_deg", "plane_of_elevation_deg", "axial_yxy_deg"),
        ("Elevation", "Plane", "YXY axial"),
    ):
        for side in ("R", "L"):
            subset = [r for r in pitch_rows if r["side"] == side]
            ax.plot([r["time_s"] for r in subset], [r[key] for r in subset], label=side)
        ax.set(ylabel=label + " (deg)")
        ax.grid(alpha=0.2)
        ax.legend()
    axes[-1].set_xlabel("Original time (s)")
    fig.suptitle("Pitch v2: model-landmark reference; no learned calibration")
    fig.savefig(a.out / "pitch-reference.png", dpi=130)
    plt.close(fig)
(a.out / "report.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
fig, axes = plt.subplots(1, 2, figsize=(10, 4.5), constrained_layout=True)
for ax, movement, channel, other in zip(
    axes,
    ("abduction", "anteflexion"),
    ("frontal_component_deg", "sagittal_component_deg"),
    ("sagittal_component_deg", "frontal_component_deg"),
):
    subset = [
        r
        for r in rows
        if r["case_id"].startswith(movement)
        and r["side"] == "R"
        and r["world_index"] == 0
        and r["expected_elevation_deg"] < 180
    ]
    expected = [r["expected_elevation_deg"] for r in subset]
    ax.plot(expected, expected, "k--", label="Known input")
    ax.plot(
        expected, [r[channel] for r in subset], "o", label="Geometric main component"
    )
    ax.plot(expected, [r[other] for r in subset], label="Other swing component")
    ax.plot(
        expected, [r["minimal_twist_deg"] for r in subset], ":", label="Added twist"
    )
    ax.set(title=movement, xlabel="Known elevation (deg)", ylabel="Reference (deg)")
    ax.grid(alpha=0.2)
    ax.legend(fontsize=8)
fig.suptitle("Geometric swing controls; supplementary to ISB YXY coordinates")
fig.savefig(a.out / "isolated-checks.png", dpi=140)
plt.close(fig)
print(json.dumps(report, indent=2))
