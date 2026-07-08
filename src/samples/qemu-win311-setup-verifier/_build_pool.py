#!/usr/bin/env python3
"""Materialize the labeled pool the agent's verifier is graded against.

Run from the task root (needs pillow + numpy):

    uv run --with pillow --with numpy python _build_pool.py

Each pool item is a captured runtime-evidence bundle for a QEMU Windows 3.11 setup
attempt: tests/pool/<NN_name>/solution/{qemu_cmdline.txt, listening_ports.txt,
base_image.img, screenshots/*.png} and optional artifacts/. A correct verifier PASSes
every "pass" item and FAILs every "fail" item. All fixtures are generated deterministically
here so the labels can't drift, and the reference image is synced into tests/reference so
the grade-time pristine copy matches the pool's basis.
"""
import json
import shutil
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent
ENV_REF = ROOT / "environment" / "reference"
POOL = ROOT / "tests" / "pool"

IMG_N = 131072  # bytes in the stand-in base image
H, W = 240, 320  # screenshot dimensions
PIXELS = H * W


def reference_image_bytes():
    a = np.arange(IMG_N, dtype=np.int64) * 1103515245 + 12345
    return ((a >> 8) & 0xFF).astype(np.uint8).tobytes()


REF_BYTES = reference_image_bytes()
BASELINE = ((np.arange(PIXELS) * 7 + 13) % 256).astype(np.uint8).reshape(H, W)


def after_with_changed(k):
    """The baseline with exactly k pixels flipped (always a real change)."""
    flat = BASELINE.reshape(-1).astype(np.int64).copy()
    flat[:k] = (flat[:k] + 128) % 256
    return flat.astype(np.uint8).reshape(H, W)


AFTER_OK = after_with_changed(int(0.15 * PIXELS))   # keystroke visibly changed the screen
AFTER_FROZEN = BASELINE.copy()                       # screen unchanged -> key never reached the VM
BLANK = np.zeros((H, W), dtype=np.uint8)             # uniform screen -> VM never reached the desktop


