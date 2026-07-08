# Clean-room verifier image. Built from the tests/ directory as context and used as a
# SEPARATE verifier environment, so the harness never runs in a container the agent
# influenced. The agent's verifier is injected at verify time via artifact collection.
FROM python:3.11-slim

RUN pip install --no-cache-dir pillow==11.0.0 numpy==2.1.3

WORKDIR /app
# Pristine reference image: the trusted source of truth the reference verifier compares
# each attempt's base image against, and what the candidate verifier's /app/reference
# reads resolve to here. The agent cannot tamper with this copy.
COPY reference/ /app/reference/

# Baked in at build — a separate verifier env isn't sent tests at runtime.
COPY . /tests/
RUN chmod +x /tests/test.sh && chmod -R go-rwx /tests/pool
