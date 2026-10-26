import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from meshlearning.binding import weights_for_vertices
from meshlearning.frames import (
    MODEL_FROM_ISB,
    humerus_frame,
    landmark_yxy,
    map_registered_frames,
    thorax_frame,
    virtual_landmarks,
)
from meshlearning.motion import rotation
from meshlearning.pitch import (
    INDEX,
    RADII,
    functional_rotation,
    generate,
    neutral_parameters,
    pose,
)

ROOT = Path(__file__).resolve().parents[1]


class RevisionTests(unittest.TestCase):
    def test_forearm_shaft_is_owned_only_by_forearm(self):
        p, r, e, _ = pose(neutral_parameters())
        for side in ("R", "L"):
            j = INDEX[f"humerus_{side}"]
            d = (e[j] - p[j]) / 0.30
            points = np.array(
                [
                    p[j] + d * t + r[j] @ np.array([0, 0.025, 0])
                    for t in (0.35, 0.4, 0.45, 0.5)
                ]
            )
            weights, regions = weights_for_vertices(points, p, r, e, np.array(RADII))
            np.testing.assert_allclose(weights[:, INDEX[f"forearm_{side}"]], 1)
            self.assertTrue(np.all(regions == f"rigid_forearm_{side}"))

    def test_upper_chest_cannot_be_pulled_by_arm(self):
        p, r, e, _ = pose(neutral_parameters())
        points = np.array(
            [
                [x, 0.08, p[INDEX["thorax"], 2] + 0.22]
                for x in (-0.15, -0.1, 0, 0.1, 0.15)
            ]
        )
        weights, regions = weights_for_vertices(points, p, r, e, np.array(RADII))
        np.testing.assert_allclose(weights[:, INDEX["thorax"]], 1)
        self.assertTrue(np.all(regions == "protected_torso"))

    def test_landmark_frames_match_explicit_basis(self):
        tr = rotation([20, -14, 55])
        hr = tr @ functional_rotation(-25, 95, -115)
        lm = virtual_landmarks([0, 0, 1], tr, [0.2, 0.1, 1.4], hr, "R")
        t = thorax_frame(*(lm[k] for k in ("IJ", "C7", "PX", "T8")))
        h = humerus_frame(*(lm[k] for k in ("GH", "EL", "EM")), "R")
        np.testing.assert_allclose(t, tr @ MODEL_FROM_ISB, atol=1e-12)
        np.testing.assert_allclose(h, hr @ MODEL_FROM_ISB, atol=1e-12)

    def test_yxy_proxy_agrees_with_geometry_for_both_sides(self):
        for side, s in [("R", 1), ("L", -1)]:
            for elevation in (15, 90, 110):
                tr = rotation([20, -15, 55])
                hr = tr @ functional_rotation(-25, elevation, -115, side)
                lm = virtual_landmarks([0, 0, 1], tr, [0.2, 0.1, 1.4], hr, side)
                yxy, valid = landmark_yxy(lm, side)
                self.assertTrue(valid)
                np.testing.assert_allclose(
                    yxy, [s * -25, -s * elevation, s * -115], atol=1e-10
                )

    def test_singular_proxy_angles_and_degenerate_landmarks_rejected(self):
        lm = virtual_landmarks([0, 0, 1], np.eye(3), [0.2, 0, 1.4], np.eye(3), "R")
        angles, valid = landmark_yxy(lm, "R")
        self.assertFalse(valid)
        self.assertTrue(np.isnan(angles[0]))
        with self.assertRaisesRegex(ValueError, "Degenerate"):
            thorax_frame([0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0])

    def test_registered_mapping_is_world_invariant_and_reversible(self):
        tr = rotation([20, -15, 55])
        hr = tr @ functional_rotation(-25, 100, -115)
        bt = rotation([13, 8, -21])
        bh = rotation([-12, 17, 35])
        g = rotation([-20, 36, 13])
        mapped = map_registered_frames(tr, hr, bt, bh)
        np.testing.assert_allclose(mapped, (g @ tr @ bt).T @ (g @ hr @ bh), atol=1e-12)
        np.testing.assert_allclose(bt @ mapped @ bh.T, tr.T @ hr, atol=1e-12)
        with self.assertRaisesRegex(ValueError, "no identity fallback"):
            map_registered_frames(tr, hr, None, None)

    def test_v2_timing_and_trunk_excursion_improve_explicit_design(self):
        v1 = json.loads((ROOT / "configs/pitch_v1.json").read_text())
        v2 = json.loads((ROOT / "configs/pitch_v2.json").read_text())
        dt1 = v1["key_times_s"][5] - v1["key_times_s"][4]
        dt2 = v2["key_times_s"][5] - v2["key_times_s"][4]
        self.assertGreater(dt2, 3 * dt1)
        self.assertGreater(
            max(v2["tracks"]["trunk_lean"]), max(v1["tracks"]["trunk_lean"])
        )
        self.assertGreater(
            np.ptp(v2["tracks"]["thorax_yaw"]), np.ptp(v1["tracks"]["thorax_yaw"])
        )
        with tempfile.TemporaryDirectory() as tmp:
            report = generate(ROOT / "configs/pitch_v2.json", Path(tmp) / "motion")
            self.assertEqual(report["version"], "designed-pitch-v2")
            self.assertEqual(report["source_frames"], 601)
            self.assertEqual(report["phases"][4]["time_s"], 1.15)
            self.assertTrue(all(report["checks"].values()))
