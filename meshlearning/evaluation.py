"""Compare externally validated reference angles to Movalytics wide CSVs.

Reference CSV: frame_idx,time_s,joint,column,value_deg.
`column` is the exact Movalytics output column (e.g. hip_r_rot_deg).
No inferred sign conversion, offset fitting, time warping or angle wrapping.
"""

import csv
import json
from pathlib import Path

import numpy as np


def compare_angles(reference, predictions, out, fps, tolerance_s=1e-6):
    if fps <= 0 or tolerance_s < 0:
        raise ValueError("fps must be positive and tolerance nonnegative")
    with Path(reference).open() as reference_file:
        rows = list(csv.DictReader(reference_file))
    if not rows:
        raise ValueError("Reference contains no observations")
    tables = {}
    groups = {}
    seen = set()
    errors = []
    for row in rows:
        joint = row["joint"]
        column = row["column"]
        frame = int(row["frame_idx"])
        key = (joint, column, frame)
        if key in seen:
            raise ValueError(f"Duplicate reference observation: {key}")
        seen.add(key)
        if joint not in tables:
            if Path(joint).name != joint or joint in (".", ".."):
                raise ValueError("Invalid joint filename")
            with (Path(predictions) / f"{joint}.csv").open() as f:
                tables[joint] = list(csv.DictReader(f))
        table = tables[joint]
        if frame < 0 or frame >= len(table):
            raise ValueError(f"Missing prediction frame: {key}")
        pred = table[frame]
        t = float(row["time_s"])
        pt = float(pred["time_s"])
        gt = float(row["value_deg"])
        estimate = float(pred[column])
        if not np.isfinite([t, pt, gt, estimate]).all():
            raise ValueError(f"Nonfinite data: {key}")
        if abs(t - frame / fps) > tolerance_s or abs(t - pt) > tolerance_s:
            raise ValueError(
                f"Timestamp mismatch: {key}; explicit synchronization required"
            )
        lock_columns = [k for k in pred if k.endswith("_lock_flag")]
        locked = any(float(pred[k]) != 0 for k in lock_columns)
        error = estimate - gt
        groups.setdefault((joint, column), []).append((gt, error, locked))
        errors.append(
            {
                "frame_idx": frame,
                "time_s": t,
                "joint": joint,
                "column": column,
                "reference_deg": gt,
                "predicted_deg": estimate,
                "error_deg": error,
                "lock_flag": int(locked),
            }
        )

    def metrics(values):
        v = np.array(values, dtype=float)
        e = v[:, 1]
        return {
            "count": len(e),
            "mae_deg": float(np.abs(e).mean()),
            "rmse_deg": float(np.sqrt((e * e).mean())),
            "bias_deg": float(e.mean()),
            "max_abs_deg": float(np.abs(e).max()),
            "p95_abs_deg": float(np.percentile(np.abs(e), 95)),
            "lock_count": int(v[:, 2].sum()),
        }

    report = {
        "metric": "signed prediction minus reference; degrees; no automatic correction",
        "coverage": "Only explicitly supplied reference observations; no claim of full-body coverage",
        "channels": {},
    }
    for (joint, column), values in groups.items():
        channel = metrics(values)
        channel["absolute_reference_bins"] = {}
        for low, high in [(0, 30), (30, 60), (60, 90), (90, float("inf"))]:
            selected = [v for v in values if low <= abs(v[0]) < high]
            if selected:
                channel["absolute_reference_bins"][f"{low}_to_{high}"] = metrics(
                    selected
                )
        report["channels"][f"{joint}/{column}"] = channel
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    if (out / "report.json").exists() or (out / "errors.csv").exists():
        raise ValueError(
            "Existing comparison files are preserved; choose another output directory"
        )
    (out / "report.json").write_text(json.dumps(report, indent=2))
    with (out / "errors.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(errors[0]))
        w.writeheader()
        w.writerows(errors)
    return report
