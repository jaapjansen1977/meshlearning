import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from meshlearning.controls import (
    definitions,
    local_motion,
    reconstruct,
    recover_isolated,
    rodrigues,
    run_checks,
    write_motion,
    write_package,
)
from meshlearning.motion import NAMES, forward


class ControlTests(unittest.TestCase):
    def test_known_matrices_and_signs(self):
        # Explicit matrices are an oracle independent of Rodrigues and Euler.
        examples = [
            (0, [[1, 0, 0], [0, 0, -1], [0, 1, 0]]),
            (1, [[0, 0, 1], [0, 1, 0], [-1, 0, 0]]),
            (2, [[0, -1, 0], [1, 0, 0], [0, 0, 1]]),
        ]
        for axis, matrix in examples:
            recovered, _ = recover_isolated(matrix, axis)
            self.assertAlmostEqual(recovered, 90)
            recovered, _ = recover_isolated(matrix, axis, -1)
            self.assertAlmostEqual(recovered, -90)

    def test_reject_compound_and_wrong_axis(self):
        compound = rodrigues([1, 0, 0], 30) @ rodrigues([0, 1, 0], 20)
        for matrix in (compound, rodrigues([0, 1, 0], 30)):
            with self.assertRaisesRegex(ValueError, "Off-axis"):
                recover_isolated(matrix, 0)

    def test_reject_invalid_and_ambiguous_matrices(self):
        for matrix in (np.diag([-1, 1, 1]), np.zeros((3, 3)), np.full((3, 3), np.nan)):
            with self.assertRaises(ValueError):
                recover_isolated(matrix, 0)
        with self.assertRaisesRegex(ValueError, "180 degree"):
            recover_isolated(np.diag([1, -1, -1]), 0)
        with self.assertRaises(ValueError):
            rodrigues([1, 0, 0], 180)

    def test_parent_and_nonidentity_rest_are_actually_removed(self):
        parent = np.array([[0, -1, 0], [1, 0, 0], [0, 0, 1]])
        rest = np.array([[0, 0, 1], [0, 1, 0], [-1, 0, 0]])
        motion = np.array([[1, 0, 0], [0, 0, -1], [0, 1, 0]])
        child = parent @ motion @ rest
        recovered, _ = recover_isolated(local_motion(parent, child, rest), 0)
        self.assertAlmostEqual(recovered, 90)
        # Wrong multiplication order must fail rather than accidentally pass.
        wrong = rest.T @ parent.T @ child
        with self.assertRaisesRegex(ValueError, "Off-axis"):
            recover_isolated(wrong, 0)

    def test_left_right_geometry_and_candidate_signs(self):
        zero = np.zeros((len(NAMES), 3))
        positions, _, _ = forward(zero)
        self.assertLess(positions[NAMES.index("thigh_L"), 0], 0)
        self.assertGreater(positions[NAMES.index("thigh_R"), 0], 0)
        for side, outward in [("L", -1), ("R", 1)]:
            for part in ("thigh", "upperarm"):
                channel = next(
                    d for d in definitions() if d["id"] == f"{part}_{side}.y"
                )
                motions = np.tile(np.eye(3), (len(NAMES), 1, 1))
                index = NAMES.index(f"{part}_{side}")
                motions[index] = rodrigues(channel["positive_axis_parent_rest"], 30)
                p, _, ends = reconstruct(motions)
                self.assertGreater((ends[index, 0] - p[index, 0]) * outward, 0)
            # A virtual anterior arrow turns medially in positive hip internal rotation.
            channel = next(d for d in definitions() if d["id"] == f"thigh_{side}.z")
            arrow = rodrigues(channel["positive_axis_parent_rest"], 30) @ np.array(
                [0, 1, 0]
            )
            self.assertLess(arrow[0] * outward, 0)

    def test_flexion_and_dorsiflexion_geometric_directions(self):
        for side in ("L", "R"):
            for part, coordinate, direction in (
                ("thigh", 1, 1),
                ("upperarm", 1, 1),
                ("forearm", 1, 1),
                ("shank", 1, -1),
                ("foot", 2, 1),
            ):
                channel = next(
                    d for d in definitions() if d["id"] == f"{part}_{side}.x"
                )
                neutral = np.tile(np.eye(3), (len(NAMES), 1, 1))
                _, _, endpoints0 = reconstruct(neutral)
                index = NAMES.index(f"{part}_{side}")
                neutral[index] = rodrigues(channel["positive_axis_parent_rest"], 30)
                _, _, endpoints = reconstruct(neutral)
                self.assertGreater(
                    (endpoints[index, coordinate] - endpoints0[index, coordinate])
                    * direction,
                    0,
                )

    def test_all_channels_conditions_and_passive_joints(self):
        rows = run_checks()
        self.assertEqual(len(rows), 54 * 11 * 3)
        self.assertTrue(all(row["passed"] for row in rows))
        self.assertEqual(len({row["case"] for row in rows}), 54)

    def test_motion_export_and_report_preserve_existing_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out = write_motion(root / "motion", "thigh_L.z", frames=25, fps=12)
            with np.load(out / "reference.npz", allow_pickle=False) as blob:
                self.assertEqual(blob["global_rots"].shape, (25, 18, 3, 3))
                np.testing.assert_allclose(
                    blob["expected_deg"], blob["calculated_deg"], atol=1e-10
                )
                self.assertAlmostEqual(blob["expected_deg"][6], 60)
                self.assertAlmostEqual(blob["expected_deg"][18], -60)
                self.assertAlmostEqual(blob["expected_deg"][0], 0)
                self.assertAlmostEqual(blob["expected_deg"][-1], 0)
            with self.assertRaisesRegex(ValueError, "empty"):
                write_motion(out)
            summary = write_package(root / "checks")
            self.assertEqual(summary["failed"], 0)
            report = json.loads((root / "checks" / "report.json").read_text())
            self.assertEqual(report["checks"], 1782)
            with self.assertRaisesRegex(ValueError, "empty"):
                write_package(root / "checks")
