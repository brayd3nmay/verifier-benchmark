import os
import sys
import json

CODON_TABLE = {
    'ATA':'I', 'ATC':'I', 'ATT':'I', 'ATG':'M',
    'ACA':'T', 'ACC':'T', 'ACG':'T', 'ACT':'T',
    'AAC':'N', 'AAT':'N', 'AAA':'K', 'AAG':'K',
    'AGC':'S', 'AGT':'S', 'AGA':'R', 'AGG':'R',
    'CTA':'L', 'CTC':'L', 'CTG':'L', 'CTT':'L',
    'CCA':'P', 'CCC':'P', 'CCG':'P', 'CCT':'P',
    'CAC':'H', 'CAT':'H', 'CAA':'Q', 'CAG':'Q',
    'CGA':'R', 'CGC':'R', 'CGG':'R', 'CGT':'R',
    'GTA':'V', 'GTC':'V', 'GTG':'V', 'GTT':'V',
    'GCA':'A', 'GCC':'A', 'GCG':'A', 'GCT':'A',
    'GAC':'D', 'GAT':'D', 'GAA':'E', 'GAG':'E',
    'GGA':'G', 'GGC':'G', 'GGG':'G', 'GGT':'G',
    'TCA':'S', 'TCC':'S', 'TCG':'S', 'TCT':'S',
    'TTC':'F', 'TTT':'F', 'TTA':'L', 'TTG':'L',
    'TAC':'Y', 'TAT':'Y', 'TAA':'*','TAG':'*',
    'TGC':'C', 'TGT':'C', 'TGA':'*','TGG':'W',
}

def translate(dna):
    protein = []
    for i in range(0, len(dna) - 2, 3):
        codon = dna[i:i+3]
        protein.append(CODON_TABLE.get(codon, 'X'))
    return "".join(protein)

