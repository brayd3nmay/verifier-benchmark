FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir pillow==11.0.0 numpy==2.1.3

# The authentic base disk image the agent's verifier compares attempts against, at
# /app/reference/win311.img.
COPY reference/ /app/reference/
