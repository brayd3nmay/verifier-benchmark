# Mini-Eval Report: Verifier Synthesis for Data-Science Tasks

## Summary

This eval measures a capability one level up from doing data science: **writing the
verifier** for a data-science task. The agent is handed a data problem and must produce the
grader that decides whether a given attempt solved it. That grader is then scored,
deterministically, against a hidden pool of labeled solutions — correct ones must pass,
adversarial ones must fail. No LLM judge: the judgment happened once, offline, when we
labeled the pool.

Scope note: this submission contains **two fully-built, hardened tasks**, deliberately a
matched pair:

- `samples/multi-source-data-verifier` — the **difficulty exemplar**. `gemini-3.5-flash`
  pass@3 = **0%** (3 × 0.818). Clears the take-home's < 30% bar with a consistent,
  diagnosable failure mode.
- `samples/log-summary-verifier` — an **honest contrast**. Same method, a different
  underlying task (date-ranged log-severity counting). `gemini-3.5-flash` pass@3 = **100%**
  (6 × 1.0). It is *not* a < 30% task, and I am not dressing it up as one.

I chose depth over breadth, and I kept the second task even though the model aced it, because
**the contrast is the result**: the pair isolates *what property makes a verifier-synthesis
target hard*, which is exactly the question the scale plan has to answer. `PLAYBOOK.md` (repo
root) is the reproducible SOP that produced both. The scale plan (§4) is how this becomes 10
and then 1,000 — and now includes the target-selection gate the contrast surfaced.

## 1. Distribution — what I chose to measure, and why this slice

The take-home is, at its core, about **verifiers** — the glossary and the "experiment with
different types of verifiers" hint make that explicit. So rather than test whether a model
can *perform* a data task (a capability frontier models largely have), I test whether it can
**verify** one: turn a data-correctness spec into a rigorous, non-gameable grader.

