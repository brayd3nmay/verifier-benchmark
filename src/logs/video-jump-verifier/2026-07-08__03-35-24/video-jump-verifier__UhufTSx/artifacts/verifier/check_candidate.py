import sys
import os
import ast
import tomllib
import subprocess
import tempfile
import shutil

def check_imports(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        try:
            tree = ast.parse(f.read())
        except SyntaxError:
            return False, "Syntax error in candidate file"
            
    allowed_3rd = {'cv2', 'numpy', 'toml'}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split('.')[0]
                if top not in sys.stdlib_module_names and top not in allowed_3rd:
                    return False, f"Disallowed import: {alias.name}"
        elif isinstance(node, ast.ImportFrom):
            if node.level > 0:  # relative import
                continue
            if node.module:
                top = node.module.split('.')[0]
                if top not in sys.stdlib_module_names and top not in allowed_3rd:
                    return False, f"Disallowed import from: {node.module}"
    return True, "Imports are fine"

def check_video(candidate_path, video_path, expected_takeoff_range, expected_land_range):
    # Create a temporary directory
    temp_dir = tempfile.mkdtemp()
    try:
        # Candidate is run as `python3 jump_analyzer.py <video_path>`
        # and writes output.toml in the working directory it runs in.
        cmd = ["python3", candidate_path, video_path]
        try:
            res = subprocess.run(cmd, cwd=temp_dir, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60, text=True)
            if res.returncode != 0:
                return False, f"Candidate execution failed with code {res.returncode}. Stderr: {res.stderr}"
        except subprocess.TimeoutExpired:
            return False, "Candidate execution timed out after 60 seconds"

        output_toml_path = os.path.join(temp_dir, "output.toml")
        if not os.path.exists(output_toml_path):
            return False, f"Candidate did not produce output.toml in working directory"

        try:
            with open(output_toml_path, 'rb') as f:
                data = tomllib.load(f)
        except Exception as e:
            return False, f"Failed to parse output.toml: {e}"

        if 'jump_takeoff_frame_number' not in data:
            return False, "Missing 'jump_takeoff_frame_number' in output.toml"
        if 'jump_land_frame_number' not in data:
            return False, "Missing 'jump_land_frame_number' in output.toml"

        takeoff = data['jump_takeoff_frame_number']
        land = data['jump_land_frame_number']

        if not isinstance(takeoff, int) or isinstance(takeoff, bool):
            return False, f"jump_takeoff_frame_number is not a valid TOML integer: {type(takeoff)}"
        if not isinstance(land, int) or isinstance(land, bool):
            return False, f"jump_land_frame_number is not a valid TOML integer: {type(land)}"

        min_t, max_t = expected_takeoff_range
        min_l, max_l = expected_land_range

        if not (min_t <= takeoff <= max_t):
            return False, f"jump_takeoff_frame_number ({takeoff}) is outside correct range [{min_t}, {max_t}]"
        if not (min_l <= land <= max_l):
            return False, f"jump_land_frame_number ({land}) is outside correct range [{min_l}, {max_l}]"

        return True, "Video analysis is correct"
    finally:
        # Clean up temp dir
        shutil.rmtree(temp_dir, ignore_errors=True)

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 check_candidate.py <candidate_path>")
        sys.exit(1)

    candidate_path = os.path.abspath(sys.argv[1])
    if not os.path.isfile(candidate_path):
        print(f"Candidate file not found: {candidate_path}")
        sys.exit(1)

    # 1. Check imports
    res, msg = check_imports(candidate_path)
    if not res:
        print(f"Verification failed (imports): {msg}")
        print("VERDICT: 0")
        return

    # 2. Check example video
    # example_video.mp4: takeoff range [50, 54], landing range [62, 64]
    res, msg = check_video(candidate_path, "/app/data/example_video.mp4", (50, 54), (62, 64))
    if not res:
        print(f"Verification failed (example video): {msg}")
        print("VERDICT: 0")
        return

    # 3. Check test video
    # test_video.mp4: takeoff range [219, 223], landing range [231, 234]
    res, msg = check_video(candidate_path, "/app/data/test_video.mp4", (219, 223), (231, 234))
    if not res:
        print(f"Verification failed (test video): {msg}")
        print("VERDICT: 0")
        return

    print("VERDICT: 1")

if __name__ == '__main__':
    main()
