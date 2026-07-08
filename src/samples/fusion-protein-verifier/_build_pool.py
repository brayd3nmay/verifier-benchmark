#!/usr/bin/env python3
"""Materialize the labeled pool the agent's verifier is graded against.

Run from the task root (needs biopython + dnachisel + pandas):

    uv run --with biopython --with dnachisel --with pandas python _build_pool.py

Writes tests/pool/<NN_name>/solution/gblock.txt (candidate output), optional
tests/pool/<NN_name>/artifacts/... (agent logs), and tests/pool/labels.json. The pool is
the answer key: a correct verifier PASSes every "pass" item and FAILs every "fail" item.

Each valid gBlock is codon-optimized so its every 50-nt window sits inside 30-70% GC; each
FAIL item perturbs exactly one stated rule. Every item is self-checked here against the same
logic the oracle verifier uses (`oracle_check`), so the pool can't drift from the grader.
"""
import json
import os
import shutil

import numpy as np
from Bio.Seq import Seq
from dnachisel import (
    CodonOptimize,
    DnaOptimizationProblem,
    EnforceGCContent,
    EnforceTranslation,
    reverse_translate,
)

np.random.seed(0)  # keep dnachisel's search reproducible across builds

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "environment", "data")
POOL = os.path.join(ROOT, "tests", "pool")

# Reference subprotein sequences (N-terminal Met removed), resolved once from the design
# inputs + public APIs. Kept identical to solution/solve.sh (the oracle) — the ground truth.
FLAG = "DYKDDDDK"
DONOR = ("GSSHHHHHHSSGENLYFQGHMVSKGEELFTGVVPILVELDGDVNGHKFSVRGEGEGDATNGKLTLKFICTTGKLPVP"
         "WPTLVTTFGYGVACFSRYPDHMKQHDFFKSAMPEGYVQERTISFKDDGTYKTRAEVKFEGDTLVNRIELKGIDFKEDG"
         "NILGHKLEYNFNSHNVYITADKQKNGIKANFKIRHNVEDGSVQLADHYQQNTPIGDGPVLLPDNHYLSHQSALSKDPN"
         "EKRDHMVLLEFVTAAGITHGMDELYK")
DHFR = ("ISLIAALAVDRVIGMENAMPWNLPADLAWFKRNTLNKPVIMGRHTWESIGRPLPGRKNIILSSQPGTDDRVTWVKSVD"
        "EAIAACGDVPEIMVIGGGRVYEQFLPKAQKLYLTHIDAEVEGDTHFPDYEPDDWESVFSEFHDADAQNSHSYCFEILERR")
ACCEPTOR = ("VSKGEEDNMAIIKEFMRFKVHMEGSVNGHEFEIEGEGEGRPYEGTQTAKLKVTKGGPLPFAWDILSPQFMYGSKAYVK"
            "HPADIPDYLKLSFPEGFKWERVMNFEDGGVVTVTQDSSLQDGEFIYKVKLRGTNFPSDGPVMQKKTMGWEASSERMYP"
            "EDGALKGEIKQRLKLKDGGHYDAEVKTTYKAKKPVQLPGAYNVNIKLDITSHNEDYTIVEQYERAEGRHSTGGMDELYK")
SNAP = ("GPGSDKDCEMKRTTLDSPLGKLELSGCEQGLHEIIFLGKGTSAADAVEVPAPAAVLGGPEPLMQATAWLNAYFHQPEA"
        "IEEFPVPALHHPVFQQESFTRQVLWKLLKVVKFGEVISYSHLAALAGNPAATAAVKTALSGNPVPILIPCHRVVQGDL"
        "DVGGYEGGLAVKEWLLAHEGHRLGKR")
PROTEINS = [FLAG, DONOR, DHFR, ACCEPTOR, SNAP]

# Highest-GC synonymous codon per amino acid — used to spike a region's GC for the GC-window
# FAIL items without changing the translation.
MAX_GC_CODON = {
    "A": "GCC", "R": "CGC", "N": "AAC", "D": "GAC", "C": "TGC", "Q": "CAG", "E": "GAG",
    "G": "GGC", "H": "CAC", "I": "ATC", "L": "CTG", "K": "AAG", "M": "ATG", "F": "TTC",
    "P": "CCC", "S": "TCC", "T": "ACC", "W": "TGG", "Y": "TAC", "V": "GTG",
}


