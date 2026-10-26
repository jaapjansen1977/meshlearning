import hashlib
import importlib.util
import tempfile
import unittest
from pathlib import Path

import numpy as np

from meshlearning.motion import rotation
from meshlearning.pitch import INDEX, NAMES, functional_rotation
from meshlearning.soma_bridge import map_motion, read_rig, template_registration

USD_AVAILABLE = importlib.util.find_spec("pxr") is not None


class AssetGuardTests(unittest.TestCase):
    def test_lfs_pointer_is_not_accepted_as_actual_rig(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rig.usda"
            path.write_text(
                "version https://git-lfs.github.com/spec/v1\noid sha256:"
                + "0" * 64
                + "\nsize 344934193\n"
            )
            with self.assertRaisesRegex(ValueError, "Git LFS pointer"):
                read_rig(path)

    def test_unverified_bytes_are_rejected_before_usd_parse(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rig.usda"
            path.write_text("#usda 1.0\n")
            with self.assertRaisesRegex(ValueError, "SHA256"):
                read_rig(path)


@unittest.skipUnless(USD_AVAILABLE, "Install the bridge extra to test USD parsing")
class USDReaderTests(unittest.TestCase):
    def make_fixture(self, path):
        from pxr import Gf, Usd, UsdGeom, UsdSkel, Vt

        paths = [
            "Root",
            "Root/Hips",
            "Root/Hips/Chest",
            "Root/Hips/Chest/RightArm",
            "Root/Hips/Chest/LeftArm",
            "Root/Hips/Chest/RightArm/RightForeArm",
            "Root/Hips/Chest/LeftArm/LeftForeArm",
        ]
        parents = [-1, 0, 1, 2, 2, 3, 4]
        positions = [
            [0, 0, 0],
            [0, 0, 1],
            [0, 0, 1.3],
            [0.2, 0, 1.4],
            [-0.2, 0, 1.4],
            [0.5, 0, 1.4],
            [-0.5, 0, 1.4],
        ]
        world = np.tile(np.eye(4), (7, 1, 1))
        world[:, :3, 3] = positions
        world[2, :3, :3] = rotation([5, 8, 17])
        world[3, :3, :3] = rotation([15, 30, 40])
        world[4, :3, :3] = rotation([-20, 50, -15])
        local = np.array(
            [
                w if parents[i] < 0 else np.linalg.inv(world[parents[i]]) @ w
                for i, w in enumerate(world)
            ]
        )
        stage = Usd.Stage.CreateNew(str(path))
        UsdGeom.SetStageUpAxis(stage, "Z")
        UsdGeom.SetStageMetersPerUnit(stage, 1)
        UsdGeom.Xform.Define(stage, "/World").AddTranslateOp().Set(Gf.Vec3d(4, 7, 2))
        skel = UsdSkel.Skeleton.Define(stage, "/World/Skeleton")
        skel.CreateJointsAttr(Vt.TokenArray(paths))
        skel.CreateRestTransformsAttr(
            Vt.Matrix4dArray([Gf.Matrix4d(m.T.tolist()) for m in local])
        )
        skel.CreateBindTransformsAttr(
            Vt.Matrix4dArray([Gf.Matrix4d(m.T.tolist()) for m in world])
        )
        stage.GetRootLayer().Save()
        return world

    def test_usd_transposition_and_parent_accumulation_match_soma_loader(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "synthetic_fixture_only.usda"
            expected = self.make_fixture(path)
            rig = read_rig(path, hashlib.sha256(path.read_bytes()).hexdigest())
            np.testing.assert_allclose(rig["t_pose_world"], expected, atol=1e-12)
            np.testing.assert_allclose(rig["bind_pose_world"], expected, atol=1e-12)
            self.assertEqual(rig["up_axis"], "Z")
            self.assertEqual(rig["joint_names"][3], "RightArm")
            # The extra scene Xform is deliberately ignored, as in pinned soma/io.py.
            self.assertAlmostEqual(rig["t_pose_world"][2, 1, 3], 0)

    def test_nonrigid_helpers_are_reported_but_not_used_as_measurement_frames(self):
        from pxr import Gf, Usd, UsdSkel, Vt

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "synthetic_fixture_only.usda"
            self.make_fixture(path)
            stage = Usd.Stage.Open(str(path))
            skel = UsdSkel.Skeleton.Get(stage, "/World/Skeleton")
            joints = list(skel.GetJointsAttr().Get())
            joints.append("Root/ScaledHelper")
            skel.GetJointsAttr().Set(Vt.TokenArray(joints))
            m = Gf.Matrix4d(1)
            m[0, 0] = 1.04
            for attr in (skel.GetRestTransformsAttr(), skel.GetBindTransformsAttr()):
                values = list(attr.Get())
                values.append(m)
                attr.Set(Vt.Matrix4dArray(values))
            stage.GetRootLayer().Save()
            rig = read_rig(path, hashlib.sha256(path.read_bytes()).hexdigest())
            self.assertEqual(rig["nonrigid_auxiliary_joints"], ["ScaledHelper"])

    def test_nonrigid_measurement_segment_is_rejected(self):
        from pxr import Usd, UsdSkel, Vt

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "synthetic_fixture_only.usda"
            self.make_fixture(path)
            stage = Usd.Stage.Open(str(path))
            skel = UsdSkel.Skeleton.Get(stage, "/World/Skeleton")
            values = list(skel.GetRestTransformsAttr().Get())
            values[2][0, 0] *= 1.04
            skel.GetRestTransformsAttr().Set(Vt.Matrix4dArray(values))
            stage.GetRootLayer().Save()
            with self.assertRaisesRegex(ValueError, "proper rotation"):
                read_rig(path, hashlib.sha256(path.read_bytes()).hexdigest())

    def test_template_registration_and_multiple_pose_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "synthetic_fixture_only.usda"
            self.make_fixture(path)
            rig = read_rig(path, hashlib.sha256(path.read_bytes()).hexdigest())
            registration = template_registration(rig)
            rotations = np.tile(np.eye(3), (4, len(NAMES), 1, 1))
            for f in range(4):
                tr = rotation([f * 10, -f * 8, f * 20])
                rotations[f, INDEX["thorax"]] = tr
                for side in ("R", "L"):
                    rotations[f, INDEX[f"humerus_{side}"]] = tr @ functional_rotation(
                        -20 + f * 10, 30 + f * 20, -60 + f * 40, side
                    )
            mapped, error = map_motion(
                {"frame_idx": np.arange(4), "global_rots": rotations}, registration
            )
            self.assertLess(error, 1e-12)
            self.assertEqual(mapped["global_rots"].shape, (4, 3, 3, 3))
            np.testing.assert_allclose(
                np.linalg.det(mapped["global_rots"]), 1, atol=1e-12
            )
            np.testing.assert_allclose(
                mapped["rest_global_rots"], np.tile(np.eye(3), (3, 1, 1))
            )
