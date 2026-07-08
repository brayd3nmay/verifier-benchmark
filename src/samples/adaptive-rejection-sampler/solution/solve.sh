#!/bin/bash
# Oracle solution: write a correct reference verifier to /app/verifier/verify.sh.
# The harness runs it against the labeled pool; it must classify every item correctly
# (reward 1.0). This is what "a good verifier" looks like for this task: it *runs* the
# candidate ars.R and judges its behavior, rather than eyeballing files or the trajectory.
set -euo pipefail

mkdir -p /app/verifier

cat > /app/verifier/ref_verify.R <<'REOF'
# Reference verifier for the adaptive-rejection-sampler task.
# Sources the candidate's ars.R and exercises it. Deterministic: every stochastic check
# is seeded and uses large n, so a given ars.R always gets the same verdict.
sol <- Sys.getenv("SOLUTION_DIR", "/app")
verdict_file <- Sys.getenv("VERDICT_FILE", "/logs/verifier/reward.txt")

emit <- function(ok, msg = "") {
  d <- dirname(verdict_file); if (nchar(d) > 0) dir.create(d, showWarnings = FALSE, recursive = TRUE)
  writeLines(if (ok) "1" else "0", verdict_file)
  cat(if (ok) "PASS" else "FAIL", "-", msg, "\n")
  quit(save = "no", status = 0)
}

errored <- function(expr) inherits(tryCatch(expr, error = function(e) e), "error")

ars_file <- file.path(sol, "ars.R")
if (!file.exists(ars_file)) emit(FALSE, "no ars.R produced")

env <- new.env()
if (errored(sys.source(ars_file, envir = env))) emit(FALSE, "ars.R failed to source")
if (!is.function(env$ars))  emit(FALSE, "no ars() function")
if (!is.function(env$test)) emit(FALSE, "no test() function")

# Sample a density and check the samples actually follow it: mean, sd, and shape (KS).
check_density <- function(densfun, D, mu, sigma, pdist, seed) {
  set.seed(seed)
  s <- tryCatch(env$ars(densfun, D, n = 5000), error = function(e) NULL)
  if (is.null(s) || length(s) < 4500) return("sampling failed or too few samples")
  if (abs(mean(s) - mu) > 0.12)   return(sprintf("mean %.3f != %.3f", mean(s), mu))
  if (abs(sd(s) - sigma) > 0.15)  return(sprintf("sd %.3f != %.3f", sd(s), sigma))
  Dks <- suppressWarnings(as.numeric(ks.test(s, pdist, mu, sigma)$statistic))
  if (Dks > 0.04) return(sprintf("distribution shape off (KS D=%.3f)", Dks))
  ""
}

# Standard normal (every attempt handles this).
r <- check_density(function(x) dnorm(x), c(-Inf, Inf), 0, 1, "pnorm", 101)
if (nzchar(r)) emit(FALSE, paste("N(0,1):", r))

# Held-out density: catches attempts that ignore g and only ever emit N(0,1).
r <- check_density(function(x) dnorm(x, 3, 0.5), c(-Inf, Inf), 3, 0.5, "pnorm", 202)
if (nzchar(r)) emit(FALSE, paste("N(3,0.5):", r))

# Randomness: independent calls must produce different draws. A deterministic quantile
# table has the right marginal distribution but is not sampling.
set.seed(11); a1 <- tryCatch(env$ars(function(x) dnorm(x), c(-Inf, Inf), n = 2000), error = function(e) NULL)
set.seed(22); a2 <- tryCatch(env$ars(function(x) dnorm(x), c(-Inf, Inf), n = 2000), error = function(e) NULL)
if (is.null(a1) || is.null(a2) || length(a1) != length(a2)) emit(FALSE, "sampling failed on repeat call")
if (max(abs(sort(a1) - sort(a2))) < 1e-8) emit(FALSE, "draws are deterministic (not random sampling)")

# Input validation: must reject a non-positive n and an inverted domain.
if (!errored(env$ars(function(x) dnorm(x), c(-5, 5), n = -10))) emit(FALSE, "accepted negative n")
if (!errored(env$ars(function(x) dnorm(x), c(5, -5), n = 100))) emit(FALSE, "accepted invalid domain")

# Log-concavity: must reject a bimodal (non-log-concave) density.
bimodal <- function(x) 0.5 * dnorm(x, -2, 1) + 0.5 * dnorm(x, 2, 1)
if (!errored(env$ars(bimodal, c(-10, 10), n = 200))) emit(FALSE, "accepted non-log-concave density")

# Required deliverable: a sample file with plausible samples.
sf <- Filter(file.exists, file.path(sol, c("normal_samples.txt", "exponential_samples.txt")))
if (length(sf) == 0) emit(FALSE, "no sample file produced")
vals <- tryCatch(scan(sf[1], quiet = TRUE), error = function(e) numeric(0))
if (length(vals) < 100) emit(FALSE, "sample file has fewer than 100 samples")

emit(TRUE, "all checks passed")
REOF

cat > /app/verifier/verify.sh <<'SHEOF'
#!/bin/bash
Rscript /app/verifier/ref_verify.R
SHEOF

chmod +x /app/verifier/verify.sh
echo "Reference verifier written to /app/verifier/verify.sh"
