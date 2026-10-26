"""Build review artifacts from exact rendered frames and source-time labels.

Install the `review` extra. This script annotates renders without changing poses.
"""

import argparse
import csv
import json
import os
import subprocess
import sys
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/tmp/meshlearning-matplotlib")
os.environ.setdefault("XDG_CACHE_HOME", "/tmp/meshlearning-review-cache")
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from meshlearning.pitch import INDEX

p = argparse.ArgumentParser()
p.add_argument("--motion", type=Path, required=True)
p.add_argument("--renders", type=Path, required=True)
p.add_argument("--out", type=Path, required=True)
a = p.parse_args()
a.out.mkdir(parents=True, exist_ok=True)
metadata = json.loads((a.renders / "render_metadata.json").read_text())
report = json.loads((a.motion / "report.json").read_text())
PHASES = [(phase["time_s"], phase["name"]) for phase in report["phases"]]
data = np.load(a.motion / "motion.npz", allow_pickle=False)
with (a.motion / "angles.csv").open() as f:
    angles = list(csv.DictReader(f))
views = list(metadata["views"])
assert views == ["front", "side", "rear"]
reference_frames = metadata["views"]["front"]["frames"]
for name, view in metadata["views"].items():
    assert [r["source_frame"] for r in view["frames"]] == [
        r["source_frame"] for r in reference_frames
    ]
    assert len(list((a.renders / name).glob("*.png"))) == report["render_frames"]
    assert max(r["max_rig_export_error"] for r in view["frames"]) < 1e-4
size = metadata["views"]["front"]["image_size"][0]
try:
    font = ImageFont.truetype("DejaVuSans.ttf", 16)
    small = ImageFont.truetype("DejaVuSans.ttf", 13)
    title = ImageFont.truetype("DejaVuSans.ttf", 21)
except OSError:
    font = small = title = ImageFont.load_default()


def annotate(image, lines, footer=""):
    canvas = Image.new("RGB", (image.width, image.height + 66), (20, 26, 34))
    canvas.paste(image, (0, 60))
    draw = ImageDraw.Draw(canvas)
    for j, line in enumerate(lines):
        draw.text((10, 6 + 22 * j), line, font=font if j == 0 else small, fill="white")
    if footer:
        draw.text((10, canvas.height - 18), footer, font=small, fill="white")
    return canvas


# Three synchronized views, one shared original-time label, 4x slow playback.
combined = a.renders / "annotated"
combined.mkdir(exist_ok=True)
for k, row in enumerate(reference_frames):
    f = row["source_frame"]
    t = row["source_time_s"]
    joint = angles[f]
    image = Image.new("RGB", (size * 3, size + 112), (20, 26, 34))
    draw = ImageDraw.Draw(image)
    draw.text(
        (12, 8),
        "ONTWORPEN PITCH | 4x vertraagd | geen gemeten referentieworp",
        font=title,
        fill="white",
    )
    draw.text(
        (12, 38),
        f"Bronframe {f:03d} | echte ontwerptijd {t:.3f} s | {row['phase']}",
        font=font,
        fill="white",
    )
    for j, name in enumerate(views):
        frame = Image.open(a.renders / name / f"{k:04d}.png").convert("RGB")
        axes_draw = ImageDraw.Draw(frame)
        camera = metadata["views"][name]
        projection = np.array(camera["projection_matrix"]) @ np.linalg.inv(
            np.array(camera["world_from_camera"])
        )

        def project_axis(point, projection=projection):
            clip = projection @ np.append(point, 1)
            ndc = clip[:2] / clip[3]
            return tuple(((ndc + 1) * [size / 2, -size / 2] + [0, size]).tolist())

        origin = data["joint_positions_world"][f, INDEX["thorax"]] + data[
            "global_rots"
        ][f, INDEX["thorax"]] @ np.array([0, 0, 0.19])
        for axis, color, label in [
            (0, "#ff5555", "X rechts"),
            (1, "#55ef88", "Y voor"),
            (2, "#55aaff", "Z boven"),
        ]:
            start = project_axis(origin)
            end = project_axis(
                origin + 0.21 * data["global_rots"][f, INDEX["thorax"], :, axis]
            )
            axes_draw.line([start, end], fill=color, width=3)
            axes_draw.text(end, label, font=small, fill=color)
        image.paste(frame, (j * size, 92))
        draw.text(
            (j * size + 12, 69),
            {"front": "VOOR", "side": "ZIJ / WERPARM", "rear": "ACHTER / SCHUIN"}[name],
            font=font,
            fill="white",
        )
    draw.text(
        (12, size + 94),
        f"Rechts: elevatie {float(joint['R_elevation_deg']):.1f} | vlak {float(joint['R_plane_deg']):.1f} | axiaal {float(joint['R_axial_deg']):+.1f} graden (technische conventie)",
        font=small,
        fill="white",
    )
    image.save(combined / f"{k:04d}.png")
