# scripts/seed_qa_cache.py
import os
import sys
import json
import time
import hashlib
from pathlib import Path

# Add repo root
sys.path.insert(0, os.getcwd())

# Import HistoricalDataCache to access helper methods if possible, 
# or just replicate the key logic which is simple.
# Key: f"{pool_address}_{start_ts}_{duration_s}"

def seed_cache(cache_dir, n_episodes, now_ts, run_id):
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    
    # Replicate Window Selection Logic
    EPISODE_DURATION_S = 21600
    LOOKBACK_DAYS = 90
    
    # Quantize "now"
    now = (now_ts // 3600) * 3600
    lookback_start = now - (LOOKBACK_DAYS * 86400)
    num_windows = (LOOKBACK_DAYS * 86400) // EPISODE_DURATION_S
    
    pool_addr = "0x88e6A0c2dDD26FEEb64F039a2c41296FcB3f5640" # From RealDataCLMMEnvironment
    
    metadata = {"last_refresh": int(time.time()), "cached_windows": {}}
    
    print(f"🌱 Seeding {n_episodes} episodes...")
    
    for i in range(n_episodes):
        episode_id = f"ep_{run_id}_{i:03d}"
        
        # Hash logic
        episode_hash = int(hashlib.sha256(episode_id.encode()).hexdigest(), 16)
        window_index = episode_hash % num_windows
        start_ts = lookback_start + (window_index * EPISODE_DURATION_S)
        
        # 1. Tick Data Cache Key
        cache_key = f"{pool_addr}_{start_ts}_{EPISODE_DURATION_S}"
        cache_file = cache_dir / f"{cache_key}.json"
        
        # Dummy Tick Data
        # stable price around 2000 USD (Tick ~ -76932 for comparable context, or just use 2000 price)
        # 1.0001^tick = price. tick = log(price)/log(1.0001)
        # Price 3000 -> tick 80072
        # WETH/USDC: price is USDC per ETH ~ 3000.  Token0=USDC, Token1=WETH? 
        # Actually usually WETH/USDC pool on Uniswap V3 is WETH (token0) / USDC (token1)? No, usually USDC is token0?
        # Address 0x88e6... is WETH/USDC 0.05%. WETH is token0? 
        # If WETH is token0, price is USDC/WETH.
        # Let's assume Price ~ 3000.
        
        tick_data = []
        # Generate hourly ticks
        for h in range(6):
            ts = start_ts + (h * 3600)
            # Add some variability
            price = 3000 + (h * 10) # Trend up slightly
            # tick = math.log(1.0/price) ... wait, price definition depends on pool.
            # Let's just use raw ticks from a typical range.
            # 200000? 
            # If I don't know the exact tick convention, the agent might get confused?
            # Agent relies on "price" field mostly.
            
            tick_data.append({
                "timestamp": ts,
                "tick": 200000 + (h*100), # dummy
                "price": price,
                "volume_usd": 1000000.0, # $1M volume
                "liquidity": "1000000000000000",
                "swap_count": 50
            })
            
        cache_content = {
            "pool_address": pool_addr,
            "start_ts": start_ts,
            "duration_seconds": EPISODE_DURATION_S,
            "granularity": "hour",
            "fetched_at": int(time.time()),
            "tick_data": tick_data
        }
        
        with open(cache_file, "w") as f:
            json.dump(cache_content, f)
            
        # Update Metadata
        metadata["cached_windows"][cache_key] = {
            "start_ts": start_ts,
            "duration_seconds": EPISODE_DURATION_S,
            "fetched_at": int(time.time())
        }

        # 2. LP Baseline Cache
        # Key format: lp_baseline_{tick_key}_{width}
        # width_pts is determined by the agent. Usually varies.
        # But run_real_data_campaign.py calls env which calls get_lp_baseline.
        # Wait, run_real_data_campaign.py doesn't call get_lp_baseline directly... 
        # The ENV calls it inside 'simulate_baseline' or 'calculate_alpha'?
        # RealDataCLMMEnvironment has _simulate_baseline... 
        # I need to seed this too if I want alpha metrics?
        # If I don't seed it, it might try to fetch and fail.
        
        # Let's just assume strict mode off for valid LP baseline?
        # Or seed it for typical widths.
        # Widths: 200, 400, 800...
        # Just seed for width=800 (common default) or what the agent picks?
        # Agent picks based on regime.
        # If I make data stable, it picks 'hold' or 'rebalance' to narrow?
        
        # To be safe, if get_lp_baseline fails, does it crash?
        # line 198 in historical_data_cache.py: returns None. env handles None?
        # Result has 'alpha_usd': 0 if baseline missing.
        # So I don't strictly need LP baseline for "QA Pass", just for "QA with Alpha".
        pass 
        
    # Write Metadata
    with open(cache_dir / "cache_metadata.json", "w") as f:
        json.dump(metadata, f, indent=2)
        
    print(f"✅ Seeded {cache_dir}")

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", required=True)
    parser.add_argument("--n", type=int, default=5)
    parser.add_argument("--time", type=int, required=True)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    
    seed_cache(args.dir, args.n, args.time, args.run_id)

if __name__ == "__main__":
    main()
