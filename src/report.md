# Mini-Eval Report: Verifier Synthesis for Data-Science Tasks

## Summary

This eval measures a capability one level up from doing data science: **writing the
verifier** for a data-science task. The agent is handed a data-merge problem and must
produce the grader that decides whether a given attempt solved it. That grader is then
scored, deterministically, against a hidden pool of labeled solutions — correct ones must
pass, adversarial ones must fail.

Scope note: this submission contains **two fully-built, hardened tasks** spanning two
distinct archetypes, plus the methodology and tooling to generate the rest (`PLAYBOOK.md`
at the repo root is the reproducible SOP):

- **`samples/multi-source-data-verifier`** — a *dirty-data ETL* task (merge three
  inconsistent user exports into one Parquet table + conflict report).
- **`samples/adaptive-rejection-sampler`** — a *low-level scientific-computing* task
  (implement an adaptive rejection sampler in R). This one is deliberately different: the
  graded artifact is **stochastic code**, so a correct verifier must *run* each candidate
  and judge its behavior statistically, not diff it against a fixed output.

Both clear the < 30% pass@3 bar with a consistent, diagnosable failure mode, and both come
with the anti-cheat and validation worked all the way through. Two archetypes give a real
(if short) difficulty curve rather than a point; the scale plan (below) is how this becomes
10 and then 1,000.

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

**Second task — a different axis of verification difficulty.** The ETL task tests verifying
a *deterministic data artifact*. The second task, `adaptive-rejection-sampler`, tests
verifying *stochastic code*: the underlying task (from Terminal-Bench 2) is to implement an
adaptive rejection sampler in R — `ars(g, D, n)` draws `n` samples from an arbitrary
log-concave density, with input validation, log-concavity checking, and generated samples.
A correct verifier can't diff against a reference; it must run the candidate and test its
*behavior* — goodness-of-fit against known distributions, rejection of invalid inputs and
non-log-concave densities, and that the output is actually random. This is a genuinely
harder verification problem (statistical, behavioral, no fixed answer) and a different slice
of DS/DE work (numerical / scientific computing rather than ETL). It's included precisely
because "verify a stochastic algorithm" stresses a different skill than "verify a data
merge."

**Honest caveat on framing.** "The agent writes the verifier" is a meta-twist on "data
science task." I think it's defensible and on-brief (the whole take-home is about
verifiers), but a reviewer expecting a literal analyze-this-dataset task should know it's a
deliberate reinterpretation, not an oversight.

## 2. Difficulty profile vs `gemini-3.5-flash`

### Task A — `multi-source-data-verifier`

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

### Task B — `adaptive-rejection-sampler`

Three trials of `harbor run -p samples/adaptive-rejection-sampler -a terminus-2 -m
gemini/gemini-3.5-flash` (logs in `logs/adaptive-rejection-sampler/`):

| Trial | reward (accuracy) | all_correct | fp | fn | items missed |
| --- | --- | --- | --- | --- | --- |
| 1 | 0.909 (10/11) | 0 | 1 | 0 | `deterministic_quantiles` |
| 2 | 0.909 (10/11) | 0 | 1 | 0 | `deterministic_quantiles` |
| 3 | 0.909 (10/11) | 0 | 1 | 0 | `deterministic_quantiles` |

- **pass@1 = 0%, pass@3 = 0%** at the 1.0 bar; mean reward **0.909**. Again identical across
  three runs — a systematic gap, not variance.
- Gemini here writes a genuinely *thorough* verifier: it tests standard-normal sampling with
  a KS goodness-of-fit test, a held-out shifted/scaled normal and an exponential, input
  validation, and log-concavity rejection — and gets all 3 PASS and 7 of 8 FAIL items right.
  It fails on exactly one: `deterministic_quantiles`, a submission that returns a fixed table
  of evenly-spaced quantiles. That table has the *exact* right marginal distribution (mean,
  sd, and shape all pass), so every verifier that checks the distribution accepts it — but it
  is not random sampling. Only a verifier that tests that repeated calls differ catches it,
  and none of the three did.
