import tempfile
import unittest
from pathlib import Path

import numpy as np

from meshlearning.football import generate, kick_pose
from meshlearning.pitch import INDEX, neutral_parameters

ROOT = Path(__file__).resolve().parents[1]


class FootballTests(unittest.TestCase):
    def parameters(self):
        return {
            **neutral_parameters(),
            "kick_hip_flexion": 30,
            "kick_knee_flexion": 60,
            "kick_ankle_dorsiflexion": 0,
        }

    def test_fully_extended_knee_gives_one_straight_ninety_centimetre_leg(self):
        params = self.parameters()
        params.update(kick_hip_flexion=55, kick_knee_flexion=0, pelvis_yaw=47)
        p, _, e, _ = kick_pose(params)
        hip, knee, ankle = p[INDEX["thigh_R"]], e[INDEX["thigh_R"]], e[INDEX["shank_R"]]
        self.assertAlmostEqual(np.linalg.norm(ankle - hip), 0.9)
        np.testing.assert_allclose(knee, (hip + ankle) / 2, atol=1e-12)

    def test_kicking_leg_does_not_move_planted_support_ankle(self):
        params = self.parameters()
        params.update(L_ankle_x=-0.1, L_ankle_y=0.06, L_ankle_z=0.075)
        for hip, knee in ((-25, 95), (42, 20), (75, 25)):
            params.update(kick_hip_flexion=hip, kick_knee_flexion=knee)
            p, _, _, errors = kick_pose(params)
            np.testing.assert_allclose(
                p[INDEX["foot_L"]], [-0.1, 0.06, 0.075], atol=1e-12
            )
            self.assertLess(errors["support_L_ik_error_m"], 1e-12)

    def test_export_has_grounded_ball_contact_and_keeps_original_rest_rig(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "kick"
            report = generate(ROOT / "configs/football_kick_v1.json", out)
            self.assertTrue(report["passed"])
            self.assertLess(report["max_angle_check_error_deg"], 1e-8)
            self.assertGreater(report["minimum_kick_toe_height_m"], 0)
            with np.load(out / "motion.npz", allow_pickle=False) as data:
                contact = round(
                    float(data["nominal_contact_time_s"]) * int(data["source_fps"])
                )
                toe = data["endpoints_world"][contact, INDEX["foot_R"]]
                ball = data["ball_positions_world"][contact]
                radius = float(data["ball_radius_m"])
                self.assertAlmostEqual(np.linalg.norm(ball - toe), radius)
                self.assertAlmostEqual(ball[2], radius)
                np.testing.assert_allclose(
                    data["ball_positions_world"][: contact + 1],
                    np.broadcast_to(ball, (contact + 1, 3)),
                )
                self.assertGreater(
                    data["ball_positions_world"][contact + 1, 1], ball[1]
                )
                self.assertEqual(
                    int(data["render_frames"][-1]), len(data["time_s"]) - 1
                )

    def test_foot_follows_lower_leg_when_ankle_control_is_unchanged(self):
        params = self.parameters()
        relatives = []
        worlds = []
        for hip, knee in ((20, 40), (-25, 95)):
            params.update(
                kick_hip_flexion=hip,
                kick_knee_flexion=knee,
                kick_ankle_dorsiflexion=-20,
            )
            _, r, _, _ = kick_pose(params)
            relatives.append(r[INDEX["shank_R"]].T @ r[INDEX["foot_R"]])
            worlds.append(r[INDEX["foot_R"]])
        np.testing.assert_allclose(relatives[0], relatives[1], atol=1e-12)
        self.assertGreater(np.linalg.norm(worlds[0] - worlds[1]), 1)
