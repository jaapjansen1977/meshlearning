"""Read-only audit of a user-selected Movalytics checkout; no source/code copying.

Saves the interface contract and calibration hash. Does not invent registration
matrices or run a calibration on an incompatible procedural skeleton.
"""

import argparse
import ast
import hashlib
import json
import subprocess
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument("--movalytics", type=Path, required=True)
p.add_argument("--out", type=Path, required=True)
a = p.parse_args()
root = a.movalytics
source = root / "src/movalytics/kinematics/extract.py"
runner = root / "tools/run_gemx/run_gemx.py"
calibration = root / "calibrations/soma_gemx_v14.json"
commit = subprocess.check_output(
    ["git", "-C", str(root), "rev-parse", "HEAD"], text=True
).strip()
pairs = None
for node in ast.parse(source.read_text()).body:
    if (
        isinstance(node, ast.AnnAssign)
        and isinstance(node.target, ast.Name)
        and node.target.id == "_JOINT_PAIRS"
    ):
        pairs = ast.literal_eval(node.value)
if pairs is None:
    raise RuntimeError("Cannot establish Movalytics segment pairs")
expected = [("shoulder_R", "Chest", "RightArm"), ("shoulder_L", "Chest", "LeftArm")]
if not all(pair in pairs for pair in expected):
    raise RuntimeError("Shoulder segment contract changed")
config = json.loads(calibration.read_text())
for joint, _, _ in expected:
    if config["joints"][joint]["decomposition"] != "swing_twist":
        raise RuntimeError("Calibration method changed")
runner_tree = ast.parse(runner.read_text())
# Check the exact runner statement uses an identity rest array, not just a comment.
identity_rest = False
for node in ast.walk(runner_tree):
    if isinstance(node, ast.Assign) and any(
        isinstance(t, ast.Name) and t.id == "rest_global_rots" for t in node.targets
    ):
        expression = ast.unparse(node.value)
        identity_rest = identity_rest or (
            "np.eye(3" in expression and "broadcast_to" in expression
        )
if not identity_rest:
    raise RuntimeError("Identity-rest runner contract changed; inspect before mapping")
contract = {
    "status": "model landmark-frame algebra checked; actual SOMA registrations still missing",
    "model_axes": ["X subject right", "Y anterior", "Z superior"],
    "landmark_proxy_axes": ["X anterior", "Y superior", "Z subject right"],
    "model_from_landmark_proxy_basis": [[0, 0, 1], [1, 0, 0], [0, 1, 0]],
    "landmark_status": "Virtual design landmarks, not measured/palpated anatomical landmarks",
    "landmark_proxy_sequence": "Intrinsic Y-X-Y; branch beta negative on R, positive on L; undefined plane/axial at elevation 0/180",
    "movalytics": {
        "repository": "Babon-Innovations-b-v/movalytics",
        "commit": commit,
        "calibration": "soma_gemx_v14",
        "calibration_sha256": hashlib.sha256(calibration.read_bytes()).hexdigest(),
        "shoulder_pairs": [list(pair) for pair in expected],
        "decomposition": "swing_twist plus per-DOF signs, weights and offsets; not direct YXY Euler output",
        "runner_rest_policy": "Identity matrices; bind orientation absorbed in fitted axes per runner documentation",
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "runner_sha256": hashlib.sha256(runner.read_bytes()).hexdigest(),
    },
    "registrations": {"B_Chest": None, "B_RightArm": None, "B_LeftArm": None},
    "registration_meaning": "Columns of B_s express the SOMA segment axes in our model segment frame; determine from matched anatomical/static reference poses, verify on multiple non-collinear motions",
    "mapping": "R_SOMA_s = G @ R_model_s @ B_s; R_SOMA_local = B_Chest.T @ R_model_HT @ B_Arm",
    "rest_correction": "Movalytics R_motion = R_SOMA_local @ inverse(R_rest_local). For soma_gemx_v14 runner uses identity rest; do not substitute our A-pose rest matrices.",
    "forbidden_shortcuts": [
        "Do not rename humerus_R to RightArm and assume frames match",
        "Do not use the model/ISB axis permutation as a guessed SOMA registration",
        "Do not apply soma_gemx_v14 directly to unregistered procedural rotations",
        "Do not describe functional or proxy YXY angles as already validated clinical Movalytics angles",
    ],
    "missing_for_actual_application": [
        "Verified thorax-to-Chest and humerus-to-Arm frame registrations for the pinned SOMA version",
        "Clinical review of virtual landmark placement, epicondylar axis and left/right conventions",
        "Independent validation of combined shoulder motions and extreme positions",
    ],
    "checks": {
        "shoulder_pairs_match": True,
        "swing_twist_calibration_identified": True,
        "identity_rest_runner_identified": True,
        "unknown_registrations_left_explicitly_null": True,
    },
}
a.out.parent.mkdir(parents=True, exist_ok=True)
if a.out.exists():
    raise ValueError("Existing frame contract preserved; choose a new path")
a.out.write_text(json.dumps(contract, indent=2) + "\n")
print(json.dumps(contract["checks"], indent=2))
