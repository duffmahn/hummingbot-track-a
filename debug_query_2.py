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
    query_id = 6321528 # Metric Query (Q2)
    
    start_ts = 1715450800 # Arbitrary recent timestamp
    end_ts = 1715537200
    pool_address = "0x000000000004444c5dc75cB358380D2e3dE08A90"
    
    from datetime import datetime
    start_date = datetime.fromtimestamp(start_ts).strftime('%Y-%m-%d')
    end_date = datetime.fromtimestamp(end_ts).strftime('%Y-%m-%d')
            
    params = {
        'pool_address': pool_address.lower(),
        'start_date': start_date,
        'end_date': end_date
    }
    
    print(f"Executing Query {query_id} with params: {params}")
    try:
        results = client.execute_query(query_id, params)
        print("Success!")
        print(results)
    except Exception as e:
        print("Caught Exception:")
        print(e)
        # Try without params to see what it returns
        print("Retrying without params...")
        results = client.execute_query(query_id)
        print("Results without params:")
        print(results)

if __name__ == "__main__":
    debug_query()
