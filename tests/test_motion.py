import unittest

import numpy as np

from meshlearning.motion import NAMES, decompose, forward, generate, rotation


class MotionTests(unittest.TestCase):
    def test_rotation_roundtrip(self):
        for angles in ([80, 35, -65], [-45, -40, 120], [0, 0, 0]):
            np.testing.assert_allclose(decompose(rotation(angles)), angles, atol=1e-10)

    def test_parent_rotation_moves_descendants(self):
        c = np.zeros((len(NAMES), 3))
        p0, _, _ = forward(c)
        c[NAMES.index("thigh_L"), 0] = 90
        p, _r, _ = forward(c)
        np.testing.assert_allclose(
            p[NAMES.index("shank_L")] - p[NAMES.index("thigh_L")],
            [0, 0.43, 0],
            atol=1e-10,
        )
        np.testing.assert_allclose(
            p[NAMES.index("thigh_R")], p0[NAMES.index("thigh_R")]
        )

    def test_generated_rotations_and_timestamps(self):
        d = generate(24, 24)
        self.assertEqual(d["global_rots"].shape, (24, len(NAMES), 3, 3))
        np.testing.assert_allclose(np.linalg.det(d["global_rots"]), 1, atol=1e-10)
        np.testing.assert_allclose(
            d["global_rots"].swapaxes(-1, -2) @ d["global_rots"],
            np.broadcast_to(np.eye(3), d["global_rots"].shape),
            atol=1e-10,
        )
        self.assertEqual(d["time_s"][-1], 23 / 24)
        self.assertGreater(np.max(np.abs(d["controls_deg"][:, :, 2])), 40)


if __name__ == "__main__":
    unittest.main()
