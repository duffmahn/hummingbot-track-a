
import os
import sys
import json
from pathlib import Path

# Add lib to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'quants-lab/lib'))

from dune_client import DuneClient

def load_env_sh():
    # Try finding .env.sh in current or parent dirs
    search_paths = [".env.sh", "quants-lab/.env.sh", "../.env.sh", "scratch/quants-lab/.env.sh"]
    env_path = None
    for p in search_paths:
        if os.path.exists(p):
            env_path = p
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

def main():
    try:
        client = DuneClient()
        print("Fetching Swaps (Q1)...")
        # 6322162 is Q1
        results = client.execute_query(6322162)
        
        if not results:
            print("No results found.")
            return

        print(f"Found {len(results)} swaps.")
        print("Columns:", results[0].keys())
        
        # Look for pool identifier
        # Common names: pool_id, pool, address, contract_address
        possible_keys = ['pool_id', 'pool', 'address', 'contract_address', 'id']
        
        pools = set()
        for r in results:
            for k in possible_keys:
                if k in r:
                    pools.add(r[k])
        
        print("\nActive V4 Pools found:")
        for p in list(pools)[:5]:
            print(f"- {p}")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
