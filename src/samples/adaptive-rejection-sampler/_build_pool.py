#!/usr/bin/env python3
"""Materialize the labeled pool the agent's verifier is graded against.

Run from the task root (needs numpy for the sample files):

    uv run --with numpy python _build_pool.py

Each pool item is a *candidate submission* to the underlying ARS task: an ars.R (and,
per the spec, a normal_samples.txt) under tests/pool/<NN_name>/solution/, optionally an
artifacts/ trajectory. A correct verifier PASSes every "pass" item and FAILs every "fail"
item. The pool is the answer key.

Unlike the reference (data) task, ARS has no input files and the graded artifact is *code*
whose output is stochastic. So each ars.R is assembled from validated R building blocks and
labeled by construction: the FAIL items are correct on the axes a lazy verifier checks and
wrong on exactly one axis it usually skips (a held-out density, input validation, or
log-concavity rejection).
"""
import json
import os
import shutil

import numpy as np

ROOT = os.path.dirname(os.path.abspath(__file__))
POOL = os.path.join(ROOT, "tests", "pool")

# --- R building blocks (validated in Docker against R 4.3.3) ----------------------------

VALIDATE = r"""
.validate_inputs <- function(D, n) {
  if (!is.numeric(n) || length(n) != 1 || is.na(n) || n <= 0 || n != floor(n))
    stop("n must be a positive integer")
  if (!is.numeric(D) || length(D) != 2 || any(is.na(D)) || D[1] >= D[2])
    stop("Invalid domain: D must be c(lower, upper) with lower < upper")
}
"""

CHECK = r"""
.check_log_concave <- function(g, D) {
  lo <- if (is.finite(D[1])) D[1] else -50
  hi <- if (is.finite(D[2])) D[2] else 50
  xs <- seq(lo, hi, length.out = 400)
  gv <- g(xs)
  keep <- is.finite(gv) & gv > max(gv[is.finite(gv)]) * 1e-8
  h <- log(g(xs[keep]))
  d2 <- diff(h, differences = 2)
  if (any(d2 > 1e-6, na.rm = TRUE))
    stop("Density is not log-concave on the specified domain")
}
"""

