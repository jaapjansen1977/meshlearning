"""Known anatomical model poses; fixtures do not use the reference decoder."""

import unittest

import numpy as np

from meshlearning.shoulder_reference import (
    SAGITTAL_MIRROR,
    angles_from_frames,
    angles_from_landmarks,
    angles_from_registered_segments,
    frames_from_landmarks,
)


def quat_axis(axis, angle):
    # Independent fixture: quaternion -> rotation polynomial.
    v = np.asarray(axis) * np.sin(np.deg2rad(angle) / 2)
    w = np.cos(np.deg2rad(angle) / 2)
    x, y, z = v
    return np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ]
    )


def landmarks(r, side="R"):
    gh = np.array([0, 0, 0.22 if side == "R" else -0.22])
    elbow = gh - 0.3 * r[:, 1]
    lateral = r[:, 2] * (0.035 if side == "R" else -0.035)
    return {
        "IJ": np.array([0.08, 0.3, 0]),
        "C7": np.array([-0.08, 0.3, 0]),
        "PX": np.array([0.08, 0, 0]),
        "T8": np.array([-0.08, 0, 0]),
        "GH": gh,
        "EL": elbow + lateral,
        "EM": elbow - lateral,
    }


class ShoulderReferenceTests(unittest.TestCase):
    def test_160_abduction_from_anatomical_landmarks(self):
        for side in ("R", "L"):
            r = quat_axis([1, 0, 0], -160 if side == "R" else 160)
            result = angles_from_landmarks(landmarks(r, side), side)
            self.assertAlmostEqual(result.elevation_deg, 160)
            self.assertAlmostEqual(result.plane_of_elevation_deg, 0)
            self.assertAlmostEqual(result.axial_yxy_deg, 0)
            self.assertAlmostEqual(result.frontal_swing_component_deg, 160)
            self.assertAlmostEqual(result.sagittal_swing_component_deg, 0)
            self.assertAlmostEqual(result.minimal_swing_twist_deg, 0)

    def test_160_pure_anteflexion_has_different_yxy_axial_coordinate(self):
        for side in ("R", "L"):
            r = quat_axis([0, 0, 1], 160)
            result = angles_from_landmarks(landmarks(r, side), side)
            self.assertAlmostEqual(result.elevation_deg, 160)
            self.assertAlmostEqual(result.plane_of_elevation_deg, 90)
            self.assertAlmostEqual(result.axial_yxy_deg, -90)
            self.assertAlmostEqual(result.frontal_swing_component_deg, 0)
            self.assertAlmostEqual(result.sagittal_swing_component_deg, 160)
            self.assertAlmostEqual(result.minimal_swing_twist_deg, 0)

    def test_combined_pose_and_bilateral_signs(self):
        r = (
            quat_axis([0, 1, 0], 35)
            @ quat_axis([1, 0, 0], -125)
            @ quat_axis([0, 1, 0], -60)
        )
        for side in ("R", "L"):
            actual = r if side == "R" else SAGITTAL_MIRROR @ r @ SAGITTAL_MIRROR
            result = angles_from_landmarks(landmarks(actual, side), side)
            np.testing.assert_allclose(
                [
                    result.plane_of_elevation_deg,
                    result.elevation_deg,
                    result.axial_yxy_deg,
                    result.minimal_swing_twist_deg,
                ],
                [35, 125, -60, -25],
                atol=1e-10,
            )
            expected = [35, -125, -60] if side == "R" else [-35, 125, 60]
            np.testing.assert_allclose(result.raw_yxy_deg, expected, atol=1e-10)

    def test_world_rotation_and_translation_do_not_change_joint_angles(self):
        r = quat_axis([1, 0, 0], -160)
        points = landmarks(r)
        world = quat_axis([0, 0, 1], 73) @ quat_axis([1, 0, 0], 28)
        transformed = {k: world @ v + [4, -2, 7] for k, v in points.items()}
        original = angles_from_landmarks(points, "R")
        result = angles_from_landmarks(transformed, "R")
        np.testing.assert_allclose(
            [result.elevation_deg, result.plane_of_elevation_deg, result.axial_yxy_deg],
            [
                original.elevation_deg,
                original.plane_of_elevation_deg,
                original.axial_yxy_deg,
            ],
            atol=1e-10,
        )

    def test_arm_down_retains_twist_but_not_yxy_plane_or_axial(self):
        result = angles_from_frames(np.eye(3), quat_axis([0, 1, 0], 40), "R")
        self.assertFalse(result.yxy_valid)
        self.assertIsNone(result.plane_of_elevation_deg)
        self.assertIsNone(result.axial_yxy_deg)
        self.assertEqual(result.singularity, "arm_down")
        self.assertAlmostEqual(result.elevation_deg, 0)
        self.assertAlmostEqual(result.minimal_swing_twist_deg, 40)

    def test_arm_up_has_no_unique_plane_or_minimal_twist(self):
        result = angles_from_frames(np.eye(3), quat_axis([1, 0, 0], 180), "R")
        self.assertFalse(result.yxy_valid)
        self.assertEqual(result.singularity, "arm_up")
        self.assertAlmostEqual(result.elevation_deg, 180)
        self.assertIsNone(result.minimal_swing_twist_deg)
        self.assertIsNone(result.frontal_swing_component_deg)

    def test_160_is_not_near_a_yxy_singularity(self):
        result = angles_from_frames(np.eye(3), quat_axis([1, 0, 0], -160), "R")
        self.assertTrue(result.yxy_valid)
        self.assertFalse(result.near_singularity)

    def test_near_pole_warns_without_inventing_zero_angles(self):
        result = angles_from_frames(np.eye(3), quat_axis([1, 0, 0], -0.01), "R")
        self.assertTrue(result.yxy_valid)
        self.assertTrue(result.near_singularity)
        self.assertAlmostEqual(result.elevation_deg, 0.01)

    def test_frames_reject_reflections_scale_and_nonfinite(self):
        for invalid in (np.diag([1, 1, -1]), 2 * np.eye(3), np.full((3, 3), np.nan)):
            with self.assertRaises(ValueError):
                angles_from_frames(np.eye(3), invalid, "R")
        with self.assertRaises(ValueError):
            angles_from_frames(np.eye(3), np.eye(3), "left")

    def test_missing_and_degenerate_landmarks_are_rejected(self):
        points = landmarks(np.eye(3))
        del points["EM"]
        with self.assertRaisesRegex(ValueError, "Missing"):
            frames_from_landmarks(points, "R")
        points = landmarks(np.eye(3))
        points["EL"] = points["EM"]
        with self.assertRaises(ValueError):
            frames_from_landmarks(points, "R")

    def test_explicit_registrations_recover_angles_from_rotated_technical_axes(self):
        t = quat_axis([0, 0, 1], 31)
        h = t @ quat_axis([1, 0, 0], -160)
        bt = quat_axis([0, 1, 0], 72)
        bh = quat_axis([0, 0, 1], -43)
        result = angles_from_registered_segments(t @ bt.T, h @ bh.T, bt, bh, "R")
        self.assertAlmostEqual(result.elevation_deg, 160)
        self.assertAlmostEqual(result.plane_of_elevation_deg, 0)
        self.assertAlmostEqual(result.axial_yxy_deg, 0)
        with self.assertRaises(ValueError):
            angles_from_registered_segments(t, h, None, bh, "R")
