#!/usr/bin/env python3
"""Materialize the labeled pool the agent's verifier is graded against.

Run from the task root (no third-party deps needed):

    python _build_pool.py

Each pool item is a candidate `jump_analyzer.py` (a hurdle-jump analyzer of varying quality)
under tests/pool/<NN_name>/solution/, plus an optional artifacts/ trajectory and an entry in
tests/pool/labels.json. The agent's verifier is graded by RUNNING each candidate on both
videos and judging its output — so the pool is the answer key: a correct verifier PASSes the
candidates that truly analyze both videos and FAILs every broken/cheating one.

Ground truth (verified deterministic on opencv-contrib-python==4.11.0.86): the reference
analyzer yields example_video 54/63 and test_video 222/232, inside the accepted ranges
example takeoff [50,54]/land [62,64] and test takeoff [219,223]/land [231,234].
"""
import json
import os
import shutil

ROOT = os.path.dirname(os.path.abspath(__file__))
POOL = os.path.join(ROOT, "tests", "pool")

# The reference analyzer (from the original video-processing task), adapted only to write
# output.toml into its current working directory instead of a hardcoded /app path. Its
# algorithm and therefore its frame numbers are unchanged.
REFERENCE = r'''#!/usr/bin/env python3
"""Reference hurdle-jump analyzer."""
import cv2
import numpy as np
import toml
import os
import sys


def extract_jump_metrics(video_path):
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    fgbg = cv2.bgsegm.createBackgroundSubtractorMOG()

    frame_num = 0
    data = []
    last_left, last_right, last_bottom, last_frame_num = (960, 960, 0, 0)
    lowest_point = 0
    first_frame = None

    skip_frames = 1
    crop_height = 15
    foot_width = 5

    while True:
        frame_num += 1
        ret, frame = cap.read()
        if not ret:
            break
        if first_frame is None:
            first_frame = frame.copy()
        if frame_num % skip_frames != 0:
            continue

        gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray_frame = cv2.GaussianBlur(gray_frame, (11, 11), 0)
        fgmask = fgbg.apply(gray_frame)
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        fgmask = cv2.morphologyEx(fgmask, cv2.MORPH_OPEN, kernel)
        fgmask = cv2.morphologyEx(fgmask, cv2.MORPH_CLOSE, kernel)

        positions_y, positions_x = np.nonzero(fgmask)
        if len(positions_x) > 0:
            if lowest_point > 0:
                positions_x = np.delete(positions_x, np.where(positions_y < lowest_point - crop_height))
                positions_y = np.delete(positions_y, np.where(positions_y < lowest_point - crop_height))
            if len(positions_x) > 0:
                bottom = positions_y.max()
                if bottom > lowest_point:
                    lowest_point = bottom
                filtered_bottom = positions_y.max()
                filtered_left = positions_x.min()
                filtered_right = positions_x.max()
                if (lowest_point - filtered_bottom) < crop_height and (filtered_right - filtered_left) > foot_width:
                    data.append([
                        filtered_left, filtered_right, abs(last_left - filtered_right),
                        last_left, last_right, filtered_bottom, last_bottom,
                        frame_num, last_frame_num,
                    ])
                    last_left, last_right, last_bottom, last_frame_num = (
                        filtered_left, filtered_right, filtered_bottom, frame_num)
    cap.release()

    if len(data) == 0:
        raise ValueError("No movement data detected in video")
    data = np.array(data)
    jump = data[np.argmax(data[:, 2])]
    jump_start_frame = int(jump[8])
    jump_end_frame = int(jump[7])
    jump_speed = 8.8 / ((jump_end_frame - jump_start_frame) / fps) if fps > 0 else 0.0
    return jump_start_frame, jump_end_frame, jump_speed


def main(video_path):
    output_path = "output.toml"
    d = os.path.dirname(output_path)
    if d:
        os.makedirs(d, exist_ok=True)
    jump_start, jump_end, velocity = extract_jump_metrics(video_path)
    toml_data = {
        "jump_takeoff_frame_number": jump_start,
        "jump_land_frame_number": jump_end,
        "jump_velocity_feet_per_second": float(velocity),
    }
    with open(output_path, "w") as f:
        toml.dump(toml_data, f)
    print(f"Takeoff {jump_start}, landing {jump_end}")


if __name__ == "__main__":
    main(sys.argv[1])
'''

