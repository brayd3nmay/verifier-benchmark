import os
import sys
import re
import hashlib
from PIL import Image

def log(msg):
    print(f"[VERIFIER] {msg}", flush=True)

def check_all():
    solution_dir = os.environ.get('SOLUTION_DIR', '/app')
    verdict_file = os.environ.get('VERDICT_FILE', '/logs/verifier/reward.txt')
    
    req_files = [
        'qemu_cmdline.txt',
        'listening_ports.txt',
        'base_image.img',
        'screenshots/baseline.png',
        'screenshots/after_key.png'
    ]
    for f in req_files:
        path = os.path.join(solution_dir, f)
        if not os.path.exists(path):
            log(f"Required file missing: {f} at {path}")
            return False
            
    ref_image = '/app/reference/win311.img'
    test_image = os.path.join(solution_dir, 'base_image.img')
    if not os.path.exists(ref_image):
        log(f"Reference image missing at {ref_image}!")
        return False
        
    if os.path.getsize(ref_image) != os.path.getsize(test_image):
        log("base_image.img size does not match reference image size")
        return False
        
    with open(ref_image, 'rb') as f1, open(test_image, 'rb') as f2:
        while True:
            b1 = f1.read(65536)
            b2 = f2.read(65536)
            if b1 != b2:
                log("base_image.img is not byte-for-byte identical to reference image")
                return False
            if not b1:
                break
    log("base_image.img is verified to be pristine")

    ports_path = os.path.join(solution_dir, 'listening_ports.txt')
    with open(ports_path, 'r') as f:
        ports_content = f.read()
        
    has_5901 = False
    has_80 = False
    for line in ports_content.splitlines():
        if 'LISTEN' in line:
            parts = line.split()
            if len(parts) >= 4:
                local_addr = parts[3]
                if re.search(r'[:.]5901$', local_addr):
                    has_5901 = True
                if re.search(r'[:.]80$', local_addr):
                    has_80 = True
                    
    if not has_5901:
        log("Port 5901 (VNC) is not listening according to listening_ports.txt")
        return False
    if not has_80:
        log("Port 80 (web interface) is not listening according to listening_ports.txt")
        return False
    log("Ports 5901 and 80 are verified to be listening")

    cmd_path = os.path.join(solution_dir, 'qemu_cmdline.txt')
    with open(cmd_path, 'r') as f:
        cmdline = f.read()
        
    has_automation_flag = False
    for keyword in ['-monitor', '-qmp', 'qmp:', 'monitor=', 'mon:']:
        if keyword in cmdline:
            has_automation_flag = True
            break
    if not has_automation_flag:
        log("QEMU command line does not seem to configure programmatic control (monitor/QMP)")
        return False
    log("QEMU command line programmatic options verified")

    baseline_path = os.path.join(solution_dir, 'screenshots/baseline.png')
    after_key_path = os.path.join(solution_dir, 'screenshots/after_key.png')
    
    try:
        img_baseline = Image.open(baseline_path)
        img_after = Image.open(after_key_path)
    except Exception as e:
        log(f"Failed to open screenshots: {e}")
        return False
        
    colors = img_baseline.getcolors(maxcolors=256)
    if colors is not None and len(colors) <= 10:
        log("baseline.png has very few colors, it might be a blank/failed screen")
        return False
        
    h_base = hashlib.sha256(img_baseline.tobytes()).hexdigest()
    h_after = hashlib.sha256(img_after.tobytes()).hexdigest()
    if h_base == h_after:
        log("baseline.png and after_key.png are identical! Keystroke did not change the screen or reach the VM")
        return False
        
    log("Screenshots successfully verified (they are valid, baseline is not blank, and they are different)")
    return True

if __name__ == '__main__':
    verdict_file = os.environ.get('VERDICT_FILE', '/logs/verifier/reward.txt')
    success = False
    try:
        success = check_all()
    except Exception as e:
        log(f"Exception during verification: {e}")
        success = False
        
    os.makedirs(os.path.dirname(verdict_file), exist_ok=True)
    with open(verdict_file, 'w') as f:
        if success:
            f.write("1\n")
            log("VERDICT: 1 (Correct)")
        else:
            f.write("0\n")
            log("VERDICT: 0 (Incorrect)")
