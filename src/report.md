# Mini-Eval Report: Verifier Synthesis for Data-Science Tasks

## Summary

This eval measures a capability one level up from doing data science: **writing the
verifier** for a data-science task. The agent is handed a data-merge problem and must
produce the grader that decides whether a given attempt solved it. That grader is then
scored, deterministically, against a hidden pool of labeled solutions — correct ones must
pass, adversarial ones must fail.

Scope note: this submission contains **two fully-built, hardened exemplar tasks** —
`samples/multi-source-data-verifier` (a data/ETL domain) and
`samples/qemu-win311-setup-verifier` (a systems/virtualization domain) — plus the
methodology and tooling to generate the rest (`PLAYBOOK.md` at the repo root is the
reproducible SOP). I chose depth over breadth deliberately — tasks that genuinely isolate a
failure mode, with the anti-cheat and validation worked all the way through, are more
informative than a pile of shallow ones. The two span different domains on purpose (see
Task 2), so the difficulty signal is a small curve rather than a point. The scale plan
(below) is how this becomes 10 and then 1,000.

## 1. Distribution — what I chose to measure, and why this slice

The take-home is, at its core, about **verifiers** — the glossary and the "experiment with
different types of verifiers" hint make that explicit. So rather than test whether a model
can *perform* an ETL merge (a capability frontier models largely have), I test whether it
can **verify** one: turn a data-correctness spec into a rigorous, non-gameable grader.

Why this is the interesting slice:
- **It's the bottleneck.** Verifier synthesis is the one unautomated step in the RL
  task-generation flywheel (Alex Shaw, Benchtalks #1): "we don't have a way of knowing how
  good our agents are at creating verifiers." Automate it and RL environments get cheap.
- **It's genuine DS/DE work.** Writing data-quality checks, reconciliation tests, and
  contract enforcement is what data engineers actually do; the underlying domain here is a
  production-style multi-source ETL merge, which the brief lists as in-scope.
- **The metric is clean.** Precision/recall against a labeled pool — no LLM-as-judge, fully
  deterministic and reproducible.

**Underlying task:** merge three user exports (JSON, CSV, Parquet) with inconsistent
schemas into a standardized Parquet table plus a JSON conflict report, resolving
disagreements by source priority. Deterministic answer, many valid approaches.

**In scope:** deriving ground truth from inputs; enforcing declared output types/formats;
tolerating valid representational variation (order, extra columns); resisting a trajectory
that merely *claims* success. **Out of scope:** subjective quality, model-building,
anything needing an LLM judge.

**Honest caveat on framing.** "The agent writes the verifier" is a meta-twist on "data
science task." I think it's defensible and on-brief (the whole take-home is about
verifiers), but a reviewer expecting a literal analyze-this-dataset task should know it's a
deliberate reinterpretation, not an oversight.

## 2. Difficulty profile vs `gemini-3.5-flash`

Three trials of `harbor run -p samples/multi-source-data-verifier -a terminus-2 -m
gemini/gemini-3.5-flash` (logs in `logs/multi-source-data-verifier/`):

| Trial | reward (accuracy) | all_correct | fp | fn | items missed |
| --- | --- | --- | --- | --- | --- |
| 1 | 0.818 (9/11) | 0 | 2 | 0 | `wrong_dtype_userid`, `wrong_date_format` |
| 2 | 0.818 (9/11) | 0 | 2 | 0 | `wrong_dtype_userid`, `wrong_date_format` |
| 3 | 0.818 (9/11) | 0 | 2 | 0 | `wrong_dtype_userid`, `wrong_date_format` |

- **pass@1 = 0%, pass@3 = 0%** at the natural bar (a *correct* verifier = reward 1.0 /
  `all_correct`). Under the take-home's < 30% pass@3 target, this clears it — with room to
  spare, and without being impossible (the oracle scores 1.0).
- The reward is **fractional** (accuracy over the pool), so the pass number depends on the
  bar you set: 0% at the perfect-1.0 bar; mean reward **0.818** is the finer signal. I'd
  report the mean reward as the difficulty curve and reserve pass@k for the 1.0 bar.
- **Remarkable consistency** (identical score and identical misses across three
  independent runs) says this is a *systematic* capability gap, not variance — exactly what
  you want difficulty to come from.

