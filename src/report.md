## Abstract

I measured a capability one level up from doing data science: writing the verifier for a data-science task. An agent receives a data problem and must produce the script that decides whether an attempt solved it. That script is then scored deterministically against a hidden pool of labeled solutions, where correct solutions must pass and adversarial ones must fail. No LLM judge is involved; the pool was labeled beforehand, so the judgment only happens once.

I built and hardened six tasks across five domains: dirty-data ETL, stochastic scientific computing, systems and virtualization, log aggregation, video analysis, and synthetic-biology design. Against `gemini-3.5-flash`, three tasks clear the take-home's sub-30% pass@3 bar (all at 0%) and three do not (all at 100%). The 0%/100% split is the central result, not noise. I deliberately built tasks on both sides of that line, because the contrast is what isolates the property that makes a verifier hard to synthesize.

That property is a pairing. A hard task admits many valid ways to approach the problem while still having a deterministic, checkable outcome, so the verifier-writer cannot just pattern-match one correct answer. It has to reason about the end state it is testing for and, harder, about every way an implementer could produce a plausible-looking result that is actually wrong. When a task lacks that pairing, a capable model writes a correct verifier every time and the task cannot discriminate rigor. That selection rule is the most transferable output of the exercise, and it drives the scale plan.

## 1. Introduction

Verifier synthesis is the one unautomated step in the RL task-generation flywheel; in Benchtalks #1, Alex Shaw names verifier-writing as the benchmark he most wants, because there is currently no way to know how good agents are at creating verifiers [1]. Automate it and RL environments get cheap. And the metric stays clean: precision and recall against a hand-labeled pool, fully deterministic, no LLM-as-judge.

The longer bet is that this matters well beyond CS. Most of the productivity gains from LLMs so far sit inside software, a single industry with its own norms and vocabulary. Broader impact means tasks defined by people who do not know how to specify or check them, and the only thing that scales there is teaching the AI to author and verify tasks itself rather than teaching every domain to do it by hand. The same pressure shows up in robotics: as agents move from manipulating text to manipulating the physical world, usable training data gets scarcer, and synthesized, self-verified tasks become one of the few ways to produce it. I raise these as motivation, not as claims this eval settles.

This is a deliberate reinterpretation of the brief, not an oversight. A reviewer expecting a literal analyze-this-dataset task should read it as a bet that the meta-capability is the more valuable thing to measure.

## 2. Background and related work

Four sources frame the work.

Alex Shaw's Benchtalks #1 (Terminal-Bench, Harbor) [1] is the seed: the benchmark he most wants measures whether agents can write verifiers.

Bercovich, *What Makes a Good Terminal-Agent Benchmark Task* [2], argues a benchmark exists to find out if an agent can do something, not to help it succeed. Its catalog of anti-patterns (over-prescriptive specs, assumed hidden knowledge, validating the wrong thing, reward-hackable environments) shaped the instruction discipline, the anti-cheat work, and the honesty about the tasks the model aces.

HUD's *Verifier and Reward Design for RL Environments* [3] separates outcome verifiers, hard-rule guards, quality rubrics, and the reward that turns them into a training signal, and notes that more capable agents are likelier to exploit a misspecified reward. This motivated keeping the meta-verifier deterministic, with a fractional reward plus a binary `all_correct`.

DABStep (Adyen and Hugging Face) [4] shows real analysis is dirty and distributed, with a low frontier (the strongest agents scored roughly 16%), a good source of hard underlying tasks for the scale plan.

The through-line: the under-measured, valuable thing is verification quality, and the clean way to measure it is a hand-labeled adversarial pool, not a judge.

## 3. Method

### 3.1 The two-layer design

The eval nests two Harbor layers. In Layer 1, the agent writes an executable verifier (`/app/verifier/verify.sh`) that decides whether a candidate solution to an underlying data task is correct.

In Layer 2, a meta-verifier runs that verifier against *N* labeled candidate solutions, compares its verdicts to hidden labels, and emits precision, recall, accuracy, and a binary `all_correct`. There is no LLM judge; the pool's coverage is the operational definition of a good verifier.

### 3.2 Task construction

The reference task, `multi-source-data-verifier`, was built first and by hand: hand-computing the canonical answer, designing the anchored pool, wiring the clean-room anti-cheat, and writing the oracle.

