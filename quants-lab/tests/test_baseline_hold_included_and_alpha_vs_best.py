"""
Test that baseline_hold is included and alpha_vs is computed correctly.

Deliverable 6 acceptance criteria:
- After opening position, baseline_hold appears in baselines
- alpha_vs equals the best baseline (argmax pnl)
- alpha_usd equals agent_pnl - best_baseline_pnl
"""

import os
import sys
import tempfile
from pathlib import Path

# Add quants-lab to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.clmm_env import MockCLMMEnvironment
from lib.schemas import Proposal, EpisodeMetadata
from lib.run_context import RunContext
from datetime import datetime


def test_baseline_hold_included_and_alpha_vs_best():
    """Verify baseline_hold is included and alpha is computed correctly."""
    
    with tempfile.TemporaryDirectory() as tmpdir:
        run_id = "test_run_baseline_hold"
        run_dir = Path(tmpdir) / run_id
        run_dir.mkdir(parents=True)
        
        os.environ["RUNS_DIR"] = tmpdir
        os.environ["HB_EPISODE_HORIZON_S"] = "3600"
        
        env = MockCLMMEnvironment(seed=88888)
        
        # Episode 1: Open position
        episode_id_1 = "ep_test_baseline_1"
        metadata_1 = EpisodeMetadata(
            episode_id=episode_id_1,
            run_id=run_id,
            config_hash="test_hash",
            agent_version="1.0",
            extra={}
        )
        
        proposal_1 = Proposal(
            episode_id=episode_id_1,
            generated_at=datetime.now().isoformat() + "Z",
            status="pending",
            connector_execution="uniswap_v3_clmm",
            chain="ethereum",
            network="mainnet",
            pool_address="0xtest",
            params={
                "action": "rebalance",
                "width_pts": 300,
                "rebalance_threshold_pct": 0.05,
                "order_size": 0.1,
                "mid_price_usd": 2000.0,
            },
            metadata=metadata_1
        )
        
        ctx_1 = RunContext(
            run_id=run_id,
            episode_id=episode_id_1,
            exec_mode="mock",
            seed=88888,
            config_hash="test_hash",
            agent_version="1.0",
            started_at=datetime.now()
        )
        
        result_1 = env.execute_episode(proposal_1, ctx_1)
        
        print(f"Episode 1: baselines={list(result_1.baselines.keys())}")
        # First episode: baseline_hold should open wide (no prior position)
        assert "baseline_hold" in result_1.baselines, "baseline_hold should exist"
        
        # Episode 2: Hold action (position exists now)
        episode_id_2 = "ep_test_baseline_2"
        metadata_2 = EpisodeMetadata(
            episode_id=episode_id_2,
            run_id=run_id,
            config_hash="test_hash",
            agent_version="1.0",
            extra={}
        )
        
        proposal_2 = Proposal(
            episode_id=episode_id_2,
            generated_at=datetime.now().isoformat() + "Z",
            status="pending",
            connector_execution="uniswap_v3_clmm",
            chain="ethereum",
            network="mainnet",
            pool_address="0xtest",
            params={
                "action": "hold",
                "width_pts": 300,
                "rebalance_threshold_pct": 0.05,
                "order_size": 0.1,
                "mid_price_usd": 2000.0,
            },
            metadata=metadata_2
        )
        
        ctx_2 = RunContext(
            run_id=run_id,
            episode_id=episode_id_2,
            exec_mode="mock",
            seed=88888,
            config_hash="test_hash",
            agent_version="1.0",
            started_at=datetime.now()
        )
        
        result_2 = env.execute_episode(proposal_2, ctx_2)
        
        print(f"\nEpisode 2 (hold):")
        print(f"  Baselines: {list(result_2.baselines.keys())}")
        print(f"  Agent PnL: ${result_2.pnl_usd:.2f}")
        print(f"  Alpha: ${result_2.alpha_usd:.2f} vs {result_2.alpha_vs}")
        
        # Verify baseline_hold exists
        assert "baseline_hold" in result_2.baselines, "baseline_hold should exist after opening"
        assert "baseline_wide" in result_2.baselines, "baseline_wide should exist"
        assert "baseline_medium" in result_2.baselines, "baseline_medium should exist"
        assert "baseline_tight" in result_2.baselines, "baseline_tight should exist"
        
        # Verify baseline_hold has gas=0
        assert result_2.baselines["baseline_hold"]["gas_cost_usd"] == 0.0, "baseline_hold should have gas=0"
        
        # Verify alpha_vs is correct (best baseline)
        baseline_pnls = {name: bl["pnl_usd"] for name, bl in result_2.baselines.items()}
        best_baseline = max(baseline_pnls, key=baseline_pnls.get)
        best_pnl = baseline_pnls[best_baseline]
        
        print(f"\n  Baseline PnLs:")
        for name, pnl in sorted(baseline_pnls.items(), key=lambda x: x[1], reverse=True):
            print(f"    {name}: ${pnl:.2f}")
        
        assert result_2.alpha_vs == best_baseline, f"alpha_vs should be {best_baseline}, got {result_2.alpha_vs}"
        
        # Verify alpha_usd calculation
        expected_alpha = result_2.pnl_usd - best_pnl
        assert abs(result_2.alpha_usd - expected_alpha) < 0.01, \
            f"alpha_usd should be {expected_alpha:.2f}, got {result_2.alpha_usd:.2f}"
        
        print(f"\n✅ baseline_hold included in baselines")
        print(f"✅ alpha_vs = {result_2.alpha_vs} (best baseline)")
        print(f"✅ alpha_usd = agent_pnl - best_baseline_pnl")
        print("\n🎉 Baseline hold tests passed!")


if __name__ == "__main__":
    test_baseline_hold_included_and_alpha_vs_best()
