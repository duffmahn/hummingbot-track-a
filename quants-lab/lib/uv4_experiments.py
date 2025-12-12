from pathlib import Path
import json
import pandas as pd
from typing import Dict, List, Optional
from datetime import datetime
import os

class UV4ExperimentStore:
    """
    Dataset loader for Uniswap V4 Experiment Runs.
    Reads JSON files from data/uniswap_v4_runs/ and converts to DataFrame.
    """
    def __init__(self, root: str = None):
        if root:
            self.root = Path(root)
        else:
            # Default to repo root + data/uniswap_v4_runs
            # Assuming this file is in quants-lab/lib/
            # base = quants-lab/
            self.root = Path(__file__).parent.parent.parent / "data" / "uniswap_v4_runs"
        
        if not self.root.exists():
            print(f"Warning: Data directory {self.root} does not exist.")

    def list_runs(self) -> List[Path]:
        if not self.root.exists(): return []
        return sorted(self.root.glob("*.json"))

    def load_run(self, path: Path) -> Dict:
        try:
            with open(path, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading {path}: {e}")
            return {}
    
    def save_run(self, record: Dict, filename: str = None) -> Path:
        """
        Save an experiment run to the store.
        
        Args:
            record: The experiment record dict to save.
            filename: Optional custom filename. If None, auto-generates from timestamp.
        
        Returns:
            Path to the saved file.
        """
        # Ensure directory exists
        self.root.mkdir(parents=True, exist_ok=True)
        
        # Generate filename if not provided
        if not filename:
            timestamp = record.get("timestamp", datetime.now().isoformat())
            # Clean timestamp for filename
            ts_clean = timestamp.replace(":", "").replace("-", "").replace("T", "_").split(".")[0]
            pair = record.get("params", {}).get("trading_pair", "UNKNOWN")
            if not pair or pair == "UNKNOWN":
                pair = "WETH_USDC"
            pair = pair.replace("-", "_")
            filename = f"{ts_clean}_{pair}.json"
        
        filepath = self.root / filename
        
        try:
            with open(filepath, 'w') as f:
                json.dump(record, f, indent=2, default=str)
            print(f"[UV4ExperimentStore] Saved run to {filepath}")
            return filepath
        except Exception as e:
            print(f"[UV4ExperimentStore] Error saving run: {e}")
            raise

    def to_dataframe(
        self, 
        min_version: str = "v1_realtime",
        intel_quality_whitelist: tuple = ("good",), # Filter by quality
        stable_regime_only: bool = False
    ) -> pd.DataFrame:
        rows = []
        for path in self.list_runs():
            run = self.load_run(path)
            if not run: continue
            
            # Version Filtering
            version = run.get("experiment_version", "v0_mock")
            if min_version and version != min_version and min_version != "all":
                continue

            # Load Intel
            intel = run.get("intel_snapshot") or {}
            intel_start = run.get("intel_start", intel)
            intel_end = run.get("intel_end", {})
            
            # Metadata Extraction
            intel_quality = run.get("intel_quality", "unknown")
            regime_start = run.get("regime_at_start", intel_start.get("market_regime", "unknown"))
            regime_end = run.get("regime_at_end", intel_end.get("market_regime", "unknown"))
            training_phase = run.get("training_phase", "unknown")

            # Quality Filtering
            if intel_quality not in intel_quality_whitelist and "all" not in intel_quality_whitelist:
                continue
                
            # Stability Filtering
            if stable_regime_only and regime_start != regime_end:
                continue
            
            row = {
                "run_id": run.get("run_id"),
                "timestamp": run.get("timestamp"),
                "status": run.get("status"),
                "experiment_version": version,
                "training_phase": training_phase,
                "intel_source": run.get("intel_source", "unknown"),
                "intel_quality": intel_quality,
                "regime_at_start": regime_start,
                "regime_at_end": regime_end,
                
                # Metrics
                "total_pnl_usd": float(run.get("metrics", {}).get("total_pnl_usd", 0)),
                "max_drawdown_usd": float(run.get("metrics", {}).get("max_drawdown_usd", 0)),
                "gas_cost_usd": float(run.get("metrics", {}).get("gas_cost_usd", 0)),
                "trade_count": run.get("metrics", {}).get("trade_count", 0),
                "actions_count": run.get("metrics", {}).get("actions_count", 0),
                "inventory_drift": float(run.get("metrics", {}).get("inventory_drift", 0.0)),
                
                # Intel (Start)
                "regime": regime_start, # Backwards compat
                "volatility": float(intel_start.get("volatility", 0) or 0),
                "avg_liquidity": float(intel_start.get("avg_liquidity", intel_start.get("liquidity", 0)) or 0),
                "volume": float(intel_start.get("volume", 0) or 0),
                "tvl": float(intel_start.get("tvl", 0) or 0),
                "tradeable": intel_start.get("tradeable", False),
                "mev_risk": intel_start.get("mev_risk", "unknown"),
                "gas_rating": intel_start.get("gas_rating", "unknown"),
                "pool_health_score": intel_start.get("pool_health_score", intel_start.get("health_score", 0)),
                "file_path": str(path)
            }
            
            pnl = row["total_pnl_usd"]
            dd = abs(row["max_drawdown_usd"])
            gas = row["gas_cost_usd"]
            drift = abs(row["inventory_drift"])

            row["reward_v1"] = (
                pnl
                - 0.5 * dd
                - 1.0 * gas
                - 0.01 * row["actions_count"]
                - 0.5 * drift  # Reduced from 1.0, 50% penalty for full drift
            )
            
            # Flatten Params
            params = run.get("params") or run.get("params_original") or {}
            for k, v in params.items():
                row[f"param_{k}"] = v
                
            # Simulation Metrics (Phase 4)
            sim = run.get("simulation") or {}
            if sim:
                row["sim_used"] = sim.get("used", False) or sim.get("simulation_used", False)
                row["sim_success"] = sim.get("success", False) or sim.get("simulation_success", False)
                row["sim_gas_estimate"] = float(sim.get("gas_estimate", 0) or 0)
                row["sim_amount_out"] = float(sim.get("amount_out", 0) or 0)
                row["sim_latency_ms"] = float(sim.get("latency_ms", 0) or 0)
                row["sim_delta_reward"] = float(sim.get("delta_reward", 0) or 0)
            else:
                row["sim_used"] = False
                row["sim_success"] = False
                row["sim_gas_estimate"] = 0.0
                row["sim_amount_out"] = 0.0
                row["sim_latency_ms"] = 0.0
                row["sim_delta_reward"] = 0.0

            # Reward V2 (Sim-Adjusted)
            row["reward_v2"] = row.get("reward_v1", 0) + row["sim_delta_reward"]

            rows.append(row)
            
        return pd.DataFrame(rows)

if __name__ == "__main__":
    store = UV4ExperimentStore()
    df = store.to_dataframe()
    print(f"Loaded {len(df)} runs.")
    if not df.empty:
        print(df.head())
