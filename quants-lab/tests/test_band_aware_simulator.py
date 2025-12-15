#!/usr/bin/env python3
"""
Standalone test for band-aware CLMM simulator.
"""

import sys
from pathlib import Path

# Add quants-lab to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.clmm_env import (
    fee_rate_from_fee_str,
    pct_to_ticks,
    snap_to_spacing,
    width_pts_to_width_pct
)

def test_helper_functions():
    """Test all helper functions."""
    print("Testing helper functions...")
    
    # Test fee_rate_from_fee_str
    assert fee_rate_from_fee_str("3000") == 0.003
    assert fee_rate_from_fee_str("500") == 0.0005
    assert fee_rate_from_fee_str("10000") == 0.01
    print("✓ fee_rate_from_fee_str works")
    
    # Test pct_to_ticks
    assert pct_to_ticks(0.05) == 487
    assert pct_to_ticks(0.0) == 0
    assert pct_to_ticks(0.01) > 0
    print("✓ pct_to_ticks works")
    
    # Test snap_to_spacing
    assert snap_to_spacing(123, 60) == 120
    assert snap_to_spacing(150, 60) == 180
    assert snap_to_spacing(100, 60) == 120
    print("✓ snap_to_spacing works")
    
    # Test width_pts_to_width_pct
    assert width_pts_to_width_pct(200) == 0.02
    assert width_pts_to_width_pct(100) == 0.01
    assert width_pts_to_width_pct(500) == 0.05
    print("✓ width_pts_to_width_pct works")
    
    print("\n✅ All helper functions passed!")
    return True


if __name__ == "__main__":
    test_helper_functions()
