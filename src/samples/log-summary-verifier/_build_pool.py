#!/usr/bin/env python3
"""Materialize the labeled pool the agent's verifier is graded against.

Run from the task root (needs only the stdlib):

    uv run -p 3.11 --no-project python _build_pool.py

Regenerates the logs from environment/log_generator_deterministic.py into a temp
dir, derives the canonical 15 counts (and the substring-ERROR "trap" counts) from
them, then writes tests/pool/<NN_name>/solution/summary.csv (candidate output),
optional tests/pool/<NN_name>/artifacts/... (agent logs), and tests/pool/labels.json.
The pool is the answer key: a correct verifier PASSes every "pass" item and FAILs
every "fail" item. It also syncs tests/log_generator_deterministic.py from
environment/ so the verifier image's pristine logs match the pool's basis.
"""
import csv
import json
import os
import re
import runpy
import shutil
import tempfile
from datetime import date

ROOT = os.path.dirname(os.path.abspath(__file__))
GEN = os.path.join(ROOT, "environment", "log_generator_deterministic.py")
POOL = os.path.join(ROOT, "tests", "pool")

SEVERITIES = ["ERROR", "WARNING", "INFO"]
PERIODS = ["today", "last_7_days", "last_30_days", "month_to_date", "total"]
REF = date(2025, 8, 12)
# inclusive [start, end] per period
BOUNDS = {
    "today": (date(2025, 8, 12), REF),
    "last_7_days": (date(2025, 8, 6), REF),
    "last_30_days": (date(2025, 7, 14), REF),
    "month_to_date": (date(2025, 8, 1), REF),
    "total": (date.min, REF),
}
_BRACKET = re.compile(r"\[(ERROR|WARNING|INFO|DEBUG)\]")

# Ground truth guard (Playbook Step 4): these are the hand-verified canonical
# counts. If the generator ever drifts, the assert below fires instead of the pool
# silently relabeling.
EXPECTED = {
    ("today", "ERROR"): 370, ("today", "WARNING"): 463, ("today", "INFO"): 1433,
    ("last_7_days", "ERROR"): 2969, ("last_7_days", "WARNING"): 4020, ("last_7_days", "INFO"): 12203,
    ("last_30_days", "ERROR"): 9594, ("last_30_days", "WARNING"): 12847, ("last_30_days", "INFO"): 38702,
    ("month_to_date", "ERROR"): 4682, ("month_to_date", "WARNING"): 6327, ("month_to_date", "INFO"): 19420,
    ("total", "ERROR"): 14160, ("total", "WARNING"): 18772, ("total", "INFO"): 56621,
}


def derive():
    """Regenerate logs and count both the bracketed severities (canonical) and the
    substring-"ERROR" count (what a naive counter that ignores the brackets gets)."""
    tmp = tempfile.mkdtemp(prefix="lsv_logs_")
    os.environ["LOG_DIR"] = tmp
    runpy.run_path(GEN, run_name="__main__")

    canon = {p: {s: 0 for s in SEVERITIES} for p in PERIODS}
    substr_error = {p: 0 for p in PERIODS}  # lines containing "ERROR" anywhere
    try:
        for fn in os.listdir(tmp):
            if not fn.endswith(".log"):
                continue
            d = date.fromisoformat(fn.split("_")[0])
            in_p = [p for p, (a, b) in BOUNDS.items() if a <= d <= b]
            with open(os.path.join(tmp, fn)) as f:
                for line in f:
                    m = _BRACKET.search(line)
                    sev = m.group(1) if m else None
                    has_err = "ERROR" in line
                    for p in in_p:
                        if sev in SEVERITIES:
                            canon[p][sev] += 1
                        if has_err:
                            substr_error[p] += 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return canon, substr_error


def rows_from(counts):
    """Long-format rows [(period, severity, count_str), ...] in spec order."""
    return [(p, s, str(counts[p][s])) for p in PERIODS for s in SEVERITIES]


def reset(name):
    d = os.path.join(POOL, name)
    shutil.rmtree(d, ignore_errors=True)
    sol = os.path.join(d, "solution")
    os.makedirs(sol)
    return d, sol


