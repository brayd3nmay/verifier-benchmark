# ARS verification script
args <- commandArgs(trailingOnly = TRUE)
solution_dir <- if (length(args) > 0) args[1] else "/app"

# Helper function to print message and exit with failure
fail <- function(msg) {
  cat("FAILURE:", msg, "\n")
  quit(status = 1)
}

# Helper to print success
success <- function(msg) {
  cat("SUCCESS:", msg, "\n")
}

# 1. Check if ars.R exists
ars_file <- file.path(solution_dir, "ars.R")
if (!file.exists(ars_file)) {
  fail(paste("ars.R not found in", solution_dir))
}

# 2. Source the file
tryCatch({
  source(ars_file)
}, error = function(e) {
  fail(paste("Failed to source ars.R:", e$message))
})

# 3. Check if ars function is defined
if (!exists("ars", mode = "function")) {
  fail("Function 'ars' is not defined or is not a function")
}

# 4. Check if test function is defined
if (!exists("test", mode = "function")) {
  fail("Function 'test' is not defined or is not a function")
}

# 5. Check if normal_samples.txt or exponential_samples.txt exists
# The prompt says "It also defines a test function and writes normal_samples.txt or exponential_samples.txt"
# Let's verify that at least one of these is written or exists in solution_dir.
normal_file <- file.path(solution_dir, "normal_samples.txt")
exp_file <- file.path(solution_dir, "exponential_samples.txt")
if (!file.exists(normal_file) && !file.exists(exp_file)) {
  # Maybe running the test() function generates them?
  cat("Sample files not found, trying to run test() to generate them...\n")
  tryCatch({
    test()
  }, error = function(e) {
    cat("Warning: running test() failed:", e$message, "\n")
  })
  if (!file.exists(normal_file) && !file.exists(exp_file)) {
    fail("Neither normal_samples.txt nor exponential_samples.txt was found, and running test() did not produce them.")
  }
}
success("Basic file and definition checks passed")

# 6. Check invalid inputs (non-positive n, non-increasing domain, non-log-concave density)
# a. Non-positive n
err_n1 <- tryCatch({ ars(dnorm, c(-5, 5), 0); FALSE }, error = function(e) TRUE)
err_n2 <- tryCatch({ ars(dnorm, c(-5, 5), -5); FALSE }, error = function(e) TRUE)
if (!err_n1 || !err_n2) {
  fail("ars did not raise an error for non-positive n")
}
success("Invalid n validation passed")

# b. Non-increasing domain
err_D1 <- tryCatch({ ars(dnorm, c(5, 2), 10); FALSE }, error = function(e) TRUE)
err_D2 <- tryCatch({ ars(dnorm, c(3, 3), 10); FALSE }, error = function(e) TRUE)
if (!err_D1 || !err_D2) {
  fail("ars did not raise an error for non-increasing domain bounds")
}
success("Invalid domain validation passed")

# c. Non-log-concave density
# A simple bimodal normal mixture is not log-concave
bimodal_g <- function(x) { dnorm(x, -2, 0.5) + dnorm(x, 2, 0.5) }
err_lc1 <- tryCatch({ ars(bimodal_g, c(-5, 5), 10); FALSE }, error = function(e) TRUE)

# A log-convex function like exp(x^2) is not log-concave
logconvex_g <- function(x) { exp(x^2) }
err_lc2 <- tryCatch({ ars(logconvex_g, c(-1, 1), 10); FALSE }, error = function(e) TRUE)

# Let's verify that they raise an error
# Note: some samplers might not check log-concavity at the very start but during initialization/sampling.
# If they do check log-concavity, they must fail.
if (!err_lc1 && !err_lc2) {
  fail("ars did not raise an error for non-log-concave density")
}
success("Non-log-concave density validation passed")

