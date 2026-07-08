# Verifier Synthesis for Data-Science Tasks: A Mini-Eval

## Abstract

This report presents a mini-eval that measures a capability one level up from *doing* data
science: **writing the verifier** for a data-science task. An agent is handed a data problem
and must produce the grader that decides whether a given attempt solved it. That grader is
then scored, deterministically, against a hidden pool of labeled solutions — correct ones
must pass, adversarial ones must fail. There is no LLM judge: the judgment happened once,
offline, when the pool was labeled.

I built and hardened **six tasks** across five underlying domains (dirty-data ETL, stochastic
scientific computing, systems/virtualization, log aggregation, video analysis, and
synthetic-biology design). Against `gemini-3.5-flash`, three of the six clear the take-home's
< 30% pass@3 bar (all at **0%**) and three do not (all at **100%**). The 0%/100% split is not
noise — it is the central result. It isolates *which property of an underlying task makes its
verifier hard to synthesize*: a hard target combines **legitimate representational variation**
in a correct output with a **reliable semantic trap** (typically a declared type or contract
that a verifier's default tooling silently coerces away). Where that combination is absent, a
capable model writes a correct verifier and the task cannot discriminate rigor. This selection
rule is the most transferable output of the exercise and drives the scale plan.

`PLAYBOOK.md` (repo root) is the reproducible SOP that produced all six tasks.

---

## 1. Introduction

The Abundant AI take-home asks for a mini-eval of data-science tasks that are (a)
representative of real DS/DE work and (b) hard — under 30% pass@3 against `gemini-3.5-flash`.
At its core, the brief is about **verifiers**: its glossary and its "experiment with different
types of verifiers… justify your decision" hint make that explicit. So rather than test
whether a model can *perform* a data task — a capability frontier models largely have — I test
whether it can **verify** one: turn a data-correctness spec into a rigorous, non-gameable
grader.

Why this is the interesting slice:

- **It is the bottleneck.** Verifier synthesis is the one unautomated step in the RL
  task-generation flywheel. In Benchtalks #1, Alex Shaw names verifier-writing as the
  benchmark he most wants to see, because "we don't have a way of knowing how good our agents
  are at creating verifiers" [1]. Automate it and RL environments get cheap.
- **It is genuine DS/DE work.** Writing data-quality checks, reconciliation tests, and
  contract enforcement is what data engineers actually do. The underlying domains here
  (multi-source ETL merge, log aggregation, numerical sampling, VM setup, video analysis,
  synthetic-biology design) are production-style and in-scope.
- **The metric is clean.** Precision/recall against a hand-labeled pool — no LLM-as-judge,
  fully deterministic and reproducible.

**Honest framing caveat.** "The agent writes the verifier" is a meta-twist on "data-science
task." I believe it is defensible and on-brief (the whole take-home is about verifiers), but a
reviewer expecting a literal analyze-this-dataset task should know it is a deliberate
reinterpretation, not an oversight.

---

## 2. Background and related work

- **Alex Shaw — Benchtalks #1 (Terminal-Bench / Harbor)** [1]. The seed: the benchmark he most
  wants is one measuring agents' ability to write verifiers. Directly motivated this slice.
- **"What Makes a Good Terminal-Agent Benchmark Task"** (Bercovich) [2]. A benchmark is
  designed to find out *if* an agent can do something, not — like a prompt — to help it
  succeed. Its catalog of anti-patterns (over-prescriptive specs, assumed hidden knowledge,
  validating the wrong thing, reward-hackable environments; instructions should be short,
  adversarial, legible) shaped the instruction discipline here (anchoring and brevity), the
  anti-cheat work, and the honesty about the tasks the model aces.
- **HUD — "Verifier and Reward Design for RL Environments"** [3]. Verifiers confirm the
  outcome; pass/fail guards enforce hard rules; rubrics capture quality; the reward turns it
  into a training signal — and more capable agents are likelier to exploit a misspecified one.
  Reinforced keeping the meta-verifier deterministic (no judge) with a fractional reward *plus*
  a binary `all_correct`.
- **DABStep (Adyen × Hugging Face)** [4]. Real data analysis is dirty, distributed, and rarely
  straightforward — the frontier there is low (the strongest agents scored ~16%). A good source
  of *hard-target* underlying tasks for the scale plan (§7).

The through-line across all four: the hard, valuable, under-measured thing is **verification
quality**, and the way to measure it cleanly is a hand-labeled adversarial pool, not a judge.

---

## 3. Method

### 3.1 The two-layer design

The eval nests two Harbor layers:

- **Layer 1 — the agent's job.** Given an underlying data task's instruction and environment,
  the agent writes an executable verifier (`/app/verifier/verify.sh`) that decides whether a
  candidate solution is correct.
- **Layer 2 — the meta-verifier.** A custom harness runs the agent's verifier against *N*
  labeled candidate solutions, compares its verdicts to hidden labels, and emits
  precision/recall/accuracy and a binary `all_correct`. No LLM judge — the judgment happened
  once, offline, when the pool was labeled.

The reward is deterministic and clean: the fraction of the pool the candidate verifier
classifies correctly. The pool's coverage *is* the operational definition of a good verifier.

### 3.2 Task-construction workflow

The six tasks were built in two phases.

- **The reference task, by hand.** `multi-source-data-verifier` was built first, interactively
  with Claude — hand-computing the canonical answer, designing the anchored pool, wiring the
  clean-room anti-cheat, and writing the oracle. This task became the **reference
  implementation** and seeded `PLAYBOOK.md`, the step-by-step SOP for the pattern.
- **The rest, in parallel.** The other five tasks were built in **parallel coding sessions in
  Conductor**, each following the playbook against a different underlying task. Building them
  concurrently — rather than serially — is what made covering five additional domains tractable,
  and stress-tested the playbook as a transferable recipe rather than a one-off.

### 3.3 Producer-generated pools

The labeled pool is the answer key, and hand-authoring every item from scratch is the
expensive step. For **all six** tasks the base pool was **producer-generated**: a producer (a
Conductor agent session) hooked up the underlying task, ran it to **harvest genuinely-correct
and genuinely-incorrect example solutions**, and those became the base ~8 labeled items
(oracle, correct alternates, and organic failures). The producer's natural variation supplies
`correct_alt`-style PASS items and organic FAIL items essentially for free.

On top of that base, the **discriminating adversarial items** were hand-added per the
playbook's iteration step — the cases agents rarely produce on their own: the type/format items
(right value, wrong declared dtype), the randomness item (right marginal, deterministic
sampler), the decomposed-outcome items (half of an outcome satisfied), and the trajectory trap
(a narrative claiming success with no output files).

A specific, reusable trick informs this step: **the original task's verifier is a floor, not a
ceiling, and its blind spots are the best adversarial items.** The reference merger's original
test spot-checked only 2 of 4 users and used `total_conflicts >= 1`; a solution wrong on the
*other* users, or with the wrong exact conflict count, sailed past it. Those exact blind spots
became the `wrong_values` / `near_miss` FAIL items. Noting where an original verifier is loose
is a cheap way to manufacture adversarial items for any underlying task.

### 3.4 Anti-cheat

The candidate `verify.sh` is untrusted code the harness executes, so grading is locked down two
ways:

1. **Clean-room grading.** The verifier runs in a separate image (`environment_mode =
   "separate"`) that bakes in the harness, the pool, and a **pristine** copy of the input data.
   The agent's `verify.sh` is the only thing carried over — collected from the agent container
   and injected as an artifact — so a root agent cannot trojan the toolchain or poison the data
   the harness trusts.
2. **Unprivileged, label-blind execution.** The harness runs each `verify.sh` as `nobody`, with
   `tests/pool` (labels and solutions) made root-only. The candidate literally cannot read the
   answer key. (Proven: a verifier that `cat`s the labels is denied and collapses to the
   baseline score.)

Harbor also uploads and builds the verifier only *after* the agent stops, so the pool is never
visible during the agent's run — the naive fear ("the agent will read the tests") is not real.

This machinery is genuinely heavy, and that is a deliberate tradeoff: reward-hacking is a known
LLM behavior and worth defending against, but a lighter shared-environment + `nobody` variant
exists for settings where simplicity matters more than defending a root-adversarial agent.

### 3.5 Metric

The headline `reward` is **accuracy over the pool**, reported alongside a binary `all_correct`
and the raw tp/fp/fn/tn counts. Two deliberate choices:

- **Fractional reward plus a binary bar.** Fractional accuracy gives a smoother RL signal and a
  real difficulty *curve*; the binary `all_correct` is cleaner for pass@k and is the harder,
  less gameable criterion. The take-home explicitly asks this be justified: I report both, and
  define **pass ≡ reward 1.0 / `all_correct` = 1** (a perfect verifier), which is what pass@k
  uses and what the oracle alone achieves.
- **Fail-heavy pools, with a caveat.** The hard pools are deliberately fail-heavy (e.g. 3 pass /
  8 fail) to pack in adversarial cases. A known consequence: a do-nothing "reject everything"
  verifier scores 8/11 = 0.727, and the reward band just above that is not monotone in verifier
  quality. So the fractional reward is a *difficulty diagnostic*, not the pass criterion — pass
  is the perfect-verifier bar. For RL training one would use `all_correct` (or a
  chance-corrected metric like balanced accuracy) as the signal and keep fractional accuracy as
  a diagnostic.

---

## 4. Results

Three trials each of `harbor run -a terminus-2 -m gemini/gemini-3.5-flash`, logs under
`logs/<task>/`; **pass = a perfect verifier** (reward 1.0 / `all_correct`).

**Aggregate:**

| Task | oracle | pass@3 (bar = 1.0) | mean reward | dominant failure |
| --- | --- | --- | --- | --- |
| `multi-source-data-verifier` | 1.0 | **0%** | 0.818 | coerces declared types |
| `adaptive-rejection-sampler` | 1.0 | **0%** | 0.909 | checks the distribution, not randomness |
| `qemu-win311-setup-verifier` | 1.0 | **0%** | 0.81 | half-checks decomposed outcomes |
| `log-summary-verifier` | 1.0 | **100%** | 1.000 | — (easy target; kept as control) |
| `video-jump-verifier` | 1.0 | **100%** | 0.909 | — (gate-rejected; §5) |
| `fusion-protein-verifier` | 1.0 | **100%** | 0.933 | — (gate-rejected; §5) |

**Per-task, trial-level:**

*Merge* (`multi-source-data-verifier`, 11-item pool):

| Trial | reward (accuracy) | all_correct | fp | fn | items missed |
| --- | --- | --- | --- | --- | --- |
| 1–3 | 0.818 (9/11) | 0 | 2 | 0 | `wrong_dtype_userid`, `wrong_date_format` |

→ pass@1 = pass@3 = 0%. Identical score and identical misses across three independent runs — a
*systematic* capability gap, not variance.

*ARS* (`adaptive-rejection-sampler`, 11-item pool):

| Trial | reward | all_correct | fp | fn | items missed |
| --- | --- | --- | --- | --- | --- |
| 1–3 | 0.909 (10/11) | 0 | 1 | 0 | `deterministic_quantiles` |

→ pass@1 = pass@3 = 0%. Again identical across three runs.

*QEMU* (`qemu-win311-setup-verifier`, 12-item pool):

| Trial | reward | all_correct | fp | fn | items missed |
| --- | --- | --- | --- | --- | --- |
| 1 | 0.917 (11/12) | 0 | 1 | 0 | `no_snapshot` |
| 2 | 0.833 (10/12) | 0 | 2 | 0 | `no_snapshot`, `not_booted_desktop` |
| 3 | 0.667 (8/12) | 0 | 4 | 0 | `no_snapshot`, `no_monitor`, `not_booted_desktop`, … |

→ pass@1 = pass@3 = 0%, mean 0.81. Unlike merge and ARS, the three trials **vary
substantially** (0.917 / 0.833 / 0.667), all driven by false positives (fp = 1 / 2 / 4, fn
always 0): the model accepts bundles it should reject. `no_snapshot` is missed in all three.

*Log-summary* (`log-summary-verifier`, 12-item pool):

| Trial | reward | all_correct | fp | fn |
| --- | --- | --- | --- | --- |
| 1–3 | 1.000 (12/12) | 1 | 0 | 0 |

→ pass@1 = pass@3 = 100%. The model wrote a correct, robust verifier every time.

*Video-jump* (`video-jump-verifier`, 11-item pool):

| Trial | reward | all_correct | fp | fn |
| --- | --- | --- | --- | --- |
| 1 | 1.000 | 1 | 0 | 0 |
| 2 | 1.000 | 1 | 0 | 0 |
| 3 | 0.727 | 0 | 0 | 3 |

→ pass@3 = 100%. The one sub-1.0 trial is **false-negative-driven** (fn = 3, fp = 0): a
malformed `verify.sh` (Python pasted into a bash file) failed on every item and so rejected the
three correct analyzers — a plumbing slip, not a verification-logic gap (§5).

*Fusion-protein* (`fusion-protein-verifier`, 20-item pool):

| Trial | reward | all_correct | fp | fn |
| --- | --- | --- | --- | --- |
| 1 | 1.00 | 1 | 0 | 0 |
| 2 | 0.80 | 0 | 0 | 4 |
| 3 | 1.00 | 1 | 0 | 0 |

→ pass@1 = 67%, pass@3 = 100%. The 0.80 trial is again **false-negative-driven** (fn = 4, fp =
0): it mis-resolved the acceptor fluorophore and rejected all four valid gBlocks — an incidental
slip, not a systematic gap (§5).

**The hard/easy split is a dichotomy, and the dichotomy is the point (§5).** Both hard-side
*sub-perfect* failures on merge and ARS are the same shape: a competent verifier that checks
the obvious properties but misses the one place its default tooling silently accepts a wrong
answer. Note also the road to the merge number *is* the finding: the first pool tested only
values and containers (8 items) and `gemini` scored 1.0 three times — no headroom. Diagnosing
why (§6) led to three "right value, wrong declared type" items, which opened the 0.818 gap.

---

## 5. Discussion — what makes a verifier-synthesis target hard

Same author, same method, same model, same anti-cheat — and a 0%/100% split. The difference is
entirely in the **underlying task's shape**. Pinning down which property drives it is the most
transferable thing in this submission, because it is exactly the "is this a good target?"
question the scale plan must answer.

**Two properties separate a hard verifier-synthesis target from an easy one.**

1. **Legitimate representational variation.** A hard target admits many correct-but-different
   outputs, so the verifier must *tolerate* variation while staying strict on substance — and an
   over-strict or byte-diff verifier gets caught. The merge output has rich variation: row
   order, column order, extra columns/files, conflict-list order, and a nested JSON report. The
   log-summary output is 15 fixed rows of `(period, severity, count)`; the only variation is row
   order, column order, and CSV quoting — little room for discriminating PASS items.
2. **A reliable semantic trap in a declared, multiply-typed contract.** The strongest pool items
   are "right value, wrong declared type" — they separate a verifier that *enforces a data
   contract* from one that merely *checks values by coercing types*. The merge output declares
   **five** typed fields (`user_id` integer, dates as `YYYY-MM-DD` strings, `status` an enum
   string, …), giving three independent dtype items — the exact items `gemini` fails. The
   log-summary output has **one** typed column (`count`, an integer); its single dtype item is
   real and the pool discriminates on it, but rejecting `370.0` from one integer column is a much
   lower bar than enforcing a five-field contract with dates and enums, and `gemini` cleared it
   every time.

The trap has to be *reliable* — a semantic default the model reaches for regardless of raw
capability — not merely *present*. Coercing declared types (`astype(int)`, `pd.to_datetime`) is
such a default, so all three merge trials fail *identically*. Contrast `fusion-protein-verifier`
(§7), where the only sub-perfect outcomes were incidental, high-variance slips (a
case-sensitivity miss, an acceptor mis-resolution) — not a systematic gap the pool can rely on.

**Difficulty is derivation depth × contract traps, not operational complexity.** The
`video-jump-verifier` task makes this sharp. Its verifier must *run* untrusted candidate scripts
on two videos, survive crashes, and enforce integer typing and an import allowlist — operationally
fiddly. Yet `gemini` clears it, because verifying two integer frames decomposes into
**independent, standard checks** (spawn a subprocess, parse TOML, `isinstance(v, int)`,
range-test, AST-walk the imports). There is no counterintuitive trap and no complex truth to
re-derive. The ETL task hit 0% precisely because it had **both**: a three-source merge with
conflict resolution to re-derive (derivation depth) **and** the coercion trap (a place where the
obvious implementation is silently wrong). Operational complexity is *not* where difficulty
lives — a competent model handles it. It lives in derivation depth and contract traps.

**The selection rule.** Constrained output + simple derivation ⇒ easy target; rich variation +
a multi-typed contract with a reliable trap ⇒ hard target. This is the gate the scale plan
applies before spending effort on a task (§7).

I *did* try to close the log-summary gap fairly first: I hardened its pool with two
valid-variation PASS items (an RFC-4180 quoted CSV and a column-reordered CSV) that catch
non-robust verifiers, and they caught 2 of the first 3 trials. But on re-capture the model wrote
fully-robust, CSV-aware, column-by-name verifiers 3/3. Pushing further would mean overfitting
items to specific verifier bugs — difficulty from tricks, not from the problem — so I stopped and
kept it as an honest control.

---

## 6. Failure analysis — the hard-task failures are genuine

Each hard-task failure clears the "is it a task-design bug?" bar: the oracle scores 1.0 in the
same environment; every failing item is anchored to a rule stated in the instruction; and the
clean-room + `nobody` sandbox make the answer key unreadable, so it is not reward-hacking.

- **Merge — coerces declared types.** All three trials fail identically on two items, and the
  captured `verify.py` shows why: the verifier **coerces** declared types instead of enforcing
  them — `df["user_id"].astype(int)` (so a string `"101"` passes, though `user_id` is declared an
  integer) and `pd.to_datetime(...).dt.strftime(...)` (so a datetime column passes, though the
  spec declares a `YYYY-MM-DD` string). The model enforced the boolean `status` type correctly
  in these very runs — it just did not generalize the rigor. It can write a verifier that *checks
  values*, but not reliably one that *enforces a data contract*.
- **ARS — checks the distribution, not the sampling.** Every captured verifier tests the marginal
  distribution (mean, sd, a KS goodness-of-fit test against known densities) and the behavioral
  requirements (input validation, log-concavity rejection), but none tests that the sampler is
  actually *random*. A submission returning a fixed table of evenly-spaced quantiles has a
  *perfect* marginal — better than a real sampler — so it sails through every distributional
  check. It is caught only by re-calling `ars` and checking the draws differ, which no trial did.
  *Honest note on margin:* this gap is thinner than merge's. A control experiment (three extra
  runs, discarded) that reworded the instruction to state the property more loudly — "the draws
  are random, not a fixed table" — flipped one run to a perfect 1.0. That cuts both ways: it
  confirms the difficulty is a genuine thoroughness gap (the model *can* test randomness, it just
  does not by default), and it shows the shipped instruction deliberately states the requirement
  as a property of the sampler ("sampling is stochastic") rather than spelling out the check —
  because naming the test hands the model its checklist. The result is honest headroom, but it is
  more wording-sensitive than the coercion trap, and a stronger model would likely close it.
