I run Windows 3.11 for Workgroups in a QEMU virtual machine, and I need to check whether a given setup attempt did it correctly. A correct attempt boots the provided Windows 3.11 image to the desktop and leaves the VM running so that:

- the VNC display is reachable on TCP port 5901 and a web interface is reachable on TCP port 80, both for remote monitoring;
- the base disk image is kept pristine — the running VM must not be able to write to it, so it stays byte-for-byte the image I provided;
- keystrokes can be delivered to the VM programmatically — driven by automation through QEMU, not only typed by a human over VNC — and a key sent this way actually reaches the running VM.

Each attempt is captured as an evidence bundle in SOLUTION_DIR (default /app): the QEMU command line in `qemu_cmdline.txt` (arguments space-separated on one line), the host's listening sockets in `listening_ports.txt` (`netstat -tlnp` format), the VM's base disk image as `base_image.img`, and two VNC screenshots under `screenshots/` — `baseline.png` taken at the desktop and `after_key.png` taken right after one keystroke was sent to the VM programmatically. The image I provided stays readable at /app/reference/win311.img while your verifier runs. Extra files, ports, and command-line arguments in a bundle don't make an attempt wrong.

Write your verifier as an executable at /app/verifier/verify.sh. It is run once per attempt: it reads the attempt's files from SOLUTION_DIR (default /app), may read agent logs from ARTIFACTS_DIR, and writes 1 (correct) or 0 (incorrect) to VERDICT_FILE (default /logs/verifier/reward.txt).
