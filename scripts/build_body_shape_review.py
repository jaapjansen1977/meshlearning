"""Build GitHub-readable comparisons from render_body_shapes.py output."""

import argparse
import json
import shutil
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

parser = argparse.ArgumentParser()
parser.add_argument("--renders", required=True, type=Path)
parser.add_argument("--out", required=True, type=Path)
args = parser.parse_args()
report = json.loads((args.renders / "report.json").read_text())
args.out.mkdir(parents=True, exist_ok=True)
fps_tag = f"{report['sample_fps']:g}fps"
profiles = ("slender", "baseline", "fuller")
labels = ("Slank", "Basis", "Voller")
font = ImageFont.truetype("DejaVuSans.ttf", 18)
small = ImageFont.truetype("DejaVuSans.ttf", 14)
size = Image.open(args.renders / "slender/front/0000.png").width
for view in ("front", "side"):
    montage_dir = args.renders / ("montage-" + view)
    montage_dir.mkdir(exist_ok=True)
    frames = []
    for k, time in enumerate(report["time_s"]):
        panel = Image.new("RGB", (size * 3, size + 44), "#202630")
        draw = ImageDraw.Draw(panel)
        for col, (profile, label) in enumerate(zip(profiles, labels)):
            panel.paste(
                Image.open(args.renders / profile / view / f"{k:04d}.png"),
                (col * size, 44),
            )
            draw.text((col * size + 12, 5), label, font=font, fill="white")
        draw.text(
            (size * 3 - 145, 27), f"brontijd {time:.2f} s", font=small, fill="white"
        )
        panel.save(montage_dir / f"{k:04d}.png")
        frames.append(panel)
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-framerate",
            str(report["sample_fps"] / 4),
            "-i",
            str(montage_dir / "%04d.png"),
            "-c:v",
            "libx264",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(args.out / f"comparison-{view}-slow.mp4"),
        ],
        check=True,
    )
    if view == "front":
        frames[0].save(
            args.out / "comparison-front.gif",
            save_all=True,
            append_images=frames[1:],
            duration=round(4000 / report["sample_fps"]),
            loop=0,
        )
    chosen = [
        min(range(len(frames)), key=lambda k: abs(report["time_s"][k] - t))
        for t in (0, 1.15, 1.4, 1.75, 2.5)
    ]
    sheet = Image.new("RGB", (size * 3, (size + 44) * len(chosen)))
    for row, k in enumerate(chosen):
        sheet.paste(frames[k], (0, row * (size + 44)))
    sheet.save(args.out / f"poses-{view}.jpg", quality=92)
    for profile in profiles:
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-loglevel",
                "error",
                "-framerate",
                str(report["sample_fps"]),
                "-i",
                str(args.renders / profile / view / "%04d.png"),
                "-c:v",
                "libx264",
                "-crf",
                "20",
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                str(args.out / f"{profile}-{view}-{fps_tag}.mp4"),
            ],
            check=True,
        )
shutil.copyfile(args.renders / "report.json", args.out / "report.json")
