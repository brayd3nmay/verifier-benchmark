import os
import csv
import re
import sys
from datetime import date

# Determine directories
solution_dir = os.environ.get('SOLUTION_DIR', '/app')
artifacts_dir = os.environ.get('ARTIFACTS_DIR', '')
verdict_file = os.environ.get('VERDICT_FILE', '/logs/verifier/reward.txt')

# Ensure output directory for verdict file exists
verdict_dir = os.path.dirname(verdict_file)
if verdict_dir:
    os.makedirs(verdict_dir, exist_ok=True)

# True counts calculation
log_dir = '/app/logs'

today_start = date(2025, 8, 12)
today_end = date(2025, 8, 12)

last_7_start = date(2025, 8, 6)
last_7_end = date(2025, 8, 12)

last_30_start = date(2025, 7, 14)
last_30_end = date(2025, 8, 12)

mtd_start = date(2025, 8, 1)
mtd_end = date(2025, 8, 12)

def is_today(d):
    return today_start <= d <= today_end

def is_last_7(d):
    return last_7_start <= d <= last_7_end

def is_last_30(d):
    return last_30_start <= d <= last_30_end

def is_mtd(d):
    return mtd_start <= d <= mtd_end

def is_total(d):
    return True

periods = {
    'today': is_today,
    'last_7_days': is_last_7,
    'last_30_days': is_last_30,
    'month_to_date': is_mtd,
    'total': is_total
}

expected = {(p, s): 0 for p in periods for s in ['ERROR', 'WARNING', 'INFO']}

line_re = re.compile(r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} \[(ERROR|WARNING|INFO)\]')

if os.path.exists(log_dir):
    for fname in os.listdir(log_dir):
        m = re.match(r'^(\d{4}-\d{2}-\d{2})_.*\.log$', fname)
        if not m:
            continue
        try:
            y, m_val, d = map(int, m.group(1).split('-'))
            fdate = date(y, m_val, d)
        except Exception:
            continue

        active_periods = [p for p, check in periods.items() if check(fdate)]
        if not active_periods:
            continue

        with open(os.path.join(log_dir, fname), 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                lm = line_re.match(line)
                if lm:
                    sev = lm.group(1)
                    for p in active_periods:
                        expected[(p, sev)] += 1

# Read attempt's CSV
csv_path = os.path.join(solution_dir, 'summary.csv')

if not os.path.exists(csv_path):
    with open(verdict_file, 'w') as vf:
        vf.write('0\n')
    sys.exit(0)

try:
    with open(csv_path, 'r', encoding='utf-8', errors='ignore') as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise ValueError("No headers")
        
        headers = [h.strip() for h in reader.fieldnames if h]
        if 'period' not in headers or 'severity' not in headers or 'count' not in headers:
            raise ValueError("Missing headers")
        
        rows = []
        for raw_row in reader:
            clean_row = {}
            for k, v in raw_row.items():
                if k is not None:
                    clean_row[k.strip()] = v.strip() if v is not None else ""
            if any(clean_row.values()):
                rows.append(clean_row)
            
    found = {}
    valid = True
    for r in rows:
        p = r.get('period')
        s = r.get('severity')
        c_str = r.get('count')
        
        if (p, s) in expected:
            if (p, s) in found:
                valid = False
                break
            if not c_str.isdigit():
                valid = False
                break
            c_val = int(c_str)
            if expected[(p, s)] != c_val:
                valid = False
                break
            found[(p, s)] = c_val
        else:
            valid = False
            break
            
    if len(found) != 15 or len(rows) != 15:
        valid = False

except Exception as e:
    valid = False

# Write verdict
with open(verdict_file, 'w') as vf:
    vf.write('1\n' if valid else '0\n')