- **QEMU — half-checks decomposed outcomes.** The recurring misses are the *second half* of an
  outcome the model half-checked. `no_snapshot`: verifiers confirmed `base_image.img` byte-matches
  the reference (authentic) but most never checked snapshot mode (write-protected) — so a config
  where the running VM would *write to* the base image passes. "Kept pristine" = authentic **and**
  write-protected. `not_booted_desktop`: verifiers checked that the screen *changed* after a
  keystroke but not that the baseline screenshot *shows a booted desktop* — so a blank-screen
  attempt passes. The model verifies the obvious signal but does not decompose an outcome into all
  the conditions it implies.

**Log-summary — a genuine non-gap.** The 100% is real capability, not a broken pool. The oracle
scores 12/12; a files-exist-only verifier scores 7/12; a bracket-correct-but-coercing verifier
scores 10/12; the first-round non-robust `gemini` verifiers scored 10/12 and 11/12 on the
hardened pool. So weak verifiers *are* caught — the model simply wrote strong ones (all use the
`csv` module, identify columns by header name, parse the bracketed severity token to dodge the
substring trap, compute inclusive date boundaries, and reject non-integer counts). The honest
conclusion is that the *task* is an easy verifier-synthesis target — a finding about task
selection, not a defect.

---

## 7. Scale plan (10 → 1,000)

