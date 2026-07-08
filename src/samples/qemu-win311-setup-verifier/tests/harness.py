#!/usr/bin/env python3
"""Grade the agent's verifier against the labeled pool.

The agent was asked to write /app/verifier/verify.sh. We run it once per pool item,
handing it a candidate solution via $SOLUTION_DIR / $ARTIFACTS_DIR and reading its
verdict from $VERDICT_FILE (1 = the candidate is correct, 0 = incorrect). We compare
those verdicts to our hidden labels and emit precision/recall/accuracy.

Security model (see README):
- The candidate verifier is untrusted code. We run it as an unprivileged user ("nobody")
  and lock the pool + labels so it cannot read the answer key and echo it back.
- The harness itself runs as root and is the only thing that reads labels or writes the
  reward. In a separate verifier environment it also runs clean-room — the agent never
  touched this container.

Conventions:
- A run that crashes, times out, or writes no parseable verdict counts as verdict 0
  (a verifier that can't render a judgment is treated as declaring "not correct").
- "positive" = the verifier says PASS. FP (accepting a bad solution) and FN (rejecting a
  good one) are both penalized; accuracy is the headline reward.
"""
import grp
import json
import os
import pwd
import random
import shutil
import subprocess
import sys
import tempfile

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
POOL_DIR = os.path.join(TESTS_DIR, "pool")
LABELS_PATH = os.path.join(POOL_DIR, "labels.json")
VERIFIER_HOME = "/app/verifier"
REWARD_JSON = "/logs/verifier/reward.json"
REWARD_TXT = "/logs/verifier/reward.txt"
PER_ITEM_TIMEOUT_SEC = 120

try:
    UNPRIV_UID = pwd.getpwnam("nobody").pw_uid
    try:
        UNPRIV_GID = grp.getgrnam("nogroup").gr_gid
    except KeyError:
        UNPRIV_GID = pwd.getpwnam("nobody").pw_gid
except KeyError:
    UNPRIV_UID = UNPRIV_GID = None

CAN_DEMOTE = os.geteuid() == 0 and UNPRIV_UID is not None


def write_reward(rewards: dict):
    os.makedirs(os.path.dirname(REWARD_JSON), exist_ok=True)
    with open(REWARD_JSON, "w") as f:
        json.dump(rewards, f, indent=2)
    with open(REWARD_TXT, "w") as f:
        f.write(str(rewards.get("reward", 0)))


def zero_reward(**flags):
    """Canonical reward keys all zero, plus any error flag, so every failure path emits
    the same shape."""
    r = {"reward": 0.0, "accuracy": 0.0, "precision": 0.0, "recall": 0.0, "f1": 0.0,
         "all_correct": 0, "tp": 0, "fp": 0, "fn": 0, "tn": 0, "n": 0}
    r.update(flags)
    return r


def lock_pool():
    """Make the pool + labels unreadable to the unprivileged candidate verifier."""
    subprocess.run(["chmod", "-R", "go-rwx", POOL_DIR], check=False)


def prepare_verifier():
    """Locate the agent's verifier and normalize it to /app/verifier/verify.sh.

    Shared mode: it's already at /app/verifier. Separate mode: it was collected as an
    artifact under /logs/artifacts/... — copy it to /app/verifier so any sibling files
    the agent referenced by that path still resolve.
    """
    if not os.path.isfile(os.path.join(VERIFIER_HOME, "verify.sh")):
        found = None
        for root, _dirs, files in os.walk("/logs/artifacts"):
            if "verify.sh" in files:
                found = root
                break
        if found is None:
            return None
        shutil.rmtree(VERIFIER_HOME, ignore_errors=True)
        shutil.copytree(found, VERIFIER_HOME)
    # The unprivileged user must be able to read/execute the verifier code.
    subprocess.run(["chmod", "-R", "a+rX", VERIFIER_HOME], check=False)
    return os.path.join(VERIFIER_HOME, "verify.sh")


def _demote():
    os.setgid(UNPRIV_GID)
    os.setuid(UNPRIV_UID)


def parse_verdict(path: str) -> int:
    try:
        raw = open(path).read().strip().lower()
    except OSError:
        return 0
    if raw in {"pass", "true", "correct"}:
        return 1
    if raw in {"fail", "false", "incorrect", ""}:
        return 0
    try:
        return 1 if float(raw) >= 0.5 else 0
    except ValueError:
        return 0