def verify():
    solution_dir = os.environ.get("SOLUTION_DIR", "/app")
    verdict_file = os.environ.get("VERDICT_FILE", "/logs/verifier/reward.txt")

    # Ensure the directory of verdict file exists
    verdict_dir = os.path.dirname(verdict_file)
    if verdict_dir and not os.path.exists(verdict_dir):
        os.makedirs(verdict_dir, exist_ok=True)

    gblock_path = os.path.join(solution_dir, "gblock.txt")
    if not os.path.exists(gblock_path):
        print(f"gblock.txt not found at {gblock_path}")
        with open(verdict_file, "w") as f:
            f.write("0\n")
        return

    try:
        with open(gblock_path, "r") as f:
            lines = f.readlines()
    except Exception as e:
        print("Error reading file:", e)
        with open(verdict_file, "w") as f:
            f.write("0\n")
        return

    # Check format rules:
    # "contains only the gBlock sequence, on a single line — nothing else, no empty lines."
    if len(lines) != 1:
        print(f"Expected exactly 1 line, got {len(lines)}")
        with open(verdict_file, "w") as f:
            f.write("0\n")
        return

    line = lines[0]
    # Ensure no trailing newline or carriage return or whitespace EXCEPT a single standard newline is fine
    # wait, the file can end with a newline but it must be only a single line.
    # Let's clean the line. Standard text editors might append a single \n.
    # Let's check if there is an empty line at the end, or what. 
    # "on a single line — nothing else, no empty lines"
    raw_seq = line.strip()
    if not raw_seq:
        print("Empty sequence")
        with open(verdict_file, "w") as f:
            f.write("0\n")
        return

    # Check that sequence uses only bases A, T, C, G
    allowed_bases = set("ATCG")
    # DNA bases can be lowercase/uppercase, but let's check uppercase conversion
    seq = raw_seq.upper()
    if not all(c in allowed_bases for c in seq):
        print("Invalid characters in DNA sequence")
        with open(verdict_file, "w") as f:
            f.write("0\n")
        return

    # gBlock must be at most 3000 nucleotides
    if len(seq) > 3000:
        print(f"gBlock too long: {len(seq)} nt")
        with open(verdict_file, "w") as f:
            f.write("0\n")
        return

    # gBlock length must be a multiple of 3 to encode a complete protein
    if len(seq) % 3 != 0:
        print(f"gBlock length {len(seq)} is not a multiple of 3")
        with open(verdict_file, "w") as f:
            f.write("0\n")
        return

    # Every 50-nucleotide window has GC content between 30% and 70%
    if len(seq) < 50:
        print("gBlock is less than 50 nt")
        with open(verdict_file, "w") as f:
            f.write("0\n")
        return

    for i in range(len(seq) - 49):
        window = seq[i:i+50]
        gc_count = window.count('G') + window.count('C')
        gc_pct = gc_count / 50.0
        if gc_pct < 0.30 or gc_pct > 0.70:
            print(f"Window {i} to {i+50} has invalid GC content: {gc_pct:.1%}")
            with open(verdict_file, "w") as f:
                f.write("0\n")
            return

    # No start or stop codons
    # First, does the DNA contain any stop codons in-frame?
    # Also, does it have a start codon (ATG) at the beginning?
    # We also check that the translation does not contain '*'
    # Let's check stop codons in the reading frame of the gBlock (frame 1, index 0)
    for i in range(0, len(seq), 3):
        codon = seq[i:i+3]
        if codon in ['TAA', 'TAG', 'TGA']:
            print(f"In-frame stop codon {codon} found at position {i}")
            with open(verdict_file, "w") as f:
                f.write("0\n")
            return

    # Does the gBlock start with a start codon (ATG)?
    if seq.startswith("ATG"):
        print("gBlock starts with start codon ATG")
        with open(verdict_file, "w") as f:
            f.write("0\n")
        return

    # Translate sequence
    translated = translate(seq)
    if 'X' in translated:
        print("Unrecognized codon in sequence")
        with open(verdict_file, "w") as f:
            f.write("0\n")
        return

    # Load subproteins
    try:
        with open("/app/verifier/subproteins.json") as sf:
            subproteins = json.load(sf)
    except Exception as e:
        print("Failed to load subproteins list:", e)
        with open(verdict_file, "w") as f:
            f.write("0\n")
        return

    antibody_binder = subproteins["antibody_binder"]
    donor = subproteins["donor"]
    dhfr = subproteins["dhfr"]
    acceptor = subproteins["acceptor"]
    molecule_binder = subproteins["molecule_binder"]

    # Check that it encodes only the 5 subproteins and GS linkers in the correct order
    # Order: antibody binder — donor — DHFR — acceptor — molecule binder
    # No N or C terminal linkers
    if not translated.startswith(antibody_binder):
        print("Protein does not start with antibody binder")
        with open(verdict_file, "w") as f:
            f.write("0\n")
        return

    if not translated.endswith(molecule_binder):
        print("Protein does not end with molecule binder")
        with open(verdict_file, "w") as f:
            f.write("0\n")
        return

    # Find the positions
    idx_ab = 0
    len_ab = len(antibody_binder)

    idx_donor = translated.find(donor, len_ab)
    if idx_donor == -1:
        print("Donor not found in correct position")
        with open(verdict_file, "w") as f:
            f.write("0\n")
        return

    linker1 = translated[len_ab : idx_donor]

    idx_dhfr = translated.find(dhfr, idx_donor + len(donor))
    if idx_dhfr == -1:
        print("DHFR not found in correct position")
        with open(verdict_file, "w") as f:
            f.write("0\n")
        return

    linker2 = translated[idx_donor + len(donor) : idx_dhfr]

    idx_acceptor = translated.find(acceptor, idx_dhfr + len(dhfr))
    if idx_acceptor == -1:
        print("Acceptor not found in correct position")
        with open(verdict_file, "w") as f:
            f.write("0\n")
        return

    linker3 = translated[idx_dhfr + len(dhfr) : idx_acceptor]

    idx_mb = translated.find(molecule_binder, idx_acceptor + len(acceptor))
    if idx_mb == -1:
        print("Molecule binder not found in correct position")
        with open(verdict_file, "w") as f:
            f.write("0\n")
        return

    # Since we already checked endswith(molecule_binder), idx_mb + len(molecule_binder) must be len(translated)
    if idx_mb + len(molecule_binder) != len(translated):
        print("Extra sequence after molecule binder")
        with open(verdict_file, "w") as f:
            f.write("0\n")
        return

    linker4 = translated[idx_acceptor + len(acceptor) : idx_mb]

    # Check linkers
    linkers = [linker1, linker2, linker3, linker4]
    for i, l in enumerate(linkers, 1):
        # Length between 5 and 20 amino acids
        if len(l) < 5 or len(l) > 20:
            print(f"Linker {i} has invalid length {len(l)}: '{l}'")
            with open(verdict_file, "w") as f:
                f.write("0\n")
            return
        # Contains only G and S
        if not all(c in "GS" for c in l):
            print(f"Linker {i} contains non-GS amino acids: '{l}'")
            with open(verdict_file, "w") as f:
                f.write("0\n")
            return

    print("All checks passed successfully!")
    with open(verdict_file, "w") as f:
        f.write("1\n")

if __name__ == "__main__":
    verify()
