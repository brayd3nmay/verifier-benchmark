# Clean-room verifier image. Built from the tests/ directory as context and used as a
# SEPARATE verifier environment, so the harness never runs in a container the agent
# influenced. The agent's verifier is injected at verify time via artifact collection, then
# runs each candidate analyzer against the pristine videos baked in here.
FROM python:3.13-slim-bookworm

RUN apt-get update && apt-get install -y \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    "opencv-contrib-python==4.11.0.86" \
    "toml==0.10.2" \
    "requests==2.32.3"

WORKDIR /app
# Pristine videos the harness/reference verifier runs candidates against. The agent cannot
# tamper with this copy.
COPY data/ /app/data/

# Baked in at build — a separate verifier env isn't sent tests at runtime.
COPY . /tests/
RUN chmod +x /tests/test.sh && chmod -R go-rwx /tests/pool
