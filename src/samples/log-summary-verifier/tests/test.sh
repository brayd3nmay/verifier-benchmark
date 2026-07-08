#!/bin/bash
# Grade the agent's verifier (/app/verifier/verify.sh) against the labeled pool in
# /tests/pool and write precision/recall/accuracy to /logs/verifier/reward.json.
set -u

mkdir -p /logs/verifier
python3 /tests/harness.py

# Backstop: if the harness somehow produced no reward, record a failing score rather
# than letting Harbor error on a missing reward file.
if [ ! -f /logs/verifier/reward.json ] && [ ! -f /logs/verifier/reward.txt ]; then
  echo 0 > /logs/verifier/reward.txt
fi
