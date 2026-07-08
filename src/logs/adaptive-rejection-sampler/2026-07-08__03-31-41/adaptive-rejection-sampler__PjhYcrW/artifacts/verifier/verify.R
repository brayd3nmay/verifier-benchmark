# R verifier for ARS

args <- commandArgs(trailingOnly = TRUE)
solution_dir <- if (length(args) >= 1) args[1] else "/app"

ars_file <- file.path(solution_dir, "ars.R")

if (!file.exists(ars_file)) {
  cat("Error: ars.R not found\n")
  quit(status = 1)
}

# Source the submission
tryCatch({
  source(ars_file)
}, error = function(e) {
  cat("Error sourcing ars.R:", conditionMessage(e), "\n")
  quit(status = 1)
})

# Check if ars function exists
if (!exists("ars") || !is.function(ars)) {
  cat("Error: ars function not found\n")
  quit(status = 1)
}

# Check if test function exists
if (!exists("test") || !is.function(test)) {
  cat("Error: test function not found\n")
  quit(status = 1)
}

# Try running test() to see if it generates any files
tryCatch({
  test()
}, error = function(e) {
  cat("Warning calling test():", conditionMessage(e), "\n")
})

# Check if sample files are written (either normal_samples.txt or exponential_samples.txt)
sample_files <- c("normal_samples.txt", "exponential_samples.txt")
found_sample_file <- FALSE
for (f in sample_files) {
  paths_to_check <- c(
    file.path(solution_dir, f),
    file.path(".", f)
  )
  for (p in paths_to_check) {
    if (file.exists(p)) {
      # Check if it has content
      content <- tryCatch(read.table(p, header=FALSE), error=function(e) NULL)
      if (!is.null(content) && nrow(content) > 0) {
        found_sample_file <- TRUE
        cat("Found valid sample file:", p, "\n")
        break
      }
    }
  }
  if (found_sample_file) break
}

if (!found_sample_file) {
  cat("Error: Neither normal_samples.txt nor exponential_samples.txt was found with valid content\n")
  quit(status = 1)
}

# Define testing helper for stochastic correctness
# We will do a Kolmogorov-Smirnov test
check_distribution <- function(g, D, n_samples = 1000, max_tries = 3) {
  lower <- D[1]
  upper <- D[2]
  
  # Compute theoretical CDF
  # Since integrating might fail or be slow if bounds are extremely large, we assume reasonable finite bounds
  # or use tryCatch
  I <- tryCatch(integrate(g, lower, upper)$value, error = function(e) NULL)
  if (is.null(I) || I <= 0) {
    cat("Internal test error: cannot integrate density\n")
    return(FALSE)
  }
  
  cdf_fn <- function(x) {
    sapply(x, function(val) {
      if (val <= lower) return(0)
      if (val >= upper) return(1)
      val_int <- tryCatch(integrate(g, lower, val)$value, error = function(e) 0)
      val_int / I
    })
  }
  
  for (attempt in 1:max_tries) {
    samples <- tryCatch(ars(g, D, n_samples), error = function(e) NULL)
    if (is.null(samples)) {
      cat("Failed to draw samples (attempt", attempt, ")\n")
      next
    }
    if (length(samples) != n_samples) {
      cat("Incorrect number of samples returned:", length(samples), "instead of", n_samples, "\n")
      next
    }
    if (any(is.na(samples)) || any(is.nan(samples)) || any(is.infinite(samples))) {
      cat("Samples contain NA/NaN/Inf\n")
      next
    }
    if (any(samples < lower) || any(samples > upper)) {
      cat("Samples out of bounds\n")
      next
    }
    
    # Run KS test
    ks_res <- tryCatch(ks.test(samples, cdf_fn), error = function(e) NULL)
    if (is.null(ks_res)) {
      cat("KS test failed to run\n")
      next
    }
    
    cat("Attempt", attempt, "KS test p-value:", ks_res$p.value, "\n")
    if (ks_res$p.value >= 1e-4) {
      return(TRUE)
    }
  }
  return(FALSE)
}

# 1. Test standard normal
cat("Testing standard normal...\n")
if (!check_distribution(dnorm, c(-4, 4))) {
  cat("Error: Failed standard normal test\n")
  quit(status = 1)
}

# 2. Test shifted/scaled normal
cat("Testing shifted/scaled normal...\n")
shifted_normal <- function(x) dnorm(x, mean = 1.5, sd = 0.5)
if (!check_distribution(shifted_normal, c(0, 3))) {
  cat("Error: Failed shifted/scaled normal test\n")
  quit(status = 1)
}

# 3. Test exponential
cat("Testing exponential...\n")
exp_density <- function(x) dexp(x, rate = 2.0)
if (!check_distribution(exp_density, c(0, 5))) {
  cat("Error: Failed exponential test\n")
  quit(status = 1)
}

# 4. Test input validation (should raise error)
cat("Testing input validation...\n")

# Invalid domain bounds
err1 <- tryCatch({
  ars(dnorm, c(4, -4), 100)
  FALSE
}, error = function(e) TRUE)

# Invalid domain bounds (equal)
err2 <- tryCatch({
  ars(dnorm, c(4, 4), 100)
  FALSE
}, error = function(e) TRUE)

# Invalid n
err3 <- tryCatch({
  ars(dnorm, c(-4, 4), 0)
  FALSE
}, error = function(e) TRUE)

# Invalid n (negative)
err4 <- tryCatch({
  ars(dnorm, c(-4, 4), -10)
  FALSE
}, error = function(e) TRUE)

if (!err1 || !err2 || !err3 || !err4) {
  cat("Error: Input validation failed to raise error (err1:", err1, ", err2:", err2, ", err3:", err3, ", err4:", err4, ")\n")
  quit(status = 1)
}

# 5. Test non-log-concave density (should raise error)
cat("Testing non-log-concave density...\n")

# Bimodal mixture
bimodal <- function(x) dnorm(x, mean = -2, sd = 0.5) + dnorm(x, mean = 2, sd = 0.5)
err5 <- tryCatch({
  ars(bimodal, c(-5, 5), 100)
  FALSE
}, error = function(e) TRUE)

# Strictly log-convex density
log_convex <- function(x) exp(x^2)
err6 <- tryCatch({
  ars(log_convex, c(-1, 1), 100)
  FALSE
}, error = function(e) TRUE)

if (!err5 || !err6) {
  cat("Error: Non-log-concave density failed to raise error (err5 bimodal:", err5, ", err6 log_convex:", err6, ")\n")
  quit(status = 1)
}

cat("All tests passed successfully!\n")
quit(status = 0)
