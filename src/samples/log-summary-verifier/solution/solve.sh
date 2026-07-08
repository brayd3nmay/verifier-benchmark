#!/bin/bash
# Oracle solution: write a correct reference verifier to /app/verifier/verify.sh.
# The harness runs it against the labeled pool; it must classify every item correctly
# (reward 1.0). This is what "a good verifier" looks like for this task.
set -euo pipefail

mkdir -p /app/verifier

# The reference verifier: derive the correct counts from the logs (bracketed severity
# token, filename dates, DEBUG ignored), then check the candidate's summary.csv against
# them — tolerant of row order and extras, strict on values and the integer format.
cat > /app/verifier/ref_verify.py <<'PYEOF'
import csv
import os
import re
import sys
from datetime import date

SOL = os.environ.get("SOLUTION_DIR", "/app")
VERDICT = os.environ.get("VERDICT_FILE", "/logs/verifier/reward.txt")
LOG_DIR = os.environ.get("LOG_DIR", "/app/logs")

SEVERITIES = ["ERROR", "WARNING", "INFO"]
PERIODS = ["today", "last_7_days", "last_30_days", "month_to_date", "total"]
REF = date(2025, 8, 12)
BOUNDS = {
    "today": (date(2025, 8, 12), REF),
    "last_7_days": (date(2025, 8, 6), REF),
    "last_30_days": (date(2025, 7, 14), REF),
    "month_to_date": (date(2025, 8, 1), REF),
    "total": (date.min, REF),
}
BRACKET = re.compile(r"\[(ERROR|WARNING|INFO)\]")
INT_RE = re.compile(r"^\d+$")


def emit(ok, msg=""):
    d = os.path.dirname(VERDICT)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(VERDICT, "w") as f:
        f.write("1" if ok else "0")
    print(("PASS" if ok else "FAIL"), msg)
    sys.exit(0)


def canonical():
    counts = {p: {s: 0 for s in SEVERITIES} for p in PERIODS}
    for fn in os.listdir(LOG_DIR):
        if not fn.endswith(".log"):
            continue
        d = date.fromisoformat(fn.split("_")[0])
        in_p = [p for p, (a, b) in BOUNDS.items() if a <= d <= b]
        with open(os.path.join(LOG_DIR, fn)) as f:
            for line in f:
                m = BRACKET.search(line)
                if not m:
                    continue
                sev = m.group(1)
                for p in in_p:
                    counts[p][sev] += 1
    return counts


expected = canonical()

path = os.path.join(SOL, "summary.csv")
if not os.path.isfile(path):
    emit(False, "missing summary.csv")
try:
    with open(path, newline="") as f:
        rows = [r for r in csv.reader(f) if r]
except Exception as e:
    emit(False, f"unreadable summary.csv: {e}")

if not rows:
    emit(False, "empty summary.csv")
# Standard CSV: locate the required columns by name (any order; extra columns ok).
header = rows[0]
try:
    pi, si, ci = header.index("period"), header.index("severity"), header.index("count")
except ValueError:
    emit(False, f"header missing period/severity/count: {header}")

seen = {}
for r in rows[1:]:
    if max(pi, si, ci) >= len(r):
        emit(False, f"short row: {r}")
    key = (r[pi], r[si])
    if key in seen:
        emit(False, f"duplicate row for {key}")
    seen[key] = r[ci]

required = {(p, s) for p in PERIODS for s in SEVERITIES}
if set(seen) != required:
    emit(False, f"row keys {sorted(set(seen))} != required {sorted(required)}")

for (p, s), val in seen.items():
    if not INT_RE.match(val):
        emit(False, f"{p},{s} count {val!r} is not a plain integer")
    if int(val) != expected[p][s]:
        emit(False, f"{p},{s} count {val} != expected {expected[p][s]}")

emit(True, "all counts correct")
PYEOF

cat > /app/verifier/verify.sh <<'SHEOF'
#!/bin/bash
python3 /app/verifier/ref_verify.py
SHEOF

chmod +x /app/verifier/verify.sh
echo "Reference verifier written to /app/verifier/verify.sh"
