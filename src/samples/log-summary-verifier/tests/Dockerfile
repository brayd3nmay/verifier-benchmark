# Clean-room verifier image. Built from the tests/ directory as context and used as a
# SEPARATE verifier environment, so the harness never runs in a container the agent
# influenced. The agent's verifier is injected at verify time via artifact collection.
FROM python:3.11-slim

WORKDIR /app
# Pristine logs: the trusted source of truth the harness/reference verifier derives the
# correct counts from, and what the candidate verifier's /app/logs reads resolve to here.
# Generated deterministically from the same script the pool was labeled with, so the
# verifier image's logs cannot drift from the pool's basis. The agent cannot tamper here.
COPY log_generator_deterministic.py /app/
RUN python3 /app/log_generator_deterministic.py && rm -f /app/log_generator_deterministic.py

# Baked in at build — a separate verifier env isn't sent tests at runtime.
COPY . /tests/
RUN chmod +x /tests/test.sh && chmod -R go-rwx /tests/pool
