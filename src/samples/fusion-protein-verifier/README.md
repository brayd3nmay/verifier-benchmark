# fusion-protein-verifier

A **verifier-writing** Harbor meta-task. The agent under test is not asked to design a
fusion-protein gBlock — it is asked to **write the verifier** that decides whether a given
gBlock attempt is correct. That verifier (`/app/verifier/verify.sh`) is then graded,
deterministically, against a hidden pool of labeled gBlocks: correct ones must pass,
adversarial ones must fail. No LLM judge.

The underlying task is `harbor-framework/terminal-bench-2/protein-assembly`: design a gBlock
encoding a FRET fusion of five subproteins (antibody binder → donor FP → DHFR → acceptor FP
→ molecule binder) with GS linkers, per-window GC limits, and a length cap. See
`instruction.md` for the full spec the verifier must enforce.

## Layout

- `instruction.md` — the prompt (situation, gBlock spec, verifier contract).
- `environment/` — the agent image + the design inputs (`pdb_ids.txt`, `plasmid.gb`,
  `antibody.fasta`) served at `/app/data`. The agent must resolve the reference proteins
  from these plus the public APIs (PDB/FPBase/PubChem); the answer is not provided.
- `solution/solve.sh` — the oracle: writes a correct reference verifier. It hardcodes the
  resolved reference sequences so grading is deterministic and offline.
- `_build_pool.py` — dev-time pool generator (needs `dnachisel` + `biopython`). Builds
  `tests/pool/<item>/…` and `tests/pool/labels.json`, and syncs `tests/data` from
  `environment/data`.
- `tests/` — the clean-room verifier image (`Dockerfile`), the grading harness
  (`harness.py`, copied verbatim from the reference task), `test.sh`, and the baked pool.

## Anti-cheat

`environment_mode = "separate"` grades in a clean image the agent never touched; only the
agent's `verify.sh` is carried over (as an artifact). The harness runs each candidate as
`nobody` with `tests/pool` locked root-only, so the untrusted verifier cannot read
`labels.json`. Harbor builds/injects the verifier only after the agent stops, so the pool is
never visible during the agent's run.

## Build the pool

```bash
uv run --with biopython --with dnachisel --with pandas python _build_pool.py
```

## Validate

See `PLAYBOOK.md` (repo root), section 10 — oracle scores 1.0, a weak verifier scores < 1.0,
a label-reading verifier is denied, and `nop` scores 0.