This seeded `PLAYBOOK.md`, the step-by-step SOP. The other five were then built concurrently in Conductor sessions, each following the playbook against a different domain. Building them in parallel is what made five additional domains tractable, and it stress-tested the playbook as a transferable recipe.

### 3.3 Producer-generated pools

The labeled pool is the answer key, and authoring every item by hand is the expensive step. For all six tasks I used the underlying task itself to seed the pool: a Conductor agent hooked up the task and ran it to harvest genuinely-correct and genuinely-incorrect solutions, which became roughly eight labeled base items. What I was aiming for in a complete pool:

- an oracle solution
- a correct AI solution, different from the oracle
- a second correct AI solution, different from the first
- an incorrect solution with the correct shape
- a near miss, one value wrong
- logs from an AI claiming it did the right thing but producing no files (in case the verifier just reads the message trace)
- correct information in the wrong shape
- a nop, nothing happening

The idea was that the producer's natural variation would supply the correct-alternate PASS items and the organic FAIL items for free. In practice I found the underlying task's strength decides whether you actually get a varied pool. The multi-source-data producers, for example, only ever generated passing attempts under gemini, so the FAIL side had to be built by hand. How to tune underlying-task difficulty against agent strength to get a naturally varied producer pool is an open question I would want to explore.

The bigger gap is that a producer run over and over will spit out obvious passes and obvious fails but will not produce the tricky wrong answers that look almost right. I added those by hand, one per task: a value that is correct but the wrong type (a string where an integer was required), a distribution with the right shape but produced by a fixed table instead of real random sampling, an outcome where only one of two required conditions is met, and a log that claims success but never actually wrote the output files.

There is a shortcut for finding these tricky cases. Every underlying task shipped with its own grading test, and that test is usually weak, so instead of trusting it I looked for what it fails to catch. Whatever slips past it is exactly the kind of wrong answer worth putting in the pool. The merge task's original test, for instance, only checked two of the four users and only checked that at least one conflict was found rather than the exact number, so a solution that got the other two users wrong, or found the wrong conflict count, would pass it. Those two gaps became two FAIL items: one for the wrong user values, one for the near-miss conflict count.

One concern runs the other way. Agents tend to over-engineer, and that gets worse when the agent cannot reliably solve the underlying task itself: unsure of the real solution, it hedges by writing an overly elaborate test. The Windows setup task is a good example, since many state-of-the-art models and harnesses still struggle with it, so a verifier-writing agent working from a shaky understanding of the goal may pile on checks to compensate. That points to a tension I would want to probe: how precise the test actually needs to be, versus how much precision just invites the agent to over-engineer.

### 3.4 Anti-cheat

I have to assume the AI's grading script (the verifier) might try to cheat or break the rules. To prevent this, I lock down the grading process using two main security layers:

First, I use "clean-room" grading. The AI's grading script runs in a completely isolated environment. The only thing brought into this fresh environment is the AI's script itself. A pristine, untouched copy of the test data stays safe. This ensures that even if the AI writes a malicious script, it cannot permanently poison the data or hijack the testing tools.

Second, I restrict the script's permissions. The grading script runs as a regular, unprivileged user (often called a "nobody" account), while the true answer key is locked behind administrator (root) access.

For example, if the AI writes a script that simply tries to open the hidden "answer_key.txt" file to automatically give itself a perfect score, the system will deny access, and the script will fail. I use this heavy machinery because AI models are notoriously good at "reward hacking", which is finding sneaky loopholes to achieve a high score without doing the actual work.

### 3.5 Metric

I define a "Pass" strictly as a perfect score. To pass, the script must correctly grade every single test case without a single mistake.

While the system does calculate partial credit (fractional accuracy), I only use that number to diagnose problems behind the scenes, not to determine if the AI actually succeeded. This distinction is vital because the test sets are deliberately loaded with tricky, designed-to-fail examples.

For instance, imagine a test set that has 3 correct items and 8 incorrect items. A lazy AI script that just automatically rejects everything will technically guess 8 out of 11 correctly, scoring roughly 72%. If I relied on partial credit, this completely useless script would look like it performed well. Requiring a perfect 100% binary pass prevents this kind of gaming and provides a much harder, more honest bar for success.

