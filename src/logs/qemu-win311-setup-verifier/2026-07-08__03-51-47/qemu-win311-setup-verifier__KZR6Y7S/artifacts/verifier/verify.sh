#!/bin/bash

# Default paths
SOLUTION_DIR="${SOLUTION_DIR:-/app}"
VERDICT_FILE="${VERDICT_FILE:-/logs/verifier/reward.txt}"

echo "Starting verification..."
echo "SOLUTION_DIR: $SOLUTION_DIR"
echo "VERDICT_FILE: $VERDICT_FILE"

# Default verdict is 0 (incorrect)
VERDICT=0

# Helper function to write verdict and exit
write_verdict() {
    local val=$1
    mkdir -p "$(dirname "$VERDICT_FILE")"
    echo "$val" > "$VERDICT_FILE"
    echo "Verdict set to $val"
    exit 0
}

# Check if files exist in SOLUTION_DIR
if [ ! -f "$SOLUTION_DIR/qemu_cmdline.txt" ]; then
    echo "Missing qemu_cmdline.txt"
    write_verdict 0
fi

if [ ! -f "$SOLUTION_DIR/listening_ports.txt" ]; then
    echo "Missing listening_ports.txt"
    write_verdict 0
fi

if [ ! -f "$SOLUTION_DIR/base_image.img" ]; then
    echo "Missing base_image.img"
    write_verdict 0
fi

if [ ! -f "$SOLUTION_DIR/screenshots/baseline.png" ]; then
    echo "Missing baseline.png"
    write_verdict 0
fi

if [ ! -f "$SOLUTION_DIR/screenshots/after_key.png" ]; then
    echo "Missing after_key.png"
    write_verdict 0
fi

# 1. Base disk image must stay pristine (byte-for-byte identical to reference)
if ! cmp -s "$SOLUTION_DIR/base_image.img" "/app/reference/win311.img"; then
    echo "base_image.img is not pristine (differs from reference)"
    write_verdict 0
fi

# 2. VNC on port 5901 and Web interface on port 80 must be listening
# We check listening_ports.txt
# Example lines:
# tcp        0      0 0.0.0.0:5901            0.0.0.0:*               LISTEN
# tcp6       0      0 :::80                   :::*                    LISTEN
if ! grep -q -E "[:.]5901[[:space:]]" "$SOLUTION_DIR/listening_ports.txt" || ! grep -q -E "[:.]5901[[:space:]]+.*LISTEN" "$SOLUTION_DIR/listening_ports.txt"; then
    # Try a broader grep in case of different formatting
    if ! grep -q ":5901" "$SOLUTION_DIR/listening_ports.txt"; then
        echo "Port 5901 (VNC) is not listening"
        write_verdict 0
    fi
fi

if ! grep -q -E "[:.]80[[:space:]]" "$SOLUTION_DIR/listening_ports.txt" || ! grep -q -E "[:.]80[[:space:]]+.*LISTEN" "$SOLUTION_DIR/listening_ports.txt"; then
    if ! grep -q ":80" "$SOLUTION_DIR/listening_ports.txt"; then
        echo "Port 80 (Web interface) is not listening"
        write_verdict 0
    fi
fi

# 3. Automation and Keystrokes delivery check
# Check qemu_cmdline.txt to see if monitor or QMP or snapshot options are there.
# QEMU should boot with monitor options to allow programmatic key input.
CMDLINE=$(cat "$SOLUTION_DIR/qemu_cmdline.txt")

# Let's check for -monitor, -qmp or -chardev in command line
echo "QEMU command line: $CMDLINE"

# Also check if screenshots are different (keystroke reached the VM)
BASE_SUM=$(sha256sum "$SOLUTION_DIR/screenshots/baseline.png" | awk '{print $1}')
AFTER_SUM=$(sha256sum "$SOLUTION_DIR/screenshots/after_key.png" | awk '{print $1}')

if [ "$BASE_SUM" = "$AFTER_SUM" ]; then
    echo "Screenshots are identical! Keystroke did not reach the VM or VM did not boot correctly"
    write_verdict 0
fi

# If we reached here, all conditions are satisfied!
write_verdict 1