video = a.out / "pitch-slow-3views.mp4"
subprocess.run(
    [
        "ffmpeg",
        "-v",
        "error",
        "-n",
        "-framerate",
        str(report["playback_fps"]),
        "-i",
        str(combined / "%04d.png"),
        "-c:v",
        "libx264",
        "-crf",
        "22",
        "-pix_fmt",
        "yuv420p",
        str(video),
    ],
    check=True,
)
subprocess.run(
    [
        "ffmpeg",
        "-v",
        "error",
        "-n",
        "-i",
        str(video),
        "-filter_complex",
        "fps=15,scale=900:-2:flags=lanczos,split[x][y];[x]palettegen=max_colors=96[p];[y][p]paletteuse=dither=none",
        str(a.out / "pitch-slow-3views.gif"),
    ],
    check=True,
)
for name in views:
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-n",
            "-framerate",
            str(report["playback_fps"]),
            "-i",
            str(a.renders / name / "%04d.png"),
            "-c:v",
            "libx264",
            "-crf",
            "21",
            "-pix_fmt",
            "yuv420p",
            str(a.out / f"pitch-slow-{name}.mp4"),
        ],
        check=True,
    )
# Rebuild a separate image sequence so visible playback labels remain truthful.
realtime = a.renders / "realtime"
realtime.mkdir(exist_ok=True)
for k in range(len(reference_frames)):
    im = Image.open(combined / f"{k:04d}.png").convert("RGB")
    draw = ImageDraw.Draw(im)
    draw.rectangle((0, 0, im.width, 34), fill=(20, 26, 34))
    draw.text(
        (12, 8),
        "ONTWORPEN PITCH | oorspronkelijke ontwerpsnelheid | 60 fps",
        font=title,
        fill="white",
    )
    im.save(realtime / f"{k:04d}.png")
subprocess.run(
    [
        "ffmpeg",
        "-v",
        "error",
        "-n",
        "-framerate",
        str(int(report["render_source_fps"])),
        "-i",
        str(realtime / "%04d.png"),
        "-c:v",
        "libx264",
        "-crf",
        "22",
        "-pix_fmt",
        "yuv420p",
        str(a.out / "pitch-real-time.mp4"),
    ],
    check=True,
)

