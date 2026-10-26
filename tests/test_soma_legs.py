import unittest

import numpy as np

from meshlearning.motion import rotation
from meshlearning.pitch import INDEX, NAMES
from meshlearning.soma_legs import PAIRS, SEGMENTS, leg_registration, map_legs


def fixture():
    points = {
        "Hips": [0, 0, 1],
        "Chest": [0, 0, 1.3],
        "RightArm": [0.25, 0, 1.5],
        "LeftArm": [-0.25, 0, 1.5],
        "RightForeArm": [0.55, 0, 1.5],
        "LeftForeArm": [-0.55, 0, 1.5],
    }
    for side, x in (("Right", 0.1), ("Left", -0.1)):
        for name, p in (
            ("Leg", [x, 0, 0.95]),
            ("Shin", [x, 0, 0.5]),
            ("Foot", [x, 0, 0.05]),
            ("ToeBase", [x, 0.18, 0.015]),
        ):
            points[side + name] = p
    names = list(points)
    t = np.tile(np.eye(4), (len(names), 1, 1))
    for j, name in enumerate(names):
        t[j, :3, 3] = points[name]
        t[j, :3, :3] = rotation([5 * j, 3 * j, -2 * j])
    return {
        "joint_names": names,
        "t_pose_world": t,
        "up_axis": "Z",
        "sha256": "synthetic fixture",
        "skeleton_path": "/Fixture",
        "meters_per_unit": 1,
        "matrix_policy": "synthetic",
    }


class LegRegistrationTests(unittest.TestCase):
    def test_actual_template_reference_is_reconstructed(self):
        rig = fixture()
        reg = leg_registration(rig)
        g = np.array(reg["world_model_to_soma"])
        for name, entry in reg["segments"].items():
            recovered = (
                g
                @ entry["model_reference_rotation"]
                @ np.array(entry["segment_registration"])
            )
            expected = rig["t_pose_world"][rig["joint_names"].index(name), :3, :3]
            np.testing.assert_allclose(recovered, expected, atol=1e-12)

    def test_reference_foot_preserves_our_sloped_toe_vector(self):
        reg = leg_registration(fixture())
        for side in ("Right", "Left"):
            np.testing.assert_allclose(
                reg["segments"][side + "Foot"]["model_reference_rotation"],
                np.eye(3),
                atol=1e-12,
            )

    def test_mapping_is_reversible_and_common_world_motion_cancels(self):
        reg = leg_registration(fixture())
        source = np.tile(np.eye(3), (2, len(NAMES), 1, 1))
        for side in ("R", "L"):
            source[:, INDEX["thigh_" + side]] = rotation([35, 0, 0])
            source[:, INDEX["shank_" + side]] = rotation([-25, 0, 0])
            source[:, INDEX["foot_" + side]] = rotation([-10, 0, 0])
        source[1] = rotation([15, -20, 70]) @ source[1]
        mapped, error = map_legs(source, reg)
        self.assertLess(error, 1e-12)
        names = list(SEGMENTS)
        for parent, child in PAIRS:
            local = (
                mapped["global_rots"][:, names.index(parent)].swapaxes(-1, -2)
                @ mapped["global_rots"][:, names.index(child)]
            )
            np.testing.assert_allclose(local[0], local[1], atol=1e-12)

    def test_scaled_measurement_foot_is_rejected(self):
        rig = fixture()
        rig["t_pose_world"][rig["joint_names"].index("RightFoot"), :3, :3] *= 2
        with self.assertRaisesRegex(ValueError, "proper rotation"):
            leg_registration(rig)