Per-task cost is dominated by authoring the underlying task and labeling the pool. Both are
compressible, and the 0%/100% contrast adds a cheap up-front filter that stops us spending
either on weak targets.

1. **Target-strength gate (from §5).** Before building the pool, score a candidate underlying
   task on the two properties: (a) does a correct output admit representational variation? (b)
   does it declare ≥ 2 typed fields (or otherwise carry a reliable trap)? Operationalize it: run
   a *naive* reference verifier (values only, coercing) and a *strict* one against a handful of
   model-generated outputs; if their scores do not diverge, the task cannot discriminate verifier
   rigor — kick it back before labeling. Log-summary and the two gate-rejected tasks (§7)
   would be flagged here and kept only as deliberate controls.
2. **Producer + verifier-maker pairing — demonstrated per-task.** This eval already uses the
   producer step: for all six tasks, a producer harvested the base pool solutions from the
   underlying task, which were then labeled and augmented with the hand-crafted adversarial items
   (§3.3). The remaining extension for scale is to **fully automate the harvest-and-label loop** —
   run the producer at volume, auto-label the unambiguous PASS/FAIL cases, and route only the
   genuinely-ambiguous ones to a human. The pairing is proven at the single-task level; the
   automation of it is the work that turns 6 into 1,000.
3. **Augmentation.** Once one canonical answer exists, pool items are cheap perturbations of it
   (`_build_pool.py` shows the pattern: one mutation → one FAIL item). New datasets multiply the
   base; perturbation multiplies the pool per dataset.
