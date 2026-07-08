#!/bin/bash
export SOLUTION_DIR="${SOLUTION_DIR:-/app}"
export VERDICT_FILE="${VERDICT_FILE:-/logs/verifier/reward.txt}"
export ARTIFACTS_DIR="${ARTIFACTS_DIR:-}"
python3 /app/verifier/verify.py
