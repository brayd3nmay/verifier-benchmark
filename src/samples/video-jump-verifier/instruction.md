A hurdle-jump analyzer is a script, `jump_analyzer.py`, that takes the path to an MP4 of a single athlete clearing one hurdle (stationary camera, fixed background) and writes an `output.toml` reporting the frame the athlete takes off and the frame they land. I have a batch of candidate analyzers of unknown quality and need to know which ones actually work. Write a verifier that decides whether a given candidate is a correct analyzer.

The candidate is at `$SOLUTION_DIR/jump_analyzer.py`. It is run as `python3 jump_analyzer.py <video_path>` and writes its result to `output.toml` in the working directory it runs in. Two videos are available at `/app/data`:

- `/app/data/example_video.mp4` — the correct takeoff frame is an integer in the inclusive range 50 to 54, and the correct landing frame is an integer in 62 to 64.
- `/app/data/test_video.mp4` — the correct takeoff frame is an integer in 219 to 223, and the correct landing frame is an integer in 231 to 234.

A candidate is correct only if, for **both** videos, running it produces an `output.toml` containing `jump_takeoff_frame_number` and `jump_land_frame_number` as TOML integers, each within that video's range. The script may only import the third-party libraries `cv2`, `numpy`, and `toml`; standard-library imports are always fine, and a candidate that imports any other third-party library is not correct even when its frames are right. Extra output keys or files do not make a candidate wrong.

Write your verifier as an executable at `/app/verifier/verify.sh`. It is run once per candidate: it reads the candidate from `$SOLUTION_DIR` (default `/app`), may read agent logs from `$ARTIFACTS_DIR`, and writes `1` (correct) or `0` (incorrect) to `$VERDICT_FILE` (default `/logs/verifier/reward.txt`).
