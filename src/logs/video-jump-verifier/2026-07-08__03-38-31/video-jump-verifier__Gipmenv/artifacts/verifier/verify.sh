#!/usr/bin/env python3
import os
import sys
import subprocess
import tempfile
import ast
import tomllib

def write_verdict(verdict):
    verdict_file = os.environ.get("VERDICT_FILE", "/logs/verifier/reward.txt")
    os.makedirs(os.path.dirname(verdict_file), exist_ok=True)
    with open(verdict_file, "w") as f:
        f.write(str(verdict))
    print(f"Verdict written: {verdict}")
    sys.exit(0)

def check_imports(file_path):
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            code = f.read()
    except Exception as e:
        print(f"Error reading file {file_path}: {e}")
        return False

    try:
        tree = ast.parse(code)
    except Exception as e:
        print(f"Error parsing AST of {file_path}: {e}")
        return False

    allowed_top_levels = set(sys.stdlib_module_names) | {"cv2", "numpy", "toml"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for name in node.names:
                top_level = name.name.split('.')[0]
                if top_level not in allowed_top_levels:
                    print(f"Forbidden import found: {top_level}")
                    return False
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                top_level = node.module.split('.')[0]
                if top_level not in allowed_top_levels:
                    print(f"Forbidden import-from found: {top_level}")
                    return False
    return True

def run_candidate(solution_dir, video_path):
    with tempfile.TemporaryDirectory() as tmpdir:
        script_path = os.path.join(solution_dir, "jump_analyzer.py")
        try:
            cmd = ["python3", os.path.abspath(script_path), os.path.abspath(video_path)]
            result = subprocess.run(cmd, cwd=tmpdir, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=180)
            if result.returncode != 0:
                print(f"Candidate failed with return code {result.returncode} on {video_path}")
                print("STDOUT:", result.stdout.decode(errors="replace"))
                print("STDERR:", result.stderr.decode(errors="replace"))
                return None
        except subprocess.TimeoutExpired:
            print(f"Candidate timed out on {video_path}")
            return None
        except Exception as e:
            print(f"Error running candidate: {e}")
            return None

        toml_path = os.path.join(tmpdir, "output.toml")
        if not os.path.exists(toml_path):
            print(f"output.toml not found for {video_path}")
            return None

        try:
            with open(toml_path, "rb") as f:
                data = tomllib.load(f)
            return data
        except Exception as e:
            print(f"Error parsing output.toml for {video_path}: {e}")
            return None

def main():
    solution_dir = os.environ.get("SOLUTION_DIR", "/app")
    script_path = os.path.join(solution_dir, "jump_analyzer.py")
    if not os.path.exists(script_path):
        print(f"Candidate not found at {script_path}")
        write_verdict(0)

    if not check_imports(script_path):
        print("Imports check failed.")
        write_verdict(0)

    # Run for video 1
    video1 = "/app/data/example_video.mp4"
    res1 = run_candidate(solution_dir, video1)
    if res1 is None:
        write_verdict(0)

    # Check values for video 1
    takeoff1 = res1.get("jump_takeoff_frame_number")
    land1 = res1.get("jump_land_frame_number")

    # They must be integers
    if not isinstance(takeoff1, int) or isinstance(takeoff1, bool) or not isinstance(land1, int) or isinstance(land1, bool):
        print(f"Video 1 output types are incorrect: takeoff={type(takeoff1)}, land={type(land1)}")
        write_verdict(0)

    if not (50 <= takeoff1 <= 54):
        print(f"Video 1 takeoff frame {takeoff1} out of range [50, 54]")
        write_verdict(0)

    if not (62 <= land1 <= 64):
        print(f"Video 1 land frame {land1} out of range [62, 64]")
        write_verdict(0)

    # Run for video 2
    video2 = "/app/data/test_video.mp4"
    res2 = run_candidate(solution_dir, video2)
    if res2 is None:
        write_verdict(0)

    # Check values for video 2
    takeoff2 = res2.get("jump_takeoff_frame_number")
    land2 = res2.get("jump_land_frame_number")

    if not isinstance(takeoff2, int) or isinstance(takeoff2, bool) or not isinstance(land2, int) or isinstance(land2, bool):
        print(f"Video 2 output types are incorrect: takeoff={type(takeoff2)}, land={type(land2)}")
        write_verdict(0)

    if not (219 <= takeoff2 <= 223):
        print(f"Video 2 takeoff frame {takeoff2} out of range [219, 223]")
        write_verdict(0)

    if not (231 <= land2 <= 234):
        print(f"Video 2 land frame {land2} out of range [231, 234]")
        write_verdict(0)

    # All checks passed!
    write_verdict(1)

if __name__ == "__main__":
    main()