**The road to this number is itself the finding.** The first version of the pool tested
only values and file containers (8 items). `gemini-3.5-flash` wrote a competent
reference-implementation verifier and scored **1.0 three times** — no headroom. Diagnosing
why (Section 5) led to three "right value, wrong declared type" items, which is what opened
the 0.818 gap. A value-only pool cannot separate a strict verifier from a lenient one.

## 3. Research awareness

- **Alex Shaw — Benchtalks #1 (Terminal-Bench / Harbor).** The seed: the benchmark he most
  wants is one measuring agents' ability to write verifiers. Directly motivated this slice.
- **Terminal-Bench task-quality guidance.** Anti-patterns to avoid — over-prescriptive
  specs, assumed hidden knowledge, validating the wrong thing, reward-hackable verifiers;
  instructions should be short, adversarial, legible. Shaped the instruction discipline
  (Section on anchoring/brevity) and the anti-cheat work.
- **hud.ai — "Verifier & reward design for RL environments."** Verifiers confirm the
  outcome; pass/fail guards hard rules; rubrics capture quality; the reward turns it into a
  training signal. Reinforced keeping the meta-verifier deterministic (no judge) with a
  fractional reward plus a binary `all_correct`.
- **DABStep (HuggingFace).** Real data analysis is dirty, distributed, and rarely
  straightforward — a good source of realistic underlying tasks for the scale plan.

Takeaway across all four: the hard, valuable, under-measured thing is **verification
quality**, and the way to measure it cleanly is a hand-labeled adversarial pool, not a
judge.

## 4. Scale plan (10 → 1,000)

The per-task cost is dominated by two things: authoring the underlying task and
hand-labeling the pool. Both are compressible.

1. **Producer + verifier-maker pairing.** Instead of hand-authoring every pool item, run a
   *producer* pass — a normal agent solving the underlying task many times — and harvest
   its genuinely-correct and genuinely-wrong outputs. Self-label those (cheap, one-time)
   into the pool. The producer's natural variation gives you `correct_alt`-style PASS items
   and organic FAIL items for free; hand-craft only the adversarial cases agents rarely
   produce (the `logs_no_files` trace trap, the wrong-dtype items).
2. **Underlying-task sources.** Public Kaggle notebooks, terminal-bench / Harbor dataset
   hub tasks, DABStep-style analysis problems, production ETL patterns. Pick ones with a
   deterministic answer and declared output types (the requirement that makes the
   discriminating dtype items possible).
3. **Augmentation.** Once you have one canonical answer, pool items are cheap perturbations
   of it (`_build_pool.py` shows the pattern: one mutation → one FAIL item). New underlying
   datasets multiply the base; perturbation multiplies the pool per dataset.
4. **QA loop — three automated gates** (from `PLAYBOOK.md`, all deterministic):
   (a) oracle scores the pool 1.0 (solvable + self-consistent labels);
   (b) a weak/coercing verifier scores < 1.0 (the pool discriminates);
   (c) `gemini-3.5-flash` pass@3 < 30% (headroom). A task that fails any gate is auto-kicked
   back. This is what keeps quality up as volume grows, and it needs no human in the loop
   per task once the labels exist.

## 5. Failure analysis — genuine difficulty, not a task-design bug

All three trials fail identically on two items, and the trajectories + the captured
`verify.py` show exactly why. Gemini's verifier **coerces** the declared types instead of
enforcing them:
- `wrong_dtype_userid`: it does `df["user_id"].astype(int)`, so a string `"101"` is
  silently coerced to `101` and passes — but the spec declares `user_id` an **integer**.
- `wrong_date_format`: it does `pd.to_datetime(...).dt.strftime(...)`, so a datetime column
  is reparsed and passes — but the spec declares `created_date` a **`YYYY-MM-DD` string**.

This is a real capability gap, not a task artifact, and it clears every "is this a
task-design bug?" check:
- **Not an ambiguous instruction.** The instruction explicitly declares the types
  (`integer`, `string in YYYY-MM-DD format`); the failing items violate stated rules.
