"""Isolated rotation validation with explicit, versioned engineering definitions.

This package tests algebra, hierarchy, rest poses and labels. It does not assert
that a procedural segment frame is an anatomically landmark-defined ISB frame.
Generation uses Rodrigues; recovery uses signed matrix entries. Neither calls
motion.decompose. Compound rotations are deliberately outside this extractor.
"""

import csv
import hashlib
import json
from pathlib import Path

import numpy as np

from .motion import BONES, NAMES, rotation

DEFINITION_VERSION = "engineering-axes-v2"
ANGLE_SAMPLES = (0.0, 5.0, 30.0, 60.0, 120.0, 0.0, -5.0, -30.0, -60.0, -120.0, 0.0)
AXES = np.eye(3)
PARENTS = {name: parent for name, parent, *_ in BONES}
JOINTS = {
    "pelvis": "pelvis_world",
    "trunk": "trunk",
    "neck": "neck",
    "head": "head_neck",
    **{
        f"{segment}_{side}": f"{joint}_{side}"
        for side in ("L", "R")
        for segment, joint in (
            ("clavicle", "clavicle_thorax"),
            ("upperarm", "shoulder_clavicle_proxy"),
            ("forearm", "elbow_forearm_proxy"),
            ("hand", "wrist"),
            ("thigh", "hip"),
            ("shank", "knee"),
            ("foot", "ankle_foot_proxy"),
        )
    },
}


def definitions():
    """54 engineering channels; positive clinical interpretation is a proposal only."""
    result = []
    for segment in NAMES:
        side = segment.rsplit("_", 1)[-1]
        side = side if side in ("L", "R") else None
        part = segment.rsplit("_", 1)[0] if side else segment
        for axis_index, axis_name in enumerate("xyz"):
            sign = 1
            interpretation = (
                "technical axis only; no anatomical interpretation assigned"
            )
            # Definitions checked geometrically in the neutral schematic body.
            # Internal rotation sign uses a virtual anterior reference, not mesh identity.
            if part in ("thigh", "upperarm"):
                if axis_name == "x":
                    interpretation = "positive flexion candidate"
                elif axis_name == "y":
                    sign = 1 if side == "L" else -1
                    interpretation = "positive abduction candidate"
                else:
                    sign = -1 if side == "L" else 1
                    interpretation = "positive internal rotation candidate"
            elif part == "shank" and axis_name == "x":
                sign = -1
                interpretation = "positive knee flexion candidate"
            elif part == "forearm" and axis_name == "x":
                interpretation = "positive elbow flexion candidate"
            elif part == "foot" and axis_name == "x":
                interpretation = "positive dorsiflexion candidate"
            result.append(
                {
                    "id": f"{segment}.{axis_name}",
                    "joint": JOINTS[segment],
                    "parent_segment": PARENTS[segment],
                    "child_segment": segment,
                    "side": side,
                    "axis_index": axis_index,
                    "positive_axis_parent_rest": (AXES[axis_index] * sign).tolist(),
                    "positive_sign": sign,
                    "interpretation": interpretation,
                    "zero": "procedural neutral pose; straight limbs, arms down, feet anterior",
                    "definition_status": "engineering definition; not validated ISB",
                    "test_angles_deg": list(ANGLE_SAMPLES),
                    "test_range_status": "algebraic stress cases, not physiological ROM limits",
                }
            )
    return result


def validate_rotation(matrix):
    matrix = np.asarray(matrix, dtype=float)
    if (
        matrix.shape != (3, 3)
        or not np.isfinite(matrix).all()
        or not np.allclose(matrix.T @ matrix, np.eye(3), atol=1e-8, rtol=0)
        or not np.isclose(np.linalg.det(matrix), 1, atol=1e-8, rtol=0)
    ):
        raise ValueError("Expected a finite right-handed orthonormal 3x3 rotation")
    return matrix


def rodrigues(axis, angle_deg):
    """Independent fixture construction: axis-angle exponential, not Euler forward."""
    axis = np.asarray(axis, dtype=float)
    if (
        axis.shape != (3,)
        or not np.isfinite(axis).all()
        or not np.isclose(np.linalg.norm(axis), 1)
    ):
        raise ValueError("Unit axis required")
    if not np.isfinite(angle_deg) or abs(angle_deg) >= 180:
        raise ValueError(
            "Isolated test angles must be finite and strictly within +/-180 degrees"
        )
    x, y, z = axis
    skew = np.array([[0, -z, y], [z, 0, -x], [-y, x, 0]])
    a = np.deg2rad(angle_deg)
    return np.eye(3) + np.sin(a) * skew + (1 - np.cos(a)) * (skew @ skew)


