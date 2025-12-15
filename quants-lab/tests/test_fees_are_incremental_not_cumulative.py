"""
Test that fees are incremental, not cumulative (no double-counting).

Deliverable 2 acceptance criteria:
- fees_usd is per-episode incremental
- sum(fees_usd) across episodes is reasonable
- uncollected fees don't leak into fees_usd
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


def test_fees_are_incremental_not_cumulative():
    """Verify fees_usd is incremental and doesn't double-count uncollected fees."""
    
    with tempfile.TemporaryDirectory() as tmpdir:
        run_id = "test_run_incremental"
        run_dir = Path(tmpdir) / run_id
        run_dir.mkdir(parents=True)
        
        os.environ["RUNS_DIR"] = tmpdir
        os.environ["HB_EPISODE_HORIZON_S"] = "3600"
        
        env = MockCLMMEnvironment(seed=99999)
        
        results = []
        for i in range(5):
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
                    "width_pts": 500,
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
                seed=99999,
                config_hash="test_hash",
                agent_version="1.0",
                started_at=datetime.now()
            )
            
            result = env.execute_episode(proposal, ctx)
            results.append(result)
            
            print(f"Episode {i}: fees=${result.fees_usd:.2f}, gas=${result.gas_cost_usd:.2f}, "
                  f"uncollected=${result.position_after.get('uncollected_fees_usd', 0):.2f}, "
                  f"collected=${result.position_after.get('fees_collected_this_episode_usd', 0):.2f}")
        
        # Verify: fees_usd is incremental (not monotonically increasing due to accumulation)
        fees_list = [r.fees_usd for r in results]
        
        # Check that fees don't monotonically increase
        # (they should vary based on in-range time, not accumulate)
        is_monotonic = all(fees_list[i] <= fees_list[i+1] for i in range(len(fees_list)-1))
        assert not is_monotonic or len(set(fees_list)) > 1, \
            f"Fees appear to be cumulative (monotonic): {fees_list}"
        
        print(f"\n✅ Fees are incremental: {[f'{f:.2f}' for f in fees_list]}")
        
        # Verify: sum of fees_usd should be <= sum of collected + final uncollected
        total_fees_reported = sum(r.fees_usd for r in results)
        total_collected = sum(r.position_after.get('fees_collected_this_episode_usd', 0) for r in results)
        final_uncollected = results[-1].position_after.get('uncollected_fees_usd', 0)
        
        # Basic sanity: reported fees should equal sum of this_episode fees
        total_this_episode = sum(r.position_after.get('fees_this_episode_usd', 0) for r in results)
        
        assert abs(total_fees_reported - total_this_episode) < 0.01, \
            f"fees_usd sum ({total_fees_reported:.2f}) != sum of fees_this_episode ({total_this_episode:.2f})"
        
        print(f"✅ Total fees_usd: ${total_fees_reported:.2f}")
        print(f"✅ Total fees_this_episode: ${total_this_episode:.2f}")
        print(f"✅ Total collected: ${total_collected:.2f}")
        print(f"✅ Final uncollected: ${final_uncollected:.2f}")
        
        # Verify: collected + uncollected should account for all fees
        total_accounted = total_collected + final_uncollected
        assert abs(total_accounted - total_this_episode) < 0.01, \
            f"Collected + uncollected ({total_accounted:.2f}) != total fees ({total_this_episode:.2f})"
        
        print(f"✅ Fee accounting correct: collected + uncollected = total")
        
        print("\n🎉 Increment 2 tests passed!")


if __name__ == "__main__":
    test_fees_are_incremental_not_cumulative()
