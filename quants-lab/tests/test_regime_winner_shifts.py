"""
Test regime winner shifts: verify different baselines win in different regimes.

Deliverable 2C-2: Run 40 episodes with mixed schedule, assert >=2 distinct winners.
"""

import os
import sys
import tempfile
from pathlib import Path
from collections import Counter

sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.clmm_env import MockCLMMEnvironment
from lib.schemas import Proposal, EpisodeMetadata
from lib.run_context import RunContext
from datetime import datetime


def test_regime_winner_shifts():
    """Verify different baselines win in different regimes."""
    
    with tempfile.TemporaryDirectory() as tmpdir:
        os.environ["RUNS_DIR"] = tmpdir
        os.environ["HB_REGIME_SCHEDULE"] = "low,mid,trend_up,jumpy,mean_revert"
        os.environ["HB_EPISODE_HORIZON_S"] = "21600"
        
        env = MockCLMMEnvironment(seed=55555)
        
        results = []
        for i in range(40):
            episode_id = f"ep_test_regime_{i}"
            proposal = Proposal(
                episode_id=episode_id,
                generated_at=datetime.now().isoformat() + "Z",
                status="pending",
                connector_execution="uniswap_v3_clmm",
                chain="ethereum",
                network="mainnet",
                pool_address="0xtest",
                params={"action": "rebalance" if i == 0 else "auto", "width_pts": 500},
                metadata=EpisodeMetadata(
                    episode_id=episode_id,
                    run_id="test_regime_shifts",
                    config_hash="test",
                    agent_version="1.0",
                    extra={}
                )
            )
            
            ctx = RunContext(
                run_id="test_regime_shifts",
                episode_id=episode_id,
                exec_mode="mock",
                seed=55555,
                config_hash="test",
                agent_version="1.0",
                started_at=datetime.now()
            )
            
            result = env.execute_episode(proposal, ctx)
            results.append(result)
        
        # Collect winners
        alpha_vs_winners = [r.alpha_vs for r in results if r.alpha_vs]
        win_counts = Counter(alpha_vs_winners)
        
        print(f"\n📊 Baseline Policy Win Counts (40 episodes):")
        for baseline, count in sorted(win_counts.items(), key=lambda x: x[1], reverse=True):
            print(f"  {baseline}: {count} wins ({count/len(alpha_vs_winners)*100:.1f}%)")
        
        # Test: At least 2 distinct winners
        distinct_winners = len(win_counts)
        print(f"\n✅ Distinct winners: {distinct_winners}")
        
        assert distinct_winners >= 2, (
            f"Expected at least 2 distinct winners across regimes, got {distinct_winners}. "
            f"Winners: {win_counts}"
        )
        
        print("\n🎉 Regime winner shifts test passed!")


if __name__ == "__main__":
    test_regime_winner_shifts()
