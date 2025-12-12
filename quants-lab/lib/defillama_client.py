"""
DefiLlama API Client for Hummingbot Uniswap V4 Market Intelligence

Provides access to protocol TVL, DEX volumes, and cross-venue analytics.
"""

import os
import requests
from typing import Dict, Optional


class DefiLlamaClient:
    """Client for DefiLlama API - macro DeFi analytics"""
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv('DEFILLAMA_API_KEY', '')
        self.base_url = 'https://api.llama.fi'
        self.headers = {}
        if self.api_key:
            self.headers['Authorization'] = f'Bearer {self.api_key}'
    
    def get_protocol(self, protocol_slug: str) -> Dict:
        """
        Get protocol-level metrics.
        
        Args:
            protocol_slug: Protocol identifier (e.g., 'uniswap')
            
        Returns:
            Dict with TVL, chain breakdown, etc.
        """
        url = f'{self.base_url}/protocol/{protocol_slug}'
        try:
             response = requests.get(url, headers=self.headers, timeout=2)
             response.raise_for_status()
             return response.json()
        except Exception as e:
             # Fail fast
             print(f"[DefiLlama] Warning: Failed to fetch protocol {protocol_slug}: {e}")
             return {}
    
    def get_chain_tvl(self, chain: str) -> Dict:
        """
        Get TVL for a specific chain.
        
        Args:
            chain: Chain name (e.g., 'ethereum', 'arbitrum')
            
        Returns:
            Dict with current TVL and historical data
        """
        url = f'{self.base_url}/v2/historicalChainTvl/{chain}'
        try:
             response = requests.get(url, headers=self.headers, timeout=2)
             response.raise_for_status()
             return response.json()
        except Exception as e:
             print(f"[DefiLlama] Warning: Failed to fetch chain TVL {chain}: {e}")
             return []
    
    def get_dex_volumes(self, protocol: str = None) -> Dict:
        """
        Get DEX volumes across protocols.
        
        Args:
            protocol: Optional protocol filter
            
        Returns:
            Dict with volume data
        """
        url = f'{self.base_url}/overview/dexs'
        if protocol:
            url += f'/{protocol}'
        try:
            response = requests.get(url, headers=self.headers, timeout=2)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"[DefiLlama] Warning: Failed to fetch DEX volumes: {e}")
            return {}
    
    def get_uniswap_chain_metrics(self, chain: str = "ethereum") -> Dict:
        """
        Get Uniswap metrics for a specific chain.
        
        Args:
            chain: Chain name
            
        Returns:
            Dict with TVL, volume, fees for Uniswap on that chain
        """
        try:
            protocol_data = self.get_protocol('uniswap')
            
            # Extract total TVL (handle both scalar and list formats)
            # Helper to extract numeric value from various nested structures
            def extract_val(val):
                if isinstance(val, (int, float)): return float(val)
                if isinstance(val, list) and val:
                    # Recursively try last element if list
                    return extract_val(val[-1])
                if isinstance(val, dict):
                    # Try common keys
                    for k in ['totalLiquidityUSD', 'tvl', 'liquidity']:
                        if k in val: return extract_val(val[k])
                    # If dict but no known key, try values? No, safer to return 0
                    return 0.0
                return 0.0

            total_tvl_raw = protocol_data.get('tvl', 0)
            total_tvl = extract_val(total_tvl_raw)
            
            # Extract chain-specific TVL
            chain_tvls = protocol_data.get('chainTvls', {})
            chain_tvl_raw = chain_tvls.get(chain, 0)
            chain_tvl = extract_val(chain_tvl_raw)
            
            # Calculate share safely
            chain_share = (chain_tvl / total_tvl) if total_tvl > 0 else 0.0
            
            return {
                'chain': chain,
                'tvl': chain_tvl,
                'total_tvl': total_tvl,
                'chain_share': chain_share
            }
        except Exception as e:
            print(f"[DefiLlamaClient] Error getting Uniswap metrics: {e}")
            # Return zeros instead of failing
            return {
                'chain': chain,
                'tvl': 0.0,
                'total_tvl': 0.0,
                'chain_share': 0.0
            }
    
    def get_pair_competitiveness(self, token_pair: str) -> Dict:
        """
        Compare volumes/TVL for a pair across major DEXs.
        
        Args:
            token_pair: Token pair (e.g., 'WETH-USDC')
            
        Returns:
            Dict with cross-DEX comparison
        """
        try:
            # TODO: adapt to actual DefiLlama response schema
            dex_volumes = self.get_dex_volumes()
            
            # Extract relevant DEXs
            uniswap_vol = next((d for d in dex_volumes.get('protocols', []) 
                               if d['name'] == 'Uniswap'), {}).get('total24h', 0)
            
            return {
                'pair': token_pair,
                'uniswap_volume_24h': uniswap_vol,
                # Add other DEXs as needed
            }
        except Exception as e:
            print(f"[DefiLlamaClient] Error getting pair competitiveness: {e}")
            return {
                'pair': token_pair,
                'uniswap_volume_24h': 0
            }
    
    def test_connection(self) -> bool:
        """Test if connection works"""
        try:
            # Try to get Ethereum TVL
            data = self.get_chain_tvl('Ethereum')
            
            if data and len(data) > 0:
                print("[DefiLlamaClient] ✅ Connection successful")
                latest_tvl = data[-1]['tvl'] if isinstance(data, list) else data.get('tvl', 0)
                print(f"  Latest Ethereum TVL: ${latest_tvl/1e9:.2f}B")
                return True
            else:
                print("[DefiLlamaClient] ⚠️  Connection works but no data returned")
                return True
        except Exception as e:
            print(f"[DefiLlamaClient] ❌ Connection test failed: {e}")
            return False


if __name__ == "__main__":
    # Test the client
    print("Testing DefiLlama client...")
    
    client = DefiLlamaClient()
    
    if client.test_connection():
        print("\n✅ DefiLlama client initialized successfully")
        
        # Test Uniswap metrics
        print("\nTesting Uniswap metrics...")
        metrics = client.get_uniswap_chain_metrics('Ethereum')
        print(f"  Uniswap Ethereum TVL: ${metrics['tvl']/1e9:.2f}B")
        print(f"  Chain share: {metrics['chain_share']:.1%}")
    else:
        print("\n❌ DefiLlama client initialization failed")
