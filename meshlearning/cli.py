import argparse
import csv
import json
import subprocess
from pathlib import Path

import numpy as np

from .motion import BONES, NAMES, generate


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="command", required=True)
    g = sub.add_parser("demo")
    g.add_argument("--out", type=Path, default=Path("outputs/demo"))
    g.add_argument("--frames", type=int, default=48)
    g.add_argument("--fps", type=int, default=24)
    g.add_argument("--scale", type=float, default=1.0)
    g.add_argument("--render", action="store_true")
    g.add_argument("--size", type=int, default=256)
    c = sub.add_parser("compare")
    c.add_argument("--reference", type=Path, required=True)
    c.add_argument("--predictions", type=Path, required=True)
    c.add_argument("--out", type=Path, required=True)
    v = sub.add_parser("compare-angles")
    v.add_argument("--reference", type=Path, required=True)
    v.add_argument("--predictions", type=Path, required=True)
    v.add_argument("--out", type=Path, required=True)
    v.add_argument("--fps", type=float, required=True)
    controls_parser = sub.add_parser(
        "controls", help="Generate isolated-angle definitions and check report"
    )
    controls_parser.add_argument("--out", type=Path, required=True)
    motion_parser = sub.add_parser(
        "isolated-motion", help="Generate one renderable isolated rotation"
    )
    motion_parser.add_argument("--out", type=Path, required=True)
    motion_parser.add_argument("--case", default="thigh_L.z")
    motion_parser.add_argument("--frames", type=int, default=48)
    motion_parser.add_argument("--fps", type=int, default=24)
    a = p.parse_args()
    if a.command == "controls":
        from .controls import write_package

        print(json.dumps(write_package(a.out), indent=2))
        return
    if a.command == "isolated-motion":
        from .controls import write_motion

        print(write_motion(a.out, a.case, a.frames, a.fps).resolve())
        return
    if a.command == "compare-angles":
        from .evaluation import compare_angles

        print(
            json.dumps(
                compare_angles(a.reference, a.predictions, a.out, a.fps), indent=2
            )
        )
        return
    if a.command == "demo":
        if a.size < 16 or a.size % 2 or a.frames < 2 or a.fps <= 0 or a.scale <= 0:
            p.error("Require even size >=16, frames >=2, positive fps and scale")
        a.out.mkdir(parents=True, exist_ok=True)
        if any(a.out.iterdir()):
            p.error("Output directory must be empty; existing results are preserved")
        d = generate(a.frames, a.fps, a.scale)
        np.savez_compressed(a.out / "reference.npz", **d)
        with (a.out / "controls.csv").open("w", newline="") as f:
            w = csv.writer(f)
            w.writerow(
                [
                    "frame_idx",
                    "time_s",
                    "segment",
                    "x_control_deg",
                    "y_control_deg",
                    "z_control_deg",
                ]
            )
            for i in range(a.frames):
                for j, name in enumerate(NAMES):
                    w.writerow([i, d["time_s"][i], name, *d["controls_deg"][i, j]])
        (a.out / "manifest.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "fps": a.fps,
                    "frames": a.frames,
                    "scale": a.scale,
                    "angle_status": "engineering controls; NOT validated ISB angles",
                    "rotation_convention": "active local Rx(x) @ Ry(y) @ Rz(z); right-handed X right Y anterior Z up",
                    "units": {"position": "m", "controls": "deg", "rotation": "matrix"},
                    "parents": {b[0]: b[1] for b in BONES},
                    "assets": "original procedural geometry; no third-party human assets",
                    "limitations": [
                        "No anatomical validation",
                        "No collision or contact constraints",
                        "No SOMA mapping",
                        "No GEM-X training or inference performed",
                        "No occlusion labels; in_frame only",
                    ],
                    "source_reference": "Lavikainen et al., doi:10.1038/s41597-025-06243-7; method inspiration, no dataset/assets copied",
                },
                indent=2,
            )
        )
        if a.render:
            subprocess.run(
                [
                    "blender",
                    "--background",
                    "--threads",
                    "2",
                    "--python",
                    str(Path(__file__).resolve().parents[1] / "scripts/render.py"),
                    "--",
                    "--data",
                    str((a.out / "reference.npz").resolve()),
                    "--out",
                    str(a.out.resolve()),
                    "--fps",
                    str(a.fps),
                    "--size",
                    str(a.size),
                ],
                check=True,
            )
            for camera in ("front", "oblique"):
                subprocess.run(
                    [
                        "ffmpeg",
                        "-v",
                        "error",
                        "-n",
                        "-framerate",
                        str(a.fps),
                        "-i",
                        str(a.out / camera / "%05d.png"),
                        "-c:v",
                        "libx264",
                        "-pix_fmt",
                        "yuv420p",
                        str(a.out / f"{camera}.mp4"),
                    ],
                    check=True,
                )
        print(a.out.resolve())
    else:
        with (
            np.load(a.reference, allow_pickle=False) as r,
            np.load(a.predictions, allow_pickle=False) as pred,
        ):
            for key in ("joint_names", "frame_idx"):
                if not np.array_equal(r[key], pred[key]):
                    raise ValueError(
                        f"{key} must match exactly; map skeleton and align frames explicitly first"
                    )
            x = r["global_rots"]
            y = pred["global_rots"]
            if x.shape != y.shape or x.ndim != 4 or x.shape[-2:] != (3, 3):
                raise ValueError("Expected matching (T,J,3,3) rotations")
            for matrices in (x, y):
                if (
                    not np.isfinite(matrices).all()
                    or not np.allclose(
                        matrices.swapaxes(-1, -2) @ matrices, np.eye(3), atol=1e-5
                    )
                    or not np.allclose(np.linalg.det(matrices), 1, atol=1e-5)
                ):
                    raise ValueError("Invalid rotation matrices")
            rel = x.swapaxes(-1, -2) @ y
            err = np.rad2deg(
                np.arccos(np.clip((np.trace(rel, axis1=-2, axis2=-1) - 1) / 2, -1, 1))
            )
            report = {
                "metric": "global segment orientation geodesic error; NOT clinical angle error",
                "mean_deg": float(err.mean()),
                "per_segment": {
                    str(n): {
                        "mean_deg": float(err[:, j].mean()),
                        "max_deg": float(err[:, j].max()),
                    }
                    for j, n in enumerate(r["joint_names"])
                },
            }
            a.out.parent.mkdir(parents=True, exist_ok=True)
            a.out.write_text(json.dumps(report, indent=2))
            print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
