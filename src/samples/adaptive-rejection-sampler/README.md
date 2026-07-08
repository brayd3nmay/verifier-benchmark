# Adaptive Rejection Sampler Verifier

## Overview

This task evaluates an agent's ability to **write a verifier** for a numerical-algorithm task, rather than to implement the algorithm itself. The underlying task (from Terminal-Bench 2) asks for an adaptive rejection sampler (Gilks & Wild 1992) in R: a function `ars(g, D, n)` that draws `n` samples from an arbitrary log-concave density `g`, with input validation, log-concavity checking, a `test` function, and generated sample files. The agent here is given that task's spec and must produce a grader that decides whether a given attempt implemented it correctly. That grader is scored against a hidden pool of labeled submissions — correct ones must pass, adversarial ones must fail — deterministically, with no LLM judge.

Unlike a data task, the graded artifact is **stochastic code**: a correct verifier must *run* each candidate `ars.R` and judge its behavior statistically and behaviorally, not compare it to a fixed reference output.

## What This Task Tests

- **Specification comprehension**: turning "samples an arbitrary log-concave density, validates inputs, rejects non-log-concave densities" into executable checks
- **Behavioral grading of stochastic code**: sampling from the candidate and testing goodness-of-fit (mean, sd, and shape), not just a mean
- **Probing beyond the happy path**: testing a *held-out* density, invalid inputs, and a non-log-concave density — the axes a lazy verifier skips
- **Tolerating valid variation**: accepting any correct implementation regardless of coding style, helper functions, or algorithm (tangent-hull ARS vs. inverse-CDF)
- **Resisting deception**: grading what the code does, not a trajectory that claims success
- **Verifier engineering**: producing an executable that plugs into a fixed run contract and emits a pass/fail reward

## Key Details

### Environment

- **Agent base image**: `rocker/r-ver:4.3.3` with `python3` (+ numpy/scipy)
- **Verifier environment**: a separate, clean image the agent never touched — grading runs here
- **Resources**: 1 CPU, 2 GB RAM; agent timeout 30 minutes
- **Working directory**: `/app`. There is no input data — the "truth" is the analytic behavior of the requested densities.

### Agent Output

The agent writes an executable at `/app/verifier/verify.sh`, run once per attempt. It reads the attempt's files from `$SOLUTION_DIR` (default `/app`), may read agent logs from `$ARTIFACTS_DIR`, and writes `1` (correct) or `0` (incorrect) to `$VERDICT_FILE` (default `/logs/verifier/reward.txt`).

### The Implementation Being Verified

A correct attempt writes `/app/ars.R` defining `ars(g, D, n)` that returns `n` draws from the density proportional to `g` over `D = c(lower, upper)`, for any log-concave `g`. It must:

- produce draws that follow the target distribution's shape (not merely match a mean),
- reject a non-positive `n` and an inverted domain by raising an error,
- reject non-log-concave densities (e.g. a bimodal mixture) by raising an error,
- define a `test` function and write `normal_samples.txt` or `exponential_samples.txt`.

## Verification

The agent's verifier is graded against a pool of **eleven labeled submissions**. For each one, the harness stages the candidate into a fresh `$SOLUTION_DIR`, runs `verify.sh`, reads its verdict, and compares it to a hidden label in `tests/pool/labels.json`. A run that crashes, times out, or writes no parseable verdict counts as `0`.

The reward is written to `/logs/verifier/reward.json`:

- **`reward`** / **`accuracy`**: fraction of the pool classified correctly (the headline)
- **`precision`**: `TP/(TP+FP)` — penalizes accepting bad submissions (false accepts)
- **`recall`**: `TP/(TP+FN)` — penalizes rejecting good ones
- **`f1`**, **`all_correct`**, and raw **`tp`**/**`fp`**/**`fn`**/**`tn`** counts

"Positive" means the agent's verifier said PASS.

### The Labeled Pool

Each item is a candidate `ars.R` (plus a sample file), correct on the axes a lazy verifier checks and wrong on exactly one it usually skips:

1. **`01_oracle`** (pass) — a genuine tangent-hull ARS (the reference implementation)
2. **`02_correct_alt`** (pass) — a correct *inverse-CDF* sampler with none of the ARS-specific helper functions; catches verifiers that grade the algorithm or hardcode function names
3. **`03_correct_superset`** (pass) — correct ARS plus extra helper functions and an extra sample file; catches over-strict verifiers
4. **`04_fake_rnorm`** (fail) — ignores `g` and always returns `rnorm(n)`; perfect on the standard normal, wrong on any other density. Catches verifiers that only ever test `N(0,1)`
5. **`05_wrong_scale`** (fail) — right mean, wrong sd (≈1.35); catches verifiers that check the mean but not the spread
6. **`06_wrong_shape`** (fail) — right mean *and* sd, but uniform instead of normal; catches verifiers with no goodness-of-fit (KS) test
7. **`07_no_validation`** (fail) — samples correctly but silently accepts a negative `n` and an inverted domain; catches verifiers that never feed invalid inputs
8. **`08_no_logconcavity`** (fail) — samples correctly and validates inputs, but never rejects a non-log-concave density; catches verifiers that never test one
9. **`09_logs_no_files`** (fail) — no `ars.R`, only a trajectory narrating success; catches trace-gullible verifiers
10. **`10_nop`** (fail) — nothing produced
11. **`11_deterministic_quantiles`** (fail) — a deterministic quantile table with the *exact* right marginal distribution (mean, sd, and shape) for any density, but not random draws; catches verifiers that check the distribution but never that the sampler is actually stochastic

`09` and `10` form a diagnostic pair: both lack `ars.R`, so a verifier that passes `09` but fails `10` is trusting the narrative. Items `04`, `07`, `08`, and `11` are the key discriminators. `11` is the strongest: a competent verifier naturally tests the *marginal distribution* (mean/sd/goodness-of-fit) but rarely tests that repeated calls differ, so it accepts a perfect-looking deterministic table — the ARS analog of the reference task's type-coercion trap.

### Determinism

The graded code is stochastic, so the pool is built for stable verdicts: every FAIL item is wrong by a large margin (a held-out mean off by 3σ·√n, an sd off by 0.35, a KS statistic of ~0.06 vs. ~0.017 for a correct sampler), and correct items fit with room to spare. The reference verifier additionally seeds R's RNG and uses `n = 5000`, so a given `ars.R` always receives the same verdict.

### Anti-Cheating

The candidate verifier is untrusted code, so grading is locked down two ways:

1. **Clean-room grading** — the verifier runs in a separate image (`environment_mode = "separate"`) that bakes in the harness and the pool. The agent's `verify.sh` is the only thing carried over — collected from the agent container and injected as an artifact — so the agent cannot tamper with the toolchain the harness trusts.
2. **Unprivileged, label-blind execution** — the harness runs each `verify.sh` as `nobody`, with `tests/pool` (labels and submissions) made root-only. The candidate cannot read the answer key.

Harbor also uploads/builds the verifier only after the agent stops, so the pool is never visible during the agent's run.
