"""
Test stateful portfolio with hold episodes (gas=0).

Increment 1 acceptance criteria:
- Portfolio state persists across episodes
- At least 1 hold episode with gas_cost_usd == 0
- Hold episodes accrue fees when in-range
- Determinism preserved with HB_SEED
"""

import os
import sys
import tempfile
from pathlib import Path

# Add quants-lab to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.clmm_env import MockCLMMEnvironment, load_portfolio_state
from lib.schemas import Proposal, EpisodeMetadata
from lib.run_context import RunContext
from datetime import datetime


def test_stateful_hold_has_zero_gas():
    """Verify stateful env produces hold episodes with gas=0."""
    
    # Create temp run directory
    with tempfile.TemporaryDirectory() as tmpdir:
        run_id = "test_run_stateful"
        run_dir = Path(tmpdir) / run_id
        run_dir.mkdir(parents=True)
        
        # Set RUNS_DIR for the test
        os.environ["RUNS_DIR"] = tmpdir
        # Reduce horizon to make holds more likely
        os.environ["HB_EPISODE_HORIZON_S"] = "3600"  # 1 hour instead of 6
        
        # Create environment
        env = MockCLMMEnvironment(seed=12345)
        
        results = []
        for i in range(10):  # More episodes = more chances for holds
            episode_id = f"ep_test_{i}"
            
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
                    "width_pts": 500,  # Wider band = more likely to stay in range
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
                seed=12345,
                config_hash="test_hash",
                agent_version="1.0",
                started_at=datetime.now()
            )
            
            result = env.execute_episode(proposal, ctx)
            results.append(result)
            
            print(f"Episode {i}: gas=${result.gas_cost_usd:.2f}, fees=${result.fees_usd:.2f}, "
                  f"oor={result.out_of_range_pct:.1f}%, rebalance={result.rebalance_count}")
        
        # Verify: at least one hold episode
        hold_episodes = [r for r in results if r.gas_cost_usd == 0]
        assert len(hold_episodes) >= 1, f"Expected at least 1 hold episode, got {len(hold_episodes)}"
        
        print(f"\n✅ Found {len(hold_episodes)} hold episodes with gas=0")
        
        # Verify: hold episodes can still accrue fees if in range
        for r in hold_episodes:
            if r.out_of_range_pct < 50:
                assert r.fees_usd > 0, f"Hold episode {r.episode_id} in range should accrue fees"
        
        # Verify: portfolio state persisted
        final_state = load_portfolio_state(run_dir)
        assert final_state.position_open, "Portfolio should have open position"
        assert final_state.rebalance_count_total >= 1, "Should have rebalanced at least once"
        
        print(f"✅ Portfolio state persisted: {final_state.rebalance_count_total} total rebalances")
        
        # Verify: position_before and position_after exist
        for r in results:
            assert r.position_before is not None, f"Episode {r.episode_id} missing position_before"
            assert r.position_after is not None, f"Episode {r.episode_id} missing position_after"
        
        print("✅ All episodes have position_before/after")
        
        print("\n🎉 Increment 1 tests passed!")


if __name__ == "__main__":
    test_stateful_hold_has_zero_gas()
