args <- commandArgs(trailingOnly = TRUE)
solution_dir <- args[1]
verdict_file <- args[2]

write_verdict <- function(val) {
  writeLines(as.character(val), verdict_file)
  quit(save = "no", status = 0)
}

# 1. Check if ars.R exists
ars_path <- file.path(solution_dir, "ars.R")
if (!file.exists(ars_path)) {
  write_verdict(0)
}

# 2. Source the file
s_res <- tryCatch({
  source(ars_path)
  TRUE
}, error = function(e) {
  FALSE
})

if (!s_res) {
  write_verdict(0)
}

# 3. Check if ars is a function
if (!exists("ars") || !is.function(ars)) {
  write_verdict(0)
}

# 4. Check test function and sample files
test_func_exists <- exists("test") && is.function(test)
samples_exist_before <- file.exists(file.path(solution_dir, "normal_samples.txt")) || 
                        file.exists(file.path(solution_dir, "exponential_samples.txt"))

if (test_func_exists && !samples_exist_before) {
  tryCatch({
    old_wd <- getwd()
    setwd(solution_dir)
    test()
    setwd(old_wd)
  }, error = function(e) {})
}

samples_exist_after <- file.exists(file.path(solution_dir, "normal_samples.txt")) || 
                       file.exists(file.path(solution_dir, "exponential_samples.txt"))

if (!test_func_exists || !(samples_exist_before || samples_exist_after)) {
  write_verdict(0)
}

# 5. Helper for valid log-concave cases
run_test_case <- function(g, D, n, name) {
  res <- tryCatch({
    # We use integrate to find the normalizer
    C <- integrate(g, D[1], D[2])$value
    cdf <- function(x) {
      sapply(x, function(val) {
        if (val <= D[1]) return(0)
        if (val >= D[2]) return(1)
        integrate(g, D[1], val)$value / C
      })
    }
    
    passed <- FALSE
    for (attempt in 1:2) {
      samples <- ars(g, D, n)
      if (length(samples) != n) next
      if (any(samples < D[1] | samples > D[2])) next
      if (any(is.na(samples) | is.nan(samples))) next
      
      # KS test
      ks_res <- ks.test(samples, cdf)
      if (ks_res$p.value >= 0.001) {
        passed <- TRUE
        break
      }
    }
    passed
  }, error = function(e) {
    FALSE
  })
  return(res) 
}

# 6. Helper for checking that invalid inputs throw error
run_invalid_test <- function(expr) {
  tryCatch({
    eval(expr)
    FALSE # Should have thrown error
  }, error = function(e) {
    TRUE # Successfully threw error
  })
}

# 7. Run validations
# a) Invalid n
if (!run_invalid_test(quote(ars(dnorm, c(-3, 3), 0)))) write_verdict(0)
if (!run_invalid_test(quote(ars(dnorm, c(-3, 3), -5)))) write_verdict(0)

# b) Non-increasing domain
if (!run_invalid_test(quote(ars(dnorm, c(3, -3), 10)))) write_verdict(0)
if (!run_invalid_test(quote(ars(dnorm, c(1, 1), 10)))) write_verdict(0)

# c) Non-log-concave density
# Convex density: g(x) = exp(x^2)
if (!run_invalid_test(quote(ars(function(x) exp(x^2), c(-2, 2), 100)))) write_verdict(0)
# Bimodal mixture
bimodal_g <- function(x) { dnorm(x, -2, 0.5) + dnorm(x, 2, 0.5) }
if (!run_invalid_test(quote(ars(bimodal_g, c(-5, 5), 100)))) write_verdict(0)

# 8. Run log-concave test cases
# Case 1: Standard Normal
if (!run_test_case(dnorm, c(-4, 4), 500, "StdNormal")) write_verdict(0)

# Case 2: Exponential
if (!run_test_case(function(x) dexp(x, rate=1.5), c(0, 8), 500, "Exponential")) write_verdict(0)

# Case 3: Shifted/scaled Normal
shifted_norm <- function(x) dnorm(x, mean=1.5, sd=0.6)
if (!run_test_case(shifted_norm, c(-1, 4), 500, "ShiftedNormal")) write_verdict(0)

# Case 4: Custom log-concave (sin)
if (!run_test_case(sin, c(0.1, 3.0), 500, "Sin")) write_verdict(0)

# All tests passed!
write_verdict(1)
