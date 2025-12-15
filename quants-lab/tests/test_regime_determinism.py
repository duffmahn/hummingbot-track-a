"""
Test regime determinism: same seed + episode_id → same tick path and stats.

Deliverable 2C-1: Verify generate_tick_path() is deterministic.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.clmm_env import generate_tick_path, get_regime_cfg, parse_episode_index
import random


def test_regime_determinism():
    """Verify regime selection and tick path generation are deterministic."""
    
    # Test 1: parse_episode_index determinism
    assert parse_episode_index("ep_20251213_122440_5") == 5
    assert parse_episode_index("ep_test_10") == 10
    assert parse_episode_index("invalid") == 0
    print("✅ parse_episode_index is deterministic")
    
    # Test 2: generate_tick_path determinism
    regime_cfg = get_regime_cfg("mean_revert")
    
    # Generate twice with same seed
    rng1 = random.Random(12345)
    tick_path1, stats1 = generate_tick_path(
        regime_cfg, start_tick=0, steps=100, rng=rng1, anchor_tick=0, sigma_base=10.0
    )
    
    rng2 = random.Random(12345)
    tick_path2, stats2 = generate_tick_path(
        regime_cfg, start_tick=0, steps=100, rng=rng2, anchor_tick=0, sigma_base=10.0
    )
    
    # First 10 ticks must be identical
    assert tick_path1[:10] == tick_path2[:10], f"First 10 ticks differ: {tick_path1[:10]} vs {tick_path2[:10]}"
    print(f"✅ First 10 ticks identical: {tick_path1[:10]}")
    
    # Stats must be identical
    assert stats1["start_tick"] == stats2["start_tick"]
    assert stats1["end_tick"] == stats2["end_tick"]
    assert stats1["jump_count"] == stats2["jump_count"]
    print(f"✅ Tick path stats identical: {stats1}")
    
    # Test 3: Different regimes produce different paths
    rng3 = random.Random(12345)
    jumpy_cfg = get_regime_cfg("jumpy")
    tick_path3, stats3 = generate_tick_path(
        jumpy_cfg, start_tick=0, steps=100, rng=rng3, anchor_tick=0, sigma_base=10.0
    )
    
    assert tick_path1[:10] != tick_path3[:10], "Different regimes should produce different paths"
    assert stats3["jump_count"] > 0, "Jumpy regime should have jumps"
    print(f"✅ Different regimes produce different paths (jumpy had {stats3['jump_count']} jumps)")
    
    print("\n🎉 All regime determinism tests passed!")


if __name__ == "__main__":
    test_regime_determinism()