Why this is the interesting slice:
- **It's the bottleneck.** Verifier synthesis is the one unautomated step in the RL
  task-generation flywheel (Alex Shaw, Benchtalks #1): "we don't have a way of knowing how
  good our agents are at creating verifiers." Automate it and RL environments get cheap.
- **It's genuine DS/DE work.** Writing data-quality checks, reconciliation tests, and
  contract enforcement is what data engineers actually do; both underlying domains here
  (multi-source ETL merge; log aggregation) are production-style and in-scope.
- **The metric is clean.** Precision/recall against a labeled pool — no LLM-as-judge, fully
  deterministic and reproducible.

**Underlying tasks:**
- *Merge:* combine three user exports (JSON, CSV, Parquet) with inconsistent schemas into a
  standardized Parquet table plus a JSON conflict report, resolving disagreements by source
  priority.
- *Log-summary:* count ERROR/WARNING/INFO across five inclusive date ranges (today,
  last_7_days, last_30_days, month_to_date, total) over 41 days of date-stamped logs, into a
  `period,severity,count` CSV. Deterministic answer; a documented "trap" (one WARNING message
  contains the word "ERROR", to catch substring counters).

**In scope:** deriving ground truth from inputs; enforcing declared output types/formats;
tolerating valid representational variation (order, extra columns, quoting); resisting a
trajectory that merely *claims* success. **Out of scope:** subjective quality, model-building,
anything needing an LLM judge.

**Honest caveat on framing.** "The agent writes the verifier" is a meta-twist on "data
science task." I think it's defensible and on-brief (the whole take-home is about verifiers),
but a reviewer expecting a literal analyze-this-dataset task should know it's a deliberate
reinterpretation, not an oversight.

## 2. Difficulty profile vs `gemini-3.5-flash`

Three trials each of `harbor run -a terminus-2 -m gemini/gemini-3.5-flash` (logs under
`logs/<task>/`), pass = a *perfect* verifier (reward 1.0 / `all_correct`):

**Merge** (`multi-source-data-verifier`, 11-item pool):

| Trial | reward (accuracy) | all_correct | fp | fn | items missed |
| --- | --- | --- | --- | --- | --- |
| 1–3 | 0.818 (9/11) | 0 | 2 | 0 | `wrong_dtype_userid`, `wrong_date_format` |

→ **pass@1 = pass@3 = 0%.** Mean reward 0.818. Identical score and identical misses across
three independent runs — a *systematic* capability gap, not variance.

**Log-summary** (`log-summary-verifier`, 12-item pool):

| Trial | reward (accuracy) | all_correct | fp | fn |
| --- | --- | --- | --- | --- |
| 1–3 | 1.000 (12/12) | 1 | 0 | 0 |

→ **pass@1 = pass@3 = 100%.** (And 3 × 1.0 again on an earlier 10-item pool before hardening
— 6 × 1.0 total.) The model wrote a correct, robust verifier every time.

**Aggregate:** across the two tasks, pass@3 is 0% and 100% — a 2-point "curve" that is really
a *dichotomy*, and the dichotomy is the point (§3).

The bar is fractional (accuracy over the pool), so the pass number depends on where you set
the bar; I report mean reward as the difficulty curve and reserve pass@k for the 1.0 bar. For
the merge task, the road to 0.818 is itself the finding: the first pool tested only values
and file containers (8 items) and `gemini` scored 1.0 three times — no headroom. Diagnosing
why (§5) led to three "right value, wrong declared type" items, which opened the 0.818 gap.

## 3. The contrast — what makes a verifier-synthesis target hard

Same author, same method, same model, same anti-cheat — and a 0%/100% split. The difference
is entirely in the **underlying task's shape**, and pinning down which property drives it is
the most transferable thing in this submission (it's the Playbook Step-3 "is this a good
target?" question, answered with data).

Two properties separate a hard verifier-synthesis target from an easy one:

1. **Legitimate representational variation.** A hard target admits many correct-but-different
   outputs, so the verifier must *tolerate* variation while staying strict on substance — and
   an over-strict or byte-diff verifier gets caught. The merge output has rich variation: row
   order, column order, extra columns/files, conflict-list order, and a nested JSON report.
   The log-summary output is 15 fixed rows of `(period, severity, count)` — the only variation
   is row order, column order, and CSV quoting. Little room for discriminating PASS items.
2. **Declared, multiply-typed outputs.** The strongest pool items are "right value, wrong
   declared type" — they separate a verifier that *enforces a data contract* from one that
   merely *checks values by coercing types*. The merge output declares **five** typed fields
   (`user_id` integer, dates as `YYYY-MM-DD` strings, `status` an enum string, …), giving
   three independent dtype items — the exact items `gemini` fails. The log-summary output has
   **one** typed column (`count`, an integer). Its single dtype item (`count_as_float`,
   `370.0`) is real and the pool discriminates on it — but `gemini` handled it every time,
   because rejecting `370.0` from a single integer column is a much lower bar than enforcing a
   five-field contract with dates and enums.

The log-summary verification is genuinely simpler: parse a bracketed token, bucket by an
inclusive date range, count, compare integers. `gemini-3.5-flash` is *capable* of that end to
end (including the substring trap and the boundaries), so a rigorous pool can't manufacture a
gap the model doesn't have. **A verifier-synthesis task is only as hard as the contract the
verifier must enforce.** Constrained output + simple derivation ⇒ easy target; rich variation
+ multi-typed contract ⇒ hard target. That is the selection rule for the scale plan.

I *did* try to close the gap fairly first (Playbook Step 13): I hardened the log-summary pool
with two valid-variation PASS items — an RFC-4180 quoted CSV and a column-reordered CSV — that
catch non-robust verifiers (they caught 2 of the first 3 trials). But on re-capture the model
wrote fully-robust, CSV-aware, column-by-name verifiers 3/3. Pushing further would mean
overfitting items to specific verifier bugs (row-order-dependent duplicate handling, quoted
embedded newlines) — difficulty from tricks, not the problem. I stopped, per the playbook.

## 4. Research awareness

- **Alex Shaw — Benchtalks #1 (Terminal-Bench / Harbor).** The seed: the benchmark he most
  wants is one measuring agents' ability to write verifiers. Directly motivated this slice.
- **Terminal-Bench task-quality guidance.** Anti-patterns to avoid — over-prescriptive specs,
  assumed hidden knowledge, validating the wrong thing, reward-hackable verifiers;
  instructions should be short, adversarial, legible. Shaped the instruction discipline
  (anchoring/brevity) and the anti-cheat work — and the honesty about the 100% task.
- **hud.ai — "Verifier & reward design for RL environments."** Verifiers confirm the outcome;
  pass/fail guards hard rules; rubrics capture quality; the reward turns it into a training
  signal. Reinforced keeping the meta-verifier deterministic (no judge) with a fractional
  reward plus a binary `all_correct`.
- **DABStep (HuggingFace).** Real data analysis is dirty, distributed, and rarely
  straightforward — a good source of *hard-target* underlying tasks (§4 scale plan).

Takeaway across all four: the hard, valuable, under-measured thing is **verification
quality**, and the way to measure it cleanly is a hand-labeled adversarial pool, not a judge.

## 5. Scale plan (10 → 1,000)

The per-task cost is dominated by two things: authoring the underlying task and hand-labeling
the pool. Both are compressible — and the 0%/100% contrast adds a cheap up-front filter that
stops us from spending either on weak targets.

1. **Target-strength gate (new, from §3).** Before building the pool, score a candidate
   underlying task on the two properties: (a) does a correct output admit representational
   variation? (b) does it declare ≥2 typed fields? Operationalize it: run a *naive* reference
   verifier (values only, coercing) and a *strict* one against a handful of model-generated
   outputs; if their scores don't diverge, the task can't discriminate verifier rigor — kick
   it back before labeling. Log-summary would have been flagged here (one typed field, minimal
   variation) and kept only as a deliberate control.
2. **Producer + verifier-maker pairing.** Instead of hand-authoring every pool item, run a
   *producer* pass — a normal agent solving the underlying task many times — and harvest its
   genuinely-correct and genuinely-wrong outputs. Self-label those (cheap, one-time). The
   producer's natural variation gives `correct_alt`-style PASS items and organic FAIL items
   for free; hand-craft only the adversarial cases agents rarely produce (the trace trap, the
   wrong-dtype items).
3. **Underlying-task sources.** Public Kaggle notebooks, terminal-bench / Harbor hub tasks,
   DABStep-style analysis problems, production ETL patterns — filtered by the §4.1 gate for a
   deterministic answer, declared types, and real variation.
4. **Augmentation.** Once you have one canonical answer, pool items are cheap perturbations of
   it (`_build_pool.py` shows the pattern: one mutation → one FAIL item). New datasets multiply
   the base; perturbation multiplies the pool per dataset.
5. **QA loop — automated gates** (from `PLAYBOOK.md`, all deterministic): (a) oracle scores
   the pool 1.0 (solvable + self-consistent labels); (b) a weak/coercing verifier scores < 1.0
   (the pool discriminates); (c) the §4.1 target-strength divergence check; (d) `gemini`
   pass@3 < 30% (headroom). A task that fails a gate is auto-kicked. This is what keeps quality
   up as volume grows, human-free per task once labels exist.

## 6. Failure analysis — both directions are genuine

**Merge — a real capability gap, not a task-design bug.** All three trials fail identically on
two items, and the trajectories + captured `verify.py` show why: `gemini`'s verifier
**coerces** the declared types instead of enforcing them — `df["user_id"].astype(int)` (so a
string `"101"` passes, but the spec declares `user_id` an integer) and
`pd.to_datetime(...).dt.strftime(...)` (so a datetime column passes, but the spec declares a
`YYYY-MM-DD` string). This clears every "is it a task bug?" check: the types are explicitly
declared; the oracle scores 1.0 in the same env; the strict behavior *is* correct (and the
model enforced the boolean `status` type correctly in these very runs — it just didn't
generalize the rigor); and the clean-room + `nobody`-sandbox make the answer key unreadable, so
it isn't reward-hacking. The model can write a verifier that *checks values*, but not reliably
one that *enforces a data contract*.

**Log-summary — a genuine non-gap, verified not a task bug.** The 100% is real capability, not
a broken pool. Evidence the pool is rigorous and discriminating: the oracle scores 12/12; a
files-exist-only verifier scores **7/12 (0.58)**; a bracket-correct-but-coercing/positional
verifier scores **10/12 (0.83)**; the first-round non-robust `gemini` verifiers (naive
`split(',')`, hardcoded columns) score 10/12 and 11/12 on the hardened pool. So weak verifiers
*are* caught — the model simply wrote strong ones. The anti-cheat holds identically to the
merge task (a label-reading verifier is denied and collapses to baseline; nop scores 0).
Inspecting the three captured verifiers: all use the `csv` module, identify columns by header
name, parse the bracketed severity token (dodging the substring trap), compute inclusive date
boundaries correctly, and reject non-integer counts. There is no fair item that a correct
verifier of this task should pass but these fail. The honest conclusion (§3): the *task* is an
easy verifier-synthesis target, and that is a finding about task selection, not a defect.

## Appendix — reproduce

`PLAYBOOK.md` (repo root) is the full SOP for both tasks: design the underlying task,
hand-compute the canonical answer, design the anchored pool (including the discriminating
dtype items), write the situation-voice instruction and the verifier contract, wire the
separate clean-room verifier env with `nobody`-sandboxed grading, write the oracle, and run
the validation gates before the `gemini-3.5-flash` capture. Both tasks pass the deterministic
gates (oracle 1.0; pool discriminates; anti-cheat denied; nop 0; `harbor check` clean); their
`gemini` logs are in `logs/`.

---

## Rough thoughts (unrefined — to polish later)

Raw notes to self; not yet report-ready.

- **The 0%/100% pair is the strongest asset here — foreground it.** The single most
  generalizable output of this whole exercise is the §3 selection rule (variation + typed
  contract). It turns "we built some tasks" into "we know which tasks are worth building,"
  which is what a 1,000-task pipeline actually needs. Consider leading with it.
- **Binary vs fractional reward — the PDF asks us to justify this.** Went fractional
  (accuracy) + a binary `all_correct`. Fractional gives a smoother RL signal and a real
  difficulty curve; binary is cleaner for pass@k and harder. Worth a paragraph defending
  fractional-with-a-1.0-bar. For log-summary, note pass@k alone (100%) hides that the pool
  still separates weak verifiers by mean reward — an argument for reporting both.
- **Determinism caveat.** Merge returned *identical* 0.818 and identical misses three times;
  log-summary returned identical 1.0 six times. Either very systematic behavior (good) or
  `terminus-2`/gemini being near-deterministic at low temp (then pass@3 ≈ pass@1). Worth a
  temp>0 or larger-N run to show it's not just determinism.
- **Producer + verifier-maker pairing is UNTESTED.** It's the scale story but I haven't run
  it. Pilot it once or clearly label it as proposed.
- **Brief wants 5–10 tasks; I have 2.** Be upfront. The playbook is the recipe. Realistically
  build 3–4 hard targets (ETL merge, dirty-data clean, a nested-JSON report with typed fields)
  — all things that clear the §4.1 gate — so the difficulty curve is an actual curve. Keep
  log-summary as the documented easy control.
- **The "original verifier's blind spots → pool items" trick is very generalizable** and
  deserves foregrounding — it's how you make adversarial items cheaply for any target.
- **Anti-cheat is heavy** (clean-room env + `nobody`). Justified because reward-hacking is a
  known LLM behavior, but note the tradeoff; a lighter shared-env + `nobody` version exists.
