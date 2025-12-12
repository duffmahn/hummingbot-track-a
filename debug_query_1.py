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
    query_id = 6322162 # Swaps Query (Q1) - Universal with pool_id
    
    # Params matching agent_harness default (300s duration, but looking back 1h)
    pool_address = "0x000000000004444c5dc75cB358380D2e3dE08A90"
    
    print(f"Executing Swaps Query {query_id} for {pool_address}...")
    try:
        # Pass params just in case, though might fallback
        params = {
            'pool_address': pool_address.lower(),
            'period': '1h' # Some queries take period
        }
        results = client.execute_query(query_id, params)
        print(f"Success! Found {len(results)} rows.")
        if results:
            print("First row keys:", results[0].keys())
            print("First 3 rows:")
            for r in results[:3]:
                print(r)
                
            # Count pool_id frequency
            from collections import Counter
            pool_counts = Counter(r['pool_id'] for r in results if 'pool_id' in r)
            
            # Inspect likely token pair for the candidate pool
            candidate_pool = "0x636A6BA5D1DC9D6C540060B7610644FF9A6C91E16760F73A4E79F017B11B0C4E"
            print(f"\n----- INSPECTING CANDIDATE POOL {candidate_pool[:10]}... -----")
            
            candidate_rows = [r for r in results if r.get('pool_id') == candidate_pool]
            if candidate_rows:
                r = candidate_rows[0]
                a0 = float(r.get('amount0', 0))
                a1 = float(r.get('amount1', 0))
                sqrt = float(r.get('sqrt_price_x96', 0))
                
                print(f"Raw Amount0: {a0}")
                print(f"Raw Amount1: {a1}")
                print(f"SqrtPriceX96: {sqrt}")
                
                # Heuristic: WETH (18 dec) is usually small * 1e18. USDC (6 dec) is price * 1e6.
                # If Price ~ 3900.
                # 1 WETH = 1e18. 3900 USDC = 3.9e9.
                # Ratio a1/a0 (absolute) ~ 3.9e-9 if checking raw units... wait.
                # Ratio |a1|/|a0|. 
                # |3900e6| / |1e18| = 3.9e9 / 1e18 = 3.9e-9.
                
                # Let's just print them and deciding.
            else:
                print("No rows found for candidate in this batch.")
                
            # Check liquidity specifically
            liqs = [float(r.get('liquidity', 0)) for r in results if r.get('liquidity') is not None]
            
    except Exception as e:
        print("Caught Exception:")
        print(e)

if __name__ == "__main__":
    debug_query()