4. **Underlying-task sources.** Public Kaggle notebooks, Terminal-Bench / Harbor hub tasks [5],
   DABStep-style analysis problems [4], and production ETL patterns — filtered by the §7 target-strength gate
   for a deterministic answer, declared types, and real variation.
5. **QA loop — automated deterministic gates** (from `PLAYBOOK.md`): (a) the oracle scores the
   pool 1.0 (solvable + self-consistent labels); (b) a weak/coercing verifier scores < 1.0 (the
   pool discriminates); (c) the §7 target-strength divergence check; (d) `gemini` pass@3 < 30%
   (headroom). A task that fails a gate is auto-kicked. The two gate-rejected tasks below are this
   loop working as intended.

**The two gate-rejected tasks — negative results kept on purpose.** `video-jump-verifier` and
`fusion-protein-verifier` are fully-built, hardened, red-teamed tasks that pass every
*deterministic* gate (oracle 1.0; a lazy verifier scores 0.727 / 0.35; a label-reading cheat is
denied; nop scores 0) but that `gemini-3.5-flash` clears at the perfect-verifier bar (pass@3 =
100%). I built them out rather than discarding them because the negative result is load-bearing:
`video-jump` shows difficulty is not operational complexity (§5), and `fusion-protein` shows it
is not underlying-task difficulty either — protein-assembly is genuinely hard to *solve* (real
bioinformatics, a junior estimate of ~300 minutes), but its spec is *uniquely resolvable by
design*, so once a capable model resolves the five proteins the remaining verification is
mechanical string/GC bookkeeping with no coercion-style trap. Hard-to-solve and hard-to-verify
are different axes. Both tasks' anti-cheat and pool machinery are the reusable substrate for the
next task that *does* carry a trap.