- **The road to this number, again, is the finding.** The first pool (10 items, all
  large-margin errors) let gemini's thorough verifier score a perfect **1.0** — no headroom.
  Adding the one deterministic-but-perfect-marginal item opened the 0.909 gap. It is the
  direct analog of Task A's type-coercion items: a correct-looking output that a verifier's
  natural tool (a statistical fit test / a type coercion) silently waves through.

### Aggregate

| | oracle | gemini-3.5-flash pass@3 (bar = 1.0) | mean reward | dominant failure |
| --- | --- | --- | --- | --- |
| `multi-source-data-verifier` | 1.0 | **0%** | 0.818 | coerces declared types |
| `adaptive-rejection-sampler` | 1.0 | **0%** | 0.909 | checks the distribution, not randomness |

Aggregate pass@3 = **0/2 tasks passed** (0%), against a < 30% target. Both failures are the
same *shape*: the model writes a competent verifier that checks the obvious properties but
misses the one place its default tooling (type coercion; a marginal-fit test) silently
accepts a wrong answer.

**Metric note (be precise about "pass").** The headline `reward` is accuracy over the pool,
and both pools are deliberately fail-heavy (3 pass / 8 fail) to pack in adversarial cases.
That has a known consequence: a do-nothing "reject everything" verifier scores 8/11 = 0.727,
and the intermediate reward band above it is not monotone in verifier quality. So the
fractional reward is a *difficulty curve*, not the pass criterion — **pass ≡ reward 1.0 /
`all_correct` = 1** (a perfect verifier), which is what pass@3 uses and what the oracle alone
achieves. The harness already emits `all_correct` for exactly this reason; for RL training
one would use `all_correct` (or a chance-corrected metric like balanced accuracy) as the
signal and keep the fractional accuracy as a diagnostic.

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

### Task A — `multi-source-data-verifier`: coerces declared types

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

### Task B — `adaptive-rejection-sampler`: checks the distribution, not the sampling

All three trials fail identically on `deterministic_quantiles`, and the captured verifiers
show why: every one tests the *marginal distribution* (mean, sd, a KS goodness-of-fit test
against known densities) and the behavioral requirements (validation, log-concavity), but
none tests that the sampler is actually **random**. A submission returning a fixed table of
evenly-spaced quantiles has a *perfect* marginal — better than a real sampler — so it sails
through every distributional check. It is caught only by re-calling `ars` and checking the
draws differ, which no trial did.

This clears the same "is it a task-design bug?" checks:
- **Not an ambiguous instruction.** The item violates the core meaning of "adaptive
  rejection *sampling*" that "returns *n draws*" — a deterministic lookup table is not
  sampling. The oracle catches it with a two-line repeat-call check.
- **Not a mislabeled/over-strict pool.** The three PASS items are genuinely correct across
  many log-concave densities (normal, exponential, gamma, beta, logistic, custom `exp(-x⁴)`,
  bounded and unbounded domains; verified independently), and gemini passes all three. The
  oracle scores the pool 1.0.
- **Not reward hacking.** Same clean-room + `nobody`-sandbox as Task A; a label-reading
  verifier is denied and collapses to baseline.

**Honest note on the trap's margin.** This gap is thinner than Task A's. A control experiment
(three extra runs, discarded) with the instruction reworded to state the property more
loudly — "the draws are random, not a fixed table" — flipped one run to a perfect 1.0 and
made two others over-strict. The takeaway cuts both ways: (a) it confirms the difficulty is a
*genuine thoroughness gap*, not a hard limit — the model **can** test randomness, it just
doesn't by default, which is exactly the capability an eval should probe; and (b) the shipped
instruction deliberately states the requirement as a property of the sampler ("Sampling is
stochastic") rather than spelling out the check, because naming the test hands the model its
checklist. That is the same discipline as Task A (declare the types, don't say "don't coerce
them"). The result is honest headroom, not a formatting gotcha — but it is more
wording-sensitive than the type-coercion trap, and a stronger model would likely close it.

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
- **Two tasks now (ETL merge + ARS), brief wants 5–10.** Be upfront. The playbook is the
  recipe; realistically build 3–4 total (add e.g. a log-aggregation or a dirty-data clean) so
  the difficulty curve is a real curve. The two archetypes so far (deterministic data vs
  stochastic code) already probe genuinely different verification skills.
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