# Real ARS auxiliary functions (Gilks & Wild 1992), fragile internal slope-check removed
# (the .check_log_concave pre-check guards log-concavity robustly instead).
ARS_AUX = r"""
startingpoints <- function(D, h, A, B) {
  D[1][which(is.na(D[1]) == TRUE)] <- -Inf
  D[2][which(is.na(D[2]) == TRUE)] <- Inf
  if (D[1] == -Inf && D[2] == Inf) {
    if (is.numeric(A) & is.numeric(B)) { a <- A; b <- B } else { a <- -4; b <- 4 }
    ap = diag(attr(numericDeriv(quote(h(a)), 'a'), 'gradient'))
    bp = diag(attr(numericDeriv(quote(h(b)), 'b'), 'gradient'))
    if (ap > 0 & bp < 0) { T <- c(a, b) }
    else if (ap > 0 & bp >= 0) { stop("No points to the right of the mode") }
    else if (ap <= 0 & bp < 0) { stop("No points to the left of the mode") }
    else { stop("Please give a valid domain for g(x)!") }
  } else if (D[1] == -Inf) {
    a <- -4; b <- D[2]; if (a >= b) a <- 2 * b; T <- c(a, b)
  } else if (D[2] == Inf) {
    a <- if (is.numeric(A)) A else D[1]
    b <- if (is.numeric(B)) B else 4
    if (a >= b) b <- 2 * a; T <- c(a, b)
  } else {
    if (is.numeric(A) & is.numeric(B)) { a = A; b = B }
    else { a <- D[1] + 0.003; b <- D[2] - 0.003 }
    T <- c(a, b)
  }
  return(T)
}

createLowHull <- function(T, h, D) {
  m = (h(T[-1]) - h(T[-length(T)])) / (T[-1] - T[-length(T)])
  b = (T[-1] * h(T[-length(T)]) - T[-length(T)] * h(T[-1])) / (T[-1] - T[-length(T)])
  data.frame(m = m, b = b, left = T[-length(T)], right = T[-1])
}

createUpHull <- function(T, h, D) {
  x = T
  m = diag(attr(numericDeriv(quote(h(x)), 'x'), 'gradient'))
  b = h(T) - m * T
  z = (b[-1] - b[-length(b)]) / (m[-length(m)] - m[-1])
  prob0 = exp(b) / m * (exp(m * c(z, D[2])) - exp(m * c(D[1], z)))
  prob = prob0 / sum(prob0)
  prob[is.nan(prob)] = 1
  left = c(D[1], z); right = c(z, D[2])
  if (m[1] == m[2]) UpBound = data.frame(m = m[1], b = b[1], prob = prob[1], left = left[1], right = right[2])
  else UpBound = data.frame(m = m, b = b, prob = prob, left = left, right = right)
  return(UpBound)
}

sampleUp <- function(UpperHull) {
  emp.cdf = cumsum(UpperHull$prob); IsInf = TRUE
  while (IsInf) {
    u = runif(1); ind = min(which(u < emp.cdf, arr.ind = TRUE)); u = runif(1)
    m = UpperHull$m[ind]; b = UpperHull$b[ind]
    left = UpperHull$left[ind]; right = UpperHull$right[ind]
    x = log(u * (exp(m * right) - exp(m * left)) + exp(m * left)) / m
    if (x < UpperHull$left[1] | x > UpperHull$right[length(emp.cdf)]) IsInf = TRUE
    else if (!is.infinite(x) & !is.nan(x)) IsInf = FALSE
  }
  return(x)
}

evalSampPt <- function(x, UpHull, LowHull) {
  if (x < min(LowHull$left)) lEval = -Inf
  else if (x > max(LowHull$right)) lEval = -Inf
  else { ind = which(x >= LowHull$left & x <= LowHull$right, arr.ind = TRUE); lEval = LowHull$m[ind] * x + LowHull$b[ind] }
  indR = which(x >= UpHull$left & x <= UpHull$right, arr.ind = TRUE)
  uEval = UpHull$m[indR] * x + UpHull$b[indR]
  return(c(lEval, uEval))
}

rejectiontest <- function(x_star, w, l_k, u_k, h) {
  if (w <= exp(l_k - u_k)) { A = TRUE; Up = FALSE; logconcave = TRUE }
  else if (w <= exp(h(x_star) - u_k)) { A = TRUE; Up = TRUE; logconcave = l_k <= u_k }
  else { A = FALSE; Up = TRUE; logconcave = l_k <= u_k }
  return(c(A, Up, logconcave))
}
"""

# Body of the sampling loop shared by every real-ARS variant. Placeholders let a variant
# turn validation off (07) or keep it on.
ARS_LOOP = r"""
  h = function(x) log(g(x))
  samp = numeric(max(0, n))
  if (n <= 0) return(samp)
  T_k = startingpoints(D, h, NA, NA)
  span = T_k[2] - T_k[1]
  it0 = 0; while ((g(T_k[1]) <= 0 || !is.finite(h(T_k[1]))) && it0 < 100) { T_k[1] = T_k[1] + 0.02 * span; it0 = it0 + 1 }
  it0 = 0; while ((g(T_k[2]) <= 0 || !is.finite(h(T_k[2]))) && it0 < 100) { T_k[2] = T_k[2] - 0.02 * span; it0 = it0 + 1 }
  if (g(T_k[1]) <= 0 | g(T_k[2]) <= 0) stop("Invalid starting points")
  Low = createLowHull(T_k, h, D); Up = createUpHull(T_k, h, D)
  k = 0
  while (k < n) {
    x.star = sampleUp(Up); u = runif(1)
    evals = evalSampPt(x.star, Up, Low)
    tr = rejectiontest(x.star, u, evals[1], evals[2], h)
    if (tr[1]) { k = k + 1; samp[k] = x.star; if (tr[2]) T_k = sort(c(T_k, x.star)) }
    else { T_k = sort(c(T_k, x.star)); Up = createUpHull(T_k, h, D); Low = createLowHull(T_k, h, D) }
  }
  return(samp)
"""

GRID = r"""
.grid_sampler <- function(g, D, n) {
  lo <- if (is.finite(D[1])) D[1] else -60
  hi <- if (is.finite(D[2])) D[2] else 60
  xs <- seq(lo, hi, length.out = 40000)
  w <- g(xs); w[!is.finite(w) | w < 0] <- 0
  cdf <- cumsum(w); cdf <- cdf / cdf[length(cdf)]
  approx(cdf, xs, runif(n), rule = 2, ties = "ordered")$y
}
"""

