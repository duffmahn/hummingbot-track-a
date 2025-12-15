import random
import time
from typing import Dict, Any, Optional

class MockCLMMClient:
    """
    Deterministic mock CLMM client for testing.
    Seeded for reproducibility.
    """
    
    def __init__(self, seed: Optional[int] = None):
        self.seed = seed or 42
        self.rng = random.Random(self.seed)
        
    def _mock_response(self, data: Dict[str, Any], latency_range=(10, 50)) -> Dict[str, Any]:
        """Generate a mock successful response with simulated latency."""
        latency_ms = self.rng.uniform(*latency_range)
        time.sleep(latency_ms / 1000)  # Simulate network delay
        
        return {
            "success": True,
            "data": data,
            "error": None,
            "latency_ms": latency_ms
        }
    
    def pool_info(self, chain: str, network: str, connector: str, pool_address: str) -> Dict[str, Any]:
        """Mock pool info."""
        tick_spacing = 60
        
        # Generate random tick and snap to spacing
        raw_tick = self.rng.randint(-887272, 887272)
        tick = int(round(raw_tick / tick_spacing) * tick_spacing)
        
        # Compute sqrtPriceX96 from tick for consistency
        # sqrt(1.0001^tick) * 2^96
        sqrt_price_x96 = int((1.0001 ** (tick / 2)) * (2 ** 96))
        
        data = {
            "token0": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",  # WETH
            "token1": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",  # USDC
            "fee": "3000",
            "tickSpacing": tick_spacing,
            "liquidity": str(self.rng.randint(1000000, 10000000)),
            "sqrtPriceX96": str(sqrt_price_x96),
            "tick": tick
        }
        return self._mock_response(data)
    
    def position_info(self, chain: str, network: str, connector: str, token_id: int) -> Dict[str, Any]:
        """Mock position info."""
        data = {
            "tokenId": token_id,
            "token0": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
            "token1": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
            "fee": "3000",
            "tickLower": -887220,
            "tickUpper": 887220,
            "liquidity": str(self.rng.randint(100000, 1000000)),
            "tokensOwed0": str(self.rng.randint(0, 10000)),
            "tokensOwed1": str(self.rng.randint(0, 10000))
        }
        return self._mock_response(data)
    
    def positions_owned(self, chain: str, network: str, connector: str, address: str) -> Dict[str, Any]:
        """Mock positions owned."""
        num_positions = self.rng.randint(0, 3)
        data = {
            "positions": [
                {"tokenId": i, "liquidity": str(self.rng.randint(100000, 1000000))}
                for i in range(num_positions)
            ]
        }
        return self._mock_response(data)
    
    def quote_position(self, chain: str, network: str, connector: str,
                      token0: str, token1: str, fee: str,
                      lower_price: str, upper_price: str,
                      amount0: Optional[str] = None, amount1: Optional[str] = None) -> Dict[str, Any]:
        """Mock quote position."""
        data = {
            "amount0": amount0 or str(self.rng.randint(1000000, 10000000)),
            "amount1": amount1 or str(self.rng.randint(1000000, 10000000)),
            "liquidity": str(self.rng.randint(100000, 1000000)),
            "gasEstimate": str(self.rng.randint(200000, 400000))
        }
        return self._mock_response(data)
    
    def open_position(self, chain: str, network: str, connector: str,
                     address: str, token0: str, token1: str, fee: str,
                     lower_price: str, upper_price: str,
                     amount0: str, amount1: str) -> Dict[str, Any]:
        """Mock open position."""
        data = {
            "tokenId": self.rng.randint(1000, 9999),
            "txHash": f"0x{''.join(self.rng.choices('0123456789abcdef', k=64))}",
            "gasUsed": str(self.rng.randint(200000, 400000))
        }
        return self._mock_response(data, latency_range=(100, 300))
    
    def close_position(self, chain: str, network: str, connector: str,
                      address: str, token_id: int) -> Dict[str, Any]:
        """Mock close position."""
        data = {
            "txHash": f"0x{''.join(self.rng.choices('0123456789abcdef', k=64))}",
            "gasUsed": str(self.rng.randint(150000, 300000)),
            "amount0": str(self.rng.randint(1000000, 10000000)),
            "amount1": str(self.rng.randint(1000000, 10000000))
        }
        return self._mock_response(data, latency_range=(100, 300))
    
    def add_liquidity(self, chain: str, network: str, connector: str,
                     address: str, token_id: int,
                     amount0: str, amount1: str) -> Dict[str, Any]:
        """Mock add liquidity."""
        data = {
            "txHash": f"0x{''.join(self.rng.choices('0123456789abcdef', k=64))}",
            "gasUsed": str(self.rng.randint(150000, 250000)),
            "liquidity": str(self.rng.randint(100000, 1000000))
        }
        return self._mock_response(data, latency_range=(100, 300))
    
    def remove_liquidity(self, chain: str, network: str, connector: str,
                        address: str, token_id: int,
                        decrease_percent: int) -> Dict[str, Any]:
        """Mock remove liquidity."""
        data = {
            "txHash": f"0x{''.join(self.rng.choices('0123456789abcdef', k=64))}",
            "gasUsed": str(self.rng.randint(150000, 250000)),
            "amount0": str(self.rng.randint(100000, 1000000)),
            "amount1": str(self.rng.randint(100000, 1000000))
        }
        return self._mock_response(data, latency_range=(100, 300))
    
    def collect_fees(self, chain: str, network: str, connector: str,
                    address: str, token_id: int) -> Dict[str, Any]:
        """Mock collect fees."""
        data = {
            "txHash": f"0x{''.join(self.rng.choices('0123456789abcdef', k=64))}",
            "gasUsed": str(self.rng.randint(80000, 150000)),
            "amount0": str(self.rng.randint(1000, 100000)),
            "amount1": str(self.rng.randint(1000, 100000))
        }
        return self._mock_response(data, latency_range=(50, 150))
    
    def health_check(self) -> Dict[str, Any]:
        """Mock health check - always healthy."""
        return self._mock_response({"status": "ok"}, latency_range=(5, 15))