# 7. Check sampling correctness
# Function to generate CDF via numerical integration
get_cdf <- function(g, D) {
  total_integral <- tryCatch({
    integrate(g, D[1], D[2])$value
  }, error = function(e) {
    # Fallback to finite approximations if infinite integration fails for custom functions
    low <- if (D[1] == -Inf) -10 else D[1]
    high <- if (D[2] == Inf) 10 else D[2]
    integrate(g, low, high)$value
  })
  
  CDF <- function(x) {
    sapply(x, function(val) {
      if (val <= D[1]) return(0)
      if (val >= D[2]) return(1)
      val_integral <- tryCatch({
        integrate(g, D[1], val)$value
      }, error = function(e) {
        low <- if (D[1] == -Inf) -10 else D[1]
        if (val <= low) return(0)
        integrate(g, low, val)$value
      })
      val_integral / total_integral
    })
  }
  return(CDF)
}

# Function to run multiple trials of sampling and do KS test
# Returns TRUE if at least 1 out of 3 trials has KS p-value > 0.01
verify_distribution <- function(g, D, n = 500, label = "") {
  cat("Verifying distribution:", label, "...\n")
  
  # Compute theoretical CDF
  cdf_fn <- get_cdf(g, D)
  
  success_trials <- 0
  for (trial in 1:3) {
    # Generate samples using the student's ars
    samples <- tryCatch({
      ars(g, D, n)
    }, error = function(e) {
      cat("  Trial", trial, "failed to run:", e$message, "\n")
      return(NULL)
    })
    
    if (is.null(samples)) next
    if (length(samples) != n) {
      cat("  Trial", trial, "returned incorrect number of samples:", length(samples), "(expected", n, ")\n")
      next
    }
    if (!is.numeric(samples) || any(is.na(samples))) {
      cat("  Trial", trial, "returned non-numeric or NA samples\n")
      next
    }
    
    # Run Kolmogorov-Smirnov test
    ks_res <- tryCatch({
      ks.test(samples, cdf_fn)
    }, error = function(e) {
      cat("  Trial", trial, "KS test error:", e$message, "\n")
      return(NULL)
    })
    
    if (is.null(ks_res)) next
    
    p_val <- ks_res$p.value
    cat("  Trial", trial, "KS p-value:", p_val, "\n")
    if (p_val > 0.01) {
      success_trials <- success_trials + 1
    }
  }
  
  if (success_trials >= 1) {
    success(paste("Distribution", label, "passed"))
    return(TRUE)
  } else {
    cat("  All trials failed for", label, "\n")
    return(FALSE)
  }
}

# Run distribution verifications
# Test A: Standard Normal on (-Inf, Inf)
ok_normal <- verify_distribution(dnorm, c(-Inf, Inf), n = 500, label = "Standard Normal (Infinite Domain)")
if (!ok_normal) {
  # Maybe they only support finite domains? Let's check with standard normal on (-4, 4)
  ok_normal_finite <- verify_distribution(dnorm, c(-4, 4), n = 500, label = "Standard Normal (Finite Domain [-4, 4])")
  if (!ok_normal_finite) {
    fail("Normal distribution sampling verification failed on both infinite and finite domains")
  }
}

# Test B: Exponential on (0, Inf)
ok_exp <- verify_distribution(dexp, c(0, Inf), n = 500, label = "Exponential (Infinite Domain)")
if (!ok_exp) {
  ok_exp_finite <- verify_distribution(dexp, c(0, 10), n = 500, label = "Exponential (Finite Domain [0, 10])")
  if (!ok_exp_finite) {
    fail("Exponential distribution sampling verification failed on both infinite and finite domains")
  }
}

# Test C: A custom log-concave function g(x) = exp(-x^4) on c(-1.5, 1.5)
# This tests if it really works for ANY log-concave density and not just built-in ones
custom_g <- function(x) { exp(-x^4) }
ok_custom <- verify_distribution(custom_g, c(-1.5, 1.5), n = 500, label = "Custom log-concave exp(-x^4)")
if (!ok_custom) {
  fail("Custom log-concave density sampling verification failed")
}

cat("ALL TESTS PASSED SUCCESSFULLY!\n")
quit(status = 0)