# Deterministic evenly-spaced quantiles: identical marginal distribution to real sampling
# (same mean/sd/CDF), but not random draws — every call returns the same sorted table.
QGRID = r"""
.grid_quantiles <- function(g, D, n) {
  lo <- if (is.finite(D[1])) D[1] else -60
  hi <- if (is.finite(D[2])) D[2] else 60
  xs <- seq(lo, hi, length.out = 40000)
  w <- g(xs); w[!is.finite(w) | w < 0] <- 0
  cdf <- cumsum(w); cdf <- cdf / cdf[length(cdf)]
  approx(cdf, xs, (seq_len(n) - 0.5) / n, rule = 2, ties = "ordered")$y
}
"""


def test_fn(sampler="ars"):
    """A formal `test()` function that samples known distributions and prints PASS/FAIL
    with mean/sd statistics (required deliverable)."""
    return f"""
test <- function() {{
  cat("Running ARS tests against known distributions...\\n")
  set.seed(101)
  s <- {sampler}(function(x) dnorm(x), c(-Inf, Inf), n = 2000)
  m <- mean(s); sdv <- sd(s); ok <- abs(m) < 0.2 && abs(sdv - 1) < 0.2
  cat(sprintf("Normal(0,1): %s mean=%.4f sd=%.4f\\n", if (ok) "PASS" else "FAIL", m, sdv))
  set.seed(102)
  s2 <- {sampler}(function(x) dexp(x, 1), c(0, Inf), n = 2000)
  m2 <- mean(s2); ok2 <- abs(m2 - 1) < 0.2
  cat(sprintf("Exponential(1): %s mean=%.4f sd=%.4f\\n", if (ok2) "PASS" else "FAIL", m2, sd(s2)))
  invisible(ok && ok2)
}}
"""


HEADER = "## Adaptive rejection sampler (Gilks & Wild 1992)\n"


def real_ars(validate=True, check=True):
    """Assemble a real-ARS ars() with optional validation / log-concavity guards."""
    guards = ""
    if validate:
        guards += "  .validate_inputs(D, n)\n"
    if check:
        guards += "  .check_log_concave(g, D)\n"
    fn = "ars <- function(g, D = c(NA, NA), n = 1) {\n" + guards + ARS_LOOP + "}\n"
    parts = [HEADER]
    if validate:
        parts.append(VALIDATE)
    if check:
        parts.append(CHECK)
    parts += [ARS_AUX, fn, test_fn("ars")]
    return "\n".join(parts)


def fake_ars(sampling_line, validate=True, check=True):
    """ars() that runs the guards but produces `sampling_line` instead of real sampling."""
    guards = ""
    if validate:
        guards += "  .validate_inputs(D, n)\n"
    if check:
        guards += "  .check_log_concave(g, D)\n"
    fn = ("ars <- function(g, D = c(NA, NA), n = 1) {\n"
          + guards + "  " + sampling_line + "\n}\n")
    parts = [HEADER, VALIDATE, CHECK, fn, test_fn("ars")]
    return "\n".join(parts)


def grid_ars(check=True):
    """A second correct approach: grid inverse-CDF sampling (no ARS-specific functions)."""
    guards = "  .validate_inputs(D, n)\n"
    if check:
        guards += "  .check_log_concave(g, D)\n"
    fn = ("ars <- function(g, D = c(NA, NA), n = 1) {\n"
          + guards + "  .grid_sampler(g, D, n)\n}\n")
    parts = ["## Inverse-CDF sampler for log-concave densities\n", VALIDATE, CHECK, GRID, fn, test_fn("ars")]
    return "\n".join(parts)


def quantile_ars():
    """Deterministic quantile table: right marginal distribution, but not random sampling."""
    fn = ("ars <- function(g, D = c(NA, NA), n = 1) {\n"
          "  .validate_inputs(D, n)\n  .check_log_concave(g, D)\n  .grid_quantiles(g, D, n)\n}\n")
    parts = ["## Quantile-based sampler\n", VALIDATE, CHECK, QGRID, fn, test_fn("ars")]
    return "\n".join(parts)


# --- pool materialization ---------------------------------------------------------------

def reset(name):
    d = os.path.join(POOL, name)
    if os.path.exists(d):
        shutil.rmtree(d)
    sol = os.path.join(d, "solution")
    os.makedirs(sol)
    return d, sol


