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

ars <- function(g, D = c(NA, NA), n = 1) {
  .validate_inputs(D, n)
  .check_log_concave(g, D)

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