def write_csv(path, header, rows):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def main():
    canon, substr_error = derive()
    for key, want in EXPECTED.items():
        got = canon[key[0]][key[1]]
        assert got == want, f"ground truth drift at {key}: got {got}, want {want}"

    canonical_rows = rows_from(canon)
    labels = {}

    def clone_counts():
        """A per-period copy of the canonical counts, safe to mutate for one fail item."""
        return {p: dict(canon[p]) for p in PERIODS}

    def fail_csv(name, rows, header=("period", "severity", "count")):
        _, sol = reset(name)
        write_csv(os.path.join(sol, "summary.csv"), list(header), rows)
        labels[name] = "fail"

    # 01 baseline: the canonical answer every verifier must pass
    _, sol = reset("01_oracle")
    write_csv(os.path.join(sol, "summary.csv"), ["period", "severity", "count"], canonical_rows)
    labels["01_oracle"] = "pass"

    # 02 correct answer, rows in a non-spec order; catches order-assuming / byte-diff verifiers
    _, sol = reset("02_correct_alt")
    write_csv(os.path.join(sol, "summary.csv"), ["period", "severity", "count"],
              list(reversed(canonical_rows)))
    labels["02_correct_alt"] = "pass"

    # 03 correct answer with harmless extras (trailing column + extra file); over-strict verifiers
    _, sol = reset("03_correct_superset")
    write_csv(os.path.join(sol, "summary.csv"), ["period", "severity", "count", "pct"],
              [(p, s, c, "0.0") for (p, s, c) in canonical_rows])
    with open(os.path.join(sol, "summary.txt"), "w") as f:
        f.write("Summed ERROR/WARNING/INFO across 5 date ranges from /app/logs.\n")
    labels["03_correct_superset"] = "pass"

    # 04 wrong counts on the fiddly middle periods (today/total left correct);
    #    catches verifiers that only spot-check the easy periods
    wv = clone_counts()
    wv["last_30_days"]["ERROR"] = canon["last_30_days"]["ERROR"] + 100
    wv["month_to_date"]["INFO"] = canon["month_to_date"]["INFO"] - 50
    fail_csv("04_wrong_values", rows_from(wv))

    # 05 exactly one count off by one (a date-boundary slip); catches imprecise verifiers
    nm = clone_counts()
    nm["last_7_days"]["ERROR"] = canon["last_7_days"]["ERROR"] + 1
    fail_csv("05_near_miss", rows_from(nm))

    # 06 ERROR counts computed by matching the substring "ERROR" (which also hits the
    #    trap WARNING lines) instead of the bracketed [ERROR] token; WARNING/INFO canonical.
    #    Catches verifiers that derive truth by loose matching. (Signature trap of this task.)
    et = clone_counts()
    for p in PERIODS:
        et[p]["ERROR"] = substr_error[p]
    assert all(et[p]["ERROR"] > canon[p]["ERROR"] for p in PERIODS), "trap must inflate ERROR"
    fail_csv("06_error_trap", rows_from(et))

    # 07 no output file, but a trajectory narrating success; catches trace-gullible verifiers
    d, _ = reset("07_logs_no_files")
    shutil.rmtree(os.path.join(d, "solution"))  # no solution files at all
    art = os.path.join(d, "artifacts")
    os.makedirs(art)
    json.dump({"messages": [
        {"role": "assistant", "content": "Scanning /app/logs and bucketing by date range..."},
        {"role": "assistant", "content": "Counted ERROR/WARNING/INFO for today, last_7_days, last_30_days, month_to_date, total."},
        {"role": "assistant", "content": "Wrote /app/summary.csv with all 15 rows."},
        {"role": "assistant", "content": "Done. summary.csv generated successfully; tests should pass."},
    ]}, open(os.path.join(art, "trajectory.json"), "w"), indent=2)
    labels["07_logs_no_files"] = "fail"

    # 08 right numbers, wrong container: pivoted table (period,ERROR,WARNING,INFO; 5 rows)
    #    instead of the declared long format; catches verifiers that skip the output contract
    _, sol = reset("08_wrong_shape")
    write_csv(os.path.join(sol, "summary.csv"), ["period", "ERROR", "WARNING", "INFO"],
              [(p, canon[p]["ERROR"], canon[p]["WARNING"], canon[p]["INFO"]) for p in PERIODS])
    labels["08_wrong_shape"] = "fail"

    # 09 nothing produced
    reset("09_nop")
    labels["09_nop"] = "fail"

    # 10 right values, wrong declared type: counts as floats (370.0); catches type-coercing
    #    verifiers that do int(float(x)) / float==float instead of enforcing an integer string
    fail_csv("10_count_as_float", [(p, s, f"{int(c)}.0") for (p, s, c) in canonical_rows])

    # 11 correct answer with every field quoted (valid RFC-4180 CSV); catches verifiers that
    #    split on commas by hand instead of parsing CSV, so a quoted "370" fails their check
    _, sol = reset("11_correct_quoted")
    with open(os.path.join(sol, "summary.csv"), "w", newline="") as f:
        w = csv.writer(f, quoting=csv.QUOTE_ALL)
        w.writerow(["period", "severity", "count"])
        w.writerows(canonical_rows)
    labels["11_correct_quoted"] = "pass"

    # 12 correct answer with the columns in a different order (still named in the header);
    #    catches verifiers that hardcode column positions instead of reading the header
    _, sol = reset("12_correct_reordered_cols")
    write_csv(os.path.join(sol, "summary.csv"), ["count", "period", "severity"],
              [(c, p, s) for (p, s, c) in canonical_rows])
    labels["12_correct_reordered_cols"] = "pass"

    os.makedirs(POOL, exist_ok=True)
    json.dump(labels, open(os.path.join(POOL, "labels.json"), "w"), indent=2)

    # Sync the generator into tests/ so the verifier image regenerates identical logs.
    shutil.copy2(GEN, os.path.join(ROOT, "tests", "log_generator_deterministic.py"))

    print(json.dumps(labels, indent=2))
    print(f"Pool written to {POOL}; generator synced to tests/")


if __name__ == "__main__":
    main()
