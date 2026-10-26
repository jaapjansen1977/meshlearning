import tempfile
import unittest
from pathlib import Path

from meshlearning.evaluation import compare_angles


class EvaluationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.reference = self.root / "reference.csv"
        self.pred = self.root / "pred"
        self.pred.mkdir()
        self.reference.write_text(
            "frame_idx,time_s,joint,column,value_deg\n0,0,hip_L,hip_l_rot_deg,0\n1,0.1,hip_L,hip_l_rot_deg,80\n"
        )
        (self.pred / "hip_L.csv").write_text(
            "time_s,hip_l_rot_deg,hip_l_lock_flag\n0,10,0\n0.1,60,1\n"
        )

    def test_known_bias_and_extreme_errors(self):
        report = compare_angles(self.reference, self.pred, self.root / "result", 10)
        m = report["channels"]["hip_L/hip_l_rot_deg"]
        self.assertEqual(m["mae_deg"], 15)
        self.assertEqual(m["bias_deg"], -5)
        self.assertEqual(m["lock_count"], 1)
        self.assertEqual(m["absolute_reference_bins"]["60_to_90"]["mae_deg"], 20)

    def test_time_misalignment_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Timestamp mismatch"):
            compare_angles(self.reference, self.pred, self.root / "result", 20)

    def test_nonfinite_is_rejected(self):
        self.reference.write_text(self.reference.read_text().replace(",80\n", ",nan\n"))
        with self.assertRaisesRegex(ValueError, "Nonfinite"):
            compare_angles(self.reference, self.pred, self.root / "result", 10)
