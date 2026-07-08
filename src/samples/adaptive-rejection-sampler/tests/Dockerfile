# Clean-room verifier image. Built from the tests/ directory as context and used as a
# SEPARATE verifier environment, so the harness never runs in a container the agent
# influenced. The agent's verifier is injected at verify time via artifact collection.
# R runs the candidate ars.R files; Python runs the harness (and covers agent verifiers
# that shell out to numpy/scipy).
FROM rocker/r-ver:4.3.3

RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-numpy python3-scipy \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Baked in at build — a separate verifier env isn't sent tests at runtime.
COPY . /tests/
RUN chmod +x /tests/test.sh && chmod -R go-rwx /tests/pool
