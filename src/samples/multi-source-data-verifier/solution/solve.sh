#!/bin/bash
# Oracle solution: write a correct reference verifier to /app/verifier/verify.sh.
# The harness runs it against the labeled pool; it must classify every item correctly
# (reward 1.0). This is what "a good verifier" looks like for this task.
set -euo pipefail

mkdir -p /app/verifier

# The reference verifier: derive the one correct answer from the sources, then check the
# candidate's files against it — tolerant of order/extras, strict on values and shape.
cat > /app/verifier/ref_verify.py <<'PYEOF'
import json
import os
import sys

import pandas as pd

SOL = os.environ.get("SOLUTION_DIR", "/app")
VERDICT = os.environ.get("VERDICT_FILE", "/logs/verifier/reward.txt")
DATA = os.environ.get("DATA_DIR", "/app/data")


def emit(ok, msg=""):
    d = os.path.dirname(VERDICT)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(VERDICT, "w") as f:
        f.write("1" if ok else "0")
    print(("PASS" if ok else "FAIL"), msg)
    sys.exit(0)


def canonical():
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

    conflicts = set()
    for uid in alld["user_id"].unique():
        recs = alld[alld["user_id"] == uid].sort_values("_p")
        if len(recs) > 1:
            for field in ["name", "email", "created_date"]:
                vals = {}
                for _, r in recs.iterrows():
                    if pd.notna(r.get(field)):
                        vals[r["_s"]] = str(r[field])
                if len(set(vals.values())) > 1:
                    conflicts.add((int(uid), field,
                                   tuple(sorted(vals.items())), str(recs.iloc[0][field])))

    merged = alld.sort_values("_p").groupby("user_id").first().reset_index()
    users = {}
    for _, r in merged.iterrows():
        users[int(r["user_id"])] = {
            "name": str(r["name"]), "email": str(r["email"]),
            "created_date": str(r["created_date"]), "status": str(r["status"]),
        }
    return users, conflicts


exp_users, exp_conflicts = canonical()

mp = os.path.join(SOL, "merged_users.parquet")
if not os.path.isfile(mp):
    emit(False, "missing merged_users.parquet")
try:
    df = pd.read_parquet(mp)
except Exception as e:
    emit(False, f"unreadable parquet: {e}")

for col in ["user_id", "name", "email", "created_date", "status"]:
    if col not in df.columns:
        emit(False, f"missing column {col}")
if not pd.api.types.is_integer_dtype(df["user_id"]):
    emit(False, "user_id is not integer")

got = {int(r["user_id"]): r for _, r in df.iterrows()}
if set(got) != set(exp_users):
    emit(False, f"user set {sorted(got)} != {sorted(exp_users)}")
if len(df) != len(exp_users):
    emit(False, f"row count {len(df)} != {len(exp_users)} (duplicate users?)")
for uid, want in exp_users.items():
    row = got[uid]
    for field, val in want.items():
        if str(row[field]) != val:
            emit(False, f"user {uid} {field}={row[field]!r} want {val!r}")

cj = os.path.join(SOL, "conflicts.json")
if not os.path.isfile(cj):
    emit(False, "missing conflicts.json")
try:
    obj = json.load(open(cj))
except Exception as e:
    emit(False, f"unreadable conflicts.json: {e}")
if not isinstance(obj, dict):
    emit(False, "conflicts.json is not an object")
if "total_conflicts" not in obj or "conflicts" not in obj:
    emit(False, "conflicts.json missing total_conflicts/conflicts")
if not isinstance(obj["conflicts"], list):
    emit(False, "conflicts is not a list")
if obj["total_conflicts"] != len(obj["conflicts"]):
    emit(False, "total_conflicts != len(conflicts)")

got_conf = set()
for entry in obj["conflicts"]:
    try:
        got_conf.add((int(entry["user_id"]), entry["field"],
                      tuple(sorted((k, str(v)) for k, v in entry["values"].items())),
                      str(entry["selected"])))
    except Exception as e:
        emit(False, f"malformed conflict entry: {e}")
if got_conf != exp_conflicts:
    emit(False, "conflicts do not match expected set")

emit(True, "all checks passed")
PYEOF

cat > /app/verifier/verify.sh <<'SHEOF'
#!/bin/bash
python3 /app/verifier/ref_verify.py
SHEOF

chmod +x /app/verifier/verify.sh
echo "Reference verifier written to /app/verifier/verify.sh"
