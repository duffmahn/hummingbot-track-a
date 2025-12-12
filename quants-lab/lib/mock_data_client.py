"""
Mock Market Data Client - For Testing and Development

Provides realistic mock data when real data sources aren't available.
This allows experiments to proceed while real data integration is completed.

IMPORTANT: This is a TEMPORARY solution. Replace with real data ASAP:
- Option 1: Configure Dune queries (set DUNE_SWAPS_QUERY_ID, DUNE_POOL_METRICS_QUERY_ID)
- Option 2: Start Hummingbot API and use hummingbot_data_client.py
"""

import random
import math
from typing import Dict, List
from datetime import datetime, timedelta
# We just return a namedtuple-like object or a simpler dict until we fully migrate mocks to schemas
from collections import namedtuple

# Match lib.hummingbot_data_client.V4QuoteResult shape
MockQuoteResult = namedtuple('V4QuoteResult', ['success', 'simulation_success', 'amount_out', 'gas_estimate', 'error'])


class MockDataClient:
    """Mock data client for testing - returns realistic but fake data"""
    
    def __init__(self):
        print("[MockDataClient] ⚠️  Using MOCK data - not real market data!")
        print("  Replace with Dune or Hummingbot API for production")
    
    def get_swaps_for_pair(self, pair: str, start_ts: int, end_ts: int, pool_address: str = None) -> List[Dict]:
        """
        Generate mock swap data with realistic volatility.
        
        Returns list of swaps with sqrt_price_x96, amounts, liquidity
        """
        duration_seconds = end_ts - start_ts
        num_swaps = max(10, int(duration_seconds / 60))  # ~1 swap per minute
        
        # Base price for WETH-USDC: ~$2000
        base_price = 2000.0
        base_sqrt_price = int(math.sqrt(base_price) * (2**96))
        
        swaps = []
        current_time = start_ts
        current_sqrt_price = base_sqrt_price
        
        for i in range(num_swaps):
            # Random walk with realistic volatility (~50% annualized)
            volatility_per_step = 0.005  # ~0.5% per step
            price_change = random.gauss(0, volatility_per_step)
            current_sqrt_price = int(current_sqrt_price * (1 + price_change))
            
            swaps.append({
                'block_time': datetime.fromtimestamp(current_time).isoformat(),
                'tx_hash': f'0x{"".join(random.choices("0123456789abcdef", k=64))}',
                'amount0': random.uniform(-1.0, 1.0),  # WETH
                'amount1': random.uniform(-2000, 2000),  # USDC
                'sqrt_price_x96': current_sqrt_price,
                'liquidity': 5000000  # $5M liquidity
            })
            
            current_time += duration_seconds // num_swaps
        
        return swaps
    
    def get_pool_metrics(self, pool_address: str, start_ts: int, end_ts: int) -> Dict:
        """
        Generate mock pool metrics.
        
        Returns dict with avg_liquidity, total_volume0, total_volume1, swap_count
        """
        duration_hours = (end_ts - start_ts) / 3600
        
        return {
            'avg_liquidity': 5000000,  # $5M average liquidity
            'total_volume0': duration_hours * 100000,  # ~$100K per hour (USD equivalent for Mock)
            'total_volume1': duration_hours * 100000,  # ~$100K per hour
            'swap_count': int(duration_hours * 60)  # ~60 swaps per hour
        }
    
    def test_connection(self) -> bool:
        """Always returns True for mock client"""
        print("[MockDataClient] ✅ Mock client ready (not real data!)")
        return True

    def get_v4_quote(self, token_in: str, token_out: str, amount_in_wei: int, simulate: bool = False):
        """Mock V4 quote matching HummingbotAPIClient interface"""
        # Return a successful quote depending on inputs?
        # Let's say it always succeeds for now, or randomly fails
        
        # Mock price impact: amount_out is ~ 2000 * amount_in (for WETH->USDC) or 1/2000 (USDC->WETH)
        # Simplified: just return a fixed rate + small noise
        rate = 2000.0 if "WETH" in token_in else 0.0005
        
        amount_out_raw = int(amount_in_wei * rate)
        
        return MockQuoteResult(
            success=True,
            simulation_success=True,
            amount_out=amount_out_raw,
            gas_estimate=150000,
            error=None
        )


if __name__ == "__main__":
    print("Testing Mock Data Client...")
    print("=" * 60)
    
    client = MockDataClient()
    client.test_connection()
    
    # Test swaps
    print("\nGenerating mock swaps...")
    end_ts = int(datetime.now().timestamp())
    start_ts = end_ts - 3600  # 1 hour ago
    
    swaps = client.get_swaps_for_pair("WETH-USDC", start_ts, end_ts)
    print(f"  Generated {len(swaps)} swaps")
    print(f"  First swap price: ${(swaps[0]['sqrt_price_x96'] / 2**96)**2:,.2f}")
    print(f"  Last swap price: ${(swaps[-1]['sqrt_price_x96'] / 2**96)**2:,.2f}")
    
    # Test metrics
    print("\nGenerating mock pool metrics...")
    metrics = client.get_pool_metrics("0x...", start_ts, end_ts)
    print(f"  Avg liquidity: ${metrics['avg_liquidity']:,.0f}")
    print(f"  Volume: {metrics['total_volume0']:.2f} WETH")
    print(f"  Swaps: {metrics['swap_count']}")
    
    print("\n⚠️  Remember: This is MOCK data for testing only!")
    print("Replace with real data before production use.")
