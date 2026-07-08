#!/usr/bin/env python3
"""Materialize the labeled pool the agent's verifier is graded against.

Run from the task root (needs pandas + pyarrow):

    uv run --with pandas --with pyarrow python _build_pool.py

Writes tests/pool/<NN_name>/solution/... (candidate output files), optional
tests/pool/<NN_name>/artifacts/... (agent logs/trajectory), and tests/pool/labels.json.
The pool is the answer key: a correct verifier PASSes every "pass" item and FAILs every
"fail" item. Each item is built by perturbing the canonical answer, which is derived
here from the real source files so it can't drift.
"""
import json
import os
import shutil

import pandas as pd

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "environment", "data")
POOL = os.path.join(ROOT, "tests", "pool")


def canonical():
    """Re-derive the one correct merged table + conflict report from the sources."""
    a = pd.DataFrame(json.load(open(f"{DATA}/source_a/users.json")))
    b = pd.read_csv(f"{DATA}/source_b/users.csv")
    c = pd.read_parquet(f"{DATA}/source_c/users.parquet")
    a = a.rename(columns={"id": "user_id", "full_name": "name", "registration_date": "created_date"})
    b = b.rename(columns={"email_address": "email", "created_at": "created_date", "is_active": "status"})
    b["status"] = b["status"].map({True: "active", False: "inactive"})
    c = c.rename(columns={"userId": "user_id", "userName": "name", "joined": "created_date", "active": "status"})
    c["status"] = c["status"].map({True: "active", False: "inactive"})
    a["_s"], a["_p"] = "source_a", 1
    b["_s"], b["_p"] = "source_b", 2
    c["_s"], c["_p"] = "source_c", 3
    alld = pd.concat([a, b, c], ignore_index=True)

    conflicts = []
    for uid in sorted(alld["user_id"].unique()):
        recs = alld[alld["user_id"] == uid].sort_values("_p")
        if len(recs) > 1:
            for field in ["name", "email", "created_date"]:
                vals = {}
                for _, r in recs.iterrows():
                    if pd.notna(r.get(field)):
                        vals[r["_s"]] = str(r[field])
                if len(set(vals.values())) > 1:
                    conflicts.append(
                        {"user_id": int(uid), "field": field, "values": vals,
                         "selected": str(recs.iloc[0][field])}
                    )

    merged = (
        alld.sort_values("_p").groupby("user_id").first().reset_index().drop(columns=["_s", "_p"])
    )
    merged = merged[["user_id", "name", "email", "created_date", "status"]]
    merged["user_id"] = merged["user_id"].astype("int64")
    return merged, {"total_conflicts": len(conflicts), "conflicts": conflicts}


def reset(name):
    d = os.path.join(POOL, name)
    if os.path.exists(d):
        shutil.rmtree(d)
    sol = os.path.join(d, "solution")
    os.makedirs(sol)
    return d, sol


def wj(obj, path):
    json.dump(obj, open(path, "w"), indent=2)


def main():
    merged, report = canonical()
    # Guard against the ground truth silently changing.
    assert set(merged["user_id"]) == {101, 102, 103, 104}, merged["user_id"].tolist()
    assert report["total_conflicts"] == 3, report["total_conflicts"]

    labels = {}

    def fail_item(name, df):
        """A perturbed merged table plus the canonical conflict report; labeled fail."""
        _, sol = reset(name)
        df.to_parquet(f"{sol}/merged_users.parquet", index=False)
        wj(report, f"{sol}/conflicts.json")
        labels[name] = "fail"

    # baseline: the canonical answer every verifier must pass
    _, sol = reset("01_oracle")
    merged.to_parquet(f"{sol}/merged_users.parquet", index=False)
    wj(report, f"{sol}/conflicts.json")
    labels["01_oracle"] = "pass"

    # correct answer in a different representation; catches order-assuming verifiers
    _, sol = reset("02_correct_alt")
    alt = merged.iloc[::-1].reset_index(drop=True)[["status", "email", "user_id", "created_date", "name"]]
    alt.to_parquet(f"{sol}/merged_users.parquet", index=False)
    wj({"conflicts": list(reversed(report["conflicts"])), "total_conflicts": report["total_conflicts"]},
       f"{sol}/conflicts.json")
    labels["02_correct_alt"] = "pass"

    # correct answer with harmless extras; catches over-strict verifiers
    _, sol = reset("03_correct_superset")
    sup = merged.copy()
    sup["_ingested_at"] = "2026-07-08"
    sup.to_parquet(f"{sol}/merged_users.parquet", index=False)
    wj({"total_conflicts": report["total_conflicts"],
        "conflicts": [{**c, "note": "auto-detected"} for c in report["conflicts"]]},
       f"{sol}/conflicts.json")
    open(f"{sol}/summary.txt", "w").write("Merged 4 users; 3 conflicts on user 101.\n")
    labels["03_correct_superset"] = "pass"

    # wrong values on users a lazy verifier won't spot-check
    wv = merged.copy()
    wv.loc[wv["user_id"] == 102, "email"] = "jane@wrong.com"
    wv.loc[wv["user_id"] == 103, "name"] = "Bob Wrong"
    fail_item("04_wrong_values", wv)

    # exactly one value wrong; catches imprecise verifiers
    nm = merged.copy()
    nm.loc[nm["user_id"] == 103, "created_date"] = "2024-03-02"
    fail_item("05_near_miss", nm)

    # no output files, but a trajectory narrating success; catches trace-gullible verifiers
    d, sol = reset("06_logs_no_files")
    art = os.path.join(d, "artifacts")
    os.makedirs(art)
    wj({"messages": [
        {"role": "assistant", "content": "Reading /app/data sources..."},
        {"role": "assistant", "content": "Merged 4 unique users: 101, 102, 103, 104."},
        {"role": "assistant", "content": "Wrote /app/merged_users.parquet and /app/conflicts.json (total_conflicts=3)."},
        {"role": "assistant", "content": "Done. All outputs generated successfully; tests should pass."},
    ]}, f"{art}/trajectory.json")
    labels["06_logs_no_files"] = "fail"

    # correct data in the wrong containers; catches verifiers that skip the output contract
    _, sol = reset("07_wrong_shape")
    merged.to_csv(f"{sol}/merged_users.csv", index=False)
    wj(report["conflicts"], f"{sol}/conflicts.json")
    labels["07_wrong_shape"] = "fail"

    reset("08_nop")
    labels["08_nop"] = "fail"

    # 09-11: right values, wrong declared type/format — separate verifiers that enforce
    # the spec's types from ones that coerce (astype/to_datetime) and only compare values.
    fail_item("09_wrong_dtype_userid", merged.assign(user_id=merged["user_id"].astype(str)))
    fail_item("10_wrong_date_format", merged.assign(created_date=pd.to_datetime(merged["created_date"])))
    fail_item("11_status_wrong_type", merged.assign(status=merged["status"].map({"active": True, "inactive": False})))

    wj(labels, os.path.join(POOL, "labels.json"))

    # Keep the verifier image's pristine data copy identical to the pool's basis, so the
    # truth the verifier derives at grade time matches how the pool was labeled.
    tests_data = os.path.join(ROOT, "tests", "data")
    if os.path.exists(tests_data):
        shutil.rmtree(tests_data)
    shutil.copytree(DATA, tests_data)

    print(json.dumps(labels, indent=2))
    print(f"Pool written to {POOL}; tests/data synced from {DATA}")


if __name__ == "__main__":
    main()
