import os
import sys
import glob
import json
import pandas as pd

def load_source(dir_path):
    files = glob.glob(os.path.join(dir_path, "users.*"))
    if not files:
        return None
    filepath = files[0]
    ext = os.path.splitext(filepath)[1].lower()
    
    try:
        if ext == '.csv':
            df = pd.read_csv(filepath)
        elif ext == '.json':
            df = pd.read_json(filepath)
        elif ext == '.parquet':
            df = pd.read_parquet(filepath)
        else:
            return None
    except Exception:
        return None
        
    id_cols = ['id', 'user_id', 'userId']
    name_cols = ['full_name', 'name', 'userName']
    email_cols = ['email', 'email_address']
    date_cols = ['registration_date', 'created_at', 'joined']
    status_cols = ['status', 'is_active', 'active']
    
    col_map = {}
    for c in df.columns:
        if c in id_cols:
            col_map[c] = 'user_id'
        elif c in name_cols:
            col_map[c] = 'name'
        elif c in email_cols:
            col_map[c] = 'email'
        elif c in date_cols:
            col_map[c] = 'created_date'
        elif c in status_cols:
            col_map[c] = 'status'
            
    df = df.rename(columns=col_map)
    relevant = ['user_id', 'name', 'email', 'created_date', 'status']
    df = df[[c for c in relevant if c in df.columns]]
    
    if 'user_id' in df.columns:
        try:
            df['user_id'] = df['user_id'].astype(int)
        except Exception:
            pass
        
    if 'status' in df.columns:
        def norm_status(val):
            if pd.isna(val) or val is None:
                return None
            if isinstance(val, bool):
                return 'active' if val else 'inactive'
            s = str(val).strip().lower()
            if s in ['true', 'active', '1']:
                return 'active'
            if s in ['false', 'inactive', '0']:
                return 'inactive'
            return s
        df['status'] = df['status'].apply(norm_status)
        
    if 'created_date' in df.columns:
        try:
            df['created_date'] = pd.to_datetime(df['created_date']).dt.strftime('%Y-%m-%d')
        except Exception:
            pass
        
    return df

def compute_ground_truth(data_dir):
    source_dirs = sorted(glob.glob(os.path.join(data_dir, "source_*")))
    sources = {}
    for sdir in source_dirs:
        sname = os.path.basename(sdir)
        df = load_source(sdir)
        if df is not None:
            sources[sname] = df
            
    all_user_ids = set()
    for df in sources.values():
        if 'user_id' in df.columns:
            all_user_ids.update(df['user_id'].tolist())
    all_user_ids = sorted(list(all_user_ids))
    
    merged_rows = []
    conflicts = []
    fields = ['name', 'email', 'created_date', 'status']
    
    for uid in all_user_ids:
        user_sources = {}
        for sname in sorted(sources.keys()):
            df = sources[sname]
            user_row = df[df['user_id'] == uid]
            if not user_row.empty:
                user_sources[sname] = user_row.iloc[0].to_dict()
                
        priority_sources = sorted(user_sources.keys())
        if not priority_sources:
            continue
        highest_prio_source = priority_sources[0]
        selected_user_data = user_sources[highest_prio_source]
        
        merged_record = {
            'user_id': int(uid),
            'name': selected_user_data.get('name'),
            'email': selected_user_data.get('email'),
            'created_date': selected_user_data.get('created_date'),
            'status': selected_user_data.get('status')
        }
        merged_rows.append(merged_record)
        
        for field in fields:
            field_values = {}
            for sname, udata in user_sources.items():
                val = udata.get(field)
                if pd.isna(val) or val is None:
                    field_values[sname] = None
                else:
                    field_values[sname] = val
                    
            non_null_values = [v for v in field_values.values() if v is not None]
            unique_non_null = set(non_null_values)
            if len(unique_non_null) > 1:
                vals_dict = {}
                for sname in sorted(sources.keys()):
                    if sname in user_sources:
                        vals_dict[sname] = user_sources[sname].get(field)
                
                conflict_entry = {
                    'user_id': int(uid),
                    'field': field,
                    'values': vals_dict,
                    'selected': merged_record[field]
                }
                conflicts.append(conflict_entry)
                
    merged_df = pd.DataFrame(merged_rows)
    if not merged_df.empty:
        merged_df = merged_df[['user_id', 'name', 'email', 'created_date', 'status']]
    conflicts_json = {
        'total_conflicts': len(conflicts),
        'conflicts': conflicts
    }
    return merged_df, conflicts_json

