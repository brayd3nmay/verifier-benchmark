FROM python:3.11-slim

WORKDIR /app

# Bake the logs into the image so they stay readable at /app/logs while the
# agent's verifier runs. The generator is deterministic, so this same output is
# reproduced in the verifier image and by the pool builder.
COPY log_generator_deterministic.py /app/
RUN python3 /app/log_generator_deterministic.py && rm -f /app/log_generator_deterministic.py
