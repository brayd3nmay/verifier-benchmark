# Clean-room verifier image. Built from the tests/ directory as context and used as a
# SEPARATE verifier environment, so the harness never runs in a container the agent
# influenced. The agent's verifier is injected at verify time via artifact collection.
FROM python:3.13-slim

# Biopython for translation; the API clients so a candidate that resolves the reference
# proteins live at grade time can run (network is enabled at runtime for this task).
RUN pip install --no-cache-dir biopython==1.85 rcsb-api requests pandas==2.2.3

WORKDIR /app
# Pristine design inputs: what the candidate verifier's /app/data reads resolve to here.
# The agent cannot tamper with this copy. Kept in sync with environment/data by _build_pool.py.
COPY data/ /app/data/

# Baked in at build — a separate verifier env isn't sent tests at runtime.
COPY . /tests/
RUN chmod +x /tests/test.sh && chmod -R go-rwx /tests/pool
