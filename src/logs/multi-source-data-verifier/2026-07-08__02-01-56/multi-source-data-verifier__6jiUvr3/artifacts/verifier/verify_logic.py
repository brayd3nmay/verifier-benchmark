import os
import glob
import json
import sys
import pandas as pd

def load_source_file(file_path):
    ext = os.path.splitext(file_path)[1].lower()
    if ext == '.json':
        return pd.read_json(file_path)
    elif ext == '.csv':
        return pd.read_csv(file_path)
    elif ext in ('.parquet', '.pq'):
        return pd.read_parquet(file_path)
    elif ext == '.tsv':
        return pd.read_csv(file_path, sep='\t')
    else:
        try:
            return pd.read_csv(file_path)
        except Exception:
            return pd.read_json(file_path)

def normalize_df(df, source_name):
    col_mapping = {}
    for col in df.columns:
        col_lower = str(col).strip()
        if col_lower in ['id', 'user_id', 'userId']:
            col_mapping[col] = 'user_id'
        elif col_lower in ['full_name', 'name', 'userName']:
            col_mapping[col] = 'name'
        elif col_lower in ['email', 'email_address']:
            col_mapping[col] = 'email'
        elif col_lower in ['registration_date', 'created_at', 'joined']:
            col_mapping[col] = 'created_date'
        elif col_lower in ['status', 'is_active', 'active']:
            col_mapping[col] = 'status'
    df = df.rename(columns=col_mapping)
    if 'user_id' not in df.columns:
        raise ValueError(f"Source {source_name} does not have user_id")
    df = df.dropna(subset=['user_id'])
    df['user_id'] = df['user_id'].astype(int)
    if 'status' in df.columns:
        def clean_status(val):
            if pd.isna(val):
                return None
            if isinstance(val, bool):
                return 'active' if val else 'inactive'
            if hasattr(val, 'item') and isinstance(val.item(), bool):
                return 'active' if val.item() else 'inactive'
            val_str = str(val).strip().lower()
            if val_str in ['true', '1', '1.0', 'active']:
                return 'active'
            if val_str in ['false', '0', '0.0', 'inactive']:
                return 'inactive'
            return val_str
        df['status'] = df['status'].apply(clean_status)
    else:
        df['status'] = None
    if 'created_date' in df.columns:
        dates = pd.to_datetime(df['created_date'], errors='coerce')
        df['created_date'] = dates.apply(lambda x: x.strftime('%Y-%m-%d') if pd.notna(x) else None)
    else:
        df['created_date'] = None
    for field in ['name', 'email']:
        if field in df.columns:
            df[field] = df[field].apply(lambda x: str(x).strip() if pd.notna(x) else None)
        else:
            df[field] = None
    return df[['user_id', 'name', 'email', 'created_date', 'status']]

def get_expected_outputs(data_dir):
    source_dirs = sorted(glob.glob(os.path.join(data_dir, 'source_*')))
    sources = {}
    for s_dir in source_dirs:
        s_name = os.path.basename(s_dir)
        files = glob.glob(os.path.join(s_dir, 'users.*'))
        if files:
            sources[s_name] = normalize_df(load_source_file(files[0]), s_name)
    all_user_ids = set()
    for df in sources.values():
        all_user_ids.update(df['user_id'].tolist())
    all_user_ids = sorted(list(all_user_ids))
    sorted_source_names = sorted(sources.keys())
    merged_rows = []
    conflicts = []
    for uid in all_user_ids:
        user_sources = {s_name: df[df['user_id'] == uid] for s_name, df in sources.items() if uid in df['user_id'].values}
        primary_source = None
        for s_name in sorted_source_names:
            if s_name in user_sources:
                primary_source = s_name
                break
        primary_row = user_sources[primary_source].iloc[0]
        merged_rows.append({
            'user_id': int(uid),
            'name': primary_row['name'],
            'email': primary_row['email'],
            'created_date': primary_row['created_date'],
            'status': primary_row['status']
        })
        for field in ['name', 'email', 'created_date', 'status']:
            field_vals = {}
            for s_name in sorted_source_names:
                if s_name in user_sources:
                    val = user_sources[s_name].iloc[0][field]
                    field_vals[s_name] = val if pd.notna(val) else None
            non_null_vals = [v for v in field_vals.values() if v is not None]
            if len(set(non_null_vals)) > 1:
                conflicts.append({
                    'user_id': int(uid),
                    'field': field,
                    'values': field_vals,
                    'selected': primary_row[field] if pd.notna(primary_row[field]) else None
                })
    merged_df = pd.DataFrame(merged_rows)
    merged_df['user_id'] = merged_df['user_id'].astype(int)
    merged_df['name'] = merged_df['name'].astype(str)
    merged_df['email'] = merged_df['email'].astype(str)
    merged_df['created_date'] = merged_df['created_date'].astype(str)
    merged_df['status'] = merged_df['status'].astype(str)
    conflicts_json = {
        'total_conflicts': len(conflicts),
        'conflicts': conflicts
    }
    return merged_df, conflicts_json

