"""
Dune Analytics API Client for Hummingbot Uniswap V4 Market Intelligence

Provides access to on-chain swap data, pool metrics, and volatility calculations.
"""

import os
import time
import requests
from typing import Dict, List, Optional
from datetime import datetime


class DuneClient:
    """Client for Dune Analytics API - micro on-chain data"""
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv('DUNE_API_KEY')
        if not self.api_key:
            raise ValueError("DUNE_API_KEY not found in environment")
        
        self.base_url = 'https://api.dune.com/api/v1'
        self.headers = {'X-Dune-API-Key': self.api_key}
    
    def execute_query(self, query_id: int, params: Dict = None) -> List[Dict]:
        """
        Execute a saved Dune query and return results.
        
        Args:
            query_id: Dune query ID (from saved query in Dune UI)
            params: Query parameters (e.g., {'pool_address': '0x...', 'hours': 24})
            
        Returns:
            List of result rows as dicts
        """
        # Execute query
        execute_url = f'{self.base_url}/query/{query_id}/execute'
        
        try:
            # First attempt: Send provided parameters
            response = requests.post(
                execute_url,
                headers=self.headers,
                json={'query_parameters': params or {}}
            )
            response.raise_for_status()
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 400 and params:
                print(f"[DuneClient] 400 Bad Request with params. Retrying without params (assuming hardcoded query)...")
                # Retry with empty params
                response = requests.post(
                    execute_url,
                    headers=self.headers,
                    json={'query_parameters': {}}
                )
                response.raise_for_status()
            else:
                raise

        execution_id = response.json()['execution_id']
        
        # Poll for results
        results_url = f'{self.base_url}/execution/{execution_id}/results'
        max_retries = 60
        retry_count = 0
        
        while retry_count < max_retries:
            response = requests.get(results_url, headers=self.headers)
            response.raise_for_status()
            data = response.json()
            
            if data['state'] == 'QUERY_STATE_COMPLETED':
                return data['result']['rows']
            elif data['state'] == 'QUERY_STATE_FAILED':
                raise Exception(f"Query failed: {data.get('error', 'Unknown error')}")
            
            time.sleep(1)
            retry_count += 1
        
        raise TimeoutError(f"Query execution timed out after {max_retries} seconds")
    
    def get_swaps_for_pair(self, pair: str, start_ts: int, end_ts: int, pool_address: str = None) -> List[Dict]:
        """
        Get swap events for a trading pair.
        
        Args:
            pair: Trading pair (e.g., 'WETH-USDC')
            start_ts: Start timestamp (Unix)
            end_ts: End timestamp (Unix)
            pool_address: Pool address (if None, uses default WETH-USDC V3)
            
        Returns:
            List of swap events with timestamps, prices, amounts
        """
        # Default to WETH-USDC V3 mainnet pool
        if pool_address is None:
            pool_address = "0x88e6A0c2dDD26FEEb64F039a2c41296FcB3f5640"
        
        # Query ID from environment or use placeholder
        query_id = int(os.getenv('DUNE_SWAPS_QUERY_ID', '0'))
        
        if query_id == 0:
            # No query configured - return empty but don't spam logs
            return []
        
        try:
            # Send parameters to support parameterized queries
            params = {
                'pool_address': pool_address.lower(),
                'start_time': start_ts,
                'end_time': end_ts,
                'num_surrounding_ticks': 100 # Default for liquidity depth
            }
            return self.execute_query(query_id, params)
        except Exception as e:
            print(f"[DuneClient] Error fetching swaps: {e}")
            return []
    
    def get_pool_metrics(self, pool_address: str, start_ts: int, end_ts: int) -> Dict:
        """
        Get pool metrics (liquidity, volume, fees).
        """
        # Query ID from environment or use placeholder
        query_id = int(os.getenv('DUNE_POOL_METRICS_QUERY_ID', '0'))
        
        if query_id == 0:
            return {}
        
        try:
            # Send parameters to support parameterized queries
            # SQL uses: CAST('{{start_date}}' AS DATE) -> Needs YYYY-MM-DD string
            start_date = datetime.fromtimestamp(start_ts).strftime('%Y-%m-%d')
            end_date = datetime.fromtimestamp(end_ts).strftime('%Y-%m-%d')
            
            params = {
                'pool_address': pool_address.lower(),
                'start_date': start_date,
                'end_date': end_date
            }
            results = self.execute_query(query_id, params)
            return results[0] if results else {}
        except Exception as e:
            print(f"[DuneClient] Error fetching pool metrics: {e}")
            return {}

    def get_liquidity_depth(self, pool_address: str = None) -> List[Dict]:
        """Get Liquidity Depth (Heatmap). Uses DUNE_Q1_LIQ_DEPTH."""
        query_id = int(os.getenv('DUNE_Q1_LIQ_DEPTH') or os.getenv('DUNE_LIQUIDITY_QUERY_ID', '0'))
        if query_id == 0: return []
        params = {'pool_address': pool_address.lower()} if pool_address else {}
        try:
            return self.execute_query(query_id, params)
        except Exception as e:
            print(f"[DuneClient] Error fetching liquidity depth: {e}")
            return []

    def get_gas_regime(self) -> List[Dict]:
        """Get Gas Optimization Signal. Uses DUNE_Q4_GAS (Query #4: 6321836)."""
        query_id = int(os.getenv('DUNE_Q4_GAS', '0'))
        if query_id == 0: return []
        try:
            return self.execute_query(query_id)
        except Exception as e:
            print(f"[DuneClient] Error fetching gas regime: {e}")
            return []

    def get_mev_risk(self, pool_address: str = None) -> List[Dict]:
        """Get MEV Sandwich Attack Protection. Uses DUNE_Q8_MEV (Query #8: 6321856)."""
        query_id = int(os.getenv('DUNE_Q8_MEV', '0'))
        if query_id == 0: return []
        params = {'pool_address': pool_address.lower()} if pool_address else {}
        try:
            return self.execute_query(query_id, params)
        except Exception as e:
            print(f"[DuneClient] Error fetching MEV risk: {e}")
            return []

    def get_whale_sentiment(self, pair: str = None) -> List[Dict]:
        """Get Institutional Wallet Tracking. Uses DUNE_Q9_WHALES_TRADES (Query #9: 6321861)."""
        query_id = int(os.getenv('DUNE_Q9_WHALES_TRADES', '0'))
        if query_id == 0: return []
        try:
            return self.execute_query(query_id)
        except Exception as e:
            print(f"[DuneClient] Error fetching whale sentiment: {e}")
            return []

    def get_cross_dex_migration(self, pool_address: str = None) -> List[Dict]:
        """Get Cross-DEX Liquidity Migration Tracker. Uses DUNE_Q10_MIGRATION (Query #10: 6321866)."""
        query_id = int(os.getenv('DUNE_Q10_MIGRATION', '0'))
        if query_id == 0: return []
        params = {'pool_address': pool_address.lower()} if pool_address else {}
        try:
            return self.execute_query(query_id, params)
        except Exception as e:
            print(f"[DuneClient] Error fetching migration tracker: {e}")
            return []

    def get_fee_tier_optimization(self, pool_address: str = None) -> List[Dict]:
        """Get Fee Tier Optimization Analysis. Uses DUNE_Q11_FEE_OPT (Query #11: 6321869)."""
        query_id = int(os.getenv('DUNE_Q11_FEE_OPT', '0'))
        if query_id == 0: return []
        params = {'pool_address': pool_address.lower()} if pool_address else {}
        try:
            return self.execute_query(query_id, params)
        except Exception as e:
            print(f"[DuneClient] Error fetching fee optimization: {e}")
            return []

    def get_pool_health_score(self, pool_address: str = None) -> List[Dict]:
        """Get Liquidity Pool Health Score. Uses DUNE_Q12_POOL_HEALTH (Query #12: 6321874)."""
        query_id = int(os.getenv('DUNE_Q12_POOL_HEALTH', '0'))
        if query_id == 0: return []
        params = {'pool_address': pool_address.lower()} if pool_address else {}
        try:
            return self.execute_query(query_id, params)
        except Exception as e:
            print(f"[DuneClient] Error fetching pool health score: {e}")
            return []

    def get_yield_farming_opportunities(self) -> List[Dict]:
        """Get Real-Time Yield Farming Opportunity Scanner. Uses DUNE_Q13_YIELD (Query #13: 6321882)."""
        query_id = int(os.getenv('DUNE_Q13_YIELD', '0'))
        if query_id == 0: return []
        try:
            return self.execute_query(query_id)
        except Exception as e:
            print(f"[DuneClient] Error fetching yield opportunities: {e}")
            return []

    def get_rebalance_hint(self, pool_address: str = None) -> List[Dict]:
        """Get Automated Rebalancing Signal Generator. Uses DUNE_Q14_REBALANCE (Query #14: 6321886)."""
        query_id = int(os.getenv('DUNE_Q14_REBALANCE', '0'))
        if query_id == 0: return []
        params = {'pool_address': pool_address.lower()} if pool_address else {}
        try:
            return self.execute_query(query_id, params)
        except Exception as e:
            print(f"[DuneClient] Error fetching rebalance hint: {e}")
            return []
            
    def get_portfolio_dashboard(self, wallet_address: str = None) -> List[Dict]:
        """Get Portfolio Performance Dashboard. Uses DUNE_Q15_DASHBOARD (Query #15: 6321891)."""
        query_id = int(os.getenv('DUNE_Q15_DASHBOARD', '0'))
        if query_id == 0: return []
        params = {'wallet_address': wallet_address.lower()} if wallet_address else {}
        try:
            return self.execute_query(query_id, params)
        except Exception as e:
            print(f"[DuneClient] Error fetching portfolio dashboard: {e}")
            return []
    
    # Adding new methods for the new queries provided:
    
    def get_dynamic_fee_analysis(self, pool_address: str = None) -> List[Dict]:
        """Get Dynamic Fee & Volume Analysis. Uses DUNE_Q2_DYNAMIC_FEE (Query #2: 6321824)."""
        query_id = int(os.getenv('DUNE_Q2_DYNAMIC_FEE', '0'))
        if query_id == 0: return []
        params = {'pool_address': pool_address.lower()} if pool_address else {}
        try:
            return self.execute_query(query_id, params)
        except Exception as e:
            print(f"[DuneClient] Error fetching dynamic fee analysis: {e}")
            return []

    def get_impermanent_loss_tracker(self, pool_address: str = None) -> List[Dict]:
        """Get Impermanent Loss Tracker. Uses DUNE_Q3_IL_TRACKER (Query #3: 6321829)."""
        query_id = int(os.getenv('DUNE_Q3_IL_TRACKER', '0'))
        if query_id == 0: return []
        params = {'pool_address': pool_address.lower()} if pool_address else {}
        try:
            return self.execute_query(query_id, params)
        except Exception as e:
            print(f"[DuneClient] Error fetching IL tracker: {e}")
            return []

    def get_liquidity_competition(self, pool_address: str = None) -> List[Dict]:
        """Get Liquidity Competition Analysis. Uses DUNE_Q5_LIQ_COMP (Query #5: 6321842)."""
        query_id = int(os.getenv('DUNE_Q5_LIQ_COMP', '0'))
        if query_id == 0: return []
        params = {'pool_address': pool_address.lower()} if pool_address else {}
        try:
            return self.execute_query(query_id, params)
        except Exception as e:
            print(f"[DuneClient] Error fetching liquidity competition: {e}")
            return []

    def get_arbitrage_opportunities(self, pool_address: str = None) -> List[Dict]:
        """Get Arbitrage Opportunity Detection. Uses DUNE_Q6_ARBITRAGE (Query #6: 6321846)."""
        query_id = int(os.getenv('DUNE_Q6_ARBITRAGE', '0'))
        if query_id == 0: return []
        params = {'pool_address': pool_address.lower()} if pool_address else {}
        try:
            return self.execute_query(query_id, params)
        except Exception as e:
            print(f"[DuneClient] Error fetching arbitrage opportunities: {e}")
            return []

    def get_hook_analysis(self, hook_address: str = None) -> List[Dict]:
        """Get Uniswap V4 Hook Analysis. Uses DUNE_Q7_HOOK_ANALYSIS (Query #7: 6321849)."""
        query_id = int(os.getenv('DUNE_Q7_HOOK_ANALYSIS', '0'))
        if query_id == 0: return []
        # Hook analysis might take hook_address or just be general. Assuming param support.
        params = {'hook_address': hook_address.lower()} if hook_address else {}
        try:
            return self.execute_query(query_id, params)
        except Exception as e:
            print(f"[DuneClient] Error fetching hook analysis: {e}")
            return []

    # --- Wishlist Queries (Q16-Q19) ---

    def get_toxic_flow_index(self, pool_address: str = None) -> List[Dict]:
        """Get Toxic Flow Index (LVR Estimator). Uses DUNE_Q16_TOXIC_FLOW (Query #16: 6321899)."""
        query_id = int(os.getenv('DUNE_Q16_TOXIC_FLOW', '0'))
        if query_id == 0: return []
        params = {'pool_address': pool_address.lower()} if pool_address else {}
        try:
            return self.execute_query(query_id, params)
        except Exception as e:
            print(f"[DuneClient] Error fetching toxic flow index: {e}")
            return []

    def get_jit_liquidity_monitor(self, pool_address: str = None) -> List[Dict]:
        """Get V4 JIT Liquidity Monitor. Uses DUNE_Q17_JIT_MONITOR (Query #17: 6321924)."""
        query_id = int(os.getenv('DUNE_Q17_JIT_MONITOR', '0'))
        if query_id == 0: return []
        params = {'pool_address': pool_address.lower()} if pool_address else {}
        try:
            return self.execute_query(query_id, params)
        except Exception as e:
            print(f"[DuneClient] Error fetching JIT monitor: {e}")
            return []

    def get_correlation_matrix(self, pool_address: str = None) -> List[Dict]:
        """Get Correlation Matrix V4. Uses DUNE_Q18_CORRELATION (Query #18: 6321931)."""
        query_id = int(os.getenv('DUNE_Q18_CORRELATION', '0'))
        if query_id == 0: return []
        params = {'pool_address': pool_address.lower()} if pool_address else {}
        try:
            return self.execute_query(query_id, params)
        except Exception as e:
            print(f"[DuneClient] Error fetching correlation matrix: {e}")
            return []

    def get_hook_gas_performance(self, hook_address: str = None) -> List[Dict]:
        """Get V4 Hook Gas Efficiency & Performance. Uses DUNE_Q19_HOOK_GAS (Query #19: 6321949)."""
        query_id = int(os.getenv('DUNE_Q19_HOOK_GAS', '0'))
        if query_id == 0: return []
        params = {'hook_address': hook_address.lower()} if hook_address else {}
        try:
            return self.execute_query(query_id, params)
        except Exception as e:
            print(f"[DuneClient] Error fetching hook gas performance: {e}")
            return []

    # --- Hummingbot Quants Lab Specialized Queries (Q20-Q25) ---

    def get_backtesting_data(self, start_date: str = None, end_date: str = None) -> List[Dict]:
        """Get Backtesting Data Pipeline. Uses DUNE_Q20_BACKTEST."""
        query_id = int(os.getenv('DUNE_Q20_BACKTEST', '0'))
        if query_id == 0: return []
        
        params = {}
        if start_date: params['start_date'] = start_date
        if end_date: params['end_date'] = end_date
        
        try:
            return self.execute_query(query_id, params)
        except Exception as e:
            print(f"[DuneClient] Error fetching backtesting data: {e}")
            return []

    def get_order_impact(self) -> List[Dict]:
        """Get Order Book Impact Estimation. Uses DUNE_Q21_ORDER_IMPACT."""
        query_id = int(os.getenv('DUNE_Q21_ORDER_IMPACT', '0'))
        if query_id == 0: return []
        try:
            return self.execute_query(query_id)
        except Exception as e:
            print(f"[DuneClient] Error fetching order impact: {e}")
            return []

    def get_strategy_attribution(self) -> List[Dict]:
        """Get Strategy Performance Attribution. Uses DUNE_Q22_ATTRIBUTION."""
        query_id = int(os.getenv('DUNE_Q22_ATTRIBUTION', '0'))
        if query_id == 0: return []
        try:
            return self.execute_query(query_id)
        except Exception as e:
            print(f"[DuneClient] Error fetching strategy attribution: {e}")
            return []

    def get_execution_quality(self) -> List[Dict]:
        """Get Execution Quality Monitor. Uses DUNE_Q23_EXECUTION."""
        query_id = int(os.getenv('DUNE_Q23_EXECUTION', '0'))
        if query_id == 0: return []
        try:
            return self.execute_query(query_id)
        except Exception as e:
            print(f"[DuneClient] Error fetching execution quality: {e}")
            return []

    def get_portfolio_allocation(self) -> List[Dict]:
        """Get Portfolio Rebalancing Optimizer. Uses DUNE_Q24_ALLOCATION."""
        query_id = int(os.getenv('DUNE_Q24_ALLOCATION', '0'))
        if query_id == 0: return []
        try:
            return self.execute_query(query_id)
        except Exception as e:
            print(f"[DuneClient] Error fetching portfolio allocation: {e}")
            return []

    def get_hummingbot_config(self) -> List[Dict]:
        """Get Dynamic Hummingbot Config. Uses DUNE_Q25_CONFIG_GEN."""
        query_id = int(os.getenv('DUNE_Q25_CONFIG_GEN', '0'))
        if query_id == 0: return []
        try:
            return self.execute_query(query_id)
        except Exception as e:
            print(f"[DuneClient] Error fetching dynamic config: {e}")
            return []

    def get_hook_metrics(self, hook_address: str, start_ts: int, end_ts: int) -> Dict:     
        """
        Get Uniswap V4 hook metrics (when indexed).
        
        Args:
            hook_address: Hook contract address
            start_ts: Start timestamp (Unix)
            end_ts: End timestamp (Unix)
            
        Returns:
            Dict with hook call count, gas usage, volume
        """
        # TODO: Create query in Dune UI when V4 is indexed
        print(f"[DuneClient] get_hook_metrics not yet implemented (V4 not indexed)")
        return {}
    
    def test_connection(self) -> bool:
        """Test if API key is valid and connection works"""
        try:
            # Try to get execution status for a dummy execution
            # This will fail but tells us if auth works
            test_url = f'{self.base_url}/execution/test/status'
            response = requests.get(test_url, headers=self.headers)
            
            # 404 is expected (execution doesn't exist)
            # 401 means auth failed
            if response.status_code == 401:
                print("[DuneClient] ❌ Authentication failed - check API key")
                return False
            
            print("[DuneClient] ✅ Connection successful")
            return True
        except Exception as e:
            print(f"[DuneClient] ❌ Connection test failed: {e}")
            return False


