#!/usr/bin/env bash

# Set default values if environment variables are not set
SOLUTION_DIR="${SOLUTION_DIR:-/app}"
VERDICT_FILE="${VERDICT_FILE:-/logs/verifier/reward.txt}"

# Create verdict directory if it doesn't exist
mkdir -p "$(dirname "$VERDICT_FILE")"

# Run the R verification script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

Rscript "$SCRIPT_DIR/verify.R" "$SOLUTION_DIR"

if [ $? -eq 0 ]; then
  echo "1" > "$VERDICT_FILE"
  echo "Verification SUCCEEDED. Wrote 1 to $VERDICT_FILE"
  exit 0
else
  echo "0" > "$VERDICT_FILE"
  echo "Verification FAILED. Wrote 0 to $VERDICT_FILE"
  exit 0
fi
