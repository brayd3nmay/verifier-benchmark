#!/usr/bin/env bash
set -u

SOLUTION_DIR=${SOLUTION_DIR:-/app}
VERDICT_FILE=${VERDICT_FILE:-/logs/verifier/reward.txt}

echo "=== Running Verification ==="
echo "SOLUTION_DIR: $SOLUTION_DIR"
echo "VERDICT_FILE: $VERDICT_FILE"

candidate_file="$SOLUTION_DIR/jump_analyzer.py"
if [ ! -f "$candidate_file" ]; then
    echo "Candidate file $candidate_file not found."
    verdict="0"
else
    # Run python check
    output=$(python3 /app/verifier/check_candidate.py "$candidate_file")
    echo "$output"
    if echo "$output" | grep -q "VERDICT: 1"; then
        verdict="1"
    else
        verdict="0"
    fi
fi

echo "Final Verdict: $verdict"
mkdir -p "$(dirname "$VERDICT_FILE")"
echo "$verdict" > "$VERDICT_FILE"
echo "=== Verification Completed ==="
