import os
import re
import csv
import sys
import glob
from datetime import datetime, date

# Get directories from environment or use defaults
solution_dir = os.environ.get("SOLUTION_DIR", "/app")
verdict_file = os.environ.get("VERDICT_FILE", "/logs/verifier/reward.txt")
log_dir = "/app/logs"

def write_verdict(val, msg=""):
    if msg:
        sys.stderr.write(msg + "\n")
    try:
        os.makedirs(os.path.dirname(verdict_file), exist_ok=True)
        with open(verdict_file, "w") as f:
            f.write(str(val) + "\n")
    except Exception as e:
        sys.stderr.write(f"Failed to write verdict: {e}\n")
    sys.exit(0)

# 1. Compute ground truth counts
def get_ground_truth():
    ref_date = date(2025, 8, 12)
    periods = {
        'today': lambda d: d == date(2025, 8, 12),
        'last_7_days': lambda d: date(2025, 8, 6) <= d <= date(2025, 8, 12),
        'last_30_days': lambda d: date(2025, 7, 14) <= d <= date(2025, 8, 12),
        'month_to_date': lambda d: date(2025, 8, 1) <= d <= date(2025, 8, 12),
        'total': lambda d: True
    }
    
    counts = {p: {'ERROR': 0, 'WARNING': 0, 'INFO': 0} for p in periods}
    
    filepaths = glob.glob(os.path.join(log_dir, "*.log"))
    
    for fp in filepaths:
        basename = os.path.basename(fp)
        match = re.match(r'^([0-9]{4}-[0-9]{2}-[0-9]{2})_', basename)
        if not match:
            continue
        try:
            d = datetime.strptime(match.group(1), "%Y-%m-%d").date()
        except ValueError:
            continue
            
        with open(fp, 'r', errors='ignore') as f:
            for line in f:
                parts = line.strip().split(' ')
                if len(parts) >= 3:
                    sev_part = parts[2]
                    if sev_part in ('[ERROR]', '[WARNING]', '[INFO]'):
                        sev = sev_part[1:-1]
                        for p, cond in periods.items():
                            if cond(d):
                                counts[p][sev] += 1
    return counts

try:
    ground_truth = get_ground_truth()
except Exception as e:
    write_verdict(0, f"Error computing ground truth: {e}")

# 2. Check if summary.csv exists
csv_path = os.path.join(solution_dir, "summary.csv")
if not os.path.isfile(csv_path):
    write_verdict(0, f"File summary.csv not found at {csv_path}")

# 3. Read and parse summary.csv
try:
    with open(csv_path, 'r', newline='', encoding='utf-8', errors='ignore') as f:
        reader = csv.DictReader(f)
        
        # Check headers
        headers = reader.fieldnames
        if not headers:
            write_verdict(0, "summary.csv is empty or has no headers")
        
        # Strip whitespaces from header names just in case
        headers_stripped = [h.strip() for h in headers if h]
        required_cols = {'period', 'severity', 'count'}
        if not required_cols.issubset(set(headers_stripped)):
            write_verdict(0, f"Missing required columns. Found headers: {headers_stripped}")
            
        # Map original headers to stripped names for safe lookup
        header_map = {}
        for h in headers:
            if h:
                header_map[h.strip()] = h
                
        col_period = header_map['period']
        col_severity = header_map['severity']
        col_count = header_map['count']
        
        # Parse rows
        parsed_counts = {}
        for row in reader:
            p_val = row[col_period]
            s_val = row[col_severity]
            c_val = row[col_count]
            
            if p_val is None or s_val is None or c_val is None:
                continue # skip malformed row or empty values
                
            p_val = p_val.strip()
            s_val = s_val.strip()
            c_val = c_val.strip()
            
            # We only record rows matching our required periods and severities
            if p_val in ground_truth and s_val in ('ERROR', 'WARNING', 'INFO'):
                # Count must be non-negative integer with no decimal, sign, or thousand separators
                # i.e., must match ^[0-9]+$
                if not re.match(r'^[0-9]+$', c_val):
                    write_verdict(0, f"Invalid count format: {c_val} for {p_val}, {s_val}")
                
                key = (p_val, s_val)
                if key in parsed_counts:
                    write_verdict(0, f"Duplicate entry for period={p_val}, severity={s_val}")
                parsed_counts[key] = int(c_val)
                
except Exception as e:
    write_verdict(0, f"Error parsing summary.csv: {e}")

# 4. Compare with ground truth
# Ensure all 15 entries are present and correct
for period, sevs in ground_truth.items():
    for sev, expected_count in sevs.items():
        key = (period, sev)
        if key not in parsed_counts:
            write_verdict(0, f"Missing entry for period={period}, severity={sev}")
        
        actual_count = parsed_counts[key]
        if actual_count != expected_count:
            write_verdict(0, f"Mismatch for period={period}, severity={sev}. Expected {expected_count}, got {actual_count}")

write_verdict(1, "Verification successful!")