## 4. Results

I tested the AI (`gemini-3.5-flash`) three times on each of the six tasks.

| Task | oracle | pass@3 | rewards across trials |
| --- | --- | --- | --- |
| `multi-source-data-verifier` | 1.0 | **0%** | 0.818, 0.818, 0.818 |
| `adaptive-rejection-sampler` | 1.0 | **0%** | 0.909, 0.909, 0.909 |
| `qemu-win311-setup-verifier` | 1.0 | **0%** | 0.917, 0.833, 0.667 |
| `log-summary-verifier` | 1.0 | **100%** | 1.0, 1.0, 1.0 |
| `video-jump-verifier` | 1.0 | **100%** | 1.0, 1.0, 0.727 |
| `fusion-protein-verifier` | 1.0 | **100%** | 1.0, 0.8, 1.0 |

Here is a summary of what I found:

- **Merge and ARS Tasks:** The AI failed in the exact same way across all three attempts. It missed specific, tricky test cases every single time, scoring around 81% and 90% respectively, but never passing.
    
- **QEMU Task:** The AI failed every time, but its score bounced around between 66% and 91%. The main issue was that it constantly accepted faulty setups that it should have rejected.
    
- **Log-summary, Video-jump, and Fusion-protein Tasks:** The AI consistently wrote perfect grading scripts, scoring 100% almost every time.
    

The most revealing part of this data is how the "Merge" task failed. Initially, I gave the AI a simple test pool, and it scored a perfect 100%. But as soon as I added just three tricky test cases (where the data looked correct but had the wrong internal format), the AI failed.

## 5. Discussion: what makes a target hard?

Why did the same AI perfectly solve some tasks and completely fail others? Difficulty comes down to two features, and a task is a hard target only when it has both.

**1. Allowed variation.** A hard task has many different ways for an answer to be technically correct. The grading script has to be flexible enough to accept harmless differences but strict enough to catch real errors. It has to test the "what," not the "where." Grading a database report, for instance, a valid report might list its columns in a different order or include extra harmless files. A script that demands one exact byte-for-byte match will wrongly fail perfectly good reports.

**2. Reliable traps.** A hard task contains a common pitfall where the most obvious, default way to write the script is silently wrong. Across the hard tasks I saw three kinds:

- **Type coercion.** Instead of checking whether data is correct, the script forces it to fit. Rather than verifying a user ID is actually a number, the AI just converts the text `"101"` into `101`, letting invalid text slip through.
- **Averages instead of randomness.** On the sampling task, the AI checked whether the overall average of the dataset looked right, rather than whether the individual numbers were truly being drawn at random.
- **Half-checking.** On the virtual machine (QEMU) task, the AI checked that the system booted but forgot the second requirement, like verifying the disk was locked in read-only mode.

Operational complexity, by itself, does not make a task hard. The video-jump task made the AI write a script that processes video files, survives crashes, and enforces import rules, and it handled all of that easily. Real difficulty lives in deep logic and reliable traps, not in how many complicated tools the script has to run.

### Are the failures genuine?

Before reading the 0% results as capability gaps, I have to rule out the alternative explanation: that the tasks were unfair, underspecified, or impossible. Three checks say they were not.

First, the agent had everything it needed, by construction. I built the tasks against the anti-pattern catalog in [2], which says difficulty should come from the problem, not the environment. Every rule a pool item tests is stated in the instruction: the merge instruction declares `user_id` an integer and `created_date` a `YYYY-MM-DD` string, the exact contracts the failed items probe. The instructions also state the tolerances ("extra columns or files do not make an attempt wrong") and the full run contract (output path, environment variables, verdict format), so no Harbor-specific or hidden knowledge is assumed. And the environment is not the obstacle: standard slim images with the needed libraries preinstalled and pinned, and the source data readable while the verifier runs.

Second, a perfect verifier is provably writable from those materials, because one already exists. Every task ships with a hand-written oracle verifier, and every oracle scores 1.0 against the same hidden pool in the same environment. Cheating is also ruled out as an explanation in either direction: grading runs clean-room as an unprivileged user, so no verifier, mine or the agent's, can read the answer key.

Third, the failure modes are specific, repeatable reasoning gaps, not noise:

