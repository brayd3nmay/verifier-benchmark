import os
import sys
import csv
import re
import datetime

def main():
    solution_dir = os.environ.get('SOLUTION_DIR', '/app')
    verdict_file = os.environ.get('VERDICT_FILE', '/logs/verifier/reward.txt')
    
    # default failure
    def write_verdict(val):
        try:
            os.makedirs(os.path.dirname(verdict_file), exist_ok=True)
            with open(verdict_file, 'w') as f:
                f.write(str(val) + '\n')
        except Exception as e:
            print(f"Error writing verdict: {e}")
        sys.exit(0)

    # Calculate correct counts
    ref_date = datetime.date(2025, 8, 12)
    today_range = (ref_date, ref_date)
    last_7_days_range = (ref_date - datetime.timedelta(days=6), ref_date)
    last_30_days_range = (ref_date - datetime.timedelta(days=29), ref_date)
    month_to_date_range = (datetime.date(2025, 8, 1), ref_date)

    def in_range(date_str, date_range):
        try:
            d = datetime.datetime.strptime(date_str, '%Y-%m-%d').date()
            return date_range[0] <= d <= date_range[1]
        except:
            return False

    periods = {'today', 'last_7_days', 'last_30_days', 'month_to_date', 'total'}
    severities = {'ERROR', 'WARNING', 'INFO'}

    expected = {p: {s: 0 for s in severities} for p in periods}

    log_dir = '/app/logs'
    if not os.path.exists(log_dir):
        print("Log directory does not exist")
        write_verdict(0)

    try:
        for f in os.listdir(log_dir):
            m = re.match('^([0-9]{4}-[0-9]{2}-[0-9]{2})_', f)
            if not m: continue
            date_str = m.group(1)
            
            file_periods = ['total']
            if in_range(date_str, today_range): file_periods.append('today')
            if in_range(date_str, last_7_days_range): file_periods.append('last_7_days')
            if in_range(date_str, last_30_days_range): file_periods.append('last_30_days')
            if in_range(date_str, month_to_date_range): file_periods.append('month_to_date')
            
            with open(os.path.join(log_dir, f), 'r', encoding='utf-8', errors='ignore') as fh:
                for line in fh:
                    parts = line.strip().split(' ', 3)
                    if len(parts) >= 3:
                        sev = parts[2]
                        if sev.startswith('[') and sev.endswith(']'):
                            sev_name = sev[1:-1]
                            if sev_name in severities:
                                for p in file_periods:
                                    expected[p][sev_name] += 1
    except Exception as e:
        print(f"Error processing log files: {e}")
        write_verdict(0)

    # Read and parse SOLUTION_DIR/summary.csv
    csv_path = os.path.join(solution_dir, 'summary.csv')
    if not os.path.exists(csv_path):
        print(f"summary.csv not found at {csv_path}")
        write_verdict(0)

    try:
        with open(csv_path, 'r', newline='', encoding='utf-8') as f:
            # Read header and normalize column names
            # RFC 4180 standard CSV
            reader = csv.reader(f)
            header = next(reader, None)
            if not header:
                print("CSV is empty")
                write_verdict(0)
            
            header_norm = [h.strip() for h in header]
            if 'period' not in header_norm or 'severity' not in header_norm or 'count' not in header_norm:
                print(f"Missing required columns in header: {header_norm}")
                write_verdict(0)
                
            idx_period = header_norm.index('period')
            idx_severity = header_norm.index('severity')
            idx_count = header_norm.index('count')
            
            submitted = {}
            for row in reader:
                if not row:
                    continue # empty row
                if len(row) < max(idx_period, idx_severity, idx_count) + 1:
                    print(f"Row has fewer columns than expected: {row}")
                    write_verdict(0)
                
                p_val = row[idx_period].strip()
                s_val = row[idx_severity].strip()
                c_val = row[idx_count].strip()
                
                # Validate period
                if p_val not in periods:
                    print(f"Unknown period: {p_val}")
                    write_verdict(0)
                # Validate severity
                if s_val not in severities:
                    print(f"Unknown severity: {s_val}")
                    write_verdict(0)
                # Validate count format
                if not re.match('^[0-9]+$', c_val):
                    print(f"Invalid count format: {c_val}")
                    write_verdict(0)
                
                count_int = int(c_val)
                key = (p_val, s_val)
                if key in submitted:
                    print(f"Duplicate row for pair: {key}")
                    write_verdict(0)
                submitted[key] = count_int
                
            # Verify exact 15 pairs are present
            if len(submitted) != 15:
                print(f"Expected 15 unique rows, found {len(submitted)}")
                write_verdict(0)
                
            # Now compare values
            for p in periods:
                for s in severities:
                    if (p, s) not in submitted:
                        print(f"Missing pair: {p}, {s}")
                        write_verdict(0)
                    if submitted[(p, s)] != expected[p][s]:
                        print(f"Count mismatch for {p}, {s}: expected {expected[p][s]}, got {submitted[(p, s)]}")
                        write_verdict(0)
                        
            print("All checks passed!")
            write_verdict(1)
            
    except Exception as e:
        print(f"Error processing CSV file: {e}")
        write_verdict(0)

if __name__ == '__main__':
    main()
