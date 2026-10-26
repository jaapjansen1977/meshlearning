"""Original designed right-foot kick, sharing our procedural adult rig.

Right leg is authored in joint space (hip then knee); the left support ankle
is fixed through two-link IK. No external motion, human model or learned
calibration is used. Controls are explicit model angles, not validated ISB hip
or knee angles. Ball motion is illustrative, not a dynamics simulation.
"""

import csv
import json
from pathlib import Path

import numpy as np

from .motion import rotation
from .pitch import (
    INDEX,
    NAMES,
    PARENTS,
    RADII,
    interpolate,
    neutral_parameters,
    pose,
)


def kick_pose(parameters):
    params = neutral_parameters()
    params.update(parameters)
    # The existing upper-body and support-leg construction is retained.
    p, r, e, errors = pose(params)
    thigh, shank, foot = (INDEX[f"{name}_R"] for name in ("thigh", "shank", "foot"))
    pelvis = r[INDEX["pelvis"]]
    r[thigh] = pelvis @ rotation([parameters["kick_hip_flexion"], 0, 0])
    e[thigh] = p[thigh] + r[thigh] @ np.array([0, 0, -0.45])
    p[shank] = e[thigh]
    r[shank] = r[thigh] @ rotation([-parameters["kick_knee_flexion"], 0, 0])
    e[shank] = p[shank] + r[shank] @ np.array([0, 0, -0.45])
    p[foot] = e[shank]
    r[foot] = r[shank] @ rotation([parameters["kick_ankle_dorsiflexion"], 0, 0])
    e[foot] = p[foot] + r[foot] @ np.array([0, 0.18, -0.035])
    # The discarded right IK request is not an active constraint in this motion.
    return p, r, e, {"support_L_ik_error_m": errors["L"]}


