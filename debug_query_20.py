import os
import sys
from pathlib import Path

# Append lib to path FIRST
sys.path.append('/home/a/.gemini/antigravity/scratch/quants-lab/lib')

from dune_client import DuneClient

# Load env
def load_env_sh():
    base_dir = Path(__file__).parent
    search_paths = [
        base_dir / "quants-lab" / ".env.sh",
        base_dir / ".env.sh",
        ".env.sh"
    ]
    env_path = None
    for p in search_paths:
        path_obj = Path(p)
        if path_obj.exists():
            env_path = path_obj
            break
            
    if env_path:
        print(f"Loading env from: {env_path}")
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'): continue
                if line.startswith('export '):
                    line = line[7:]
                if '=' in line:
                    key, val = line.split('=', 1)
                    val = val.strip().strip('"').strip("'")
                    os.environ[key] = val

load_env_sh()

def debug_query():
    client = DuneClient()
    query_id = 6322000 # Backtest Query (Q20)
    
    print(f"Executing Backtest Query {query_id}...")
    try:
        # Try passing recent connection/date params
        # This will fail if the query doesn't accept them, which tells us if it's hardcoded
        from datetime import datetime, timedelta
        
        # Test a recent range (last 3 days)
        end_d = datetime.now()
        start_d = end_d - timedelta(days=3)
        
        params = {
            'start_date': start_d.strftime('%Y-%m-%d %H:%M:%S'),
            'end_date': end_d.strftime('%Y-%m-%d %H:%M:%S')
        }
        print(f"Testing with params: {params}")
        
        # Note: We need to use the client's method if we want to test the wrapper, 
        # or execute_query directly. Let's use execute_query to be raw.
        # But wait, execute_query in dune_client.py takes query_id and params.
        # The params keys must match {{key}} in SQL.
        
        results = client.execute_query(query_id, params)
        
        if results:
            print(f"Success! Found {len(results)} rows.")
            print("First row keys:", results[0].keys())
            print("First row:", results[0])
            
            # Check dates
            timestamps = [r.get('interval_start') or r.get('time') or r.get('dt') for r in results]
            timestamps = [t for t in timestamps if t]
            if timestamps:
                print(f"Date Range: {min(timestamps)} to {max(timestamps)}")
            
    except Exception as e:
        print("Caught Exception with params:")
        print(e)
        
        # Fallback to no params
        print("Retrying without params...")
        results = client.execute_query(query_id)
        if results:
             # Check dates
            timestamps = [r.get('interval_start') or r.get('time') or r.get('dt') for r in results]
            timestamps = [t for t in timestamps if t]
            if timestamps:
                print(f"Hardcoded Date Range: {min(timestamps)} to {max(timestamps)}")

if __name__ == "__main__":
    debug_query()