# ---------------------------------------------------------------------------
# The oracle's grading logic, reused to self-check every item at build time.
# Mirrors solution/solve.sh:ref_verify.py exactly.
# ---------------------------------------------------------------------------
def oracle_check(text):
    lines = [ln.rstrip() for ln in text.split("\n")]
    # split keeps a trailing "" for a final newline; drop a single trailing empty line the
    # way iterating a file object does (a file "x\n" yields one line, "x\n\n" yields two).
    if lines and lines[-1] == "":
        lines = lines[:-1]
    if len(lines) != 1:
        return False, f"expected one line, got {len(lines)}"
    g = lines[0].lower()
    import re
    if not re.fullmatch(r"[atcg]+", g):
        return False, "non-ATCG"
    if len(g) > 3000:
        return False, "too long"
    if len(g) % 3 != 0:
        return False, "not multiple of 3"
    aa = str(Seq(g).translate())
    names = ["antibody_binder", "donor", "dhfr", "acceptor", "molecule_binder"]
    idx = {}
    for name, seq in zip(names, PROTEINS):
        i = aa.find(seq)
        if i < 0:
            return False, f"missing {name}"
        idx[name] = i
    pos = [idx[n] for n in names]
    if not all(pos[k] < pos[k + 1] for k in range(len(pos) - 1)):
        return False, "out of order"
    if idx["antibody_binder"] != 0:
        return False, "no antibody binder at start"
    if idx["molecule_binder"] + len(SNAP) != len(aa):
        return False, "no molecule binder at end"
    for (a_name, a_seq), b_name in zip(zip(names, PROTEINS), names[1:]):
        linker = aa[idx[a_name] + len(a_seq):idx[b_name]]
        if not re.fullmatch(r"[GS]+", linker):
            return False, f"linker {a_name}->{b_name} not G/S"
        if not (5 <= len(linker) <= 20):
            return False, f"linker {a_name}->{b_name} len {len(linker)}"
    gc = sum(c in "gc" for c in g[:50])
    if not (15 <= gc <= 35):
        return False, "GC window (first)"
    for i in range(50, len(g)):
        gc += (g[i] in "gc") - (g[i - 50] in "gc")
        if not (15 <= gc <= 35):
            return False, "GC window"
    return True, "ok"


def max_window_gc(dna):
    g = dna.lower()
    gc = sum(c in "gc" for c in g[:50])
    hi = gc
    for i in range(50, len(g)):
        gc += (g[i] in "gc") - (g[i - 50] in "gc")
        hi = max(hi, gc)
    return hi


# ---------------------------------------------------------------------------
# gBlock construction
# ---------------------------------------------------------------------------
def assemble(linkers):
    """AA sequence: antibody-binder, then donor/dhfr/acceptor/molecule joined by linkers."""
    parts = [FLAG]
    for prot, link in zip(PROTEINS[1:], linkers):
        parts.append(link)
        parts.append(prot)
    return "".join(parts)


def optimize(aa, mini=0.34, maxi=0.66, species=None):
    """Codon-optimize AA -> DNA keeping every 50-nt window in [mini, maxi] GC."""
    problem = DnaOptimizationProblem(
        sequence=reverse_translate(aa),
        constraints=[EnforceTranslation(),
                     EnforceGCContent(mini=mini, maxi=maxi, window=50)],
        objectives=[CodonOptimize(species=species)] if species else [],
        logger=None,
    )
    problem.resolve_constraints()
    if species:
        problem.optimize()
    dna = problem.sequence.lower()
    assert str(Seq(dna).translate()) == aa, "translation drift"
    return dna


def reencode(dna, aa, start_codon, end_codon):
    """Replace codons [start_codon, end_codon) with their max-GC synonyms (spike GC)."""
    codons = [dna[i * 3:i * 3 + 3] for i in range(len(aa))]
    for i in range(start_codon, end_codon):
        codons[i] = MAX_GC_CODON[aa[i]].lower()
    return "".join(codons)


# ---------------------------------------------------------------------------
# Pool item helpers
# ---------------------------------------------------------------------------
def reset(name):
    d = os.path.join(POOL, name)
    if os.path.exists(d):
        shutil.rmtree(d)
    sol = os.path.join(d, "solution")
    os.makedirs(sol)
    return d, sol


