# Agent image. The agent writes a verifier that must run and judge candidate ars.R files,
# so R (matching the underlying task's R 4.3.3) and Python are both available. There is no
# input data: the "truth" is the analytic behavior of the requested densities.
FROM rocker/r-ver:4.3.3

RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-numpy python3-scipy \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