if __name__ == "__main__":
    # Test the client
    print("Testing Dune Analytics client...")
    
    client = DuneClient()
    
    if client.test_connection():
        print("\n✅ Dune client initialized successfully")
        print(f"API Key: {client.api_key[:10]}...")
    else:
        print("\n❌ Dune client initialization failed")


if __name__ == "__main__":
    from datetime import datetime, timedelta
    
    print("Testing Dune Client...")
    print("=" * 60)
    
    client = DuneClient()
    
    # Test with WETH-USDC V3 pool
    pool = "0x88e6A0c2dDD26FEEb64F039a2c41296FcB3f5640"
    
    # Use recent 1-hour window
    end_ts = int(datetime.utcnow().timestamp())
    start_ts = end_ts - 3600
    
    print(f"\nTesting pool: {pool}")
    print(f"Time window: {datetime.fromtimestamp(start_ts)} to {datetime.fromtimestamp(end_ts)}")
    
    # Test pool metrics
    print("\n1. Testing get_pool_metrics...")
    metrics = client.get_pool_metrics(pool, start_ts, end_ts)
    print(f"   Pool metrics: {metrics}")
    
    if metrics:
        print(f"   ✅ avg_liquidity: ${metrics.get('avg_liquidity', 0):,.0f}")
        print(f"   ✅ total_volume0: {metrics.get('total_volume0', 0):.2f}")
        print(f"   ✅ total_volume1: ${metrics.get('total_volume1', 0):,.0f}")
        print(f"   ✅ swap_count: {metrics.get('swap_count', 0)}")
    else:
        print("   ❌ No metrics returned")
    
    # Test swaps
    print("\n2. Testing get_swaps_for_pair...")
    swaps = client.get_swaps_for_pair("WETH-USDC", start_ts, end_ts, pool)
    print(f"   Swaps returned: {len(swaps)}")
    
    if swaps:
        print(f"   ✅ First swap: {swaps[0].get('block_time')}")
        print(f"   ✅ Last swap: {swaps[-1].get('block_time')}")
        first_price = (swaps[0]['sqrt_price_x96'] / 2**96) ** 2
        last_price = (swaps[-1]['sqrt_price_x96'] / 2**96) ** 2
        print(f"   ✅ Price range: ${first_price:,.2f} - ${last_price:,.2f}")
    else:
        print("   ❌ No swaps returned")
    
    # Summary
    print("\n" + "=" * 60)
    if metrics and swaps:
        print("✅ Dune client working - REAL on-chain data!")
    else:
        print("⚠️  Dune queries not configured")
        print("\nTo fix:")
        print("  1. Create queries in Dune UI (see dune_integration_plan.md)")
        print("  2. Set DUNE_SWAPS_QUERY_ID and DUNE_POOL_METRICS_QUERY_ID in .env.sh")
        print("  3. Run: source .env.sh && python3 lib/dune_client.py")