*(Red-team note: I attempted an independent second-model adversarial review via Codex for these
two. It surfaced and I fixed two real issues on the QEMU task — a fixed pool ordering a stateful
verifier could game, now shuffled; and a `127.0.0.1` bind on a "remote monitoring" item, now
any-interface — and found no anti-cheat hole or mislabeled item on fusion-protein. On video-jump
Codex was unavailable (no credits), so that task's assurance rests on the deterministic gates and
a manual pass: no shortcut verifier can score 1.0, because all 11 items require simultaneously
running both videos, enforcing the integer type, checking imports, and rejecting no-output
candidates.)*

---

## 8. Limitations and honest caveats

- **Determinism vs. systematic behavior.** Merge returned *identical* 0.818 and identical misses
  three times; ARS identical 0.909 three times; log-summary identical 1.0 (six times counting an
  earlier pool). This is either very systematic behavior (the intended reading) or `terminus-2` /
  `gemini` being near-deterministic at low temperature, in which case pass@3 ≈ pass@1. A temp > 0
  or larger-N run would confirm the gaps are capability, not sampling artifacts. QEMU, whose
  trials vary (0.917 / 0.833 / 0.667), is evidence for the former.
- **Pool size.** 11–20 items is enough to discriminate but thin; more items — especially more
  dtype/format and conflict edge cases — would tighten the precision/recall estimate.