# Contact sheet samples actual rendered times, never relabel a nearest frame as exact.
contact = Image.new("RGB", (size * 3, (size + 66) * 3), (20, 26, 34))
for i, (time, label) in enumerate(PHASES):
    k = min(
        range(len(reference_frames)),
        key=lambda f: abs(reference_frames[f]["source_time_s"] - time),
    )
    row = reference_frames[k]
    im = (
        Image.open(combined / f"{k:04d}.png")
        .convert("RGB")
        .crop((size, 92, size * 2, 92 + size))
    )
    card = annotate(
        im,
        [label, f"Bron t={row['source_time_s']:.3f} s / frame {row['source_frame']}"],
    )
    contact.paste(card, ((i % 3) * size, (i // 3) * (size + 66)))
contact.save(a.out / "phase-contact-sheet.png")

# Shoulder rig overlay: a schematic control chain, not anatomical bone outlines.
k = min(
    range(len(reference_frames)),
    key=lambda f: abs(reference_frames[f]["source_time_s"] - PHASES[4][0]),
)
source = reference_frames[k]["source_frame"]
rig_image = Image.new("RGB", (size * 3, size + 100), (20, 26, 34))
draw = ImageDraw.Draw(rig_image)
draw.text(
    (10, 8),
    "Rig-controls bij ontworpen maximale exorotatie (geen bot-anatomie)",
    font=title,
    fill="white",
)
colors = {
    "thorax": "#00d9e8",
    "clavicle_R": "#ffe600",
    "scapula_R": "#cf74ff",
    "deltoid_R": "#7aff86",
    "humerus_R": "#ff4e45",
    "forearm_R": "#ff9e4a",
}
for v, name in enumerate(views):
    im = Image.open(a.renders / name / f"{k:04d}.png").convert("RGB")
    d = ImageDraw.Draw(im)
    cam = metadata["views"][name]
    world = np.array(cam["world_from_camera"])
    proj = np.array(cam["projection_matrix"])

    def project(point, proj=proj, world=world):
        clip = proj @ np.linalg.inv(world) @ np.append(point, 1)
        ndc = clip[:2] / clip[3]
        return tuple(((ndc + 1) * [size / 2, -size / 2] + [0, size]).tolist())

    for segment, color in colors.items():
        j = INDEX[segment]
        start = project(data["joint_positions_world"][source, j])
        end = project(data["endpoints_world"][source, j])
        d.line([start, end], fill=color, width=4)
        d.ellipse((start[0] - 4, start[1] - 4, start[0] + 4, start[1] + 4), fill=color)
    rig_image.paste(im, (v * size, 50))
    draw.text((v * size + 10, 32), name, font=small, fill="white")
x = 10
for segment, color in colors.items():
    text = segment.replace("_R", "")
    draw.text((x, size + 58), text, font=small, fill=color)
    x += int(draw.textlength(text, font=small)) + 25
rig_image.save(a.out / "shoulder-rig-review.png")

# Scientific plots use source time, never slow-playback time.
t = np.array([float(row["time_s"]) for row in angles])
fig, axes = plt.subplots(4, 1, figsize=(10, 9), sharex=True)
for ax, column, label in zip(
    axes,
    ["R_elevation_deg", "R_plane_deg", "R_axial_deg", "R_elbow_control_deg"],
    [
        "Humeruselevatie",
        "Bewegingsvlak",
        "Axiale rotatie (+ intern gericht)",
        "Elleboogflexie-control",
    ],
):
    y = np.array([float(row[column]) for row in angles])
    ax.plot(t, y, color="#be4b24", linewidth=2)
    ax.set_ylabel(label + "\n(graden)", fontsize=9)
    ax.grid(alpha=0.25)
    for time, name in (PHASES[3], PHASES[4], PHASES[5]):
        ax.axvline(time, color="gray", alpha=0.5, linewidth=0.8)
axes[0].set_title(
    "Ontworpen beweging: functionele labels, geen ISB-/Movalytics-hoeken", fontsize=12
)
axes[-1].set_xlabel(
    "Oorspronkelijke ontwerptijd (s); video wordt 4x vertraagd afgespeeld"
)
fig.tight_layout()
fig.savefig(a.out / "angle-curves.png", dpi=150)
plt.close(fig)
# Trunk signals are explicit authored controls, not clinical lumbar angles.
if "thorax_yaw_world_control_deg" in angles[0]:
    fig, axes = plt.subplots(3, 1, figsize=(10, 8), sharex=True)
    for key, label, color in [
        ("pelvis_yaw_world_control_deg", "Bekken yaw", "#555555"),
        ("thorax_yaw_world_control_deg", "Thorax yaw", "#1976b5"),
    ]:
        axes[0].plot(t, [float(row[key]) for row in angles], label=label, color=color)
    axes[0].legend()
    axes[0].set_ylabel("Yaw wereld (graden)")
    axes[1].plot(
        t,
        [float(row["thorax_yaw_relative_pelvis_control_deg"]) for row in angles],
        color="#1976b5",
    )
    axes[1].set_ylabel("Yaw-control verschil\nthorax - bekken (graden)")
    axes[2].plot(
        t,
        [float(row["thorax_extension_control_deg"]) for row in angles],
        label="Extensie + / flexie -",
        color="#be4b24",
    )
    axes[2].axhline(0, color="gray", linewidth=0.7)
    axes[2].legend()
    axes[2].set_ylabel("Romp sagittaal (graden)")
    for ax in axes:
        ax.grid(alpha=0.25)
        for time, _ in (PHASES[3], PHASES[4], PHASES[5]):
            ax.axvline(time, color="gray", alpha=0.5, linewidth=0.8)
    axes[0].set_title(
        "Romp-bekken-coordinatie: ontwerpcontrols, geen klinische wervelkolomhoeken"
    )
    axes[-1].set_xlabel("Oorspronkelijke ontwerptijd (s)")
    fig.tight_layout()
    fig.savefig(a.out / "trunk-curves.png", dpi=150)
    plt.close(fig)

# Copy exact labels, definitions/config and numerical checks for review.
for name in ("angles.csv", "report.json", "design.json"):
    (a.out / name).write_bytes((a.motion / name).read_bytes())
render_checks = {
    "views": views,
    "rendered_frames_per_view": len(reference_frames),
    "max_rig_export_error": max(
        r["max_rig_export_error"]
        for view in metadata["views"].values()
        for r in view["frames"]
    ),
    "mesh_vertices": metadata["mesh_vertices"],
    "skin_weight_sum_max_error": metadata["skin_weight_sum_max_error"],
    "binding_profile": metadata.get("binding_profile", "legacy"),
    "rigid_forearm_vertex_counts": metadata.get("rigid_forearm_vertex_counts", {}),
    "max_surface_ownership_error_m": max(
        (
            value
            for view in metadata["views"].values()
            for row in view["frames"]
            for value in row.get("surface_ownership_error_m", {}).values()
        ),
        default=0,
    ),
    "review_source_frames": [r["source_frame"] for r in reference_frames],
    "review_original_times_s": [r["source_time_s"] for r in reference_frames],
    "all_views_synchronized": True,
}
render_checks["camera_profiles"] = {
    name: "orthographic_review"
    if np.allclose(np.array(view["projection_matrix"])[3], [0, 0, 0, 1])
    else "perspective"
    for name, view in metadata["views"].items()
}
encoded_videos = {}
for filename in (
    "pitch-slow-3views.mp4",
    "pitch-real-time.mp4",
    "pitch-slow-front.mp4",
    "pitch-slow-side.mp4",
    "pitch-slow-rear.mp4",
):
    probe = json.loads(
        subprocess.check_output(
            [
                "ffprobe",
                "-v",
                "error",
                "-count_frames",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width,height,nb_read_frames,r_frame_rate,duration",
                "-of",
                "json",
                str(a.out / filename),
            ]
        )
    )["streams"][0]
    if int(probe["nb_read_frames"]) != len(reference_frames):
        raise RuntimeError(f"Wrong encoded frame count in {filename}")
    wanted_fps = (
        report["render_source_fps"]
        if filename == "pitch-real-time.mp4"
        else report["playback_fps"]
    )
    numerator, denominator = map(float, probe["r_frame_rate"].split("/"))
    if numerator / denominator != wanted_fps:
        raise RuntimeError(f"Wrong playback speed in {filename}")
    encoded_videos[filename] = probe
with Image.open(a.out / "pitch-slow-3views.gif") as gif:
    if gif.n_frames != len(reference_frames):
        raise RuntimeError("GIF frame count mismatch")
    render_checks["gif_frames"] = gif.n_frames
render_checks["encoded_videos"] = encoded_videos
(a.out / "render-checks.json").write_text(json.dumps(render_checks, indent=2) + "\n")
print(json.dumps(render_checks, indent=2))
