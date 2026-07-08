A colleague is preparing a FRET experiment on dihydrofolate reductase (DHFR). They image with a filter cube whose excitation and emission filters pass 505 nm and 610 nm respectively. They need a fusion protein containing DHFR that can be pulled down onto beads coated with the molecule whose SMILES is `Nc3nc(OCc1ccccc1)c2nc[nH]c2n3`, and that binds the antibody whose heavy and light chains are in `/app/data/antibody.fasta`. They will encode this fusion in a gBlock (a synthetic DNA fragment) and will hand you attempts as a file `/app/gblock.txt`.

Write a verifier that decides whether a given attempt is a correct gBlock. The design inputs stay readable at `/app/data` while your verifier runs — `pdb_ids.txt`, `plasmid.gb`, and `antibody.fasta` — and the public bioinformatics APIs (PDB, FPBase, PubChem) are reachable, so you can derive the correct reference proteins.

A correct gBlock meets all of the following:

 * `/app/gblock.txt` contains only the gBlock sequence, on a single line — nothing else, no empty lines.
 * The sequence uses only the DNA bases A, T, C, and G.
 * It encodes only GS linkers and five subproteins: the molecule-binding protein, the antibody-binding protein, the donor, the acceptor, and DHFR.
 * The molecule binder, the donor, and the acceptor each encode a protein whose PDB id is listed in `pdb_ids.txt`, with the protein sequence the PDB API returns for that id.
 * The antibody binder encodes the protein the antibody in `antibody.fasta` was raised against — only the most common variant of that protein, encoded once (repeating it to raise affinity is not allowed). It does not need to be one of the PDB ids.
 * DHFR reuses the protein sequence found in `plasmid.gb`.
 * The donor's peak excitation and the acceptor's peak emission match the filter cube exactly (505 nm and 610 nm) per the data returned by the FPBase API.
 * No start or stop codons (the plasmid supplies those).
 * The N-terminal methionine is removed from every subprotein (the plasmid supplies it).
 * Subprotein order from N to C terminus is: antibody binder — donor — DHFR — acceptor — molecule binder.
 * There is a GS linker between every adjacent pair of subproteins, and no linker on the N or C terminus.
 * Each linker contains only G and S amino acids and is between 5 and 20 amino acids long.
 * Every 50-nucleotide window of the gBlock has GC content between 30% and 70%.
 * The gBlock is at most 3000 nucleotides long.

Write your verifier as an executable at `/app/verifier/verify.sh`. It is run once per attempt: it reads the attempt's `gblock.txt` from `SOLUTION_DIR` (default `/app`), may read agent logs from `ARTIFACTS_DIR`, and writes `1` (correct) or `0` (incorrect) to `VERDICT_FILE` (default `/logs/verifier/reward.txt`).
