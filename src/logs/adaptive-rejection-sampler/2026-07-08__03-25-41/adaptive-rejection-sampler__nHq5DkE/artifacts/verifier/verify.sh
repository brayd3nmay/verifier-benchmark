#!/bin/bash

SOLUTION_DIR=${SOLUTION_DIR:-/app}
ARTIFACTS_DIR=${ARTIFACTS_DIR:-/logs/artifacts}
VERDICT_FILE=${VERDICT_FILE:-/logs/verifier/reward.txt}

# Ensure the output directory for the verdict file exists
mkdir -p "$(dirname "$VERDICT_FILE")"

# Run the R verifier script
Rscript /app/verifier/verifier.R "$SOLUTION_DIR" "$VERDICT_FILE"
