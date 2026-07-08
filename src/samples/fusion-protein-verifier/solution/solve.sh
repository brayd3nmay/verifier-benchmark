#!/bin/bash
# Oracle solution: write a correct reference verifier to /app/verifier/verify.sh.
# The harness runs it against the labeled pool; it must classify every item correctly
# (reward 1.0). This is what "a good verifier" looks like for this task.
#
# The task lets the verifier resolve the five reference proteins live (PDB/FPBase/plasmid).
# We instead hardcode the once-resolved sequences: an equally valid verifier that keeps
# grading deterministic and offline. Strictness is the point — the oracle enforces the
# declared order, terminus anchoring, GS-only bounded linkers, the ATCG alphabet, the
# reading frame, the length cap, and the GC content of EVERY 50-nt window.
set -euo pipefail

mkdir -p /app/verifier

cat > /app/verifier/ref_verify.py <<'PYEOF'
import os
import re
import sys

from Bio.Seq import Seq

SOL = os.environ.get("SOLUTION_DIR", "/app")
VERDICT = os.environ.get("VERDICT_FILE", "/logs/verifier/reward.txt")

# Reference subprotein sequences (N-terminal Met removed), resolved once from the design
# inputs + public APIs: FLAG antibody-binder (DYKDDDDK); donor FP (505 nm excitation) and
# acceptor FP (610 nm emission) from FPBase-matched PDB ids; DHFR from plasmid.gb; SNAP-tag
# molecule-binder (binds the O6-benzylguanine SMILES). Order is N->C.
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
ORDER = [("antibody_binder", FLAG), ("donor", DONOR), ("dhfr", DHFR),
         ("acceptor", ACCEPTOR), ("molecule_binder", SNAP)]


def emit(ok, msg=""):
    d = os.path.dirname(VERDICT)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(VERDICT, "w") as f:
        f.write("1" if ok else "0")
    print(("PASS" if ok else "FAIL"), msg)
    sys.exit(0)


path = os.path.join(SOL, "gblock.txt")
if not os.path.isfile(path):
    emit(False, "missing gblock.txt")

with open(path) as f:
    lines = [ln.rstrip() for ln in f]
if len(lines) != 1:
    emit(False, f"expected exactly one line, got {len(lines)}")
gblock = lines[0].lower()

if not re.fullmatch(r"[atcg]+", gblock):
    emit(False, "gBlock must contain only A, T, C, G")
if len(gblock) > 3000:
    emit(False, f"gBlock too long ({len(gblock)} nt)")
if len(gblock) % 3 != 0:
    emit(False, "gBlock length is not a multiple of 3")

aa = str(Seq(gblock).translate())

idx = {}
for name, seq in ORDER:
    i = aa.find(seq)
    if i < 0:
        emit(False, f"missing {name}")
    idx[name] = i

pos = [idx[name] for name, _ in ORDER]
if not all(pos[k] < pos[k + 1] for k in range(len(pos) - 1)):
    emit(False, "subproteins not in order antibody-donor-dhfr-acceptor-molecule")
if idx["antibody_binder"] != 0:
    emit(False, "gBlock does not start with the antibody binder")
if idx["molecule_binder"] + len(SNAP) != len(aa):
    emit(False, "gBlock does not end with the molecule binder")

for (a_name, a_seq), (b_name, _b_seq) in zip(ORDER, ORDER[1:]):
    linker = aa[idx[a_name] + len(a_seq):idx[b_name]]
    if not re.fullmatch(r"[GS]+", linker):
        emit(False, f"linker {a_name}->{b_name} is not all G/S")
    if not (5 <= len(linker) <= 20):
        emit(False, f"linker {a_name}->{b_name} length {len(linker)} not in 5..20")

gc = sum(c in "gc" for c in gblock[:50])
if not (15 <= gc <= 35):
    emit(False, "GC content outside 30-70% in a 50-nt window")
for i in range(50, len(gblock)):
    gc += (gblock[i] in "gc") - (gblock[i - 50] in "gc")
    if not (15 <= gc <= 35):
        emit(False, "GC content outside 30-70% in a 50-nt window")

emit(True, "all checks passed")
PYEOF

cat > /app/verifier/verify.sh <<'SHEOF'
#!/bin/bash
python3 /app/verifier/ref_verify.py
SHEOF

chmod +x /app/verifier/verify.sh
echo "Reference verifier written to /app/verifier/verify.sh"
