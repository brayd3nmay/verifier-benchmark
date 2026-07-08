#!/bin/bash
# Oracle solution: write a correct reference verifier to /app/verifier/verify.sh.
# The harness runs it against the labeled pool; it must classify every item correctly
# (reward 1.0). This is what "a good verifier" looks like for this task.
set -euo pipefail

mkdir -p /app/verifier

# The reference verifier: decide whether a captured evidence bundle reflects a correct
# setup. It checks the outcomes the spec calls for (right image kept pristine, VNC/web on
# the named ports, a programmatic key channel that actually moved the screen), strict on
# each while tolerant of extras and ordering.
cat > /app/verifier/ref_verify.py <<'PYEOF'
import hashlib
import os
import sys

import numpy as np
from PIL import Image

SOL = os.environ.get("SOLUTION_DIR", "/app")
REF = os.environ.get("REFERENCE_DIR", "/app/reference")
VERDICT = os.environ.get("VERDICT_FILE", "/logs/verifier/reward.txt")


def emit(ok, msg=""):
    d = os.path.dirname(VERDICT)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(VERDICT, "w") as f:
        f.write("1" if ok else "0")
    print(("PASS" if ok else "FAIL"), msg)
    sys.exit(0)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def listening_ports(text):
    """The set of TCP ports in LISTEN state, parsed as ints (never substrings)."""
    ports = set()
    for line in text.splitlines():
        if "LISTEN" not in line:
            continue
        cols = line.split()
        if len(cols) < 4:
            continue
        try:
            ports.add(int(cols[3].rsplit(":", 1)[1]))
        except (ValueError, IndexError):
            continue
    return ports


# --- the QEMU command line: a VM, base kept unwritable, a programmatic key channel ---
cmd_path = os.path.join(SOL, "qemu_cmdline.txt")
if not os.path.isfile(cmd_path):
    emit(False, "missing qemu_cmdline.txt")
cmd = open(cmd_path).read()
tok = cmd.split()

if "qemu-system" not in cmd:
    emit(False, "no QEMU VM in the command line")
# snapshot mode is what keeps the running VM from writing to the base image.
if "-snapshot" not in tok and "snapshot=on" not in cmd:
    emit(False, "base image not protected from writes (no snapshot mode)")
# a monitor/QMP unix socket is the channel automation uses to inject keystrokes.
if not (("-monitor" in tok or "-qmp" in tok) and "unix:" in cmd):
    emit(False, "no programmatic keyboard channel (monitor/QMP socket)")

# --- base image is the pristine image I provided ---
att_img = os.path.join(SOL, "base_image.img")
ref_img = os.path.join(REF, "win311.img")
if not os.path.isfile(att_img):
    emit(False, "missing base_image.img")
if sha256(att_img) != sha256(ref_img):
    emit(False, "base_image.img is not the authentic reference image")

# --- VNC and the web interface are reachable on the named ports ---
ports_path = os.path.join(SOL, "listening_ports.txt")
if not os.path.isfile(ports_path):
    emit(False, "missing listening_ports.txt")
ports = listening_ports(open(ports_path).read())
if 5901 not in ports:
    emit(False, "VNC not listening on TCP 5901")
if 80 not in ports:
    emit(False, "web interface not listening on TCP 80")

# --- the programmatically-sent keystroke actually reached the VM (screen changed) ---
base_png = os.path.join(SOL, "screenshots", "baseline.png")
after_png = os.path.join(SOL, "screenshots", "after_key.png")
if not (os.path.isfile(base_png) and os.path.isfile(after_png)):
    emit(False, "missing baseline/after screenshots")
b = np.asarray(Image.open(base_png).convert("L"))
a = np.asarray(Image.open(after_png).convert("L"))
# The desktop screenshot must show a booted GUI, not a blank/uniform screen.
if len(np.unique(b)) < 16:
    emit(False, "baseline is a blank screen (VM never reached the desktop)")
if b.shape == a.shape and np.array_equal(a, b):
    emit(False, "keystroke did not change the screen (never reached the VM)")

emit(True, "all checks passed")
PYEOF

cat > /app/verifier/verify.sh <<'SHEOF'
#!/bin/bash
python3 /app/verifier/ref_verify.py
SHEOF

chmod +x /app/verifier/verify.sh
echo "Reference verifier written to /app/verifier/verify.sh"