def local_motion(parent_world, child_world, rest_local):
    """R_motion = (R_parent.T @ R_child) @ R_rest_local.T.

    Motion acts about parent-rest axes, with R_local = R_motion @ R_rest_local.
    This multiplication order is part of the definition, not a universal ISB rule.
    """
    parent_world = validate_rotation(parent_world)
    child_world = validate_rotation(child_world)
    rest_local = validate_rotation(rest_local)
    return parent_world.T @ child_world @ rest_local.T


def recover_isolated(motion, axis_index, positive_sign=1, isolation_tolerance=1e-7):
    """Recover a principal signed single-axis angle; reject combined/off-axis motion.

    Axis entries provide atan2(sin(theta), cos(theta)); this also works at 90 deg.
    Angles are in (-180, 180); pi and compounds have no unique supported label.
    """
    r = validate_rotation(motion)
    if axis_index not in (0, 1, 2) or positive_sign not in (-1, 1):
        raise ValueError("Invalid axis or sign")
    if not np.isfinite(isolation_tolerance) or isolation_tolerance <= 0:
        raise ValueError("Positive finite isolation tolerance required")
    first, second = ((2, 1), (0, 2), (1, 0))[axis_index]
    sine = (r[first, second] - r[second, first]) / 2
    cosine = (np.trace(r) - 1) / 2
    angle = np.arctan2(sine, cosine)
    if abs(abs(angle) - np.pi) < 1e-7:
        raise ValueError("180 degree sign ambiguity; isolated reference excluded")
    # Build the expected 2x2 plane block without calling the fixture generator.
    expected = np.eye(3)
    expected[first, first] = np.cos(angle)
    expected[second, second] = np.cos(angle)
    expected[first, second] = np.sin(angle)
    expected[second, first] = -np.sin(angle)
    residual = float(np.max(np.abs(r - expected)))
    if residual > isolation_tolerance:
        raise ValueError(
            "Off-axis/combined rotation: isolated-angle extraction is invalid"
        )
    return float(np.rad2deg(angle) * positive_sign), residual


def reconstruct(local_motions, rest_locals=None, world_orientation=None):
    """Full hierarchy FK used for rest/parent invariance fixtures and renderer output."""
    if rest_locals is None:
        rest_locals = np.tile(np.eye(3), (len(NAMES), 1, 1))
    if world_orientation is None:
        world_orientation = np.eye(3)
    positions, globals_, endpoints = [], [], []
    for j, (name, parent, offset, end, _) in enumerate(BONES):
        parent_rot = (
            world_orientation if parent is None else globals_[NAMES.index(parent)]
        )
        parent_pos = np.zeros(3) if parent is None else positions[NAMES.index(parent)]
        pos = parent_pos + parent_rot @ np.array(offset)
        rot = parent_rot @ local_motions[j] @ rest_locals[j]
        positions.append(pos)
        globals_.append(rot)
        endpoints.append(pos + rot @ np.array(end))
    return np.array(positions), np.array(globals_), np.array(endpoints)


def run_checks():
    defs = definitions()
    rows = []
    conditions = [
        ("neutral", np.eye(3), False),
        ("rotated_parent", rotation([23, -17, 38]), False),
        ("nonidentity_rest_and_parent", rotation([-19, 32, 14]), True),
    ]
    for definition in defs:
        target = NAMES.index(definition["child_segment"])
        axis = np.array(definition["positive_axis_parent_rest"])
        for condition, world_rot, use_rest in conditions:
            rest = np.array(
                [
                    rotation([7 + j % 5, -11, 13]) if use_rest else np.eye(3)
                    for j in range(len(NAMES))
                ]
            )
            for expected_deg in ANGLE_SAMPLES:
                motions = np.tile(np.eye(3), (len(NAMES), 1, 1))
                motions[target] = rodrigues(axis, expected_deg)
                _, global_rots, _ = reconstruct(motions, rest, world_rot)
                all_recovered = []
                target_residual = 0.0
                for j, name in enumerate(NAMES):
                    parent = PARENTS[name]
                    parent_rot = (
                        world_rot
                        if parent is None
                        else global_rots[NAMES.index(parent)]
                    )
                    motion = local_motion(parent_rot, global_rots[j], rest[j])
                    if j == target:
                        calculated, target_residual = recover_isolated(
                            motion,
                            definition["axis_index"],
                            definition["positive_sign"],
                        )
                    else:
                        all_recovered.append(float(np.max(np.abs(motion - np.eye(3)))))
                error = calculated - expected_deg
                passive = max(all_recovered, default=0.0)
                rows.append(
                    {
                        "case": definition["id"],
                        "condition": condition,
                        "expected_deg": expected_deg,
                        "calculated_deg": calculated,
                        "error_deg": error,
                        "off_axis_matrix_residual": target_residual,
                        "passive_joint_matrix_residual": passive,
                        "passed": abs(error) < 1e-8
                        and target_residual < 1e-8
                        and passive < 1e-8,
                    }
                )
    return rows


