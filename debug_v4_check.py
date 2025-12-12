import os
import sys
from pathlib import Path

# Append lib to path
sys.path.append('/home/a/.gemini/antigravity/scratch/quants-lab/lib')
from dune_client import DuneClient

# Load env
def load_env_sh():
    base_dir = Path(__file__).parent.parent
    # Check current dir too
    search_paths = [
        Path("/home/a/.gemini/antigravity/scratch/quants-lab/.env.sh"),
        Path(".env.sh")
    ]
    env_path = None
    for p in search_paths:
        if p.exists():
            env_path = p
            break
            
    if env_path:
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

def debug_v4_access():
    client = DuneClient()
    
    # We will use the Query 20 ID (or any ID) to execute a custom SQL
    # Wait, client.execute_query takes an ID. We can't send raw SQL.
    # We have to depend on the query already saved on Dune unless we use the API to update it.
    
    # Since we can't edit the query from here without the API returning a token for editing (limited scope),
    # We should rely on checking `debug_query_1` output CAREFULLY to see the `pool_id` format.
    
    # Let's inspect the Raw Result from the working Query 1 again.
    # It must have the pool_id in it.
    
    q1_id = os.getenv('DUNE_SWAPS_QUERY_ID')
    print(f"Inspecting Query 1 ({q1_id}) results for Pool ID format...")
    
    # Fetch recent results (no params, or default params if valid)
    try:
        results = client.execute_query(int(q1_id), {'limit': 5})
        if results:
            print("Found results!")
            row = results[0]
            print("Keys:", row.keys())
            if 'pool_id' in row:
                pid = row['pool_id']
                print(f"Pool ID Value: {pid}")
                print(f"Pool ID Type: {type(pid)}")
            if 'id' in row:
                print(f"ID Value: {row['id']}")
        else:
            print("No results from Q1.")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    debug_v4_access()
