"""
Real Data Campaign Runner (100 Episodes)
========================================

Executes a 100-episode campaign using:
1. RealDataCLMMEnvironment (Dune historical data)
2. Dune-Calibrated EV-Gated Policy

Captures:
- Care Score vs Potential PnL
- Efficacy of Gating (Did we avoid losses?)
- Regime performance

Output:
- data/runs/real_data_campaign_{timestamp}/results.json
- Summary text
"""

import os
import sys
import json
import time
import statistics
from pathlib import Path
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.getcwd())

from lib.real_data_clmm_env import RealDataCLMMEnvironment
from lib.dune_calibrated_policy import create_dune_calibrated_proposal
from lib.run_context import RunContext
from lib.schemas import Proposal, EpisodeMetadata

def run_campaign():
    # Configuration
    CAMPAIGN_SIZE = int(os.environ.get("CAMPAIGN_SIZE", "100"))
    TIMESTAMP = datetime.now().strftime('%Y%m%d_%H%M%S')
    RUN_ID = os.environ.get("RUN_ID", f"real_data_campaign_{TIMESTAMP}")
    # CACHE_DIR defaults to timestamp if not set, else respects env
    if "HISTORICAL_DATA_CACHE_DIR" in os.environ:
         CACHE_DIR = Path(os.environ["HISTORICAL_DATA_CACHE_DIR"])
    else:
         CACHE_DIR = Path(f"scratch/data/real_data_campaign_cache_{TIMESTAMP}")
         
    RUNS_DIR = Path("data/runs") / RUN_ID
    
    # Ensure directories exist
    # Use absolute paths to prevent confusion
    CWD = Path(os.getcwd())
    
    # Set Environment Variables if not set (allow reuse)
    if "HISTORICAL_DATA_CACHE_DIR" not in os.environ:
        CACHE_DIR = CWD / f"scratch/data/real_data_campaign_cache_{TIMESTAMP}"
        os.environ["HISTORICAL_DATA_CACHE_DIR"] = str(CACHE_DIR)
    else:
        CACHE_DIR = Path(os.environ["HISTORICAL_DATA_CACHE_DIR"])
        if not CACHE_DIR.is_absolute():
            CACHE_DIR = CWD / CACHE_DIR
        
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
        
    # Runs directory
    BASE_RUNS_DIR = CWD / "data/runs"
    RUNS_DIR = BASE_RUNS_DIR / RUN_ID
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    
    os.environ["USE_REAL_DATA"] = "true"
    # Respect env var for REAL_DATA_REQUIRED (default to false for loose runs, true for QA)
    if "REAL_DATA_REQUIRED" not in os.environ:
        os.environ["REAL_DATA_REQUIRED"] = "false"
        
    os.environ["FEE_GATE_USD"] = "3.0"
    os.environ["RUNS_DIR"] = str(BASE_RUNS_DIR) # Absolute path
    
    print("=" * 70)
    print(f"STARTING REAL DATA CAMPAIGN: {RUN_ID}")
    print(f"Episodes: {CAMPAIGN_SIZE}")
    print(f"Cache: {CACHE_DIR}")
    print(f"Runs Dir: {RUNS_DIR}")
    print("=" * 70)
    
    env = RealDataCLMMEnvironment()
    # State for campaign
    current_position = None
    # Shadow State for counterfactual (always-in-market baseline)
    shadow_position = None

    results = []
    skipped_count = 0
    
    for i in range(CAMPAIGN_SIZE):
        episode_id = f"ep_{RUN_ID}_{i:03d}"
        print(f"\nProcessing {i+1}/{CAMPAIGN_SIZE}: {episode_id}")
        
        try:
            # 1. Select Window
            start_ts, end_ts, window_index = env._select_historical_window(episode_id)
            duration_s = end_ts - start_ts
            
            # 2. Fetch Data
            tick_data = env.cache.get_tick_window(
                pool_address=env.pool_address,
                start_ts=start_ts,
                duration_seconds=duration_s,
                granularity="hour"
            )
            
            if not tick_data or len(tick_data) < 2:
                print(f"  ⚠️  Insufficient data for window {window_index}, skipping")
                skipped_count += 1
                continue
                
            # 3. Analyze Regime
            tick_path = [int(t.get('tick', 0)) for t in tick_data]
            total_volume_usd = sum(float(t.get('volume_usdc', 0)) for t in tick_data)
            derived_regime, regime_features = env._derive_regime_label(tick_path)
            
            # 4. Generate Strategy Proposal (Dune Calibrated)
            # This calculates Care Score and Decision
            proposal_dict = create_dune_calibrated_proposal(
                episode_id=episode_id,
                tick_path=tick_path,
                volume_usd=total_volume_usd,
                derived_regime=derived_regime,
                derived_regime_features=regime_features,
                intel_snapshot=None, # Not used in this version of policy
                current_position=current_position, # State passed in
                cooldown_active=False,
                order_size=10.0 # Match campaign size
            )
            
            care_score = proposal_dict["care_score"]
            policy_action = proposal_dict["action"]
            width_pts = proposal_dict["width_pts"]
            
            print(f"  Window: {window_index} | Vol: ${total_volume_usd/1e6:.1f}M | Regime: {derived_regime}")
            print(f"  Care Score: {care_score:.2f} | Action: {policy_action} | Width: {width_pts}")
            if current_position:
                print(f"  Has Position: True (Range {current_position.get('tick_lower')} - {current_position.get('tick_upper')})")
            
            # Snapshot safe position before mutation
            from copy import deepcopy
            position_before = deepcopy(current_position)
            
            # 5. Execute Episode (Real Policy)
            proposal = Proposal(
                episode_id=episode_id,
                generated_at=datetime.utcnow().isoformat(),
                status="active",
                connector_execution="uniswap_v3_clmm",
                chain="ethereum",
                network="mainnet",
                pool_address=env.pool_address,
                params={
                    "order_size": 10.0, # 10.0 ETH (~$35k) for visible fees
                    "width_pts": width_pts,
                    "rebalance_threshold_pct": 10.0,
                    "action": policy_action, 
                    "historical_window_start_ts": start_ts, # Enforce same window in Env
                    "current_position": position_before # Pass state to env
                },
                metadata=EpisodeMetadata(
                    episode_id=episode_id,
                    run_id=RUN_ID,
                    timestamp=datetime.utcnow().isoformat(),
                    config_hash="real_data_campaign",
                    agent_version="dune_calibrated_v1",
                    exec_mode="real",
                    seed=i,
                    regime_key=derived_regime,
                    extra={
                        "care_score": care_score,
                        "policy_action": policy_action,
                        "window_index": window_index
                    }
                )
            )
            
            ctx = RunContext(
                run_id=RUN_ID,
                episode_id=episode_id,
                config_hash="real_data_campaign",
                agent_version="dune_calibrated_v1",
                exec_mode="real",
                seed=i,
                started_at=datetime.utcnow().isoformat()
            )
            
            # Run Real Simulation
            result = env.execute_episode(proposal, ctx)
            
            # Update Real State with Performance Attributes for Policy V2
            pos_info = result.position_after or {}
            next_pos = pos_info.get("current_position")

            if next_pos is not None:
                # attach last-window performance hints for the policy
                # Note: this mutates the dict which becomes the state for next iter
                next_pos["_last_in_range_frac"] = float(pos_info.get("in_range_frac", 0.0))
                # width_pts might not be in pos_info depending on env implementation, verify if needed.
                # Env returns 'width_pts' in params_used but implies it in bounds.
                # We calculate from bounds for safety.
                next_pos["_last_width_pts"] = int(next_pos["tick_upper"] - next_pos["tick_lower"])
                next_pos["_last_position_share"] = float(pos_info.get("position_share", 0.0))
                
                # Update Churn Brake Counter
                if policy_action in ("enter", "rebalance"):
                    next_pos["_episodes_since_rebalance"] = 0
                else:
                    # Inherit and increment from previous state
                    prev_count = 0
                    if current_position:
                         prev_count = current_position.get("_episodes_since_rebalance", 0)
                    next_pos["_episodes_since_rebalance"] = prev_count + 1
            
            current_position = next_pos

            # --- Shadow Counterfactual (Stateful Baseline) ---
            # Define Shadow Action (Always In Market)
            def shadow_baseline_action(pos, path):
                if pos is None: return "enter"
                end_tick = path[-1]
                if not (pos["tick_lower"] <= end_tick <= pos["tick_upper"]):
                    return "rebalance"
                return "hold"
                
            shadow_action = shadow_baseline_action(shadow_position, tick_path)
            shadow_episode_id = f"{episode_id}__shadow"
            
            shadow_proposal = Proposal(
                episode_id=shadow_episode_id,
                generated_at=datetime.utcnow().isoformat(),
                status="active",
                connector_execution="uniswap_v3_clmm",
                chain="ethereum",
                network="mainnet",
                pool_address=env.pool_address,
                params={
                    "order_size": 10.0,
                    "width_pts": width_pts, # Use same width for fair comparison
                    "rebalance_threshold_pct": 10.0,
                    "action": shadow_action,
                    "historical_window_start_ts": start_ts, # Exact same window
                    "current_position": deepcopy(shadow_position)
                },
                metadata=EpisodeMetadata(
                    episode_id=shadow_episode_id,
                    run_id=RUN_ID,
                    timestamp=datetime.utcnow().isoformat(),
                    config_hash="real_data_campaign_shadow",
                    agent_version="baseline_always_in_market_v1",
                    exec_mode="real",
                    seed=i,
                    regime_key=derived_regime,
                    extra={
                        "baseline": "always_in_market",
                        "window_index": window_index,
                        "care_score_actual": care_score
                    }
                )
            )
            
            shadow_ctx = RunContext(
                run_id=RUN_ID,
                episode_id=shadow_episode_id,
                config_hash="real_data_campaign_shadow",
                agent_version="baseline_always_in_market_v1",
                exec_mode="real",
                seed=i,
                started_at=datetime.utcnow().isoformat()
            )
            
            # Run Shadow Simulation
            shadow_result = env.execute_episode(shadow_proposal, shadow_ctx)
            shadow_position = shadow_result.position_after.get("current_position")
            
            # Extract Metrics
            actual_pnl = result.pnl_usd # This is Net PnL from env
            shadow_net_pnl = shadow_result.pnl_usd
            
            actual_fees = result.fees_usd
            actual_gas = result.gas_cost_usd
            
            # Determine if we were in market
            # If fees > 0 or gas > 0 or action != hold, or position_after.position_share > 0
            # For logging:
            pos_info = result.position_after
            
            # Store Result
            record = {
                "episode": i,
                "window_index": window_index,
                "start_ts": start_ts,
                "end_ts": end_ts,
                "volume_usd": total_volume_usd,
                "regime": derived_regime,
                "care_score": care_score,
                
                # Action & Config
                "policy_action": policy_action,
                "width_pts": width_pts,
                "position_before": proposal.params.get("current_position"),
                "position_after": current_position,
                
                # Outcomes
                "fees_usd": actual_fees,
                "gas_cost_usd": actual_gas,
                "pnl_usd": actual_pnl + actual_gas, # Gross PnL (approx)
                "net_pnl_usd": actual_pnl,          # Net PnL
                
                # Fee Validation (Canonical + Auditable)
                "fees_0": result.fees_0,
                "fees_1": result.fees_1,
                "pool_fees_usd_input_based": result.pool_fees_usd_input_based,
                "pool_fees_usd_amount_usd_based": result.pool_fees_usd_amount_usd_based,

                # Shadow / Value of Gating

                "actual_pnl": actual_pnl,
                "potential_pnl": shadow_net_pnl, # Shadow Net PnL (Ungated)
                "gating_value_usd": actual_pnl - shadow_net_pnl,
                "shadow_action": shadow_action,
                "shadow_net_pnl_usd": shadow_net_pnl,
                
                # Metadata
                "decision_basis": proposal_dict["decision_basis"],
                "in_range_frac": pos_info.get("in_range_frac", 0.0),
                "position_share": pos_info.get("position_share", 0.0)
            }
            
            # Backwards compatibility fields
            record["action"] = policy_action

            if pos_info and "historical_window" in pos_info:
                hw = pos_info["historical_window"]
                record["order_size_usd_mult"] = hw.get("order_size_usd_mult")
                record["position_share"] = hw.get("position_share") # Ensure it's here
                record["hit_max_share_cap"] = (float(hw.get("position_share",0)) >= float(hw.get("max_position_share",1))*0.999)

            results.append(record)
            
            print(f"  Net: ${actual_pnl:.2f} | Fees: ${actual_fees:.4f} | In-Range: {pos_info.get('in_range_frac',0)*100:.1f}%")
            print(f"  Shadow Net: ${shadow_net_pnl:.2f} | Gate Val: ${actual_pnl - shadow_net_pnl:.2f}")
            
        except Exception as e:
            print(f"  ❌ Error in episode {i}: {e}")
            import traceback
            traceback.print_exc()
            skipped_count += 1
            
    # Save Results
    results_path = RUNS_DIR / "results.json"
    with open(results_path, "w") as f:
        json.dump(results, f, indent=2)
        
    # Generate Summary Report
    generate_summary(results, skipped_count, CAMPAIGN_SIZE)

