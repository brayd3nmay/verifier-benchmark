FROM python:3.13-slim

WORKDIR /app

# The agent writes a verifier; it needs Biopython (translation) and the API clients to
# resolve the reference proteins (PDB / FPBase / PubChem) during its run.
RUN pip install --no-cache-dir biopython==1.85 rcsb-api requests pandas==2.2.3

# Design inputs the agent's verifier reads at /app/data. NOT the answer — the agent must
# derive the correct reference proteins from these plus the public APIs.
COPY data/ /app/data/
