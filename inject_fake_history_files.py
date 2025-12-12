
import json
import random
import os
from datetime import datetime, timedelta

# Create 30 fake runs for the new regime
new_regime = "vol_mid-liq_high"
output_dir = "scratch/data/uniswap_v4_runs"

for i in range(30):
    # Gaussian centered on 300 with some noise
    width = int(random.gauss(300, 50))
    # Gaussian centered on 0.08
    thresh = max(0.01, random.gauss(0.08, 0.02))
    
    # Simple reward function: convex hull around 300 width
    reward = 10.0 - (abs(width - 300) / 100.0) 
    
    timestamp = (datetime.utcnow() - timedelta(minutes=i*10)).strftime("%Y%m%d_%H%M%S")
    ep_id = f"fake_{timestamp}_{i}"
    
    run_data = {
        "episode_id": ep_id,
        "market_regime": new_regime, # Old key field
        "regime": new_regime, # New key field
        "regime_at_start": new_regime, # Key used by loader

        "params": {
            "width_pts": width,
            "rebalance_threshold_pct": thresh
        },
        "calculated_reward": reward,
        "intel_quality": "good",
        "experiment_version": "v1_realtime",
        "reward_v1": reward,
        "timestamp": timestamp
    }
    
    filename = f"{output_dir}/{timestamp}_fake_WETH_USDC.json"
    with open(filename, "w") as f:
        json.dump(run_data, f, indent=2)

print(f"Injected 30 fake experiment files into {output_dir}")