def wrong_image_bytes():
    ba = bytearray(REF_BYTES)
    ba[0] ^= 0xFF
    ba[IMG_N // 2] ^= 0xFF
    return bytes(ba)


CMDLINE_OK = ("qemu-system-i386 -m 32 -hda base.img -snapshot -vga cirrus -vnc :1 "
              "-monitor unix:/tmp/qemu-monitor.sock,server,nowait")
# Correct, but every discriminating token in an alternate valid form: x86_64, std VGA,
# snapshot=on inside -drive, and -qmp instead of -monitor.
CMDLINE_ALT = ("qemu-system-x86_64 -vga std -m 64 -vnc :1 "
               "-drive file=base.img,snapshot=on -qmp unix:/tmp/qmp.sock,server,nowait")
CMDLINE_SUPERSET = CMDLINE_OK + " -device usb-tablet -netdev user,id=n0 -device e1000,netdev=n0"
CMDLINE_NO_SNAP = ("qemu-system-i386 -m 32 -hda base.img -vga cirrus -vnc :1 "
                   "-monitor unix:/tmp/qemu-monitor.sock,server,nowait")
CMDLINE_NO_MON = "qemu-system-i386 -m 32 -hda base.img -snapshot -vga cirrus -vnc :1"

_HDR = ("Active Internet connections (only servers)\n"
        "Proto Recv-Q Send-Q Local Address           Foreign Address         State       PID/Program name\n")


def netstat(*rows):
    return _HDR + "\n".join(rows) + "\n"


R_VNC = "tcp        0      0 0.0.0.0:5901            0.0.0.0:*               LISTEN      42/qemu-system-i38"
R_HTTP = "tcp        0      0 0.0.0.0:80              0.0.0.0:*               LISTEN      55/nginx: master"
R_SSH = "tcp        0      0 0.0.0.0:22              0.0.0.0:*               LISTEN      30/sshd"

NETSTAT_OK = netstat(R_VNC, R_HTTP)
# Correct, but reordered and using IPv6 any-interface local addresses.
NETSTAT_ALT = netstat(
    "tcp6       0      0 :::80                   :::*                    LISTEN      55/nginx",
    "tcp6       0      0 :::5901                 :::*                    LISTEN      42/qemu",
)
NETSTAT_SUPERSET = netstat(R_VNC, R_HTTP, R_SSH)
NETSTAT_VNC_5900 = netstat(
    "tcp        0      0 0.0.0.0:5900            0.0.0.0:*               LISTEN      42/qemu", R_HTTP)
# nginx on 8080, NOT 80. ':8080' contains the substring ':80' — the trap.
NETSTAT_HTTP_8080 = netstat(
    R_VNC, "tcp        0      0 0.0.0.0:8080            0.0.0.0:*               LISTEN      55/nginx")

labels = {}


def reset(name):
    d = POOL / name
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    return d


def save_png(arr, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(arr, "L").save(path)


def bundle(name, label, *, cmdline=CMDLINE_OK, ports=NETSTAT_OK,
           image=REF_BYTES, baseline=BASELINE, after=AFTER_OK, extras=None):
    sol = reset(name) / "solution"
    sol.mkdir()
    (sol / "qemu_cmdline.txt").write_text(cmdline + "\n")
    (sol / "listening_ports.txt").write_text(ports)
    (sol / "base_image.img").write_bytes(image)
    save_png(baseline, sol / "screenshots" / "baseline.png")
    save_png(after, sol / "screenshots" / "after_key.png")
    for rel, content in (extras or {}).items():
        (sol / rel).write_text(content)
    labels[name] = label


def main():
    ENV_REF.mkdir(parents=True, exist_ok=True)
    (ENV_REF / "win311.img").write_bytes(REF_BYTES)

    # Guard the fixtures that define the pass/fail boundary.
    assert (BASELINE != AFTER_OK).any()
    assert not (BASELINE != AFTER_FROZEN).any()
    assert len(np.unique(BASELINE)) > 16 and len(np.unique(BLANK)) == 1

    bundle("01_oracle", "pass")
    bundle("02_correct_alt", "pass", cmdline=CMDLINE_ALT, ports=NETSTAT_ALT)
    bundle("03_correct_superset", "pass", cmdline=CMDLINE_SUPERSET, ports=NETSTAT_SUPERSET,
           extras={"notes.txt": "Booted to desktop; VNC on :1; nginx up.\n"})

    bundle("04_wrong_vnc_port", "fail", ports=NETSTAT_VNC_5900)
    bundle("05_port80_substring_trap", "fail", ports=NETSTAT_HTTP_8080)
    bundle("06_no_snapshot", "fail", cmdline=CMDLINE_NO_SNAP)
    bundle("07_wrong_image", "fail", image=wrong_image_bytes())
    bundle("08_no_monitor", "fail", cmdline=CMDLINE_NO_MON)
    bundle("09_no_screen_response", "fail", after=AFTER_FROZEN)
    bundle("12_not_booted_desktop", "fail", baseline=BLANK)

    # No output files, but a trajectory narrating success; catches trace-gullible verifiers.
    art = reset("10_logs_no_evidence") / "artifacts"
    art.mkdir()
    json.dump({"messages": [
        {"role": "assistant", "content": "Building QEMU 5.2.0 and booting win311.img..."},
        {"role": "assistant", "content": "VM at the Windows 3.11 desktop. VNC on :1 (5901); nginx on 80."},
        {"role": "assistant", "content": "Monitor socket at /tmp/qemu-monitor.sock; sent F1, screen updated."},
        {"role": "assistant", "content": "Done. Everything is configured and running; tests should pass."},
    ]}, open(art / "trajectory.json", "w"), indent=2)
    labels["10_logs_no_evidence"] = "fail"

    reset("11_nop")
    labels["11_nop"] = "fail"

    assert len(labels) == 12 and sum(v == "pass" for v in labels.values()) == 3, labels

    json.dump(labels, open(POOL / "labels.json", "w"), indent=2)

    # Keep the verifier image's pristine reference identical to the pool's basis.
    tests_ref = ROOT / "tests" / "reference"
    if tests_ref.exists():
        shutil.rmtree(tests_ref)
    shutil.copytree(ENV_REF, tests_ref)

    print(json.dumps(labels, indent=2))
    print(f"Pool written to {POOL}; reference image synced to {tests_ref}")


if __name__ == "__main__":
    main()
