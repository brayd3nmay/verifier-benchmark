import os
import sys
import ast
import tempfile
import subprocess
import tomllib

def check_imports(file_path, sol_dir):
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            source = f.read()
        tree = ast.parse(source, filename=file_path)
    except Exception as e:
        print(f"AST parsing failed: {e}", file=sys.stderr)
        return False

    allowed_3rd_party = {'cv2', 'numpy', 'toml'}
    
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for name in node.names:
                top_level = name.name.split('.')[0]
                if top_level in sys.stdlib_module_names:
                    continue
                if top_level in allowed_3rd_party:
                    continue
                if os.path.exists(os.path.join(sol_dir, top_level + '.py')) or os.path.isdir(os.path.join(sol_dir, top_level)):
                    continue
                print(f"Disallowed import: {name.name}", file=sys.stderr)
                return False
        elif isinstance(node, ast.ImportFrom):
            if node.level is not None and node.level > 0:
                continue
            if node.module:
                top_level = node.module.split('.')[0]
                if top_level in sys.stdlib_module_names:
                    continue
                if top_level in allowed_3rd_party:
                    continue
                if os.path.exists(os.path.join(sol_dir, top_level + '.py')) or os.path.isdir(os.path.join(sol_dir, top_level)):
                    continue
                print(f"Disallowed import from: {node.module}", file=sys.stderr)
                return False
    return True

def run_candidate(sol_dir, video_path):
    with tempfile.TemporaryDirectory() as tmpdir:
        script_path = os.path.join(sol_dir, 'jump_analyzer.py')
        cmd = [sys.executable, script_path, video_path]
        try:
            res = subprocess.run(cmd, cwd=tmpdir, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=180)
        except subprocess.TimeoutExpired as e:
            print(f"Timeout expired while running candidate: {e}", file=sys.stderr)
            return None
        except Exception as e:
            print(f"Failed to run candidate: {e}", file=sys.stderr)
            return None
        
        if res.returncode != 0:
            print(f"Candidate exited with code {res.returncode}", file=sys.stderr)
            print(f"STDOUT:\n{res.stdout}", file=sys.stderr)
            print(f"STDERR:\n{res.stderr}", file=sys.stderr)
            return None
        
        output_toml_path = os.path.join(tmpdir, 'output.toml')
        if not os.path.exists(output_toml_path):
            print("Candidate finished but output.toml was not created", file=sys.stderr)
            return None
        
        try:
            with open(output_toml_path, 'rb') as f:
                data = tomllib.load(f)
            return data
        except Exception as e:
            print(f"Failed to parse output.toml: {e}", file=sys.stderr)
            return None

def verify():
    sol_dir = os.environ.get('SOLUTION_DIR', '/app')
    verdict_file = os.environ.get('VERDICT_FILE', '/logs/verifier/reward.txt')
    
    verdict_dir = os.path.dirname(verdict_file)
    if verdict_dir:
        os.makedirs(verdict_dir, exist_ok=True)
    
    script_path = os.path.join(sol_dir, 'jump_analyzer.py')
    if not os.path.exists(script_path):
        print(f"jump_analyzer.py not found at {script_path}", file=sys.stderr)
        with open(verdict_file, 'w') as f:
            f.write('0\n')
        return
    
    if not check_imports(script_path, sol_dir):
        print("Import check failed", file=sys.stderr)
        with open(verdict_file, 'w') as f:
            f.write('0\n')
        return
    
    print("Running on example_video.mp4...")
    example_res = run_candidate(sol_dir, '/app/data/example_video.mp4')
    if example_res is None:
        print("Example video run failed", file=sys.stderr)
        with open(verdict_file, 'w') as f:
            f.write('0\n')
        return
    
    takeoff = example_res.get('jump_takeoff_frame_number')
    land = example_res.get('jump_land_frame_number')
    
    if not isinstance(takeoff, int) or isinstance(takeoff, bool):
        print(f"Invalid takeoff type for example: {type(takeoff)}", file=sys.stderr)
        with open(verdict_file, 'w') as f:
            f.write('0\n')
        return
    if not isinstance(land, int) or isinstance(land, bool):
        print(f"Invalid land type for example: {type(land)}", file=sys.stderr)
        with open(verdict_file, 'w') as f:
            f.write('0\n')
        return
        
    if not (50 <= takeoff <= 54):
        print(f"Takeoff frame {takeoff} out of range [50, 54] for example", file=sys.stderr)
        with open(verdict_file, 'w') as f:
            f.write('0\n')
        return
        
    if not (62 <= land <= 64):
        print(f"Land frame {land} out of range [62, 64] for example", file=sys.stderr)
        with open(verdict_file, 'w') as f:
            f.write('0\n')
        return
        
    print("Running on test_video.mp4...")
    test_res = run_candidate(sol_dir, '/app/data/test_video.mp4')
    if test_res is None:
        print("Test video run failed", file=sys.stderr)
        with open(verdict_file, 'w') as f:
            f.write('0\n')
        return
        
    takeoff = test_res.get('jump_takeoff_frame_number')
    land = test_res.get('jump_land_frame_number')
    
    if not isinstance(takeoff, int) or isinstance(takeoff, bool):
        print(f"Invalid takeoff type for test: {type(takeoff)}", file=sys.stderr)
        with open(verdict_file, 'w') as f:
            f.write('0\n')
        return
    if not isinstance(land, int) or isinstance(land, bool):
        print(f"Invalid land type for test: {type(land)}", file=sys.stderr)
        with open(verdict_file, 'w') as f:
            f.write('0\n')
        return
        
    if not (219 <= takeoff <= 223):
        print(f"Takeoff frame {takeoff} out of range [219, 223] for test", file=sys.stderr)
        with open(verdict_file, 'w') as f:
            f.write('0\n')
        return
        
    if not (231 <= land <= 234):
        print(f"Land frame {land} out of range [231, 234] for test", file=sys.stderr)
        with open(verdict_file, 'w') as f:
            f.write('0\n')
        return
        
    print("All checks passed!")
    with open(verdict_file, 'w') as f:
        f.write('1\n')

if __name__ == '__main__':
    verify()