labels = {}


def emit(name, text, expect_pass):
    _, sol = reset(name)
    with open(os.path.join(sol, "gblock.txt"), "w") as f:
        f.write(text)
    ok, msg = oracle_check(text)
    assert ok == expect_pass, f"{name}: oracle {ok} ({msg}) but expected pass={expect_pass}"
    labels[name] = "pass" if expect_pass else "fail"


# Standard set of four valid linkers (all G/S, lengths 5..20).
CANON_LINKERS = ["GGGGSGGGGS", "GSGSGSGS", "GGSGGSGGS", "SGGGGSGGGGS"]


def main():
    for seq, n in zip(PROTEINS, (8, 259, 158, 235, 182)):
        assert len(seq) == n, f"reference length drift: {len(seq)} != {n}"

    canon_aa = assemble(CANON_LINKERS)
    canon = optimize(canon_aa)
    assert len(canon) <= 3000, len(canon)

    # ---- PASS items -------------------------------------------------------
    emit("01_oracle", canon + "\n", True)

    # different codon usage + linkers at the length bounds (5 and 20) + varied G/S patterns
    alt_linkers = ["GGGGS", "GSGSGSGSGSGSGSGSGSGS", "GGGGSGGGGS", "SSGGSSGGSS"]
    alt = optimize(assemble(alt_linkers), species="e_coli")
    emit("02_correct_alt", alt + "\n", True)

    # UPPERCASE + GC hugging the 30/70% edges; catches case-sensitive / too-tight verifiers
    edge = optimize(canon_aa, mini=0.30, maxi=0.70)
    emit("03_correct_upper_edge", edge.upper() + "\n", True)

    # ---- FAIL items -------------------------------------------------------
    # donor/acceptor swapped
    swapped_aa = (FLAG + CANON_LINKERS[0] + ACCEPTOR + CANON_LINKERS[1] + DHFR
                  + CANON_LINKERS[2] + DONOR + CANON_LINKERS[3] + SNAP)
    emit("04_wrong_order", optimize(swapped_aa) + "\n", False)

    # extra non-G/S residues after the molecule binder (molecule binder not at the end)
    junk_aa = canon_aa + "AAAAAA"
    emit("05_junk_terminus", optimize(junk_aa) + "\n", False)

    # a valid-looking GS linker AFTER the molecule binder (terminus linker)
    term_aa = canon_aa + "GSGSGSGS"
    emit("06_terminal_linker", optimize(term_aa) + "\n", False)

    # interior linker containing a non-G/S residue
    ng_linkers = list(CANON_LINKERS)
    ng_linkers[1] = "GGASGGSGG"  # 'A' is not allowed in a linker
    emit("07_linker_nongs", optimize(assemble(ng_linkers)) + "\n", False)

    # interior linker shorter than 5
    short_linkers = list(CANON_LINKERS)
    short_linkers[2] = "GGSS"  # length 4
    emit("08_linker_too_short", optimize(assemble(short_linkers)) + "\n", False)

    # two subproteins directly adjacent (no linker between donor and dhfr)
    miss_linkers = list(CANON_LINKERS)
    miss_linkers[1] = ""
    emit("09_missing_linker", optimize(assemble(miss_linkers)) + "\n", False)

    # GC-maxed throughout (first window and many interior windows well above 70% GC);
    # catches verifiers that skip the GC check or check only the first window
    gc_bad = reencode(canon, canon_aa, 0, len(canon_aa))
    assert oracle_check(gc_bad + "\n")[0] is False
    assert max_window_gc(gc_bad) > 35
    emit("10_gc_violation", gc_bad + "\n", False)

    # local interior GC spike: the FIRST window is fine but an interior window exceeds 70%
    # (catches verifiers that check only the first window or a sparse subset of windows)
    mid = len(canon_aa) // 2
    near = reencode(canon, canon_aa, mid - 9, mid + 9)
    first_win_gc = sum(c in "gc" for c in near[:50].lower())
    assert first_win_gc <= 35, first_win_gc
    assert max_window_gc(near) > 35, max_window_gc(near)
    emit("11_gc_near_miss", near + "\n", False)

    # spectrally-wrong donor: right structure, but the donor is not the exact resolved
    # protein (a handful of residues changed) -> a verifier that only checks "an FP is
    # present" passes it wrongly
    wrong_donor = DONOR[:40] + "AAAAA" + DONOR[45:]
    assert wrong_donor != DONOR and len(wrong_donor) == len(DONOR)
    wp_aa = (FLAG + CANON_LINKERS[0] + wrong_donor + CANON_LINKERS[1] + DHFR
             + CANON_LINKERS[2] + ACCEPTOR + CANON_LINKERS[3] + SNAP)
    emit("12_wrong_protein", optimize(wp_aa) + "\n", False)

    # contains a non-ATCG base
    non_atcg = canon[:100] + "n" + canon[101:]
    emit("13_non_atcg", non_atcg + "\n", False)

    # valid sequence but a trailing empty line (file must hold only the sequence)
    emit("14_multiline", canon + "\n\n", False)

    # nothing produced
    reset("15_nop")
    labels["15_nop"] = "fail"
    assert oracle_check("")[0] is False

    # no gblock.txt, but a trajectory narrating success (catches trace-gullible verifiers)
    d, _sol = reset("16_logs_no_files")
    shutil.rmtree(os.path.join(d, "solution"))
    art = os.path.join(d, "artifacts")
    os.makedirs(art)
    json.dump({"messages": [
        {"role": "assistant", "content": "Resolved donor/acceptor from FPBase and the PDB ids."},
        {"role": "assistant", "content": "Assembled FLAG-donor-DHFR-acceptor-SNAP with GS linkers."},
        {"role": "assistant", "content": "Codon-optimized; all 50-nt GC windows within 30-70%."},
        {"role": "assistant", "content": "Wrote /app/gblock.txt (2586 nt). Done; tests should pass."},
    ]}, open(os.path.join(art, "trajectory.json"), "w"), indent=2)
    labels["16_logs_no_files"] = "fail"

    # ---- extra coverage surfaced by the red-team ----
    # valid, but linkers are pure-G / pure-S runs (still [GS], 5..20) + different codons;
    # catches verifiers that hardcode an alternating "GS" pattern
    pure_linkers = ["GGGGGGGGGG", "SSSSSSSSSS", "GGGGGSSSSS", "SGSGSGSGSG"]
    emit("17_correct_pure_linkers", optimize(assemble(pure_linkers), species="e_coli") + "\n", True)

    # length not a multiple of 3 (a frameshift): isolates the reading-frame check — a verifier
    # that translates without checking the frame still finds all five proteins and passes
    emit("18_frameshift", canon + "a\n", False)

    # an interior linker longer than 20 aa (the upper bound; 08 covers the lower bound)
    long_linkers = list(CANON_LINKERS)
    long_linkers[0] = "GS" * 10 + "G"  # 21 aa
    emit("19_linker_too_long", optimize(assemble(long_linkers)) + "\n", False)

    # wrong molecule binder: right structure, but the SNAP-tag is not the exact resolved
    # protein (broadens exact-identity coverage beyond the donor in 12)
    wrong_snap = SNAP[:60] + "AAAAA" + SNAP[65:]
    assert wrong_snap != SNAP and len(wrong_snap) == len(SNAP)
    wm_aa = (FLAG + CANON_LINKERS[0] + DONOR + CANON_LINKERS[1] + DHFR
             + CANON_LINKERS[2] + ACCEPTOR + CANON_LINKERS[3] + wrong_snap)
    emit("20_wrong_molecule_binder", optimize(wm_aa) + "\n", False)

    with open(os.path.join(POOL, "labels.json"), "w") as f:
        json.dump(labels, f, indent=2)

    # Keep the verifier image's pristine input copy identical to what the agent sees.
    tests_data = os.path.join(ROOT, "tests", "data")
    if os.path.exists(tests_data):
        shutil.rmtree(tests_data)
    shutil.copytree(DATA, tests_data)

    n_pass = sum(v == "pass" for v in labels.values())
    print(json.dumps(labels, indent=2))
    print(f"\n{len(labels)} items ({n_pass} pass / {len(labels) - n_pass} fail); "
          f"canonical gBlock = {len(canon)} nt")
    print(f"Pool written to {POOL}; tests/data synced from {DATA}")


if __name__ == "__main__":
    main()
