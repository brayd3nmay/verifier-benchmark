FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir pandas==2.2.3 pyarrow==17.0.0

# Source files the agent reads at /app/data.
COPY data/ /app/data/
