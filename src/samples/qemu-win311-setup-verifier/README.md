# QEMU Windows 3.11 Setup Verifier

## Overview

This task evaluates an agent's ability to **write a verifier** for a systems-administration
task, rather than to perform the setup itself. The underlying task (adapted from
terminal-bench-2 `install-windows-3.11`) is to run Windows 3.11 for Workgroups in a QEMU VM
with VNC, a web interface, snapshot mode, an authentic base image, and a monitor socket for
programmatic keyboard input.

Because that is a live-runtime task, each candidate "solution" is reframed as a captured
**evidence bundle** of a setup attempt. The agent is given the setup spec and must produce a
grader that decides whether a given bundle reflects a correct setup. That grader is then
scored against a hidden pool of labeled bundles — correct ones must pass, adversarial ones
must fail — deterministically, with no LLM judge.

## What This Task Tests

- **Specification comprehension**: turning a setup spec (ports, snapshot mode, image
  authenticity, keyboard-input interface) into precise programmatic checks
- **Robust parsing**: reading a QEMU command line and a `netstat` table without being fooled
  by substring matches (`:8080` contains `:80`) or address forms (`:::5901`)
- **Tolerating valid variation**: accepting alternate-but-correct forms (`-snapshot` vs
  `snapshot=on`, `qemu-system-i386` vs `-x86_64`, extra args/ports/files)
- **Decomposing outcomes into checks**: a stated outcome often needs two checks (a pristine
  base image needs authenticity *and* snapshot mode; a working key needs a channel *and* a
  screen response)
- **Resisting deception**: grading the captured evidence, not a trajectory that claims success
- **Verifier engineering**: producing an executable that plugs into a fixed run contract and
  emits a pass/fail reward

## Key Details

### Environment

- **Agent base image**: `python:3.11-slim` with `pillow` (11.0.0) and `numpy` (2.1.3)
- **Verifier environment**: a separate, clean image the agent never touched — grading runs here
- **Resources**: 1 CPU, 2GB RAM; agent timeout 30 minutes

### Input

The authentic base disk image stays readable at `/app/reference/win311.img` while the
verifier runs, so the verifier can compare an attempt's base image against it. (It is a small
deterministic stand-in for the licensed Windows 3.11 image.)

### The Evidence Bundle

Each attempt is captured under `$SOLUTION_DIR` (default `/app`):

- `qemu_cmdline.txt` — the QEMU command line (arguments space-separated on one line)
- `listening_ports.txt` — host listeners in `netstat -tlnp` format
- `base_image.img` — the VM's base disk image
- `screenshots/baseline.png`, `screenshots/after_key.png` — VNC snapshots before/after one
  programmatically-sent keystroke

### Agent Output

The agent writes an executable at `/app/verifier/verify.sh`, run once per attempt. It reads
the bundle from `$SOLUTION_DIR`, may read agent logs from `$ARTIFACTS_DIR`, and writes `1`
(correct) or `0` (incorrect) to `$VERDICT_FILE` (default `/logs/verifier/reward.txt`).

### The Setup Being Verified

The instruction states the task **outcomes**, not how to check them — the agent must decide
what evidence proves each one. A correct attempt boots the provided Windows 3.11 image to the
desktop and leaves the VM running so that: VNC is reachable on TCP 5901 and a web interface on
TCP 80; the base disk image is kept pristine (the running VM must not be able to write to it,
so it stays byte-identical to the provided image); and keystrokes can be delivered
programmatically and a key sent that way actually reaches the running VM. Extra ports,
arguments, devices, and files do not make an attempt wrong.

Turning those outcomes into checks is the work: the base image staying pristine implies both
image authenticity (compare to `/app/reference/win311.img`) *and* snapshot mode (so the
running VM can't write to it); "keystrokes reach the VM" implies both a programmatic input
channel (a monitor/QMP socket) *and* a screen that actually responded.

## Verification

The agent's verifier is graded against a pool of **twelve labeled bundles**. For each, the
harness stages it into a fresh `$SOLUTION_DIR`/`$ARTIFACTS_DIR`, runs `verify.sh`, reads the
verdict, and compares it to a hidden label in `tests/pool/labels.json`. A run that crashes,
times out, or writes no parseable verdict counts as `0`. The reward
(`/logs/verifier/reward.json`) reports `reward`/`accuracy` (the headline), `precision`,
`recall`, `f1`, `all_correct`, and raw `tp`/`fp`/`fn`/`tn`.

### The Labeled Pool

Each item targets a specific way a verifier can be wrong:

1. **`01_oracle`** (pass) — the canonical correct bundle
2. **`02_correct_alt`** (pass) — correct in alternate forms (`x86_64`, `std` VGA,
   `snapshot=on`, `-qmp`, IPv6 `:::5901`, reordered listeners); catches rigid string/order matching
3. **`03_correct_superset`** (pass) — correct plus extras (extra port, cmdline devices, extra
   file); catches over-strict verifiers
4. **`04_wrong_vnc_port`** (fail) — VNC on 5900 not 5901
5. **`05_port80_substring_trap`** (fail) — web on 8080 not 80; `:8080` contains the substring
   `:80`, so a naive substring check wrongly passes it
6. **`06_no_snapshot`** (fail) — base image is authentic, but the VM runs without snapshot
   mode, so it can write to (mutate) the base; only a verifier that reasons "pristine ⇒
   snapshot" catches it
7. **`07_wrong_image`** (fail) — `base_image.img` not byte-identical to the reference
8. **`08_no_monitor`** (fail) — no programmatic input channel, even though the screen changed
9. **`09_no_screen_response`** (fail) — an input channel is configured, but the before/after
   screenshots are identical, so the keystroke never reached the VM
10. **`10_logs_no_evidence`** (fail) — no bundle files, only a trajectory narrating success
11. **`11_nop`** (fail) — nothing produced
12. **`12_not_booted_desktop`** (fail) — every other signal is right, but `baseline.png` is a
    blank screen, so the VM never reached the desktop

The subtle discriminators are `05` (parse ports as integers, not substrings), the `06`/`07`
pair (a pristine base needs *both* the authentic image *and* snapshot mode), the `08`/`09`
pair (programmatic keyboard needs *both* a channel *and* a screen that responded), and `12`
(the desktop screenshot must actually show a booted GUI). `10` and `11` form a diagnostic
pair — a verifier that passes `10` but fails `11` is provably trusting the narrative rather
than the evidence.

### Anti-Cheating

1. **Clean-room grading** — the verifier runs in a separate image
   (`environment_mode = "separate"`) that bakes in the harness, the pool, and a pristine copy
   of the reference image. The agent's `verify.sh` is the only thing carried over.
2. **Unprivileged, label-blind execution** — the harness runs each `verify.sh` as `nobody`,
   with `tests/pool` (labels and bundles) made root-only, so the candidate cannot read the
   answer key.

Harbor also uploads/builds the verifier only after the agent stops, so the pool is never
visible during the agent's run.
