# Python verifier
import os, sys, glob, json
import pandas as pd

def standardize_df(df):
    col_map = {}
    for col in df.columns:
        if col in ['id', 'user_id', 'userId']:
            col_map[col] = 'user_id'
        elif col in ['full_name', 'name', 'userName']:
            col_map[col] = 'name'
        elif col in ['email', 'email_address']:
            col_map[col] = 'email'
        elif col in ['registration_date', 'created_at', 'joined']:
            col_map[col] = 'created_date'
        elif col in ['status', 'is_active', 'active']:
            col_map[col] = 'status'
    
    df = df.rename(columns=col_map)
    valid_cols = ['user_id', 'name', 'email', 'created_date', 'status']
    df = df[[c for c in valid_cols if c in df.columns]].copy()
    
    if 'user_id' in df.columns:
        df['user_id'] = df['user_id'].astype(int)
    
    if 'status' in df.columns:
        def clean_status(val):
            if pd.isna(val):
                return None
            if isinstance(val, bool):
                return 'active' if val else 'inactive'
            if isinstance(val, str):
                v_lower = val.lower().strip()
                if v_lower in ('true', '1', 'active'):
                    return 'active'
                elif v_lower in ('false', '0', 'inactive'):
                    return 'inactive'
            if val == 1 or val == 1.0:
                return 'active'
            if val == 0 or val == 0.0:
                return 'inactive'
            return str(val)
        df['status'] = df['status'].apply(clean_status)
        
    if 'created_date' in df.columns:
        df['created_date'] = pd.to_datetime(df['created_date']).dt.strftime('%Y-%m-%d')
        
    for col in ['name', 'email']:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip()
            
    return df

def compute_reference():
    sources = sorted(glob.glob('/app/data/source_*'))
    dfs = {}
    for s_path in sources:
        s_name = os.path.basename(s_path)
        files = glob.glob(os.path.join(s_path, 'users.*'))
        if not files: continue
        file_path = files[0]
        ext = os.path.splitext(file_path)[1].lower()
        if ext == '.json':
            df = pd.read_json(file_path)
        elif ext == '.csv':
            df = pd.read_csv(file_path)
        elif ext in ('.parquet', '.pq'):
            df = pd.read_parquet(file_path)
        else:
            continue
        dfs[s_name] = standardize_df(df)
        
    all_user_ids = set()
    for df in dfs.values():
        all_user_ids.update(df['user_id'].tolist())
    all_user_ids = sorted(list(all_user_ids))
    
    priority_order = sorted(dfs.keys())
    merged_rows = []
    conflicts = []
    
    for uid in all_user_ids:
        user_sources = {}
        for s_name in priority_order:
            s_df = dfs[s_name]
            row = s_df[s_df['user_id'] == uid]
            if not row.empty:
                user_sources[s_name] = row.iloc[0].to_dict()
                
        selected_record = {}
        for s_name in priority_order:
            if s_name in user_sources:
                selected_record = user_sources[s_name]
                break
                
        merged_rows.append({
            'user_id': uid,
            'name': selected_record.get('name'),
            'email': selected_record.get('email'),
            'created_date': selected_record.get('created_date'),
            'status': selected_record.get('status')
        })
        
        fields = ['name', 'email', 'created_date', 'status']
        for field in fields:
            vals = {}
            for s_name, record in user_sources.items():
                if field in record:
                    vals[s_name] = record[field]
            
            if len(vals) > 1:
                unique_vals = set(vals.values())
                if len(unique_vals) > 1:
                    conflicts.append({
                        'user_id': int(uid),
                        'field': field,
                        'values': vals,
                        'selected': selected_record.get(field)
                    })
                    
    merged_df = pd.DataFrame(merged_rows)
    return merged_df, conflicts

def verify():
    solution_dir = os.environ.get('SOLUTION_DIR', '/app')
    verdict_file = os.environ.get('VERDICT_FILE', '/logs/verifier/reward.txt')
    os.makedirs(os.path.dirname(verdict_file), exist_ok=True)
    
    try:
        ref_df, ref_conflicts = compute_reference()
    except Exception as e:
        with open(verdict_file, 'w') as f:
            f.write('0')
        return
        
    try:
        attempt_parquet_path = os.path.join(solution_dir, 'merged_users.parquet')
        attempt_json_path = os.path.join(solution_dir, 'conflicts.json')
        
        if not os.path.exists(attempt_parquet_path) or not os.path.exists(attempt_json_path):
            with open(verdict_file, 'w') as f:
                f.write('0')
            return
            
        att_df = pd.read_parquet(attempt_parquet_path)
        required_cols = ['user_id', 'name', 'email', 'created_date', 'status']
        
        for col in required_cols:
            if col not in att_df.columns:
                with open(verdict_file, 'w') as f:
                    f.write('0')
                return
                
        att_df = att_df[required_cols].copy()
        att_df['user_id'] = att_df['user_id'].astype(int)
        if 'status' in att_df.columns:
            att_df['status'] = att_df['status'].astype(str)
        if 'created_date' in att_df.columns:
            att_df['created_date'] = pd.to_datetime(att_df['created_date']).dt.strftime('%Y-%m-%d')
        for col in ['name', 'email']:
            att_df[col] = att_df[col].astype(str).str.strip()
            
        att_df = att_df.sort_values(by='user_id').reset_index(drop=True)
        ref_df = ref_df.sort_values(by='user_id').reset_index(drop=True)
        
        if not att_df.equals(ref_df):
            with open(verdict_file, 'w') as f:
                f.write('0')
            return
            
        with open(attempt_json_path, 'r') as f:
            att_json = json.load(f)
            
        if 'total_conflicts' not in att_json or 'conflicts' not in att_json:
            with open(verdict_file, 'w') as f:
                f.write('0')
            return
            
        att_conflicts = att_json['conflicts']
        if not isinstance(att_conflicts, list):
            with open(verdict_file, 'w') as f:
                f.write('0')
            return
            
        normalized_att = []
        for c in att_conflicts:
            if not all(k in c for k in ['user_id', 'field', 'values', 'selected']):
                with open(verdict_file, 'w') as f:
                    f.write('0')
                return
            normalized_att.append({
                'user_id': int(c['user_id']),
                'field': str(c['field']).strip(),
                'values': {k: str(v).strip() for k, v in c['values'].items()},
                'selected': str(c['selected']).strip()
            })
        normalized_att = sorted(normalized_att, key=lambda x: (x['user_id'], x['field']))
        
        normalized_ref = []
        for c in ref_conflicts:
            normalized_ref.append({
                'user_id': int(c['user_id']),
                'field': str(c['field']).strip(),
                'values': {k: str(v).strip() for k, v in c['values'].items()},
                'selected': str(c['selected']).strip()
            })
        normalized_ref = sorted(normalized_ref, key=lambda x: (x['user_id'], x['field']))
        
        if len(normalized_att) != len(normalized_ref):
            with open(verdict_file, 'w') as f:
                f.write('0')
            return
            
        for a_c, r_c in zip(normalized_att, normalized_ref):
            if a_c != r_c:
                with open(verdict_file, 'w') as f:
                    f.write('0')
                return
                
        if int(att_json['total_conflicts']) != len(normalized_ref):
            with open(verdict_file, 'w') as f:
                f.write('0')
            return
            
        with open(verdict_file, 'w') as f:
            f.write('1')
            
    except Exception as e:
        with open(verdict_file, 'w') as f:
            f.write('0')

if __name__ == '__main__':
    verify()