def compare_outputs(solution_dir, expected_df, expected_conflicts):
    cand_parquet_path = os.path.join(solution_dir, 'merged_users.parquet')
    if not os.path.exists(cand_parquet_path):
        print(f"Missing merged_users.parquet in {solution_dir}")
        return False
    try:
        cand_df = pd.read_parquet(cand_parquet_path)
    except Exception as e:
        print(f"Error reading candidate parquet: {e}")
        return False
    required_cols = ['user_id', 'name', 'email', 'created_date', 'status']
    for col in required_cols:
        if col not in cand_df.columns:
            print(f"Missing required column {col} in merged_users.parquet")
            return False
    cand_df = cand_df[required_cols].copy()
    try:
        cand_df['user_id'] = cand_df['user_id'].astype(int)
        cand_df['name'] = cand_df['name'].astype(str)
        cand_df['email'] = cand_df['email'].astype(str)
        cand_df['created_date'] = cand_df['created_date'].astype(str)
        cand_df['status'] = cand_df['status'].astype(str)
    except Exception as e:
        print(f"Error casting candidate types: {e}")
        return False
    cand_df = cand_df.sort_values('user_id').reset_index(drop=True)
    exp_df_sorted = expected_df.sort_values('user_id').reset_index(drop=True)
    try:
        pd.testing.assert_frame_equal(cand_df, exp_df_sorted, check_dtype=False)
    except Exception as e:
        print(f"Parquet data disagreement: {e}")
        return False
    cand_json_path = os.path.join(solution_dir, 'conflicts.json')
    if not os.path.exists(cand_json_path):
        print(f"Missing conflicts.json in {solution_dir}")
        return False
    try:
        with open(cand_json_path, 'r') as f:
            cand_data = json.load(f)
    except Exception as e:
        print(f"Error reading candidate json: {e}")
        return False
    if 'total_conflicts' not in cand_data or 'conflicts' not in cand_data:
        print("Candidate json is missing required keys: total_conflicts or conflicts")
        return False
    cand_conflicts = cand_data['conflicts']
    if len(cand_conflicts) != cand_data['total_conflicts']:
        print(f"Candidate total_conflicts ({cand_data['total_conflicts']}) does not match actual length ({len(cand_conflicts)})")
        return False
    def get_conflict_key(item):
        try:
            return (int(item.get('user_id')), str(item.get('field')))
        except Exception:
            return (None, None)
    exp_conflicts = expected_conflicts['conflicts']
    exp_dict = {}
    for item in exp_conflicts:
        k = get_conflict_key(item)
        if k[0] is not None:
            exp_dict[k] = item
    cand_dict = {}
    for item in cand_conflicts:
        k = get_conflict_key(item)
        if k[0] is not None:
            cand_dict[k] = item
    if set(exp_dict.keys()) != set(cand_dict.keys()):
        print(f"Conflict keys mismatch.")
        return False
    for k in exp_dict:
        exp_item = exp_dict[k]
        cand_item = cand_dict[k]
        def normalize_val(v):
            if pd.isna(v) or v is None:
                return None
            if isinstance(v, bool):
                return 'active' if v else 'inactive'
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                if int(v) == v:
                    return int(v)
                return float(v)
            val_str = str(v).strip()
            if val_str.lower() == 'true':
                return 'active'
            if val_str.lower() == 'false':
                return 'inactive'
            return val_str
        exp_vals = {s: normalize_val(v) for s, v in exp_item['values'].items()}
        cand_vals = {s: normalize_val(v) for s, v in cand_item.get('values', {}).items()}
        if exp_vals != cand_vals:
            print(f"Values mismatch for key {k}. Expected: {exp_vals}. Candidate: {cand_vals}")
            return False
        exp_sel = normalize_val(exp_item['selected'])
        cand_sel = normalize_val(cand_item.get('selected'))
        if exp_sel != cand_sel:
            print(f"Selected value mismatch for key {k}. Expected: {exp_sel}. Candidate: {cand_sel}")
            return False
    if cand_data['total_conflicts'] != expected_conflicts['total_conflicts']:
        print(f"total_conflicts mismatch. Expected: {expected_conflicts['total_conflicts']}. Candidate: {cand_data['total_conflicts']}")
        return False
    return True

if __name__ == '__main__':
    data_dir = os.environ.get('DATA_DIR', '/app/data')
    solution_dir = os.environ.get('SOLUTION_DIR', '/app')
    verdict_file = os.environ.get('VERDICT_FILE', '/logs/verifier/reward.txt')
    os.makedirs(os.path.dirname(verdict_file), exist_ok=True)
    try:
        expected_df, expected_conflicts = get_expected_outputs(data_dir)
        is_correct = compare_outputs(solution_dir, expected_df, expected_conflicts)
    except Exception as e:
        print(f"Verifier error: {e}")
        is_correct = False
    verdict_val = '1' if is_correct else '0'
    try:
        with open(verdict_file, 'w') as f:
            f.write(verdict_val)
        print(f"Verifier run completed. Verdict: {verdict_val} written to {verdict_file}")
    except Exception as e:
        print(f"Failed to write to verdict file {verdict_file}: {e}")
        sys.exit(1)
    sys.exit(0)
