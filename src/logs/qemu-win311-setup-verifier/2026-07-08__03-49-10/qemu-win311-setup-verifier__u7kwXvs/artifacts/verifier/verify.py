import os
import sys
import shlex
from PIL import Image

def main():
    solution_dir = os.environ.get('SOLUTION_DIR', '/app')
    verdict_file = os.environ.get('VERDICT_FILE', '/logs/verifier/reward.txt')

    # Ensure the directory of verdict_file exists
    verdict_dir = os.path.dirname(verdict_file)
    if verdict_dir and not os.path.exists(verdict_dir):
        os.makedirs(verdict_dir, exist_ok=True)

    def write_verdict(val):
        with open(verdict_file, 'w') as f:
            f.write(str(val) + '\n')
        print(f"VERDICT WRITTEN: {val}")
        sys.exit(0)

    # List of expected files
    expected_files = [
        'qemu_cmdline.txt',
        'listening_ports.txt',
        'base_image.img',
        'screenshots/baseline.png',
        'screenshots/after_key.png'
    ]

    # 1. Existence Check
    for f in expected_files:
        path = os.path.join(solution_dir, f)
        if not os.path.exists(path):
            print(f"File missing: {path}")
            write_verdict(0)

    # 2. Pristine Base Image Check (Byte-for-byte identical)
    ref_image = '/app/reference/win311.img'
    base_image = os.path.join(solution_dir, 'base_image.img')
    if not os.path.exists(ref_image):
        print(f"Reference image missing: {ref_image}")
        write_verdict(0)

    try:
        if os.path.getsize(ref_image) != os.path.getsize(base_image):
            print("Base image size mismatch")
            write_verdict(0)

        with open(ref_image, 'rb') as f1, open(base_image, 'rb') as f2:
            while True:
                b1 = f1.read(65536)
                b2 = f2.read(65536)
                if b1 != b2:
                    print("Base image contents mismatch (not pristine)")
                    write_verdict(0)
                if not b1:
                    break
    except Exception as e:
        print(f"Error comparing images: {e}")
        write_verdict(0)

    # 3. Listening Ports Check
    listening_ports_file = os.path.join(solution_dir, 'listening_ports.txt')
    has_5901 = False
    has_80 = False
    try:
        with open(listening_ports_file, 'r') as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) >= 6 and parts[0] in ('tcp', 'tcp6'):
                    local_addr = parts[3]
                    state = parts[5]
                    if state == 'LISTEN':
                        port = local_addr.split(':')[-1]
                        if port == '5901':
                            has_5901 = True
                        elif port == '80':
                            has_80 = True
    except Exception as e:
        print(f"Error reading/parsing listening ports: {e}")
        write_verdict(0)

    if not has_5901:
        print("Port 5901 (VNC) is not listening on TCP")
        write_verdict(0)
    if not has_80:
        print("Port 80 (HTTP) is not listening on TCP")
        write_verdict(0)

    # 4. QEMU Command Line Check
    cmd_line_file = os.path.join(solution_dir, 'qemu_cmdline.txt')
    try:
        with open(cmd_line_file, 'r') as f:
            cmd_content = f.read().strip()
        try:
            args = shlex.split(cmd_content)
        except Exception:
            args = cmd_content.split()
    except Exception as e:
        print(f"Error reading QEMU command line: {e}")
        write_verdict(0)

    # Check for pristine/read-only enforcement
    has_base_image = False
    for arg in args:
        if 'base_image.img' in arg:
            has_base_image = True
            break

    if has_base_image:
        is_pristine_enforced = False
        if any(arg == '-snapshot' for arg in args):
            is_pristine_enforced = True
        else:
            for arg in args:
                if 'snapshot=on' in arg or 'read-only=on' in arg or 'readonly=on' in arg:
                    is_pristine_enforced = True
                    break
        if not is_pristine_enforced:
            print("Base image is directly used but snapshotting/read-only is not enforced on command line")
            write_verdict(0)

    # Check for programmatic input support (monitor or QMP)
    has_monitor = False
    for arg in args:
        if arg in ('-monitor', '-qmp', '-mon', '-qmp-pretty'):
            has_monitor = True
        elif arg.startswith('-monitor') or arg.startswith('-qmp') or arg.startswith('-mon'):
            has_monitor = True

    if not has_monitor:
        print("No QEMU monitor or QMP option found in command line")
        write_verdict(0)

    # 5. Screenshot Comparison (Baseline vs After Key)
    baseline_path = os.path.join(solution_dir, 'screenshots/baseline.png')
    after_key_path = os.path.join(solution_dir, 'screenshots/after_key.png')
    try:
        img_baseline = Image.open(baseline_path)
        img_after = Image.open(after_key_path)

        if img_baseline.size != img_after.size:
            different = True
        else:
            # Compare pixel-by-pixel
            # We can use ImageChops.difference or simply load data and compare
            from PIL import ImageChops
            diff = ImageChops.difference(img_baseline, img_after)
            different = diff.getbbox() is not None

        if not different:
            print("Screenshots are identical — keystroke did not reach VM or cause any visible change")
            write_verdict(0)
    except Exception as e:
        print(f"Error comparing screenshots: {e}")
        write_verdict(0)

    # All checks passed
    print("All checks passed successfully!")
    write_verdict(1)

if __name__ == '__main__':
    main()