* Merge: all three runs scored an identical 9/11 and missed the same two items, the wrong-integer-type and wrong-date-format traps. The captured verifier shows why: it coerces the declared types instead of enforcing them, converting `"101"` to an integer rather than rejecting it. It enforced the boolean `status` type correctly in those same runs, so the rigor exists; it just does not generalize across the whole contract.
* ARS: all three runs missed exactly one item, a submission that returns a fixed table of quantiles instead of sampling. Every captured verifier checked the distribution's shape but never checked that the draws were actually random. A control experiment (three extra runs, discarded from the results) that reworded the instruction to say "random, not a fixed table" flipped one run to a perfect score, which confirms the reading: the agent can write the randomness check when pointed at it, but lacks the default intuition to reach for it unprompted.
* Log-summary: the flip side, confirming the 100% tasks are honest too. The pool does catch weak verifiers, since a files-exist-only verifier scores 7/12 on it. The agent simply wrote strong verifiers every time, which is why the task earns its place only as a control.

## 6. Scale plan (10 to 1,000)

Per-task cost is dominated by authoring the underlying task and labeling the pool. The plan attacks both.

* Start from tasks that already exist. The first hundred targets come from Terminal-Bench 2, the Harbor hub, DABStep-style problems, and public Kaggle notebooks rather than being authored from scratch. This eval already proved the pattern: the ARS task was lifted from Terminal-Bench 2 and converted into a verifier-synthesis target. Converting existing tasks gets the scaffolding right before any money is spent inventing new problems.

* The difficulty filter. Before building a pool, run a lazy reference verifier (values only, coerces types) and a strict one against a few model-generated outputs. If their scores do not diverge, the task cannot discriminate rigor and is kicked back before labeling. This is the §5 selection rule made operational; log-summary would be flagged here and kept only as a control.

* Cheap producers, one strong checker. The producer harvesting pool solutions just needs to generate varied attempts, so a cheap model does it fine. Labels then come nearly free: the hand-validated oracle scores every output automatically, a stronger model spot-checks, and a human reviews only the disagreements.

* Manufactured traps and multiplication. Producers will not generate the near miss that looks almost right, and §3.3 showed those items do the discriminating. Two automatable sources: a mutation library keyed to the three trap species from §5, and the weak-test audit, where whatever slips past the task's own shipped test becomes a FAIL item. From there, perturbing the canonical answer multiplies the pool cheaply.

* Quality gates and refresh. Every task must pass automated gates before it ships: the oracle scores 1.0, a lazy verifier scores below 1.0, and a reference model's pass@3 stays under 30%. Tasks failing any gate are auto-kicked; video-jump and fusion-protein are that loop working as intended. And since hard is relative to the model, the headroom gate reruns periodically and saturated tasks are retired or re-armed, so the benchmark does not silently decay into 1,000 controls.

## 7. Limitations and Honest Caveats

There are a few limitations to keep in mind regarding this study:

- **Repetitive Behavior:** On some tasks, the AI made the exact same mistakes multiple times. I believe this represents a true capability limit, but it could partly be due to the AI's temperature settings making it highly repetitive. Running tests at a higher temperature would help confirm this.
    
- **Small Test Pools:** The test sets only contained between 11 and 20 items. Expanding these to include more edge cases would give sharper, more precise metrics. For example, adding tests with bizarre date formats or corrupted files would better reveal the AI's weak spots.
    
- **Few Tasks:** I only built six tasks total. Adding a few more hard tasks (like cleaning dirty data or grading complex JSON reports) would give a better picture of exactly where the AI struggles, rather than just a simple "pass or fail" dichotomy.

## References

[1] Benchtalks #1: Alex Shaw (Terminal-Bench, Harbor). https://www.youtube.com/watch?v=UCn5gG0haCI

[2] Bercovich, *What Makes a Good Terminal-Agent Benchmark Task*. arXiv:2604.28093. https://arxiv.org/pdf/2604.28093

[3] HUD, *Verifier and Reward Design for RL Environments*. https://www.hud.ai/resources/verifier-reward-design-rl-environments

[4] DABStep: Data Agent Benchmark for Multi-step Reasoning (Adyen and Hugging Face). https://huggingface.co/blog/dabstep
