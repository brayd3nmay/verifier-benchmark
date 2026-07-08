FROM python:3.13-slim-bookworm

WORKDIR /app

# OpenCV system libraries (the analyzer scripts the verifier runs use cv2).
RUN apt-get update && apt-get install -y \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# opencv-contrib pinned so the reference analyzer's frame numbers are reproducible.
# requests is present as a non-allowlisted third-party library so a candidate that imports
# it still runs — only static analysis of the imports should reject it.
RUN pip install --no-cache-dir \
    "opencv-contrib-python==4.11.0.86" \
    "toml==0.10.2" \
    "requests==2.32.3"

# The two videos the verifier runs candidates against, available while the agent develops.
COPY data/ /app/data/