def write_package(out):
    out = Path(out)
    if out.exists() and any(out.iterdir()):
        raise ValueError(
            "Control output directory must be empty; existing results preserved"
        )
    out.mkdir(parents=True, exist_ok=True)
    defs = definitions()
    definition_document = {
        "schema_version": 1,
        "definition_version": DEFINITION_VERSION,
        "world_axes": {"x": "subject right", "y": "anterior", "z": "superior"},
        "handedness": "right-handed",
        "side_convention": "L has negative X; R positive X in the neutral pose",
        "rotation_convention": "active; column vectors; R_local = R_motion @ R_rest_local",
        "rest_correction": "R_motion = (R_parent_world.T @ R_child_world) @ R_rest_local.T",
        "angle_domain": "signed principal angle (-180,180); 180 excluded; single axis only",
        "isb_status": "NOT validated against anatomical landmarks or per-joint ISB recommendations",
        "channels": defs,
    }
    definition_bytes = (json.dumps(definition_document, indent=2) + "\n").encode()
    (out / "definitions.json").write_bytes(definition_bytes)
    rows = run_checks()
    with (out / "angle_checks.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    summary = {
        "definition_version": DEFINITION_VERSION,
        "definition_sha256": hashlib.sha256(definition_bytes).hexdigest(),
        "segments": len(NAMES),
        "channels": len(defs),
        "checks": len(rows),
        "passed": sum(bool(row["passed"]) for row in rows),
        "failed": sum(not row["passed"] for row in rows),
        "max_abs_error_deg": max(abs(row["error_deg"]) for row in rows),
        "max_off_axis_matrix_residual": max(
            row["off_axis_matrix_residual"] for row in rows
        ),
        "max_passive_joint_matrix_residual": max(
            row["passive_joint_matrix_residual"] for row in rows
        ),
        "scope": "algebraic isolated-axis checks; no anatomical accuracy claim",
        "movalytics_status": "not executed; this procedural skeleton is not calibrated SOMA",
        "gemx_status": "not executed; no image estimation measured",
        "tolerances": {"angle_deg": 1e-8, "matrix_absolute": 1e-8},
    }
    (out / "report.json").write_text(json.dumps(summary, indent=2) + "\n")
    lines = [
        "# Controlepakket: geïsoleerde bewegingen",
        "",
        "**Dit rapport toetst rotaties, lokale assen en rustcorrectie; geen anatomische ISB-validatie.**",
        "",
        f"Definities: `{DEFINITION_VERSION}`. Rechtshandig: X rechts, Y voorwaarts, Z omhoog.",
        "Links is negatieve X; rechts positieve X. Hoeken in graden; actieve rotaties met kolomvectoren.",
        "",
        f"- {len(NAMES)} segmenten, {len(defs)} technische assen.",
        f"- {len(rows)} controles: {summary['passed']} geslaagd, {summary['failed']} mislukt.",
        f"- Maximale absolute hoekfout: {summary['max_abs_error_deg']:.3g}°.",
        f"- Maximale afwijking op passieve gewrichten (matrix): {summary['max_passive_joint_matrix_residual']:.3g}.",
        "- Teststanden: 0, ±5, ±30, ±60 en ±120 graden, inclusief herhaalde nulstanden.",
        "- Drie omstandigheden: neutraal, gedraaide ouder/wereld en gedraaide ouder met niet-neutrale rustrotaties.",
        "",
        "## Verwacht versus berekend",
        "",
        "Onderstaande voorbeelden gebruiken een bekende +60°-rotatie met niet-neutrale rustrotaties.",
        "Elke technische as heeft dezelfde volledige reeks; zie de CSV voor alle controles.",
        "",
        "| Segment/as | Positieve interpretatie (voorlopig) | Verwacht | Berekend | Fout |",
        "|---|---|---:|---:|---:|",
    ]
    for definition in defs:
        row = next(
            r
            for r in rows
            if r["case"] == definition["id"]
            and r["condition"] == "nonidentity_rest_and_parent"
            and r["expected_deg"] == 60
        )
        lines.append(
            f"| {definition['id']} | {definition['interpretation']} | 60° | {row['calculated_deg']:.6f}° | {row['error_deg']:.2g}° |"
        )
    lines += [
        "",
        "## Wat dit bewijst",
        "",
        "De fixture gebruikt Rodrigues-rotaties. De terugrekening gebruikt afzonderlijke atan2-matrixformules;",
        "zij roept de Euler-terugrekening van de demonstratie niet aan. Ouderrotaties en ruststanden worden verwijderd.",
        "Bij een actieve beweging blijven de lokale bewegingen van alle andere gewrichten nul.",
        "Afzonderlijke tests controleren bekende rotatiematrices, linker/rechter geometrie, fout teken,",
        "verkeerde rustcorrectie, gecombineerde rotaties, ongeldige matrices en de ambiguïteit bij 180°.",
        "",
        "## Wat nog niet is aangetoond",
        "",
        "De procedurele segmentassen zijn niet uit anatomische landmarks bepaald. De klinische namen zijn",
        "voorlopige geometrische interpretaties. 54 technische assen betekenen niet 54 vrije fysiologische DOF.",
        "±120° is een algebraïsche stresstest; het is geen toegestaan bewegingsbereik voor elk gewricht.",
        "Schouder is een clavicula-bovenarmproxy zonder scapula; enkel en onderarm zijn vereenvoudigd.",
        "Er is geen test van gekoppelde klinische hoeken, huidvervorming, botsingen of beeldschattingsfouten.",
        "GEM-X en Movalytics zijn hier niet uitgevoerd. Dit rapport beoordeelt hun nauwkeurigheid niet.",
        "",
        "## Bestanden",
        "",
        "- [Expliciete definities en tekenafspraken](definitions.json)",
        "- [Alle verwachte en berekende hoeken](angle_checks.csv)",
        "- [Machineleesbaar rapport](report.json)",
        "",
        "## Reproduceren",
        "",
        "```bash",
        "python -m meshlearning.cli controls --out outputs/controls-new",
        "python -m unittest discover -s tests -v",
        "```",
    ]
    (out / "README.md").write_text("\n".join(lines) + "\n")
    if summary["failed"]:
        raise RuntimeError(
            f"{summary['failed']} isolated control checks failed; inspect {out}"
        )
    return summary