def generate_summary(results, skipped, total):
    print("\n" + "=" * 70)
    print("CAMPAIGN SUMMARY")
    print("=" * 70)
    
    if not results:
        print("No results generated.")
        return

    # 1. Action Rates
    actions = [r["policy_action"] for r in results]
    act_count = actions.count("rebalance")
    hold_count = actions.count("hold")
    
    print(f"\nCompleted: {len(results)}/{total} (Skipped: {skipped})")
    print(f"Action Rate: {act_count}/{len(results)} ({act_count/len(results)*100:.1f}%)")
    
    # 2. PnL Analysis
    actual_pnls = [r["actual_pnl"] for r in results]
    potential_pnls = [r["potential_pnl"] for r in results]
    
    total_actual = sum(actual_pnls)
    total_potential = sum(potential_pnls) # If we acted every time
    
    print(f"\n💰 PnL Performance:")
    print(f"  Total Actual PnL (Gated):   ${total_actual:.2f}")
    print(f"  Total Potential PnL (Ungated): ${total_potential:.2f}")
    print(f"  Difference (Value of Gating): ${total_actual - total_potential:.2f}")
    
    # 3. Care Score Correlation
    # Do high care scores correlate with positive Potential PnL?
    high_care = [r for r in results if r["care_score"] > 2.0]
    low_care = [r for r in results if r["care_score"] < 1.0]
    
    avg_pnl_high = statistics.mean([r["potential_pnl"] for r in high_care]) if high_care else 0
    avg_pnl_low = statistics.mean([r["potential_pnl"] for r in low_care]) if low_care else 0
    
    print(f"\n🎯 Care Score Analysis:")
    print(f"  High Confidence (>2.0) Count: {len(high_care)}")
    print(f"  High Confidence Avg PnL: ${avg_pnl_high:.2f}")
    print(f"  Low Confidence (<1.0) Count: {len(low_care)}")
    print(f"  Low Confidence Avg PnL: ${avg_pnl_low:.2f}")
    
    # 4. Regime Analysis
    regimes = set(r["regime"] for r in results)
    print(f"\n🌍 Regime Performance:")
    for regime in regimes:
        rs = [r for r in results if r["regime"] == regime]
        avg_pot_pnl = statistics.mean([r["potential_pnl"] for r in rs])
        action_rate = [r["policy_action"] for r in rs].count("rebalance") / len(rs)
        print(f"  {regime:12s}: Avg PnL ${avg_pot_pnl:6.2f} | Act Rate {action_rate*100:4.1f}% | Count {len(rs)}")

if __name__ == "__main__":
    run_campaign()
