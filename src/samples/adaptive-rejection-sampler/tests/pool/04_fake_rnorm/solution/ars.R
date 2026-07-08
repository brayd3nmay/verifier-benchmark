## Adaptive rejection sampler (Gilks & Wild 1992)


.validate_inputs <- function(D, n) {
  if (!is.numeric(n) || length(n) != 1 || is.na(n) || n <= 0 || n != floor(n))
    stop("n must be a positive integer")
  if (!is.numeric(D) || length(D) != 2 || any(is.na(D)) || D[1] >= D[2])
    stop("Invalid domain: D must be c(lower, upper) with lower < upper")
}


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

ars <- function(g, D = c(NA, NA), n = 1) {
  .validate_inputs(D, n)
  .check_log_concave(g, D)
  rnorm(n)
}


test <- function() {
  cat("Running ARS tests against known distributions...\n")
  set.seed(101)
  s <- ars(function(x) dnorm(x), c(-Inf, Inf), n = 2000)
  m <- mean(s); sdv <- sd(s); ok <- abs(m) < 0.2 && abs(sdv - 1) < 0.2
  cat(sprintf("Normal(0,1): %s mean=%.4f sd=%.4f\n", if (ok) "PASS" else "FAIL", m, sdv))
  set.seed(102)
  s2 <- ars(function(x) dexp(x, 1), c(0, Inf), n = 2000)
  m2 <- mean(s2); ok2 <- abs(m2 - 1) < 0.2
  cat(sprintf("Exponential(1): %s mean=%.4f sd=%.4f\n", if (ok2) "PASS" else "FAIL", m2, sd(s2)))
  invisible(ok && ok2)
}