def run_verifier_on(verifier: str, item_dir: str) -> tuple[int, str]:
    work = tempfile.mkdtemp(prefix="pool_")
    try:
        sol = os.path.join(work, "solution")
        art = os.path.join(work, "artifacts")
        os.makedirs(sol)
        os.makedirs(art)
        src_sol = os.path.join(item_dir, "solution")
        src_art = os.path.join(item_dir, "artifacts")
        if os.path.isdir(src_sol):
            shutil.copytree(src_sol, sol, dirs_exist_ok=True)
        if os.path.isdir(src_art):
            shutil.copytree(src_art, art, dirs_exist_ok=True)
        verdict_file = os.path.join(work, "verdict")

        # The candidate runs unprivileged; give it a readable/writable sandbox + tmp.
        # (Staged copies inherit the pool's locked-down perms, so re-open them here — the
        # originals under /tests/pool stay root-only.)
        subprocess.run(["chmod", "-R", "a+rwX", work], check=False)

        env = {
            "PATH": "/usr/local/bin:/usr/bin:/bin",
            "SOLUTION_DIR": sol,
            "ARTIFACTS_DIR": art,
            "VERDICT_FILE": verdict_file,
            "TMPDIR": work,
            "HOME": work,
        }
        try:
            proc = subprocess.run(
                ["bash", verifier],
                env=env,
                cwd=VERIFIER_HOME,
                timeout=PER_ITEM_TIMEOUT_SEC,
                capture_output=True,
                text=True,
                preexec_fn=_demote if CAN_DEMOTE else None,
            )
        except subprocess.TimeoutExpired:
            return 0, "timeout"
        out = ((proc.stdout or "") + (proc.stderr or "")).strip()
        tail = out.splitlines()[-1] if out else ""
        note = tail if proc.returncode == 0 else f"exit={proc.returncode} {tail}"
        return parse_verdict(verdict_file), note
    finally:
        shutil.rmtree(work, ignore_errors=True)


def main():
    labels = json.load(open(LABELS_PATH))
    verifier = prepare_verifier()
    lock_pool()  # after reading labels/staging is done by root; before running candidates

    if verifier is None:
        write_reward(zero_reward(error_no_verifier=1))
        print(f"No verify.sh found (looked in {VERIFIER_HOME} and /logs/artifacts); scored 0.")
        return

    if not CAN_DEMOTE:
        print("WARNING: not running as root or no 'nobody' user; candidate verifier runs "
              "with the harness's privileges (label isolation not enforced).", file=sys.stderr)

    # Randomize order so a verifier can't game a fixed pass/fail sequence by counting
    # invocations in persistent state (e.g. /tmp) instead of reading each bundle. Scoring
    # is order-independent, so this never affects an honest verifier's reward.
    items = sorted(labels.keys())
    random.shuffle(items)
    tp = fp = fn = tn = 0
    rows = []
    for item in items:
        label_pass = labels[item] == "pass"
        verdict, note = run_verifier_on(verifier, os.path.join(POOL_DIR, item))
        verdict_pass = verdict == 1
        correct = verdict_pass == label_pass
        if label_pass and verdict_pass:
            tp += 1
        elif (not label_pass) and verdict_pass:
            fp += 1
        elif label_pass and (not verdict_pass):
            fn += 1
        else:
            tn += 1
        rows.append((item, labels[item], "pass" if verdict_pass else "fail", correct, note))

    n = len(items)
    accuracy = (tp + tn) / n if n else 0.0
    precision = tp / (tp + fp) if (tp + fp) else 1.0
    recall = tp / (tp + fn) if (tp + fn) else 1.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0

    print(f"{'item':<22}{'label':<8}{'verdict':<9}{'ok':<4}note")
    for item, lab, ver, ok, note in rows:
        print(f"{item:<22}{lab:<8}{ver:<9}{('Y' if ok else 'N'):<4}{note}")
    print(f"\nTP={tp} FP={fp} FN={fn} TN={tn}  "
          f"accuracy={accuracy:.3f} precision={precision:.3f} recall={recall:.3f} f1={f1:.3f}")

    write_reward({
        "reward": round(accuracy, 4),
        "accuracy": round(accuracy, 4),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "all_correct": 1 if (fp == 0 and fn == 0) else 0,
        "tp": tp, "fp": fp, "fn": fn, "tn": tn, "n": n,
    })


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # never leave Harbor without a reward file
        write_reward(zero_reward(error=1))
        print(f"harness error: {e}", file=sys.stderr)
        raise
