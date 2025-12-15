"""
Test MockCLMMClient pool_info() internal consistency.

Verifies that tick and sqrtPriceX96 are coherent and tick is snapped to spacing.
"""

import math
import sys
from pathlib import Path

# Add quants-lab to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.mock_clmm_client import MockCLMMClient

Q96 = 2 ** 96


def tick_to_sqrtPriceX96(tick: int) -> int:
    """Convert tick to sqrtPriceX96.
    
    sqrt(1.0001^tick) * 2^96 = 1.0001^(tick/2) * 2^96
    """
    return int((1.0001 ** (tick / 2)) * Q96)


def sqrtPriceX96_to_tick(sqrt_price_x96: int) -> int:
    """Convert sqrtPriceX96 back to tick.
    
    price = (sqrtP/Q96)^2
    tick = log(price)/log(1.0001)
    """
    sp = sqrt_price_x96 / Q96
    price = sp * sp
    return int(round(math.log(price) / math.log(1.0001)))


def snap_to_spacing(tick: int, spacing: int) -> int:
    """Snap tick to nearest valid tick spacing."""
    return int(round(tick / spacing) * spacing)


def test_pool_info_tick_sqrt_consistent():
    """Test that pool_info generates consistent tick/sqrtPriceX96 pairs."""
    print("Testing pool_info() internal consistency...")
    
    client = MockCLMMClient(seed=12345)
    
    passed = 0
    failed = 0
    
    for i in range(200):
        resp = client.pool_info(
            chain="ethereum",
            network="mainnet",
            connector="uniswap",
            pool_address="0xmock"
        )
        
        assert resp["success"] is True, f"pool_info failed on iteration {i}"
        data = resp["data"]
        
        tick = int(data["tick"])
        spacing = int(data["tickSpacing"])
        sqrtp = int(data["sqrtPriceX96"])
        
        # Test 1: Tick should be snapped to spacing
        expected_snapped = snap_to_spacing(tick, spacing)
        if tick != expected_snapped:
            print(f"  ❌ Iteration {i}: tick {tick} not snapped to spacing {spacing} (expected {expected_snapped})")
            failed += 1
            continue
        
        # Test 2: sqrtPriceX96 should match tick (within rounding error)
        tick_back = sqrtPriceX96_to_tick(sqrtp)
        if abs(tick_back - tick) > 1:
            print(f"  ❌ Iteration {i}: tick roundtrip error too large: {tick} -> {sqrtp} -> {tick_back}")
            failed += 1
            continue
        
        passed += 1
    
    print(f"\n✅ Passed: {passed}/200")
    if failed > 0:
        print(f"❌ Failed: {failed}/200")
        return False
    
    print("✅ All pool_info() consistency tests passed!")
    return True


if __name__ == "__main__":
    success = test_pool_info_tick_sqrt_consistent()
    sys.exit(0 if success else 1)
