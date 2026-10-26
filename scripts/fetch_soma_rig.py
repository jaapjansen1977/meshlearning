"""Fetch only the pinned official rig, preserving TLS and LFS SHA256 verification."""

import argparse
import hashlib
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from meshlearning.soma_bridge import RIG_BYTES, RIG_SHA256, SOMA_COMMIT, sha256_file

p = argparse.ArgumentParser()
p.add_argument("--out", type=Path, required=True)
a = p.parse_args()
if a.out.exists():
    if a.out.stat().st_size != RIG_BYTES or sha256_file(a.out) != RIG_SHA256:
        raise ValueError("Existing file differs from pinned rig; preserved unchanged")
    print("Reusing verified pinned SOMA rig:", a.out)
    raise SystemExit(0)
a.out.parent.mkdir(parents=True, exist_ok=True)
partial = a.out.with_name(a.out.name + ".partial")
if partial.exists():
    raise ValueError("Existing partial download preserved; choose another output path")
url = f"https://media.githubusercontent.com/media/NVlabs/SOMA-X/{SOMA_COMMIT}/assets/SOMA_template_rig.usda"
digest = hashlib.sha256()
size = 0
with urllib.request.urlopen(url, timeout=60) as response, partial.open("xb") as output:
    while block := response.read(1024 * 1024):
        output.write(block)
        digest.update(block)
        size += len(block)
if size != RIG_BYTES or digest.hexdigest() != RIG_SHA256:
    raise RuntimeError(
        "Rig size/SHA256 mismatch; unverified partial file will not be used"
    )
partial.rename(a.out)
print("Downloaded and verified", size, "bytes:", RIG_SHA256)
