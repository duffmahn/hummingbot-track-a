#!/usr/bin/env python3
"""
Fetch real data from Dune Analytics for strategy calibration.
"""

import os
import sys
import json
import time
import requests
from pathlib import Path


class DuneClient:
    """Simple Dune Analytics API client."""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.dune.com/api/v1"
        self.headers = {"X-Dune-API-Key": api_key}
    
    def execute_query(self, query_sql: str, max_wait: int = 300) -> dict:
        """Execute a query and wait for results."""
        # Create query
        response = requests.post(
            f"{self.base_url}/query/execute",
            headers=self.headers,
            json={"query_sql": query_sql}
        )
        response.raise_for_status()
        execution_id = response.json()["execution_id"]
        
        print(f"Query submitted, execution_id: {execution_id}")
        
        # Poll for results
        start_time = time.time()
        while time.time() - start_time < max_wait:
            response = requests.get(
                f"{self.base_url}/execution/{execution_id}/results",
                headers=self.headers
            )
            response.raise_for_status()
            data = response.json()
            
            state = data.get("state")
            if state == "QUERY_STATE_COMPLETED":
                print(f"Query completed!")
                return data
            elif state == "QUERY_STATE_FAILED":
                raise Exception(f"Query failed: {data.get('error')}")
            
            print(f"Query running... ({state})")
            time.sleep(5)
        
        raise Exception(f"Query timeout after {max_wait}s")


def main():
    api_key = os.environ.get("DUNE_API_KEY")
    if not api_key:
        print("❌ DUNE_API_KEY not set in environment")
        sys.exit(1)
    
    client = DuneClient(api_key)
    queries_dir = Path(__file__).parent.parent / "dune_queries"
    
    # Load queries
    queries = {
        "pool_fees": queries_dir / "01_pool_hourly_fees.sql",
        "gas_costs": queries_dir / "02_gas_cost_distribution.sql",
        "volatility": queries_dir / "03_realized_vol_jumps.sql"
    }
    
    results = {}
    
    print("=" * 80)
    print("FETCHING REAL DUNE DATA")
    print("=" * 80)
    
    for name, query_file in queries.items():
        print(f"\n📊 Executing {name}...")
        
        with open(query_file) as f:
            query_sql = f.read()
        
        try:
            data = client.execute_query(query_sql)
            rows = data.get("result", {}).get("rows", [])
            
            if rows:
                results[name] = rows[0]  # First row has summary stats
                print(f"✅ Got {len(rows)} rows")
            else:
                print(f"⚠️  No results returned")
                results[name] = {}
        
        except Exception as e:
            print(f"❌ Error: {e}")
            results[name] = {}
    
    # Combine into calibration format
    calibration_data = {
        "fees_median_usd": results["pool_fees"].get("fees_median_usd", 0),
        "fees_p90_usd": results["pool_fees"].get("fees_p90_usd", 0),
        "gas_median_usd": results["gas_costs"].get("gas_median_usd", 0),
        "gas_p75_usd": results["gas_costs"].get("gas_p75_usd", 0),
        "gas_p90_usd": results["gas_costs"].get("gas_p90_usd", 0),
        "vol_median": results["volatility"].get("vol_median", 0),
        "vol_p90": results["volatility"].get("vol_p90", 0),
        "jump_rate": results["volatility"].get("jump_rate", 0),
        "trend_rate": results["volatility"].get("trend_rate", 0),
        "mean_revert_rate": results["volatility"].get("mean_revert_rate", 0)
    }
    
    # Save results
    output_file = queries_dir / "real_dune_results.json"
    with open(output_file, "w") as f:
        json.dump(calibration_data, f, indent=2)
    
    print("\n" + "=" * 80)
    print("RESULTS SUMMARY")
    print("=" * 80)
    for key, value in calibration_data.items():
        print(f"{key}: {value}")
    
    print(f"\n✅ Saved to: {output_file}")
    
    # Also save raw results
    raw_output = queries_dir / "raw_dune_results.json"
    with open(raw_output, "w") as f:
        json.dump(results, f, indent=2)
    print(f"✅ Raw results: {raw_output}")


if __name__ == "__main__":
    main()
