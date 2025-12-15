"""
Test that baselines and alpha fields are present in EpisodeResult.

Deliverable B acceptance criteria:
- result.baselines exists and has 3 baseline keys
- alpha_usd and alpha_vs are not None
- baseline dicts contain required fields
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


def test_baselines_alpha_fields_present():
    """Verify baselines and alpha fields are populated in result."""
    
    with tempfile.TemporaryDirectory() as tmpdir:
        run_id = "test_run_baselines"
        run_dir = Path(tmpdir) / run_id
        run_dir.mkdir(parents=True)
        
        os.environ["RUNS_DIR"] = tmpdir
        os.environ["HB_EPISODE_HORIZON_S"] = "3600"
        
        env = MockCLMMEnvironment(seed=55555)
        
        episode_id = "ep_test_baselines"
        
        metadata = EpisodeMetadata(
            episode_id=episode_id,
            run_id=run_id,
            config_hash="test_hash",
            agent_version="1.0",
            extra={}
        )
        
        proposal = Proposal(
            episode_id=episode_id,
            generated_at=datetime.now().isoformat() + "Z",
            status="pending",
            connector_execution="uniswap_v3_clmm",
            chain="ethereum",
            network="mainnet",
            pool_address="0xtest",
            params={
                "width_pts": 300,
                "rebalance_threshold_pct": 0.05,
                "order_size": 0.1,
                "mid_price_usd": 2000.0,
            },
            metadata=metadata
        )
        
        ctx = RunContext(
            run_id=run_id,
            episode_id=episode_id,
            exec_mode="mock",
            seed=55555,
            config_hash="test_hash",
            agent_version="1.0",
            started_at=datetime.now()
        )
        
        result = env.execute_episode(proposal, ctx)
        
        # Verify baselines exist
        assert result.baselines is not None, "baselines should not be None"
        assert isinstance(result.baselines, dict), "baselines should be a dict"
        
        # Verify 3 baseline keys
        expected_baselines = ["baseline_wide", "baseline_medium", "baseline_tight"]
        for bl_name in expected_baselines:
            assert bl_name in result.baselines, f"Missing baseline: {bl_name}"
        
        print(f"✅ Found {len(result.baselines)} baselines: {list(result.baselines.keys())}")
        
        # Verify baseline structure
        for bl_name, bl_data in result.baselines.items():
            assert "pnl_usd" in bl_data, f"{bl_name} missing pnl_usd"
            assert "fees_usd" in bl_data, f"{bl_name} missing fees_usd"
            assert "gas_cost_usd" in bl_data, f"{bl_name} missing gas_cost_usd"
            assert "out_of_range_pct" in bl_data, f"{bl_name} missing out_of_range_pct"
            assert "rebalance_count" in bl_data, f"{bl_name} missing rebalance_count"
            print(f"  {bl_name}: pnl=${bl_data['pnl_usd']:.2f}, gas=${bl_data['gas_cost_usd']:.2f}, oor={bl_data['out_of_range_pct']:.1f}%")
        
        # Verify alpha fields
        assert result.alpha_usd is not None, "alpha_usd should not be None"
        assert result.alpha_vs is not None, "alpha_vs should not be None"
        assert result.alpha_per_100k_vol is not None, "alpha_per_100k_vol should not be None"
        assert result.alpha_per_gas_usd is not None, "alpha_per_gas_usd should not be None"
        
        assert isinstance(result.alpha_usd, float), "alpha_usd should be float"
        assert isinstance(result.alpha_vs, str), "alpha_vs should be string"
        # ✅ DELIVERABLE 3: baseline_hold is now included
        all_baselines = ["baseline_hold", "baseline_wide", "baseline_medium", "baseline_tight"]
        assert result.alpha_vs in all_baselines, f"alpha_vs should be one of {all_baselines}"
        
        print(f"\n✅ Alpha fields present:")
        print(f"  Agent PnL: ${result.pnl_usd:.2f}")
        print(f"  Alpha: ${result.alpha_usd:.2f} vs {result.alpha_vs}")
        print(f"  Alpha/100k vol: ${result.alpha_per_100k_vol:.2f}")
        print(f"  Alpha/gas: ${result.alpha_per_gas_usd:.2f}")
        
        print("\n🎉 Baseline and alpha tests passed!")


if __name__ == "__main__":
    test_baselines_alpha_fields_present()
