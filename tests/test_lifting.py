import unittest

import numpy as np

from meshlearning.lifting import VARIANTS, sample


class LiftingTests(unittest.TestCase):
    def test_independent_segment_directions_and_fixed_feet(self):
        for name in VARIANTS:
            for t in np.linspace(0, 6, 121):
                f = sample(name, t)
                p, e = f["joint_positions_world"], f["endpoints_world"]
                r = f["global_rots"]
                ix = {n: i for i, n in enumerate(f["joint_names"])}
                for side, sign in [("R", 1), ("L", -1)]:
                    np.testing.assert_allclose(
                        p[ix[f"foot_{side}"]], [sign * 0.095, 0, 0.08], atol=1e-12
                    )
                    upper = e[ix[f"thigh_{side}"]] - p[ix[f"thigh_{side}"]]
                    lower = e[ix[f"shank_{side}"]] - p[ix[f"shank_{side}"]]
                    knee = np.rad2deg(
                        np.arctan2(
                            np.linalg.norm(np.cross(upper, lower)), upper @ lower
                        )
                    )
                    self.assertAlmostEqual(
                        knee, f["row"]["knee_flexion_deg"], places=10
                    )
                    pelvic_down = r[ix["pelvis"]] @ np.array([0.0, 0.0, -1.0])
                    thigh_down = upper / np.linalg.norm(upper)
                    hip = np.rad2deg(
                        np.arctan2(
                            np.cross(pelvic_down, thigh_down)[0],
                            pelvic_down @ thigh_down,
                        )
                    )
                    self.assertAlmostEqual(hip, f["row"]["hip_flexion_deg"], places=10)
                    for part, length in [("humerus", 0.32), ("forearm", 0.29)]:
                        j = ix[f"{part}_{side}"]
                        self.assertAlmostEqual(
                            np.linalg.norm(e[j] - p[j]), length, places=12
                        )
                for j, n in enumerate(f["joint_names"]):
                    if n.startswith("lumbar"):
                        np.testing.assert_allclose(
                            e[j] - p[j], r[j] @ np.array([0, 0, 0.035]), atol=1e-12
                        )
                a = r[ix["pelvis"]] @ np.array([0, 0, 1.0])
                b = r[ix["thorax"]] @ np.array([0, 0, 1.0])
                lumbar = np.rad2deg(np.arctan2(np.linalg.norm(np.cross(a, b)), a @ b))
                self.assertAlmostEqual(
                    lumbar, f["row"]["lumbar_flexion_deg"], places=10
                )

    def test_same_bottom_target_and_distinct_strategies(self):
        rows = {n: sample(n, 1.8)["row"] for n in VARIANTS}
        self.assertEqual({r["handle_height_m"] for r in rows.values()}, {0.65})
        self.assertLess(rows["hip_hinge"]["lumbar_flexion_deg"], 6)
        self.assertGreater(rows["lumbar_dominant"]["lumbar_flexion_deg"], 59)
        self.assertLess(rows["lumbar_dominant"]["pelvis_anterior_tilt_deg"], 0)
        self.assertGreater(rows["lumbar_dominant"]["hip_flexion_deg"], 0)
        self.assertGreater(rows["squat"]["knee_flexion_deg"], 90)

    def test_grasp_motion_and_cycle_continuity(self):
        for name in VARIANTS:
            for t in np.linspace(1.8, 4.7, 60):
                f = sample(name, t)
                ix = list(f["joint_names"]).index("hand_R")
                self.assertAlmostEqual(
                    f["endpoints_world"][ix, 2], f["row"]["box_handle_height_m"]
                )
            for t in [1.4, 1.8, 3, 3.5, 4.7, 5]:
                a = sample(name, t - 1e-7)
                b = sample(name, t + 1e-7)
                np.testing.assert_allclose(
                    a["joint_positions_world"], b["joint_positions_world"], atol=1e-6
                )
            a = sample(name, 0)
            b = sample(name, 6)
            np.testing.assert_allclose(
                a["joint_positions_world"], b["joint_positions_world"]
            )