def normalize_conflicts(conf_json):
    if not isinstance(conf_json, dict) or 'conflicts' not in conf_json:
        return None
    conflicts = conf_json['conflicts']
    if not isinstance(conflicts, list):
        return None
        
    normalized_list = []
    for entry in conflicts:
        if not isinstance(entry, dict):
            return None
        # required keys
        for k in ['user_id', 'field', 'values', 'selected']:
            if k not in entry:
                return None
        
        # ensure values is a dict and keys are sorted/represented nicely
        vals = entry['values']
        if not isinstance(vals, dict):
            return None
        normalized_vals = {}
        for k, v in sorted(vals.items()):
            normalized_vals[k] = v
            
        normalized_list.append({
            'user_id': int(entry['user_id']),
            'field': str(entry['field']),
            'values': normalized_vals,
            'selected': entry['selected']
        })
        
    # Sort by user_id, then field
    normalized_list.sort(key=lambda x: (x['user_id'], x['field']))
    return {
        'total_conflicts': len(normalized_list),
        'conflicts': normalized_list
    }

def compare_results(sol_dir, data_dir):
    try:
        # Compute ground truth
        gt_df, gt_conflicts = compute_ground_truth(data_dir)
        
        # 1. Compare parquet file
        cand_parquet_path = os.path.join(sol_dir, "merged_users.parquet")
        if not os.path.exists(cand_parquet_path):
            print("Candidate merged_users.parquet not found.", file=sys.stderr)
            return False
            
        try:
            cand_df = pd.read_parquet(cand_parquet_path)
        except Exception as e:
            print(f"Error reading candidate parquet: {e}", file=sys.stderr)
            return False
            
        # Check required columns exist
        required_cols = ['user_id', 'name', 'email', 'created_date', 'status']
        for c in required_cols:
            if c not in cand_df.columns:
                print(f"Required column {c} missing in candidate parquet.", file=sys.stderr)
                return False
                
        # Keep only required columns and normalize types
        cand_df = cand_df[required_cols].copy()
        try:
            cand_df['user_id'] = cand_df['user_id'].astype(int)
            cand_df['name'] = cand_df['name'].astype(str)
            cand_df['email'] = cand_df['email'].astype(str)
            cand_df['created_date'] = pd.to_datetime(cand_df['created_date']).dt.strftime('%Y-%m-%d')
            cand_df['status'] = cand_df['status'].astype(str)
        except Exception as e:
            print(f"Error converting column types in candidate: {e}", file=sys.stderr)
            return False
            
        # Sort and compare DataFrames
        gt_df_sorted = gt_df.sort_values('user_id').reset_index(drop=True)
        cand_df_sorted = cand_df.sort_values('user_id').reset_index(drop=True)
        
        # Align any float/none representations
        # Replace pd.NA, None with NaN or standard comparison
        if not gt_df_sorted.equals(cand_df_sorted):
            # Let's check with standard comparison or print difference
            print("DataFrame mismatch:", file=sys.stderr)
            print("Ground truth:", file=sys.stderr)
            print(gt_df_sorted, file=sys.stderr)
            print("Candidate:", file=sys.stderr)
            print(cand_df_sorted, file=sys.stderr)
            return False
            
        # 2. Compare conflicts JSON
        cand_json_path = os.path.join(sol_dir, "conflicts.json")
        if not os.path.exists(cand_json_path):
            print("Candidate conflicts.json not found.", file=sys.stderr)
            return False
            
        try:
            with open(cand_json_path, 'r') as f:
                cand_conflicts = json.load(f)
        except Exception as e:
            print(f"Error reading candidate JSON: {e}", file=sys.stderr)
            return False
            
        norm_gt = normalize_conflicts(gt_conflicts)
        norm_cand = normalize_conflicts(cand_conflicts)
        
        if norm_cand is None:
            print("Candidate JSON structure is invalid.", file=sys.stderr)
            return False
            
        if norm_gt != norm_cand:
            print("Conflicts JSON mismatch:", file=sys.stderr)
            print("Ground truth:", file=sys.stderr)
            print(json.dumps(norm_gt, indent=2), file=sys.stderr)
            print("Candidate:", file=sys.stderr)
            print(json.dumps(norm_cand, indent=2), file=sys.stderr)
            return False
            
        return True
    except Exception as e:
        print(f"Unexpected error during comparison: {e}", file=sys.stderr)
        return False

if __name__ == '__main__':
    sol_dir = os.environ.get('SOLUTION_DIR', '/app')
    data_dir = '/app/data'
    
    result = compare_results(sol_dir, data_dir)
    if result:
        print("1")
        sys.exit(0)
    else:
        print("0")
        sys.exit(0)