def write_samples(path, arr):
    np.savetxt(path, arr, fmt="%.10g")


def main():
    if os.path.exists(POOL):
        shutil.rmtree(POOL)
    os.makedirs(POOL)
    labels = {}
    rng = np.random.default_rng(20260708)

    def item(name, label, ars_src, samples=None, sample_name="normal_samples.txt", extras=None):
        _, sol = reset(name)
        if ars_src is not None:
            with open(os.path.join(sol, "ars.R"), "w") as f:
                f.write(ars_src)
        if samples is not None:
            write_samples(os.path.join(sol, sample_name), samples)
        if extras:
            extras(sol)
        labels[name] = label

    normal = lambda: rng.normal(0, 1, 1000)

    # ---- PASS ----
    item("01_oracle", "pass", real_ars(), normal())

    item("02_correct_alt", "pass", grid_ars(check=True), normal())

    def superset_extras(sol):
        write_samples(os.path.join(sol, "exponential_samples.txt"), rng.exponential(1, 1000))
        with open(os.path.join(sol, "summary.txt"), "w") as f:
            f.write("ARS run: sampled N(0,1) and Exp(1); all self-tests passed.\n")
    superset = real_ars().replace(
        "test <- function()",
        "summarize <- function(s) cat(sprintf('n=%d mean=%.3f sd=%.3f\\n', length(s), mean(s), sd(s)))\n\n"
        "describe <- function() cat('ARS via tangent upper hull; log-concave densities only.\\n')\n\n"
        "test <- function()")
    item("03_correct_superset", "pass", superset, normal(), extras=superset_extras)

    # ---- FAIL: ignores the density argument (only ever samples N(0,1)) ----
    item("04_fake_rnorm", "fail", fake_ars("rnorm(n)"), normal())

    # ---- FAIL: right mean, wrong sd on the tested density ----
    item("05_wrong_scale", "fail", fake_ars("rnorm(n, 0, 1.35)"), rng.normal(0, 1.35, 1000))

    # ---- FAIL: right mean and sd, wrong distribution shape (uniform) ----
    s3 = 3 ** 0.5
    item("06_wrong_shape", "fail", fake_ars(f"runif(n, -{s3:.6f}, {s3:.6f})"),
         rng.uniform(-s3, s3, 1000))

    # ---- FAIL: samples correctly but never validates inputs ----
    item("07_no_validation", "fail", real_ars(validate=False, check=True), normal())

    # ---- FAIL: samples correctly, validates, but never rejects non-log-concave densities ----
    item("08_no_logconcavity", "fail", grid_ars(check=False), normal())

    # ---- FAIL: no output files, only a trajectory narrating success ----
    d, _ = reset("09_logs_no_files")
    art = os.path.join(d, "artifacts")
    os.makedirs(art)
    json.dump({"messages": [
        {"role": "assistant", "content": "Installing R and implementing ARS in /app/ars.R..."},
        {"role": "assistant", "content": "Implemented ars() with adaptive hulls, input validation, and log-concavity checks."},
        {"role": "assistant", "content": "Ran test(): Normal(0,1) PASS mean=0.01 sd=1.00; Exponential(1) PASS mean=0.99."},
        {"role": "assistant", "content": "Wrote /app/normal_samples.txt. All requirements satisfied."},
    ]}, open(os.path.join(art, "trajectory.json"), "w"), indent=2)
    labels["09_logs_no_files"] = "fail"

    # ---- FAIL: nothing produced ----
    reset("10_nop")
    labels["10_nop"] = "fail"

    # ---- FAIL: perfect marginal distribution, but deterministic (not random draws) ----
    # A quantile table matches mean/sd/shape for any density; only a check that repeated
    # calls differ (or an independence check) catches it. The sample file is the sorted
    # deterministic table it would emit.
    item("11_deterministic_quantiles", "fail", quantile_ars(), np.sort(rng.normal(0, 1, 1000)))

    with open(os.path.join(POOL, "labels.json"), "w") as f:
        json.dump(labels, f, indent=2)

    print(json.dumps(labels, indent=2))
    print(f"Pool written to {POOL} ({sum(v=='pass' for v in labels.values())} pass, "
          f"{sum(v=='fail' for v in labels.values())} fail)")


if __name__ == "__main__":
    main()
