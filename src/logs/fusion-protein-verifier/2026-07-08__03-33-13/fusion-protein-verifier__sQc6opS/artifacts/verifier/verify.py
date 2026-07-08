import os
import sys
import requests
from Bio import SeqIO

def log(msg):
    print(msg, file=sys.stderr)

def write_verdict(verdict_file, val):
    try:
        with open(verdict_file, 'w') as f:
            f.write(str(val))
        log(f'Wrote verdict {val} to {verdict_file}')
    except Exception as e:
        log(f'Error writing verdict: {e}')

def main():
    sol_dir = os.environ.get('SOLUTION_DIR', '/app')
    verdict = os.environ.get('VERDICT_FILE', '/logs/verifier/reward.txt')
    os.makedirs(os.path.dirname(verdict), exist_ok=True)
    gblock_path = os.path.join(sol_dir, 'gblock.txt')
    if not os.path.exists(gblock_path):
        log('gblock.txt does not exist')
        write_verdict(verdict, 0)
        return
    try:
        with open(gblock_path, 'rb') as f:
            content = f.read().decode('utf-8')
    except Exception as e:
        log(f'Error reading gblock.txt: {e}')
        write_verdict(verdict, 0)
        return
    nl_split = content.split('\n')
    if len(nl_split) > 2 or (len(nl_split) == 2 and nl_split[1] != ''):
        log('gblock.txt must have exactly one line')
        write_verdict(verdict, 0)
        return
    gblock_seq = nl_split[0].strip().upper()
    if not gblock_seq:
        log('gblock.txt empty')
        write_verdict(verdict, 0)
        return
    if not all(c in 'ATCG' for c in gblock_seq):
        log('gblock contains non-ATCG')
        write_verdict(verdict, 0)
        return
    if len(gblock_seq) > 3000:
        log('gblock exceeds 3000')
        write_verdict(verdict, 0)
        return
    if len(gblock_seq) % 3 != 0:
        log('gblock length not multiple of 3')
        write_verdict(verdict, 0)
        return
    if len(gblock_seq) < 50:
        log('gblock too short')
        write_verdict(verdict, 0)
        return
    for i in range(len(gblock_seq) - 49):
        w = gblock_seq[i:i+50]
        gc = sum(1 for c in w if c in 'GC') / 50.0
        if gc < 0.3 or gc > 0.7:
            log(f'Window at {i} fails GC content')
            write_verdict(verdict, 0)
            return
    from Bio.Seq import Seq
    translated = str(Seq(gblock_seq).translate())
    if '*' in translated:
        log('Stop codon found')
        write_verdict(verdict, 0)
        return
    ab_ref = 'DYKDDDDK'
    dhfr_ref = 'ISLIAALAVDRVIGMENAMPWNLPADLAWFKRNTLNKPVIMGRHTWESIGRPLPGRKNIILSSQPGTDDRVTWVKSVDEAIAACGDVPEIMVIGGGRVYEQFLPKAQKLYLTHIDAEVEGDTHFPDYEPDDWESVFSEFHDADAQNSHSYCFEILERR'
    clover_p = 'GSSHHHHHHSSGENLYFQGHMVSKGEELFTGVVPILVELDGDVNGHKFSVRGEGEGDATNGKLTLKFICTTGKLPVPWPTLVTTFGYGVACFSRYPDHMKQHDFFKSAMPEGYVQERTISFKDDGTYKTRAEVKFEGDTLVNRIELKGIDFKEDGNILGHKLEYNFNSHNVYITADKQKNGIKANFKIRHNVEDGSVQLADHYQQNTPIGDGPVLLPDNHYLSHQSALSKDPNEKRDHMVLLEFVTAAGITHGMDELYK'
    clover_f = 'VSKGEELFTGVVPILVELDGDVNGHKFSVRGEGEGDATNGKLTLKFICTTGKLPVPWPTLVTTFGYGVACFSRYPDHMKQHDFFKSAMPEGYVQERTISFKDDGTYKTRAEVKFEGDTLVNRIELKGIDFKEDGNILGHKLEYNFNSHNVYITADKQKNGIKANFKIRHNVEDGSVQLADHYQQNTPIGDGPVLLPDNHYLSHQSALSKDPNEKRDHMVLLEFVTAAGITHGMDELYK'
    mcherry_p = 'VSKGEEDNMAIIKEFMRFKVHMEGSVNGHEFEIEGEGEGRPYEGTQTAKLKVTKGGPLPFAWDILSPQFMYGSKAYVKHPADIPDYLKLSFPEGFKWERVMNFEDGGVVTVTQDSSLQDGEFIYKVKLRGTNFPSDGPVMQKKTMGWEASSERMYPEDGALKGEIKQRLKLKDGGHYDAEVKTTYKAKKPVQLPGAYNVNIKLDITSHNEDYTIVEQYERAEGRHSTGGMDELYK'
    snap_p = 'GPGSDKDCEMKRTTLDSPLGKLELSGCEQGLHEIIFLGKGTSAADAVEVPAPAAVLGGPEPLMQATAWLNAYFHQPEAIEEFPVPALHHPVFQQESFTRQVLWKLLKVVKFGEVISYSHLAALAGNPAATAAVKTALSGNPVPILIPCHRVVQGDLDVGGYEGGLAVKEWLLAHEGHRLGKR'
    donor_opts = [clover_p, clover_f]
    acceptor_opts = [mcherry_p]
    molecule_opts = [snap_p]
    try:
        r = requests.get('https://www.fpbase.org/api/proteins/clover/?format=json', timeout=5)
        if r.status_code == 200:
            ex = next((s.get('ex_max') for s in r.json().get('states', []) if s.get('ex_max')), None)
            if ex != 505:
                log('Clover ex != 505')
                write_verdict(verdict, 0)
                return
        r2 = requests.get('https://www.fpbase.org/api/proteins/mcherry/?format=json', timeout=5)
        if r2.status_code == 200:
            em = next((s.get('em_max') for s in r2.json().get('states', []) if s.get('em_max')), None)
            if em != 610:
                log('mCherry em != 610')
                write_verdict(verdict, 0)
                return
    except Exception as e:
        log(f'FPBase dynamic check warning: {e}')
    match = False
    for d in donor_opts:
        for a in acceptor_opts:
            for m in molecule_opts:
                if not translated.startswith(ab_ref): continue
                idx1 = len(ab_ref)
                d_idx = -1
                for len_L1 in range(5, 21):
                    t = idx1 + len_L1
                    if translated[t:t+len(d)] == d:
                        if all(c in 'GS' for c in translated[idx1:t]):
                            d_idx = t; break
                if d_idx == -1: continue
                idx2 = d_idx + len(d)
                dhfr_idx = -1
                for len_L2 in range(5, 21):
                    t = idx2 + len_L2
                    if translated[t:t+len(dhfr_ref)] == dhfr_ref:
                        if all(c in 'GS' for c in translated[idx2:t]):
                            dhfr_idx = t; break
                if dhfr_idx == -1: continue
                idx3 = dhfr_idx + len(dhfr_ref)
                a_idx = -1
                for len_L3 in range(5, 21):
                    t = idx3 + len_L3
                    if translated[t:t+len(a)] == a:
                        if all(c in 'GS' for c in translated[idx3:t]):
                            a_idx = t; break
                if a_idx == -1: continue
                idx4 = a_idx + len(a)
                m_idx = -1
                for len_L4 in range(5, 21):
                    t = idx4 + len_L4
                    if translated[t:t+len(m)] == m:
                        if all(c in 'GS' for c in translated[idx4:t]):
                            m_idx = t; break
                if m_idx == -1: continue
                if m_idx + len(m) == len(translated):
                    match = True; break
            if match: break
        if match: break
    if not match:
        log('Subprotein mismatch')
        write_verdict(verdict, 0)
        return
    log('All checks passed')
    write_verdict(verdict, 1)

if __name__ == '__main__':
    main()