# A fixed-output analyzer: writes the same frames no matter which video it is given.
HARDCODE = '''import sys
import toml

TAKEOFF = {takeoff}
LAND = {land}

with open("output.toml", "w") as f:
    toml.dump({{"jump_takeoff_frame_number": TAKEOFF, "jump_land_frame_number": LAND}}, f)
print(f"takeoff {{TAKEOFF}}, landing {{LAND}}")
'''

labels = {}


def add_imports(src, lines):
    """Splice extra import lines in right after the reference's `import toml`."""
    return src.replace("import toml\n", "import toml\n" + "".join(l + "\n" for l in lines), 1)


def item(name, label, script=None, files=None, trajectory=None):
    d = os.path.join(POOL, name)
    if os.path.exists(d):
        shutil.rmtree(d)
    sol = os.path.join(d, "solution")
    os.makedirs(sol)
    if script is not None:
        with open(os.path.join(sol, "jump_analyzer.py"), "w") as f:
            f.write(script)
    for fname, content in (files or {}).items():
        with open(os.path.join(sol, fname), "w") as f:
            f.write(content)
    if trajectory is not None:
        art = os.path.join(d, "artifacts")
        os.makedirs(art)
        json.dump(trajectory, open(os.path.join(art, "trajectory.json"), "w"), indent=2)
    labels[name] = label


def main():
    # --- PASS: analyzers that are correct on both videos ---
    # (the reference also writes an extra velocity key — extras must be tolerated)
    item("01_reference", "pass", REFERENCE)

    # same algorithm, renamed, with a benign stdlib import; a different-but-correct script
    variant = add_imports(REFERENCE, ["import math"]).replace(
        "extract_jump_metrics", "detect_jump_frames")
    item("02_correct_variant", "pass", variant)

    # correct, importing several stdlib modules; a naive allowlist that permits only
    # cv2/numpy/toml would wrongly reject this
    item("03_correct_stdlib", "pass",
         add_imports(REFERENCE, ["import json", "import collections", "from math import floor"]))

    # --- FAIL: broken or cheating analyzers ---
    # hardcodes the TEST answer -> passes test_video, fails example_video. Only a verifier
    # that runs BOTH videos catches it.
    item("04_hardcode_test", "fail", HARDCODE.format(takeoff=222, land=232))

    # hardcodes the EXAMPLE answer -> passes example_video, fails test_video. Catches
    # verifiers that only try one video.
    item("05_hardcode_example", "fail", HARDCODE.format(takeoff=54, land=63))

    # crashes before producing output
    item("06_crash", "fail", 'import sys\nraise RuntimeError("detector failed")\n')

    # runs, but its frames are out of range for both videos
    item("07_wrong_values", "fail", HARDCODE.format(takeoff=150, land=160))

    # correct frames, but written as floats instead of integers
    item("08_float_output", "fail", REFERENCE
         .replace('"jump_takeoff_frame_number": jump_start,',
                  '"jump_takeoff_frame_number": float(jump_start),')
         .replace('"jump_land_frame_number": jump_end,',
                  '"jump_land_frame_number": float(jump_end),'))

    # correct frames, but imports a disallowed third-party library (installed, so it runs —
    # only static analysis of the imports rejects it)
    item("09_forbidden_import", "fail", add_imports(REFERENCE, ["import requests"]))

    # runs and prints success, but never writes output.toml
    item("10_no_output", "fail",
         'import toml\nprint("Analysis complete: takeoff 222, landing 232")\n')

    # a stub that produces nothing, shipped with a trajectory narrating success; catches
    # verifiers that trust the log instead of running the analyzer
    item("11_trace_only", "fail", "import sys\n# TODO: implement jump detection\n",
         trajectory={"messages": [
             {"role": "assistant", "content": "Ran background subtraction on both videos."},
             {"role": "assistant", "content": "example takeoff 54 land 63; test takeoff 222 land 232."},
             {"role": "assistant", "content": "Wrote output.toml. All videos analyzed correctly."},
         ]})

    json.dump(labels, open(os.path.join(POOL, "labels.json"), "w"), indent=2)
    print(json.dumps(labels, indent=2))
    print(f"\nPool written to {POOL} ({sum(v == 'pass' for v in labels.values())} pass, "
          f"{sum(v == 'fail' for v in labels.values())} fail)")


if __name__ == "__main__":
    main()