- **Task count.** The brief wants 5–10 tasks; six are built (three hard: ETL merge, ARS, QEMU
  setup; three gate-rejected controls: log-summary, video-jump, fusion-protein). The playbook is
  the recipe for more, and the three hard archetypes already probe genuinely different
  verification skills (deterministic data artifact vs. stochastic code vs. captured system
  evidence). Building a few more *hard* targets that clear the §7 target-strength gate (a dirty-data clean, a
  nested-JSON report with typed fields) would make the difficulty a real curve rather than a
  dichotomy.
- **Anti-cheat complexity.** The clean-room + `nobody` design is real complexity, justified by
  reward-hacking being a known LLM behavior; a lighter shared-env + `nobody` variant exists if
  simplicity matters more than defending a root-adversarial agent (§3.4).
- **The ARS trap is thinner than merge's** and more wording-sensitive (§6) — honest headroom, but
  the first gap a stronger model would close.
- **Possible future task type.** One deterministic-verifier task paired with one where the
  *right* verifier is itself an LLM-judge, to directly exercise the take-home's "deterministic vs.
  LLM-as-judge" prompt — while keeping the meta-grader deterministic.

---

## References

[1] A. Shaw. *Benchtalks #1: Building the benchmark factory* (Terminal-Bench, Harbor).
<https://www.youtube.com/watch?v=UCn5gG0haCI>

