# Multi-Source Data Verifier

## Overview

This task evaluates an agent's ability to **write a verifier** for a data-merge task, rather than to perform the merge itself. The agent is given a description of a pipeline that merges user records from three sources with inconsistent schemas (JSON, CSV, Parquet) and must produce a grader that decides whether a given attempt merged them correctly. That grader is then scored against a hidden pool of labeled solutions — correct ones must pass, adversarial ones must fail — deterministically, with no LLM judge.

## What This Task Tests

- **Specification comprehension**: Translating a merge spec (field mappings, source priority, conflict rules, output formats) into precise programmatic checks
- **Ground-truth derivation**: Computing the correct result from the input files rather than matching a single reference output
- **Tolerating valid variation**: Accepting different-but-correct representations (row/column order, extra columns or files)
- **Catching subtle errors**: Rejecting a single wrong value, a wrong data type, or a wrong file format
- **Resisting deception**: Grading the files an attempt produced, not a trajectory that merely claims success
- **Verifier engineering**: Producing an executable that plugs into a fixed run contract and emits a pass/fail reward

## Key Details

### Environment

- **Agent base image**: `python:3.11-slim` with `pandas` (2.2.3) and `pyarrow` (17.0.0)
- **Verifier environment**: a separate, clean image the agent never touched — grading runs here
- **Resources**: 1 CPU, 2GB RAM
- **Working directory**: `/app`; agent timeout 30 minutes

### Input Data

The agent's verifier reads three source files, which stay available at `/app/data` while it runs:

- `/app/data/source_a/users.json` - Primary source (highest priority)
- `/app/data/source_b/users.csv` - Secondary source
- `/app/data/source_c/users.parquet` - Tertiary source

### Agent Output

The agent writes an executable at `/app/verifier/verify.sh`, run once per attempt. It reads the attempt's outputs from `$SOLUTION_DIR` (default `/app`), may read agent logs from `$ARTIFACTS_DIR`, and writes `1` (correct) or `0` (incorrect) to `$VERDICT_FILE` (default `/logs/verifier/reward.txt`).

### The Merge Being Verified

A correct attempt produces two files:

1. `/app/merged_users.parquet` - one row per unique user, with columns `user_id` (integer), `name`, `email`, `created_date` (string, YYYY-MM-DD), `status` (string, `active`/`inactive`)
2. `/app/conflicts.json` - `{ "total_conflicts": <int>, "conflicts": [...] }`, one entry per field where a user's sources disagree

**Field Mappings**

- `id`, `user_id`, `userId` → `user_id`
- `full_name`, `name`, `userName` → `name`
- `email`, `email_address` → `email`
- `registration_date`, `created_at`, `joined` → `created_date`
- `status`, or the boolean `is_active` / `active` → `active` / `inactive`

**Conflict Resolution**

When the same user appears in multiple sources with different values, use the value from the highest-priority source: `source_a` > `source_b` > `source_c`.

## Verification

The agent's verifier is graded against a pool of **eleven labeled solutions**. For each one, the harness stages the candidate into a fresh `$SOLUTION_DIR`, runs `verify.sh`, reads its verdict, and compares it to a hidden label in `tests/pool/labels.json`. A run that crashes, times out, or writes no parseable verdict counts as `0`.

The reward is written to `/logs/verifier/reward.json`:

- **`reward`** / **`accuracy`**: fraction of the pool items classified correctly (the headline)
- **`precision`**: `TP/(TP+FP)` — penalizes accepting bad solutions (false accepts)
- **`recall`**: `TP/(TP+FN)` — penalizes rejecting good ones
- **`f1`**, **`all_correct`**, and raw **`tp`**/**`fp`**/**`fn`**/**`tn`** counts

"Positive" means the agent's verifier said PASS.

### The Labeled Pool

Each item targets a specific way a verifier can be wrong:

1. **`01_oracle`** (pass) - the canonical answer
2. **`02_correct_alt`** (pass) - same values, rows/columns/conflicts reordered; catches byte-diff and order-sensitive verifiers
3. **`03_correct_superset`** (pass) - canonical plus an extra column, file, and JSON key; catches over-strict verifiers
4. **`04_wrong_values`** (fail) - right shape, but users 102 and 103 have wrong values; catches spot-check-only verifiers
5. **`05_near_miss`** (fail) - one date off by a single day; catches imprecise verifiers
6. **`06_logs_no_files`** (fail) - no outputs, but a trajectory narrating success; catches trace-gullible verifiers
7. **`07_wrong_shape`** (fail) - correct data written as CSV and a bare array; catches verifiers that skip the output contract
8. **`08_nop`** (fail) - nothing produced
9. **`09_wrong_dtype_userid`** (fail) - right values, but `user_id` is a string not an integer; catches verifiers that coerce types instead of enforcing them
10. **`10_wrong_date_format`** (fail) - right dates, but `created_date` is a datetime column not a YYYY-MM-DD string; catches verifiers that reparse dates
11. **`11_status_wrong_type`** (fail) - right status, but as a boolean not the `active`/`inactive` string

`06` and `08` form a diagnostic pair: both have no output files, so a verifier that passes `06` but fails `08` is provably trusting the narrative rather than the filesystem. Items `09`–`11` probe the declared types/formats — a verifier that only checks values (coercing with `astype`/`to_datetime`) accepts them and loses points.

### Anti-Cheating

The candidate verifier is untrusted code, so grading is locked down two ways:

1. **Clean-room grading** - the verifier runs in a separate image (`environment_mode = "separate"`) that bakes in the harness, the pool, and a pristine copy of the data. The agent's `verify.sh` is the only thing carried over — collected from the agent container and injected as an artifact — so the agent cannot tamper with the toolchain or data the harness trusts.
2. **Unprivileged, label-blind execution** - the harness runs each `verify.sh` as `nobody`, with `tests/pool` (labels and solutions) made root-only. The candidate cannot read the answer key.

Harbor also uploads/builds the verifier only after the agent stops, so the pool is never visible during the agent's run.
