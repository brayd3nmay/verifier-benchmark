#!/bin/bash

# Set defaults if not provided
export SOLUTION_DIR="${SOLUTION_DIR:-/app}"
export VERDICT_FILE="${VERDICT_FILE:-/logs/verifier/reward.txt}"

# Remove any old verdict file to avoid stale results
rm -f "$VERDICT_FILE"

# Run python verifier
python3 /app/verifier/verify.py

# Fallback if python script crashed or did not produce the verdict file
if [ ! -f "$VERDICT_FILE" ]; then
    mkdir -p "$(dirname "$VERDICT_FILE")"
    echo "0" > "$VERDICT_FILE"
fi