[2] I. Bercovich. *What Makes a Good Terminal-Agent Benchmark Task: A Guideline for Adversarial,
Difficult, and Legible Evaluation Design.* arXiv:2604.28093.
<https://arxiv.org/abs/2604.28093>

[3] HUD. *Verifier and Reward Design for RL Environments.*
<https://www.hud.ai/resources/verifier-reward-design-rl-environments>

[4] Adyen × Hugging Face. *DABStep: Data Agent Benchmark for Multi-step Reasoning.*
<https://huggingface.co/blog/dabstep>

[5] Harbor Framework. *Terminal-Bench 2* (underlying tasks: `install-windows-3.11`,
`video-processing`, adaptive rejection sampler, `protein-assembly`).
<https://github.com/harbor-framework/terminal-bench-2>

---

## Appendix — reproduce

`PLAYBOOK.md` (repo root) is the full SOP for all six tasks: design the underlying task,
hand-compute the canonical answer, design the anchored pool (including the discriminating dtype
items), write the situation-voice instruction and the verifier contract, wire the separate
clean-room verifier env with `nobody`-sandboxed grading, write the oracle, and run the validation
gates before the `gemini-3.5-flash` capture. All six tasks pass the deterministic gates (oracle
1.0; pool discriminates; anti-cheat denied; nop 0; `harbor check` clean); their `gemini` logs are
in `logs/`.
