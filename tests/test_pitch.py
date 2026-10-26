import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from meshlearning.motion import rotation
from meshlearning.pitch import (
    INDEX,
    functional_angles,
    functional_rotation,
    generate,
    interpolate,
    neutral_parameters,
    pose,
)

CONFIG = Path(__file__).resolve().parents[1] / "configs/pitch_v1.json"


class PitchTests(unittest.TestCase):
    def test_independent_known_pose_geometry(self):
        # Horizontal right upper arm +X, local anterior points superior: 90 deg external.
        known = np.array([[0, 0, -1], [-1, 0, 0], [0, 1, 0]], dtype=float)
        elevation, plane, axial, valid = functional_angles(np.eye(3), known)
        self.assertTrue(valid)
        np.testing.assert_allclose([elevation, plane, axial], [90, 0, -90], atol=1e-10)

    def test_mirrored_angles_and_world_invariance(self):
        world = rotation([24, -31, 56])
        for side in ("R", "L"):
            r = functional_rotation(-25, 100, -135, side)
            elevation, plane, axial, valid = functional_angles(world, world @ r, side)
            self.assertTrue(valid)
            np.testing.assert_allclose(
                [elevation, plane, axial], [100, -25, -135], atol=1e-10
            )

    def test_parallel_humerus_does_not_get_false_axial_label(self):
        for elevation in (0, 180):
            _, plane, axial, valid = functional_angles(
                np.eye(3), functional_rotation(25, elevation, -120)
            )
            self.assertFalse(valid)
            self.assertTrue(np.isnan(plane) and np.isnan(axial))

    def test_scapula_changes_center_not_thorax_humerus_target(self):
        params = neutral_parameters()
        params.update(R_elevation=100, R_plane=-15, R_axial=-135)
        p1, r1, _, _ = pose(params, shoulder_motion=True)
        p2, r2, _, _ = pose(params, shoulder_motion=False)
        self.assertGreater(
            np.linalg.norm(p1[INDEX["humerus_R"]] - p2[INDEX["humerus_R"]]), 0.005
        )
        np.testing.assert_allclose(r1[INDEX["humerus_R"]], r2[INDEX["humerus_R"]])
        self.assertGreater(
            np.linalg.norm(r1[INDEX["scapula_R"]] - r2[INDEX["scapula_R"]]), 0.1
        )

    def test_interpolator_passes_knots_without_overshoot(self):
        times = [0.0, 0.4, 0.8, 1.1]
        values = [-20.0, 0.0, 80.0, 90.0]
        np.testing.assert_allclose(interpolate(times, values, times), values)
        sampled = interpolate(times, values, np.linspace(0, 1.1, 100))
        self.assertTrue(np.all(np.diff(sampled) >= 0))
        self.assertGreaterEqual(sampled.min(), -20)
        self.assertLessEqual(sampled.max(), 90)
        with self.assertRaises(ValueError):
            interpolate(times, values, [1.2])

    def test_export_is_dense_timed_and_review_is_four_times_slow(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "pitch"
            report = generate(CONFIG, out)
            self.assertTrue(all(report["checks"].values()))
            self.assertEqual(report["source_frames"], 505)
            self.assertEqual(report["source_fps"], 240)
            self.assertEqual(report["slowdown_factor"], 4)
            self.assertLess(report["max_leg_ik_target_error_m"], 1e-5)
            with np.load(out / "motion.npz", allow_pickle=False) as blob:
                self.assertEqual(blob["global_rots"].shape, (505, 22, 3, 3))
                np.testing.assert_allclose(np.diff(blob["time_s"]), 1 / 240, atol=1e-12)
                np.testing.assert_array_equal(np.diff(blob["render_frames"]), 4)
                # Segment lengths stay constant, including both IK leg links.
                for side in ("R", "L"):
                    for part in ("humerus", "forearm", "thigh", "shank"):
                        j = INDEX[f"{part}_{side}"]
                        lengths = np.linalg.norm(
                            blob["endpoints_world"][:, j]
                            - blob["joint_positions_world"][:, j],
                            axis=1,
                        )
                        np.testing.assert_allclose(lengths, lengths[0], atol=1e-9)
            self.assertEqual(
                json.loads((out / "report.json").read_text())["version"],
                "designed-pitch-v1",
            )
            with self.assertRaisesRegex(ValueError, "empty"):
                generate(CONFIG, out)