def write_motion(out, case="thigh_L.z", frames=48, fps=24):
    """A smooth isolated sequence consumable by the existing Blender renderer."""
    if frames < 8 or fps <= 0:
        raise ValueError("frames >= 8 and fps > 0 required")
    definition = next((d for d in definitions() if d["id"] == case), None)
    if definition is None:
        raise ValueError(f"Unknown control case {case}")
    out = Path(out)
    if out.exists() and any(out.iterdir()):
        raise ValueError("Motion output directory must be empty")
    out.mkdir(parents=True, exist_ok=True)
    j = NAMES.index(definition["child_segment"])
    axis = np.array(definition["positive_axis_parent_rest"])
    # Smooth 0 -> +60 -> 0 -> -60 -> 0; rest of hierarchy stays neutral locally.
    time = np.linspace(0, 1, frames)
    expected = 60 * np.sin(2 * np.pi * time) ** 3
    controls = np.zeros((frames, len(NAMES), 3))
    controls[:, j, definition["axis_index"]] = expected * definition["positive_sign"]
    positions, global_rots, ends, calculated = [], [], [], []
    for angle in expected:
        motions = np.tile(np.eye(3), (len(NAMES), 1, 1))
        motions[j] = rodrigues(axis, angle)
        p, r, e = reconstruct(motions)
        parent = PARENTS[definition["child_segment"]]
        pr = np.eye(3) if parent is None else r[NAMES.index(parent)]
        recovered, _ = recover_isolated(
            local_motion(pr, r[j], np.eye(3)),
            definition["axis_index"],
            definition["positive_sign"],
        )
        positions.append(p)
        global_rots.append(r)
        ends.append(e)
        calculated.append(recovered)
    np.savez_compressed(
        out / "reference.npz",
        frame_idx=np.arange(frames),
        time_s=np.arange(frames) / fps,
        joint_names=np.array(NAMES),
        controls_deg=controls,
        global_rots=np.array(global_rots),
        joint_positions_world=np.array(positions),
        endpoints_world=np.array(ends),
        rest_global_rots=np.tile(np.eye(3), (len(NAMES), 1, 1)),
        expected_deg=expected,
        calculated_deg=np.array(calculated),
        case=np.array(case),
    )
    with (out / "expected_calculated.csv").open("w", newline="") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(
            ["frame_idx", "time_s", "expected_deg", "calculated_deg", "error_deg"]
        )
        for frame, (angle, value) in enumerate(zip(expected, calculated)):
            writer.writerow([frame, frame / fps, angle, value, value - angle])
    (out / "manifest.json").write_text(
        json.dumps(
            {
                "definition_version": DEFINITION_VERSION,
                "case": definition,
                "fps": fps,
                "frames": frames,
                "amplitude_deg": 60,
                "status": "technical isolated motion; not ISB validated",
                "side_convention": "L negative X, R positive X",
            },
            indent=2,
        )
        + "\n"
    )
    return out