def generate(config_path, out):
    out = Path(out)
    if out.exists() and any(out.iterdir()):
        raise ValueError("Use a new empty directory")
    config = json.loads(Path(config_path).read_text())
    fps = int(config["source_fps"])
    knots = config["key_times_s"]
    if fps <= 0 or knots[0] != 0 or len(knots) != len(config["phase_labels"]):
        raise ValueError("Invalid source timing or phases")
    times = np.arange(round(knots[-1] * fps) + 1) / fps
    tracks = {k: interpolate(knots, v, times) for k, v in config["tracks"].items()}
    positions, rotations, endpoints, rows, errors = [], [], [], [], []
    for f, time in enumerate(times):
        params = {k: float(v[f]) for k, v in tracks.items()}
        p, r, e, error = kick_pose(params)
        positions.append(p)
        rotations.append(r)
        endpoints.append(e)
        errors.append(error["support_L_ik_error_m"])
        hip_local = r[INDEX["pelvis"]].T @ r[INDEX["thigh_R"]]
        knee_local = r[INDEX["thigh_R"]].T @ r[INDEX["shank_R"]]
        hip = float(np.rad2deg(np.arctan2(hip_local[2, 1], hip_local[1, 1])))
        knee = -float(np.rad2deg(np.arctan2(knee_local[2, 1], knee_local[1, 1])))
        ankle_local = r[INDEX["shank_R"]].T @ r[INDEX["foot_R"]]
        ankle = float(np.rad2deg(np.arctan2(ankle_local[2, 1], ankle_local[1, 1])))
        # Independent joint-position geometry: angle between both distal links.
        v1 = e[INDEX["thigh_R"]] - p[INDEX["thigh_R"]]
        v2 = e[INDEX["shank_R"]] - p[INDEX["shank_R"]]
        geometric_knee = float(
            np.rad2deg(np.arctan2(np.linalg.norm(np.cross(v1, v2)), v1 @ v2))
        )
        phase = next(
            label
            for start, label in reversed(list(zip(knots, config["phase_labels"])))
            if time >= start - 1e-8
        )
        rows.append(
            {
                "source_frame_idx": f,
                "time_s": float(time),
                "phase": phase,
                "expected_model_hip_flexion_deg": params["kick_hip_flexion"],
                "calculated_model_hip_flexion_deg": hip,
                "expected_model_knee_flexion_deg": params["kick_knee_flexion"],
                "calculated_model_knee_flexion_deg": knee,
                "knee_from_joint_positions_deg": geometric_knee,
                "expected_model_ankle_dorsiflexion_deg": params[
                    "kick_ankle_dorsiflexion"
                ],
                "calculated_model_ankle_dorsiflexion_deg": ankle,
                "pelvis_yaw_world_control_deg": params["pelvis_yaw"],
                "thorax_yaw_world_control_deg": params["thorax_yaw"],
                "thorax_extension_control_deg": params["trunk_lean"],
                "support_L_ik_error_m": error["support_L_ik_error_m"],
            }
        )
    p_all, r_all, e_all = np.array(positions), np.array(rotations), np.array(endpoints)
    support = p_all[:, INDEX["foot_L"]]
    support_error = float(np.max(np.linalg.norm(support - support[0], axis=1)))
    angle_error = max(
        max(
            abs(
                row["expected_model_hip_flexion_deg"]
                - row["calculated_model_hip_flexion_deg"]
            ),
            abs(
                row["expected_model_knee_flexion_deg"]
                - row["calculated_model_knee_flexion_deg"]
            ),
            abs(
                row["expected_model_knee_flexion_deg"]
                - row["knee_from_joint_positions_deg"]
            ),
            abs(
                row["expected_model_ankle_dorsiflexion_deg"]
                - row["calculated_model_ankle_dorsiflexion_deg"]
            ),
        )
        for row in rows
    )
    max_link_error = 0.0
    for name in ("thigh_R", "shank_R", "thigh_L", "shank_L"):
        j = INDEX[name]
        max_link_error = max(
            max_link_error,
            float(
                np.max(np.abs(np.linalg.norm(e_all[:, j] - p_all[:, j], axis=1) - 0.45))
            ),
        )
    # A marker touches the designed toe near the chosen contact time, then rolls
    # forward at authored speed. This is not an impact/force/ballistics model.
    contact = float(config["nominal_contact_time_s"])
    contact_f = round(contact * fps)
    contact_toe = e_all[contact_f, INDEX["foot_R"]]
    radius = 0.11
    vertical = radius - contact_toe[2]
    if abs(vertical) >= radius:
        raise ValueError("Designed toe misses the grounded ball height")
    ball_start = contact_toe + [0, np.sqrt(radius**2 - vertical**2), vertical]
    ball = np.tile(ball_start, (len(times), 1))
    ball[:, 1] += config["illustrative_ball_speed_m_s"] * np.maximum(times - contact, 0)
    minimum_toe = float(e_all[:, INDEX["foot_R"], 2].min())
    if (
        max(errors) > 1e-8
        or support_error > 1e-8
        or angle_error > 1e-8
        or max_link_error > 1e-8
        or minimum_toe < 0
    ):
        raise ValueError("Kick geometry/angle/support checks failed")
    rest_p, rest_r, rest_e, _ = pose(neutral_parameters())
    render_frames = np.arange(0, len(times), config["render_stride"], dtype=int)
    if render_frames[-1] != len(times) - 1:
        raise ValueError("Choose a stride that samples the final frame exactly")
    out.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        out / "motion.npz",
        source_fps=np.array(fps),
        time_s=times,
        frame_idx=np.arange(len(times)),
        joint_names=np.array(NAMES),
        parents=np.array([p or "" for p in PARENTS]),
        radii=np.array(RADII),
        phase_times_s=np.array(knots),
        phase_names=np.array(config["phase_labels"]),
        joint_positions_world=p_all,
        global_rots=r_all,
        endpoints_world=e_all,
        rest_positions_world=rest_p,
        rest_global_rots=rest_r,
        rest_endpoints_world=rest_e,
        render_frames=render_frames,
        ball_positions_world=ball,
        ball_radius_m=np.array(radius),
        nominal_contact_time_s=np.array(contact),
        motion_kind=np.array("football-kick-v1"),
    )
    with (out / "angles.csv").open("w", newline="") as stream:
        w = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    report = {
        "version": config["version"],
        "frames": len(times),
        "source_fps": fps,
        "motion_source": "original authored movement; no mocap or downloaded motion",
        "nominal_contact_time_s": contact,
        "max_angle_check_error_deg": angle_error,
        "max_link_length_error_m": max_link_error,
        "max_support_ik_error_m": max(errors),
        "max_support_ankle_drift_m": support_error,
        "minimum_kick_toe_height_m": minimum_toe,
        "ball_contact_marker_error_m": float(
            abs(np.linalg.norm(ball_start - contact_toe) - radius)
        ),
        "label_scope": "Exact procedural controls; not validated ISB hip/knee/ankle angles",
        "limitations": [
            "No contact forces or dynamic balance solved",
            "Ball departure is illustrative",
            "No all-body self-collision guarantee",
            "No measured performer or clinical validation",
        ],
        "passed": True,
    }
    (out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    (out / "design.json").write_text(json.dumps(config, indent=2) + "\n")
    return report
