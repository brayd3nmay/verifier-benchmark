# Clean-room verifier image. Built from the tests/ directory as context and used as a
# SEPARATE verifier environment, so the harness never runs in a container the agent
# influenced. The agent's verifier is injected at verify time via artifact collection.
FROM python:3.11-slim

RUN pip install --no-cache-dir pandas==2.2.3 pyarrow==17.0.0

WORKDIR /app
# Pristine source files: the trusted source of truth the harness/reference verifier
# derives the correct answer from, and what the candidate verifier's /app/data reads
# resolve to here. The agent cannot tamper with this copy.
COPY data/ /app/data/

# Baked in at build — a separate verifier env isn't sent tests at runtime.
COPY . /tests/
RUN chmod +x /tests/test.sh && chmod -R go-rwx /tests/pool
