# Log Summary Verifier

## Overview

This task evaluates an agent's ability to **write a verifier** for a log-aggregation task, rather than to perform the aggregation itself. The agent is given a spec for a pipeline that counts log severities (ERROR / WARNING / INFO) across five date ranges and writes them to a CSV, and must produce a grader that decides whether a given attempt did it correctly. That grader is then scored against a hidden pool of labeled solutions — correct ones must pass, adversarial ones must fail — deterministically, with no LLM judge.

## What This Task Tests

- **Specification comprehension**: Translating a counting spec (severity definition, inclusive date-range boundaries, output format) into precise programmatic checks
- **Ground-truth derivation**: Computing the correct counts from the raw logs rather than matching a single reference output
- **Resisting a documented trap**: One WARNING message contains the word "ERROR"; a verifier that derives truth by substring instead of the bracketed `[ERROR]` token over-counts and wrongly accepts a solution that made the same mistake
- **Tolerating valid variation**: Accepting different-but-correct representations (row order, extra columns or files)
- **Enforcing the declared format**: Rejecting counts that are the right value but the wrong type (a float `370.0`), or the right data in the wrong container (a pivoted table)
- **Resisting deception**: Grading the files an attempt produced, not a trajectory that merely claims success

## Key Details

### Environment

- **Agent base image**: `python:3.11-slim` (standard library only)
- **Verifier environment**: a separate, clean image the agent never touched — grading runs here
- **Resources**: 1 CPU, 2GB RAM; agent timeout 30 minutes

### Input Data

The agent's verifier reads date-stamped log files, which stay available at `/app/logs` while it runs. Files are named `YYYY-MM-DD_<source>.log` (sources: `db`, `app`, `auth`, `api`), 41 days ending 2025-08-12, generated deterministically. Each line is `<timestamp> [SEVERITY] <message>`; DEBUG lines exist but are never counted.

### The Summary Being Verified

A correct attempt produces `/app/summary.csv`: a standard (RFC 4180) CSV with a header naming its columns (`period`, `severity`, `count`, identified by name in any order), then 15 rows — one per (period, severity) pair — with the counts for each of five inclusive periods relative to 2025-08-12: `today`, `last_7_days` (08-06..08-12), `last_30_days` (07-14..08-12), `month_to_date` (08-01..08-12), and `total`. Severity is the bracketed `[ERROR]`/`[WARNING]`/`[INFO]` token; count is a plain non-negative integer. The 15 rows may be in any order; extra columns or extra files are allowed.

### Agent Output

The agent writes an executable at `/app/verifier/verify.sh`, run once per attempt. It reads the attempt's outputs from `$SOLUTION_DIR` (default `/app`), may read agent logs from `$ARTIFACTS_DIR`, and writes `1` (correct) or `0` (incorrect) to `$VERDICT_FILE` (default `/logs/verifier/reward.txt`).

## Verification

The agent's verifier is graded against a pool of **twelve labeled solutions**. For each one, the harness stages the candidate into a fresh `$SOLUTION_DIR`, runs `verify.sh`, reads its verdict, and compares it to a hidden label in `tests/pool/labels.json`. A run that crashes, times out, or writes no parseable verdict counts as `0`.

The reward is written to `/logs/verifier/reward.json`:

- **`reward`** / **`accuracy`**: fraction of the pool items classified correctly (the headline)
- **`precision`**: `TP/(TP+FP)` — penalizes accepting bad solutions
- **`recall`**: `TP/(TP+FN)` — penalizes rejecting good ones
- **`f1`**, **`all_correct`**, and raw **`tp`**/**`fp`**/**`fn`**/**`tn`** counts

"Positive" means the agent's verifier said PASS.

### The Labeled Pool

Each item targets a specific way a verifier can be wrong:

1. **`01_oracle`** (pass) — the canonical answer
2. **`02_correct_alt`** (pass) — same counts, rows in a different order; catches byte-diff / order-sensitive verifiers
3. **`03_correct_superset`** (pass) — canonical plus an extra trailing column and an extra file; catches over-strict verifiers
4. **`04_wrong_values`** (fail) — wrong counts on `last_30_days` and `month_to_date` (today/total left correct); catches verifiers that only spot-check the easy periods
5. **`05_near_miss`** (fail) — one count off by one (a date-boundary slip); catches imprecise verifiers
6. **`06_error_trap`** (fail) — ERROR counts inflated by the trap WARNING lines (substring `ERROR` vs. the `[ERROR]` token); catches verifiers that derive truth by loose matching
7. **`07_logs_no_files`** (fail) — no `summary.csv`, but a trajectory narrating success; catches trace-gullible verifiers
8. **`08_wrong_shape`** (fail) — right numbers, but a pivoted table (`period,ERROR,WARNING,INFO`) instead of the long format; catches verifiers that skip the output contract
9. **`09_nop`** (fail) — nothing produced
10. **`10_count_as_float`** (fail) — right values, but counts written as floats (`370.0`); catches type-coercing verifiers

`06` is this task's signature discriminator (it maps to the documented ERROR-substring trap). `10` is the type/format discriminator: a verifier that gets everything else right but coerces counts (`int(float(x))`) scores exactly 9/10. `07` and `09` form a diagnostic pair — both have no output file, so a verifier that passes `07` but fails `09` is provably trusting the narrative rather than the filesystem.

### Anti-Cheating

The candidate verifier is untrusted code, so grading is locked down two ways:

1. **Clean-room grading** — the verifier runs in a separate image (`environment_mode = "separate"`) that bakes in the harness, the pool, and a pristine copy of the logs. The agent's `verify.sh` is the only thing carried over — collected from the agent container and injected as an artifact — so the agent cannot tamper with the toolchain or data the harness trusts.
2. **Unprivileged, label-blind execution** — the harness runs each `verify.sh` as `nobody`, with `tests/pool` (labels and solutions) made root-only. The candidate cannot read the answer key.

Harbor also uploads/builds the verifier only after the agent stops, so the pool is never visible during the agent's run.

## Layout

```
log-summary-verifier/
├── instruction.md                  # The prompt the agent sees (spec + verifier contract)
├── task.toml                       # Config + anti-cheat wiring (separate verifier env, artifacts)
├── _build_pool.py                  # Derives ground truth + materializes the labeled pool (task root, not uploaded)
├── environment/
│   ├── Dockerfile                  # Agent image: python:3.11-slim, bakes /app/logs
│   └── log_generator_deterministic.py  # Deterministic log generator (LOG_DIR-parameterized)
├── solution/
│   └── solve.sh                    # Oracle: writes a correct reference verifier
└── tests/
    ├── Dockerfile                  # Clean-room verifier image (pristine logs + baked pool)
    ├── test.sh                     # Entry point → runs harness.py
    ├── harness.py                  # Runs each candidate verifier over the pool as `nobody`, scores it
    ├── log_generator_deterministic.py  # Synced from environment/ by _build_pool.py
    └── pool/                       # The labeled pool (labels.json + one dir per item)
```

## Running

```bash
# Oracle — validates the reference verifier scores the pool 1.0
harbor trials start -p src/samples/log-summary-verifier

# Real agent
harbor run -p src/samples/log-summary-verifier -a terminus-2 -m gemini/gemini-3.5-flash

# Nop baseline — should score 0
harbor run -p src/samples/log-summary-verifier -a nop
```

To rebuild the pool after changing the logs or the spec:

```bash
cd src/samples/log-summary-verifier
uv run -p 3.11 --no-project python _build_pool.py
```