- **Not a broken environment.** The oracle, in the same environment, scores 1.0.
- **Not an over-strict verifier.** The strict behavior is the *correct* behavior — and the
  model *is* capable of it (it enforced the boolean `status` type correctly in these very
  runs; it just didn't generalize the rigor to `user_id` and dates).
- **Not reward hacking.** The clean-room verifier env + `nobody`-sandboxed execution make
  the answer key unreadable; a label-reading verifier is denied and collapses to baseline.

In one line: the model can *write a verifier that checks values*, but not reliably one that
*enforces a data contract*. That gap is the headroom, and it's the kind of thing better
models should close — which is exactly what a good eval should surface.

## Task 2 — QEMU Windows 3.11 Setup Verifier (a second domain)

The second task (`samples/qemu-win311-setup-verifier`) applies the same verifier-writing
frame to a **systems/virtualization** domain, to show the difficulty comes from the method,
not one lucky dataset. The underlying task is terminal-bench-2's `install-windows-3.11`: run
Windows 3.11 in QEMU with VNC (5901), a web interface (80), the base disk image kept
immutable, and a monitor socket for programmatic keyboard input.

**The reframe.** That underlying task is *live-runtime* — its original verifier introspects a
running machine (`pgrep`, `/proc/PID/cmdline`, `netstat`, a live monitor socket, VNC pixel
diffs). That doesn't fit a static, deterministic pool. So each candidate "solution" is
reframed as a captured **evidence bundle** of a setup attempt (`qemu_cmdline.txt`,
`listening_ports.txt`, `base_image.img`, before/after VNC screenshots), and the agent writes a
verifier that grades the bundle. Grading stays fully deterministic and reuses the same
clean-room harness. It's a deliberate reinterpretation (captured evidence, not a live system),
noted as such.

**Instruction discipline — outcomes, not a checklist.** The sharpest lesson from building this
one: the instruction must state the *underlying task's outcomes* (VNC reachable on 5901; the
base image stays pristine because the running VM can't write to it; a programmatically-sent
keystroke reaches the VM), **not** the QEMU flags a verifier should grep for (`-snapshot`,
`-monitor unix:`, a pixel threshold). Handing over the check-list turns verifier-writing into
string-matching and destroys the task. The interesting checks then have to be *derived* from
the outcomes — and a single outcome often decomposes into two checks the model must both find.

**Difficulty profile vs `gemini-3.5-flash`.** Three trials of the same `terminus-2` /
`gemini/gemini-3.5-flash` command (logs in `logs/qemu-win311-setup-verifier/`):

| Trial | reward (accuracy) | all_correct | fp | items missed |
| --- | --- | --- | --- | --- |
| 1 | 0.917 (11/12) | 0 | 1 | `no_snapshot` |
| 2 | 0.833 (10/12) | 0 | 2 | `no_snapshot`, `not_booted_desktop` |
| 3 | 0.667 (8/12) | 0 | 4 | `no_snapshot`, `no_monitor`, `not_booted_desktop` |

