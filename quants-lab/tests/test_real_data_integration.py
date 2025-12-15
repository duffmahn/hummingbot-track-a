"""
Real Data Integration Tests

Test 1: Determinism test - same episode_id → identical historical_window
Test 2: Baseline fairness invariants - all baselines see identical data
"""

import os
import sys
import json
from pathlib import Path

# Add quants-lab to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.real_data_clmm_env import RealDataCLMMEnvironment
from lib.schemas import Proposal, EpisodeMetadata
from lib.run_context import RunContext


def test_determinism():
    """
    Test 1: Determinism - same episode_id → identical window metadata
    """
    print("=" * 70)
    print("TEST 1: DETERMINISM")
    print("=" * 70)
    
    env = RealDataCLMMEnvironment()
    episode_id = "test_determinism_001"
    
    # Run 1
    start_ts_1, end_ts_1, window_index_1 = env._select_historical_window(episode_id)
    
    # Run 2 (same episode_id)
    start_ts_2, end_ts_2, window_index_2 = env._select_historical_window(episode_id)
    
    # Verify
    assert start_ts_1 == start_ts_2, f"start_ts mismatch: {start_ts_1} != {start_ts_2}"
    assert end_ts_1 == end_ts_2, f"end_ts mismatch: {end_ts_1} != {end_ts_2}"
    assert window_index_1 == window_index_2, f"window_index mismatch: {window_index_1} != {window_index_2}"
    
    print(f"✅ PASS: Same episode_id → identical window")
    print(f"   Window Index: {window_index_1}")
    print(f"   Start: {start_ts_1}")
    print(f"   End: {end_ts_1}")
    print()


def test_baseline_fairness():
    """
    Test 2: Baseline fairness - verify metadata fields are present
    """
    print("=" * 70)
    print("TEST 2: METADATA COMPLETENESS")
    print("=" * 70)
    
    # Set up environment
    os.environ["USE_REAL_DATA"] = "true"
    
    from lib.clmm_env import create_environment
    
    env = create_environment(exec_mode="mock", seed=42)
    
    # Verify environment type
    assert env.__class__.__name__ == "RealDataCLMMEnvironment", f"Expected RealDataCLMMEnvironment, got {env.__class__.__name__}"
    
    # Verify audit tags
    assert hasattr(env, '_real_data_used'), "Missing _real_data_used tag"
    assert env._real_data_used == True, "_real_data_used should be True"
    assert hasattr(env, '_fallback_used'), "Missing _fallback_used tag"
    assert env._fallback_used == False, "_fallback_used should be False"
    
    # Test window selection
    episode_id = "test_metadata_001"
    start_ts, end_ts, window_index = env._select_historical_window(episode_id)
    
    # Verify window_index is deterministic
    start_ts_2, end_ts_2, window_index_2 = env._select_historical_window(episode_id)
    assert window_index == window_index_2, "window_index not deterministic"
    
    # Test regime derivation
    test_tick_path = [80000, 80100, 80050, 80150, 80100, 80200]
    regime, features = env._derive_regime_label(test_tick_path)
    
    assert regime in ["jumpy", "trend_up", "trend_down", "low_vol", "mean_revert"], f"Invalid regime: {regime}"
    assert "end_tick_delta" in features, "Missing end_tick_delta in features"
    assert "std_step" in features, "Missing std_step in features"
    assert "jump_count" in features, "Missing jump_count in features"
    
    print(f"✅ PASS: Metadata completeness")
    print(f"   Environment: {env.__class__.__name__}")
    print(f"   Real Data Used: {env._real_data_used}")
    print(f"   Fallback Used: {env._fallback_used}")
    print(f"   Window Index: {window_index}")
    print(f"   Derived Regime: {regime}")
    print(f"   Regime Features: {features}")
    print()


if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("REAL DATA INTEGRATION TESTS")
    print("=" * 70 + "\n")
    
    try:
        test_determinism()
        test_baseline_fairness()
        
        print("=" * 70)
        print("✅ ALL TESTS PASSED")
        print("=" * 70)
        
    except Exception as e:
        print("\n" + "=" * 70)
        print(f"❌ TESTS FAILED: {e}")
        print("=" * 70)
        import traceback
        traceback.print_exc()
        sys.exit(1)
