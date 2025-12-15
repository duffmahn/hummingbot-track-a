"""
Test that explicit action="hold" results in zero gas and accrues fees.

Deliverable 6 acceptance criteria:
- First episode opens position (action="rebalance")
- Subsequent episodes with action="hold" have gas=0
- Hold episodes accrue fees when in range
- Band remains unchanged for hold episodes
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


def test_action_hold_has_zero_gas_and_accrues_fees():
    """Verify action=hold results in gas=0 and fees accrue."""
    
    with tempfile.TemporaryDirectory() as tmpdir:
        run_id = "test_run_action_hold"
        run_dir = Path(tmpdir) / run_id
        run_dir.mkdir(parents=True)
        
        os.environ["RUNS_DIR"] = tmpdir
        os.environ["HB_EPISODE_HORIZON_S"] = "3600"
        
        env = MockCLMMEnvironment(seed=99999)
        
        # Episode 1: Open position (rebalance)
        episode_id_1 = "ep_test_hold_1"
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
                "action": "rebalance",  # Open position
                "width_pts": 500,
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
            seed=99999,
            config_hash="test_hash",
            agent_version="1.0",
            started_at=datetime.now()
        )
        
        result_1 = env.execute_episode(proposal_1, ctx_1)
        
        print(f"Episode 1: action={result_1.position_after['action_applied']}, gas=${result_1.gas_cost_usd:.2f}")
        assert result_1.gas_cost_usd > 0, "First episode should pay gas to open"
        assert result_1.position_after["action_applied"] == "rebalance_opening"
        
        # Episodes 2-5: Hold
        hold_episodes = []
        for i in range(2, 6):
            episode_id = f"ep_test_hold_{i}"
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
                    "action": "hold",  # Explicit hold
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
            hold_episodes.append(result)
            
            print(f"Episode {i}: action={result.position_after['action_applied']}, gas=${result.gas_cost_usd:.2f}, fees=${result.fees_usd:.2f}, oor={result.out_of_range_pct:.1f}%")
        
        # Verify hold episodes
        for result in hold_episodes:
            assert result.gas_cost_usd == 0.0, f"Hold episode {result.episode_id} should have gas=0"
            assert result.position_after["action_applied"] == "hold", f"Action should be hold"
            
            # If mostly in range, should have fees
            if result.out_of_range_pct < 50:
                assert result.fees_usd > 0, f"Hold episode in range should accrue fees"
        
        print(f"\n✅ All {len(hold_episodes)} hold episodes have gas=0")
        print(f"✅ Hold episodes accrue fees when in range")
        print("\n🎉 Action hold tests passed!")


if __name__ == "__main__":
    test_action_hold_has_zero_gas_and_accrues_fees()