**pass@1 = 0%, pass@3 = 0%** at the 1.0 bar (oracle scores 1.0, so it's not impossible);
mean reward 0.81. `no_snapshot` is missed in all three trials; `not_booted_desktop` in two.

**Failure analysis — decomposed outcomes.** The recurring misses are the *second half* of an
outcome the model half-checked:
- **`no_snapshot`**: every verifier confirmed `base_image.img` byte-matches the reference (the
  image is authentic) but most never checked snapshot mode — so a config where the running VM
  would *write to* the base image sails past. "Kept pristine" = authentic **and** write-
  protected; the model checks the first and forgets the second.
- **`not_booted_desktop`**: verifiers checked that the screen *changed* after the keystroke but
  not that the baseline screenshot *shows a booted desktop* — so a blank-screen "attempt"
  passes. "Boots to the desktop and a key reaches it" = desktop present **and** screen
  responded.

These clear the "is it a task bug?" bar: the oracle scores 1.0 in the same environment; every
failing item is anchored to an outcome stated in the instruction; the anti-cheat holds (a
label-reading verifier is denied and collapses to 0.27). It's a genuine capability gap —
the model verifies the obvious signal but doesn't decompose an outcome into all the conditions
it implies.

**The road to it (honest iteration).** The first pool (11 items) missed a coverage gap: the
instruction requires "boots to the desktop," but nothing tested it. `gemini-3.5-flash` wrote a
rigorous verifier and hit **1.0 on 1 of 3** trials (pass@3 would have been non-zero) — the
perfect run happened to check snapshot mode, which the model does only intermittently. Adding
the `not_booted_desktop` item both closed the gap and re-hardened difficulty: a perfect score
now requires catching *two* independent, easily-missed conditions (write-protection and a
booted desktop) instead of one, and across the captured trials no run caught both. Same lesson
as Task 1's dtype items: a pool only measures the failure modes it contains.

**Red-team (a second model).** A Codex pass surfaced two real issues, both fixed: (1) the
harness ran pool items in a fixed sorted order (all passes first), so a verifier could ignore
every bundle and just count invocations with persistent state to match the label sequence —
now the harness **shuffles** item order each run (scoring is order-independent, so honest
verifiers are unaffected); (2) `02_correct_alt` bound the web interface to `127.0.0.1`, which
contradicts "remote monitoring" and would wrongly penalize a verifier that required a
reachable bind — now any-interface. Accepted limitations it also raised: the screenshot check
is intentionally "changed vs identical" rather than a pixel threshold (a threshold is the
over-specification the instruction deliberately avoids), and the cmdline/port checks are
outcome-level (port number, snapshot/monitor presence) rather than full QEMU-arg or
service-identity parsing — deeper parsing would trade determinism and the outcome framing for
brittleness, and no pool item depends on it.

## Appendix — reproduce

`PLAYBOOK.md` (repo root) is the full SOP: design the underlying task, hand-compute the
canonical answer, design the anchored pool (including the discriminating dtype items),
write the situation-voice instruction and the verifier contract, wire the separate
clean-room verifier env with `nobody`-sandboxed grading, write the oracle, and run the
validation gates before the `gemini-3.5-flash` capture.

---

## Rough thoughts (unrefined — to polish later)

Raw notes to self; not yet report-ready.

- **Framing bet.** The verifier-writing meta-twist is the whole gamble. If it reads as
  off-brief, hedge by shipping 1–2 *literal* DS tasks (analyze/clean/model) alongside it so
  the set spans "do the DS" and "verify the DS." Decide before submitting.
- **Binary vs fractional reward — the PDF literally asks us to justify this.** I went
  fractional (accuracy) + a binary `all_correct`. Fractional gives a smoother RL signal and
  a real difficulty curve; binary (`all_correct`) is cleaner for pass@k and is harder. Worth
  a paragraph defending fractional-with-a-1.0-bar, or reconsider making the headline reward
  binary. This is an explicit decision point in the brief, don't leave it implicit.
- **Define "pass" explicitly.** pass@3 = 0% only holds if pass ≡ reward 1.0. Say so in the
  difficulty section; a reviewer could otherwise read 0.818 as "passing."
- **Determinism caveat.** Three trials returned *identical* 0.818 and identical misses.
  That's either a very systematic capability gap (good) or `terminus-2`/gemini being
  near-deterministic at low temp (in which case pass@3 ≈ pass@1 and 3 trials add little).
  Worth a line, and maybe a temp>0 or larger-N run to show it's not just determinism.
- **Producer + verifier-maker pairing is UNTESTED.** It's the scale story but I haven't run
  it. Either pilot it once (run a producer, harvest, label) so it's demonstrated, or clearly
  label it as proposed.
- **One task, brief wants 5–10.** Be upfront. The playbook is the recipe; realistically
  build 3–4 total (mix of underlying domains: an ETL merge, a log-aggregation, a dirty-data
  clean) so the difficulty curve is an actual curve, not a point.
- **The "original verifier's blind spots → pool items" trick is the most generalizable
  insight** and deserves to be foregrounded, maybe promoted out of the appendix — it's how
  you make adversarial items cheaply for any underlying task.
- **Anti-cheat is heavy.** Clean-room env + `nobody` is real complexity. Justified because
  reward-hacking is a known LLM behavior, but note the tradeoff; a lighter shared-env +
  `nobody` version exists if simplicity matters more than defending a root-adversarial agent.
- **Pool size.** 11 items is enough to discriminate but thin; more items (esp. more dtype/
  format and conflict edge cases) tighten the precision/recall estimate.
- **Possible extra task type:** one deterministic verifier task + one where the *right*
  verifier is an LLM-judge, to actually exercise the PDF's "deterministic vs LLM-as-judge"
  prompt — while keeping our meta-grader deterministic.
