#!/bin/bash
# Oracle solution: write a correct reference verifier to /app/verifier/verify.sh.
# The harness runs it against the labeled pool of candidate analyzers; it must classify
# every candidate correctly (reward 1.0). This is what "a good verifier" looks like for this
# task: it runs each candidate on BOTH videos, tolerates extra output, and is strict about
# the integer type, the accepted ranges, and the import allowlist.
set -euo pipefail

mkdir -p /app/verifier

cat > /app/verifier/ref_verify.py <<'PYEOF'
import ast
import os
import subprocess
import sys
import tempfile
import tomllib

SOL = os.environ.get("SOLUTION_DIR", "/app")
VERDICT = os.environ.get("VERDICT_FILE", "/logs/verifier/reward.txt")
DATA = os.environ.get("DATA_DIR", "/app/data")

# (video, takeoff range, landing range) — a correct analyzer is right on BOTH.
VIDEOS = [
    ("example_video.mp4", (50, 54), (62, 64)),
    ("test_video.mp4", (219, 223), (231, 234)),
]
ALLOWED_THIRD_PARTY = {"cv2", "numpy", "toml"}
RUN_TIMEOUT_SEC = 60


def emit(ok, msg=""):
    d = os.path.dirname(VERDICT)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(VERDICT, "w") as f:
        f.write("1" if ok else "0")
    print(("PASS" if ok else "FAIL"), msg)
    sys.exit(0)


def forbidden_imports(script_path):
    """Top-level modules imported by the script that are third-party and not allowlisted."""
    with open(script_path) as f:
        tree = ast.parse(f.read())
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:  # skip relative imports
                found.add(node.module.split(".")[0])
    third_party = {m for m in found if m and m not in sys.stdlib_module_names}
    return third_party - ALLOWED_THIRD_PARTY


script = os.path.join(SOL, "jump_analyzer.py")
if not os.path.isfile(script):
    emit(False, "no jump_analyzer.py")
script = os.path.abspath(script)

try:
    bad = forbidden_imports(script)
except SyntaxError as e:
    emit(False, f"jump_analyzer.py does not parse: {e}")
if bad:
    emit(False, f"disallowed imports: {sorted(bad)}")

for video, tk_range, ld_range in VIDEOS:
    video_path = os.path.abspath(os.path.join(DATA, video))
    with tempfile.TemporaryDirectory() as work:
        try:
            proc = subprocess.run(
                ["python3", script, video_path],
                cwd=work, capture_output=True, timeout=RUN_TIMEOUT_SEC,
            )
        except subprocess.TimeoutExpired:
            emit(False, f"{video}: timed out")
        if proc.returncode != 0:
            emit(False, f"{video}: exit {proc.returncode}")
        out = os.path.join(work, "output.toml")
        if not os.path.isfile(out):
            emit(False, f"{video}: no output.toml")
        try:
            with open(out, "rb") as f:
                data = tomllib.load(f)
        except Exception as e:
            emit(False, f"{video}: unparseable output.toml: {e}")
        for key, (lo, hi) in (("jump_takeoff_frame_number", tk_range),
                              ("jump_land_frame_number", ld_range)):
            if key not in data:
                emit(False, f"{video}: missing {key}")
            v = data[key]
            if not isinstance(v, int) or isinstance(v, bool):
                emit(False, f"{video}: {key}={v!r} is not an integer")
            if not (lo <= v <= hi):
                emit(False, f"{video}: {key}={v} not in [{lo}, {hi}]")

emit(True, "correct on both videos")
PYEOF

cat > /app/verifier/verify.sh <<'SHEOF'
#!/bin/bash
python3 /app/verifier/ref_verify.py
SHEOF

chmod +x /app/verifier/verify.sh
echo "Reference verifier written to /app/verifier/verify.sh"
