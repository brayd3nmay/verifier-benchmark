#!/bin/bash

# Set defaults if not provided
export SOLUTION_DIR="${SOLUTION_DIR:-/app}"
VERDICT_FILE="${VERDICT_FILE:-/logs/verifier/reward.txt}"

# Ensure the target directory for the verdict file exists
mkdir -p "$(dirname "$VERDICT_FILE")"

# Run the python verifier and capture the result
VERDICT=$(python3 /app/verifier/verify.py 2>/dev/null)

# If VERDICT is empty (due to some unexpected error), default to 0
if [ -z "$VERDICT" ]; then
    VERDICT="0"
fi

# Write the verdict to the verdict file
echo -n "$VERDICT" > "$VERDICT_FILE"

echo "Verification completed with verdict: $VERDICT"
