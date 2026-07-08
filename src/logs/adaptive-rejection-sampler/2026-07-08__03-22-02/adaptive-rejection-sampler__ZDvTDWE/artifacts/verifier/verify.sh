#!/bin/bash

# Fallback paths
SOLUTION_DIR="${SOLUTION_DIR:-/app}"
VERDICT_FILE="${VERDICT_FILE:-/logs/verifier/reward.txt}"
ARTIFACTS_DIR="${ARTIFACTS_DIR:-/logs/artifacts}"

echo "========================================"
echo "Running ARS Verifier"
echo "SOLUTION_DIR: $SOLUTION_DIR"
echo "VERDICT_FILE: $VERDICT_FILE"
echo "ARTIFACTS_DIR: $ARTIFACTS_DIR"
echo "========================================"

# Default verdict to 0
mkdir -p "$(dirname "$VERDICT_FILE")"
echo "0" > "$VERDICT_FILE"

# Run the R test script
Rscript /app/verifier/test_ars.R "$SOLUTION_DIR"

if [ $? -eq 0 ]; then
  echo "Verification successful. Setting verdict to 1."
  echo "1" > "$VERDICT_FILE"
  exit 0
else
  echo "Verification failed. Setting verdict to 0."
  echo "0" > "$VERDICT_FILE"
  exit 1
fi
