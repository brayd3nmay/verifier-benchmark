import sys
import toml

TAKEOFF = 150
LAND = 160

with open("output.toml", "w") as f:
    toml.dump({"jump_takeoff_frame_number": TAKEOFF, "jump_land_frame_number": LAND}, f)
print(f"takeoff {TAKEOFF}, landing {LAND}")
