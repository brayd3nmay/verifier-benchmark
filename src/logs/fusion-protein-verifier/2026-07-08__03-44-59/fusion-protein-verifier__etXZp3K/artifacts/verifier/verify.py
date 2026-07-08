import os
import sys

CODON_MAP = {
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
    'TAC':'Y', 'TAT':'Y', 'TAA':'*', 'TAG':'*',
    'TGC':'C', 'TGT':'C', 'TGA':'*', 'TGG':'W',
}

def translate(dna):
    return ''.join([CODON_MAP.get(dna[i:i+3], '?') for i in range(0, len(dna), 3)])

def check_gblock(gblock_path):
    if not os.path.exists(gblock_path):
        return 0, "File not found"
    with open(gblock_path, 'rb') as f:
        raw = f.read()
    
    text = raw.decode('utf-8', errors='ignore')
    raw_lines = text.splitlines()
    non_empty = [l for l in raw_lines if l.strip()]
    if len(non_empty) != 1:
        return 0, f"Expected 1 non-empty line, found {len(non_empty)}"
    
    # Check single line with no other empty lines
    if b'\n' in raw:
        first_nl = raw.index(b'\n')
        if first_nl < len(raw) - 1:
            remaining = raw[first_nl+1:]
            if remaining.strip() or remaining.count(b'\n') > 0:
                return 0, "Contains multiple lines"
                
    gblock_seq = non_empty[0].strip().upper()
    
    if not all(c in 'ATCG' for c in gblock_seq):
        return 0, "Contains non-ATCG"
        
    if len(gblock_seq) > 3000:
        return 0, "Length > 3000"
    if len(gblock_seq) % 3 != 0:
        return 0, "Length not multiple of 3"
        
    for i in range(len(gblock_seq) - 49):
        window = gblock_seq[i:i+50]
        gc = sum(1 for c in window if c in 'GC')
        if not (15 <= gc <= 35):
            return 0, f"GC window failed at {i}"
            
    protein = translate(gblock_seq)
    if '*' in protein:
        return 0, "Contains stop codon"
        
    sub1 = "DYKDDDDK"
    sub2 = "GSSHHHHHHSSGENLYFQGHMVSKGEELFTGVVPILVELDGDVNGHKFSVRGEGEGDATNGKLTLKFICTTGKLPVPWPTLVTTFGYGVACFSRYPDHMKQHDFFKSAMPEGYVQERTISFKDDGTYKTRAEVKFEGDTLVNRIELKGIDFKEDGNILGHKLEYNFNSHNVYITADKQKNGIKANFKIRHNVEDGSVQLADHYQQNTPIGDGPVLLPDNHYLSHQSALSKDPNEKRDHMVLLEFVTAAGITHGMDELYK"
    sub3 = "ISLIAALAVDRVIGMENAMPWNLPADLAWFKRNTLNKPVIMGRHTWESIGRPLPGRKNIILSSQPGTDDRVTWVKSVDEAIAACGDVPEIMVIGGGRVYEQFLPKAQKLYLTHIDAEVEGDTHFPDYEPDDWESVFSEFHDADAQNSHSYCFEILERR"
    sub4 = "VSKGEEDNMAIIKEFMRFKVHMEGSVNGHEFEIEGEGEGRPYEGTQTAKLKVTKGGPLPFAWDILSPQMYGSKAYVKHPADIPDYLKLSFPEGFKWERVMNFEDGGVVTVTQDSSLQDGEFIYKVKLRGTNFPSDGPVMQKKTMGWEASSERMYPEDGALKGEIKQRLKLKDGGHYDAEVKTTYKAKKPVQLPGAYNVNIKLDITSHNEDYTIVEQYERAEGRHSTGGMDELYK"
    sub5 = "GPGSDKDCEMKRTTLDSPLGKLELSGCEQGLHEIIFLGKGTSAADAVEVPAPAAVLGGPEPLMQATAWLNAYFHQPEAIEEFPVPALHHPVFQQESFTRQVLWKLLKVVKFGEVISYSHLAALAGNPAATAAVKTALSGNPVPILIPCHRVVQGDLDVGGYEGGLAVKEWLLAHEGHRLGKR"
    
    if not protein.startswith(sub1):
        return 0, "No sub1 start"
        
    idx2 = protein.find(sub2)
    if idx2 == -1:
        return 0, "sub2 not found"
    linker1 = protein[len(sub1):idx2]
    
    idx3 = protein.find(sub3, idx2 + len(sub2))
    if idx3 == -1:
        return 0, "sub3 not found"
    linker2 = protein[idx2 + len(sub2):idx3]
    
    idx4 = protein.find(sub4, idx3 + len(sub3))
    if idx4 == -1:
        return 0, "sub4 not found"
    linker3 = protein[idx3 + len(sub3):idx4]
    
    if not protein.endswith(sub5):
        return 0, "No sub5 end"
    linker4 = protein[idx4 + len(sub4):len(protein)-len(sub5)]
    
    for i, l in enumerate([linker1, linker2, linker3, linker4], 1):
        if not (5 <= len(l) <= 20):
            return 0, f"Linker {i} len {len(l)} not between 5 and 20"
        if not all(c in 'GS' for c in l):
            return 0, f"Linker {i} contains non-GS"
            
    return 1, "Correct"

if __name__ == '__main__':
    solution_dir = os.environ.get('SOLUTION_DIR', '/app')
    verdict_file = os.environ.get('VERDICT_FILE', '/logs/verifier/reward.txt')
    gblock_path = os.path.join(solution_dir, 'gblock.txt')
    verdict, message = check_gblock(gblock_path)
    print(f"Verdict: {verdict} ({message})")
    os.makedirs(os.path.dirname(verdict_file), exist_ok=True)
    with open(verdict_file, 'w') as f:
        f.write(str(verdict))
