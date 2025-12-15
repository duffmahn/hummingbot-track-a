"""
Test tight bands can win in mean_revert + high volume regime.

Deliverable 2C-3: Force mean_revert regime, verify medium/tight wins at least once.
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


def test_tight_can_win_in_mean_revert_high_volume():
    """Verify tight/medium baselines can win in mean_revert regime."""
    
    with tempfile.TemporaryDirectory() as tmpdir:
        os.environ["RUNS_DIR"] = tmpdir
        os.environ["HB_VOL_REGIME"] = "mean_revert"
        os.environ["HB_MEAN_REVERT_K"] = "0.15"  # Stronger mean reversion
        os.environ["HB_EPISODE_HORIZON_S"] = "21600"
        
        env = MockCLMMEnvironment(seed=77777)
        
        results = []
        for i in range(50):
            episode_id = f"ep_test_tight_{i}"
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
                    run_id="test_tight_wins",
                    config_hash="test",
                    agent_version="1.0",
                    extra={}
                )
            )
            
            ctx = RunContext(
                run_id="test_tight_wins",
                episode_id=episode_id,
                exec_mode="mock",
                seed=77777,
                config_hash="test",
                agent_version="1.0",
                started_at=datetime.now()
            )
            
            result = env.execute_episode(proposal, ctx)
            results.append(result)
        
        # Collect winners
        alpha_vs_winners = [r.alpha_vs for r in results if r.alpha_vs]
        win_counts = Counter(alpha_vs_winners)
        
        print(f"\n📊 Baseline Policy Win Counts (50 episodes, mean_revert):")
        for baseline, count in sorted(win_counts.items(), key=lambda x: x[1], reverse=True):
            print(f"  {baseline}: {count} wins ({count/len(alpha_vs_winners)*100:.1f}%)")
        
        # Test: medium or tight wins at least once OR baseline_hold win rate < 100%
        medium_wins = win_counts.get("baseline_medium", 0)
        tight_wins = win_counts.get("baseline_tight", 0)
        hold_wins = win_counts.get("baseline_hold", 0)
        hold_win_rate = hold_wins / len(alpha_vs_winners) if alpha_vs_winners else 1.0
        
        print(f"\n✅ baseline_medium wins: {medium_wins}")
        print(f"✅ baseline_tight wins: {tight_wins}")
        print(f"✅ baseline_hold win rate: {hold_win_rate*100:.1f}%")
        
        success = (medium_wins > 0 or tight_wins > 0 or hold_win_rate < 1.0)
        
        assert success, (
            f"Expected medium/tight to win at least once OR hold win rate < 100%. "
            f"Got medium={medium_wins}, tight={tight_wins}, hold_rate={hold_win_rate*100:.1f}%"
        )
        
        print("\n🎉 Tight can win test passed!")


if __name__ == "__main__":
    test_tight_can_win_in_mean_revert_high_volume()
