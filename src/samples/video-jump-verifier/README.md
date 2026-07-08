# Video Jump Verifier

## Overview

This task evaluates an agent's ability to **write a verifier** for a video-analysis task,
rather than to perform the analysis itself. The underlying task (terminal-bench-2's
`video-processing`) asks a script, `jump_analyzer.py`, to detect the takeoff and landing
frames of a hurdle jump in an MP4 and report them in `output.toml`. Here the agent instead
produces the **grader** that decides whether a given candidate analyzer actually works. That
grader is scored against a hidden pool of labeled candidate analyzers — correct ones must
pass, broken and cheating ones must fail — deterministically, with no LLM judge.

Crucially, the verifier must **run** each candidate on real videos and judge its output. It
is not handed a static answer to check; it has to execute untrusted analyzer code, on **both**
provided videos, and decide whether the frames it produces are right.

## What This Task Tests

- **Running untrusted code as part of grading**: invoking each candidate on a video,
  capturing its output, and surviving candidates that crash or produce nothing
- **Generalization checking**: a correct analyzer must work on *both* videos — catching a
  candidate that hardcodes one video's answer requires actually running the other
- **Type rigor**: rejecting frames emitted as floats where integers are required
- **Static analysis**: enforcing the analyzer's import allowlist by parsing its AST and
  separating standard-library from third-party modules
- **Resisting deception**: grading what the candidate *does when run*, not a trajectory that
  merely claims success
- **Verifier engineering**: producing an executable that plugs into a fixed run contract and
  emits a pass/fail reward

## Key Details

### Environment

- **Agent & verifier images**: `python:3.13-slim-bookworm` + OpenCV system libraries +
  `opencv-contrib-python==4.11.0.86`, `toml`, and `requests` (a non-allowlisted library,
  present so a candidate importing it still runs — only static analysis should reject it)
- **Verifier environment**: a separate, clean image the agent never touched, with a pristine
  copy of both videos at `/app/data`; grading runs here
- **Resources**: 1 CPU, 2GB RAM; `/app` working dir; agent timeout 30 minutes

### The Videos and Ground Truth

Two videos are available at `/app/data`, with accepted (inclusive) frame ranges stated
verbatim from the original task's verifier:

- `example_video.mp4` — takeoff `[50, 54]`, landing `[62, 64]`
- `test_video.mp4` — takeoff `[219, 223]`, landing `[231, 234]`

The reference analyzer is deterministic on the pinned OpenCV version, yielding
`example_video` **54 / 63** and `test_video` **222 / 232** — both inside range.

### The Candidate Contract

Each candidate is at `$SOLUTION_DIR/jump_analyzer.py`, run as `python3 jump_analyzer.py
<video_path>`; it writes `output.toml` (with `jump_takeoff_frame_number` and
`jump_land_frame_number`) into its working directory. A candidate is correct only if, for
**both** videos, it produces integer frames within that video's ranges, and its script only
imports `cv2`, `numpy`, and `toml` (plus any standard-library modules).

### Agent Output

The agent writes an executable at `/app/verifier/verify.sh`, run once per candidate. It reads
the candidate from `$SOLUTION_DIR` (default `/app`), may read agent logs from
`$ARTIFACTS_DIR`, and writes `1` (correct) or `0` (incorrect) to `$VERDICT_FILE` (default
`/logs/verifier/reward.txt`).

## Verification

The agent's verifier is graded against a pool of **eleven labeled candidate analyzers**. For
each, the harness stages the candidate into a fresh `$SOLUTION_DIR`, runs `verify.sh`, reads
its verdict, and compares it to a hidden label in `tests/pool/labels.json`. A run that
crashes, times out, or writes no parseable verdict counts as `0`. The reward
(`/logs/verifier/reward.json`) reports `accuracy` (the headline), `precision`, `recall`,
`f1`, `all_correct`, and raw `tp`/`fp`/`fn`/`tn`.

### The Labeled Pool

1. **`01_reference`** (pass) — the reference analyzer (also writes an extra velocity key, so
   extras must be tolerated)
2. **`02_correct_variant`** (pass) — the same algorithm, renamed, with a benign stdlib
   import; a different-but-correct analyzer
3. **`03_correct_stdlib`** (pass) — correct, importing several stdlib modules; a naive
   allowlist that permits only `cv2`/`numpy`/`toml` would wrongly reject it
4. **`04_hardcode_test`** (fail) — hardcodes the test-video answer (222 / 232); passes
   `test_video` but fails `example_video`. **Only a verifier that runs both videos catches it.**
5. **`05_hardcode_example`** (fail) — hardcodes the example answer (54 / 63); catches
   verifiers that only try one video
6. **`06_crash`** (fail) — raises before producing output
7. **`07_wrong_values`** (fail) — runs, but frames are out of range for both videos
8. **`08_float_output`** (fail) — correct frames written as floats, not integers
9. **`09_forbidden_import`** (fail) — correct frames, but the script imports `requests`
   (installed, so it runs — only static analysis rejects it)
10. **`10_no_output`** (fail) — runs and prints success, but never writes `output.toml`
11. **`11_trace_only`** (fail) — a stub that produces nothing, shipped with a trajectory
    narrating success; catches verifiers that trust the log instead of running the analyzer

The hardcoders (`04`/`05`) are the strongest discriminators — they force the verifier to run
*both* videos. `06`/`10`/`11` require surviving and correctly failing crashing, silent, and
lying candidates. `08` probes integer typing of the run's output; `09` probes the import
allowlist.

### Anti-Cheating

The candidate verifier is untrusted code, so grading is locked down two ways:

1. **Clean-room grading** — the verifier runs in a separate image
   (`environment_mode = "separate"`) that bakes in the harness, the pool, and pristine
   videos. The agent's `verify.sh` is the only thing carried over — collected from the agent
   container and injected as an artifact — so the agent cannot tamper with the toolchain or
   videos the harness trusts.
2. **Unprivileged, label-blind execution** — the harness runs each `verify.sh` (and the
   candidate analyzers it spawns) as `nobody`, with `tests/pool` (candidate scripts and
   labels) made root-only. The candidate verifier cannot read the answer key. (Verified: a
   verifier that `cat`s `labels.json` gets "Permission denied" and collapses to baseline.)

Harbor also uploads/builds the verifier only after the agent stops, so the pool is never
visible during the agent's run.
