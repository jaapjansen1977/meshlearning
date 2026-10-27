"""Assemble synchronized review, source bundle and explicit model-angle labels."""

import argparse
import csv
import hashlib
import json
import os
import shutil
import subprocess
import zipfile
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/tmp/meshlearning-matplotlib")
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from PIL import Image, ImageDraw, ImageFont

from meshlearning.lifting import VARIANTS

p = argparse.ArgumentParser()
p.add_argument("--data", type=Path, required=True)
p.add_argument("--renders", type=Path, required=True)
p.add_argument("--preview", type=Path, required=True)
p.add_argument("--out", type=Path, required=True)
a = p.parse_args()
a.out.mkdir(parents=True, exist_ok=True)
fontpath = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
font = ImageFont.truetype(fontpath, 18)
small = ImageFont.truetype(fontpath, 14)
variants = list(VARIANTS)
frames = list(range(0, 361, 6))
sequence = a.renders / "comparison"
sequence.mkdir(exist_ok=True)
rows = {}
render_manifest = json.loads((a.renders / "render-manifest.json").read_text())
for name in variants:
    if (
        render_manifest[name]["motion_sha256"]
        != hashlib.sha256((a.data / name / "motion.npz").read_bytes()).hexdigest()
        or render_manifest[name]["source_frames"] != frames
    ):
        raise ValueError("Render/source mismatch")
for name in variants:
    with (a.data / name / "angles.csv").open() as f:
        rows[name] = list(csv.DictReader(f))


def panel(f, view="side", preview=False):
    im = Image.new("RGB", (768, 900), "#20252a")
    d = ImageDraw.Draw(im)
    for i, name in enumerate(variants):
        x = (i % 2) * 384
        y = (i // 2) * 450
        root = a.preview if preview else a.renders
        im.paste(Image.open(root / name / view / f"{f:04d}.png"), (x, y + 46))
        row = rows[name][f]
        d.text((x + 10, y + 5), VARIANTS[name]["label"], font=font, fill="white")
        d.text(
            (x + 10, y + 29),
            f"Heup {float(row['hip_flexion_deg']):.0f} | Rug {float(row['lumbar_flexion_deg']):.0f} | Knie {float(row['knee_flexion_deg']):.0f} graden",
            font=small,
            fill="#ffcf8b",
        )
        d.text(
            (x + 10, y + 429),
            f"t={f / 60:.1f}s | bekken {float(row['pelvis_anterior_tilt_deg']):+.0f} graden",
            font=small,
            fill="white",
        )
    return im


for j, f in enumerate(frames):
    panel(f).save(sequence / f"{j:04d}.png")
command = [
    "ffmpeg",
    "-v",
    "error",
    "-y",
    "-framerate",
    "10",
    "-i",
    str(sequence / "%04d.png"),
    "-c:v",
    "libx264",
    "-crf",
    "20",
    "-pix_fmt",
    "yuv420p",
    "-movflags",
    "+faststart",
    str(a.out / "lifting-comparison.mp4"),
]
subprocess.run(command, check=True)
gif = [
    Image.open(sequence / f"{j:04d}.png")
    .resize((576, 675))
    .convert("P", palette=Image.Palette.ADAPTIVE, colors=96)
    for j in range(len(frames))
]
gif[0].save(
    a.out / "lifting-comparison.gif",
    save_all=True,
    append_images=gif[1:],
    duration=100,
    loop=0,
    optimize=False,
)
for view in ["side", "oblique"]:
    panel(108, view, True).save(a.out / f"bottom-{view}.jpg", quality=90)
for name in variants:
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-framerate",
            "10",
            "-pattern_type",
            "glob",
            "-i",
            str(a.renders / name / "side" / "*.png"),
            "-c:v",
            "libx264",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(a.out / f"{name}.mp4"),
        ],
        check=True,
    )
    shutil.copy(a.data / name / "angles.csv", a.out / f"{name}-angles.csv")
fig, axs = plt.subplots(4, 1, figsize=(10, 10), sharex=True, constrained_layout=True)
for name in variants:
    for ax, key in zip(
        axs,
        [
            "hip_flexion_deg",
            "lumbar_flexion_deg",
            "knee_flexion_deg",
            "pelvis_anterior_tilt_deg",
        ],
    ):
        ax.plot(
            [float(r["time_s"]) for r in rows[name]],
            [float(r[key]) for r in rows[name]],
            label=VARIANTS[name]["label"],
        )
for ax, label in zip(
    axs,
    [
        "Hip flexion",
        "Relative lumbar model flexion",
        "Knee flexion",
        "Pelvis anterior tilt (+)",
    ],
):
    ax.set_ylabel(label + " (deg)")
    ax.grid(alpha=0.2)
axs[0].legend(ncol=4, fontsize=8)
axs[-1].set_xlabel("Original time (s)")
fig.suptitle(
    "Lifting strategies: model geometry, not clinically validated ISB measurements"
)
fig.savefig(a.out / "angles.png", dpi=130)
plt.close(fig)
shutil.copy(a.data / "report.json", a.out / "checks.json")
manifest = {
    "source_fps": 60,
    "render_stride": 6,
    "video_fps": 10,
    "source_frames": frames,
    "duration_source_s": 6.0,
    "video_duration_s": 6.1,
    "motion_sha256": {
        n: hashlib.sha256((a.data / n / "motion.npz").read_bytes()).hexdigest()
        for n in variants
    },
}
(a.out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
with zipfile.ZipFile(
    a.out / "lifting-source-data.zip", "w", compression=zipfile.ZIP_DEFLATED
) as z:
    for path in sorted(a.data.rglob("*")):
        if path.is_file():
            z.write(path, path.relative_to(a.data))
print("Review assembled")
