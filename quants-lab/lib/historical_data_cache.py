"""
Historical Data Cache for CLMM Training

Provides local caching of historical tick data from Dune Analytics
to enable realistic episode replay without repeated API calls.
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timezone
import time


class HistoricalDataCache:
    """
    Cache layer for historical tick data and LP performance.
    
    Features:
    - Local file-based caching to avoid repeated Dune API calls
    - Time-window queries (e.g., "6 hours starting at timestamp X")
    - Automatic cache invalidation and refresh
    - Fallback to mock mode if cache miss and no API key
    """
    
    def __init__(self, cache_dir: Path, dune_client=None):
        """
        Initialize historical data cache.
        
        Args:
            cache_dir: Directory to store cached data
            dune_client: Optional DuneClient instance for fetching data
        """
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.dune_client = dune_client
        
        # Cache metadata
        self.metadata_file = self.cache_dir / "cache_metadata.json"
        self.metadata = self._load_metadata()
    
    def _load_metadata(self) -> Dict:
        """Load cache metadata from disk."""
        if self.metadata_file.exists():
            try:
                with open(self.metadata_file) as f:
                    return json.load(f)
            except Exception as e:
                print(f"[HistoricalCache] Error loading metadata: {e}")
        return {"last_refresh": None, "cached_windows": {}}
    
    def _save_metadata(self):
        """Save cache metadata to disk."""
        try:
            with open(self.metadata_file, 'w') as f:
                json.dump(self.metadata, f, indent=2)
        except Exception as e:
            print(f"[HistoricalCache] Error saving metadata: {e}")
    
    def _cache_key(self, pool_address: str, start_ts: int, duration_s: int) -> str:
        """Generate cache key for a time window."""
        return f"{pool_address}_{start_ts}_{duration_s}"
    
    def _cache_file(self, cache_key: str) -> Path:
        """Get cache file path for a given key."""
        return self.cache_dir / f"{cache_key}.json"
    
    def get_tick_window(
        self,
        pool_address: str,
        start_ts: int,
        duration_seconds: int,
        granularity: str = "hour"
    ) -> List[Dict]:
        """
        Get tick data for a specific time window.
        
        Args:
            pool_address: Pool contract address
            start_ts: Start timestamp (Unix)
            duration_seconds: Duration of window in seconds
            granularity: 'minute' or 'hour' (default: 'hour')
        
        Returns:
            List of tick snapshots with fields:
            - timestamp: Unix timestamp
            - tick: Current tick
            - price: WETH/USDC price
            - volume_usd: Volume in this period
            - liquidity: Pool liquidity
            - swap_count: Number of swaps
        """
        cache_key = self._cache_key(pool_address, start_ts, duration_seconds)
        cache_file = self._cache_file(cache_key)
        
        # Check cache first
        if cache_file.exists():
            try:
                with open(cache_file) as f:
                    data = json.load(f)
                print(f"[HistoricalCache] ✅ Cache hit: {cache_key}")
                return data.get("tick_data", [])
            except Exception as e:
                print(f"[HistoricalCache] ⚠️  Cache read error: {e}")
        
        # Cache miss - fetch from Dune if available
        if self.dune_client is None:
            print(f"[HistoricalCache] ❌ Cache miss and no Dune client - returning empty")
            return []
        
        print(f"[HistoricalCache] 📡 Fetching from Dune: {cache_key}")
        
        try:
            # Get query ID from environment
            query_id = int(os.getenv('DUNE_HISTORICAL_TICKS_QUERY_ID', '0'))
            if query_id == 0:
                print(f"[HistoricalCache] ❌ DUNE_HISTORICAL_TICKS_QUERY_ID not set")
                return []
            
            # Execute query with parameters
            end_ts = start_ts + duration_seconds
            params = {
                'start_timestamp': start_ts,
                'end_timestamp': end_ts
            }
            
            tick_data = self.dune_client.execute_query(query_id, params)
            
            # Cache the result
            cache_data = {
                "pool_address": pool_address,
                "start_ts": start_ts,
                "duration_seconds": duration_seconds,
                "granularity": granularity,
                "fetched_at": int(time.time()),
                "tick_data": tick_data
            }
            
            with open(cache_file, 'w') as f:
                json.dump(cache_data, f, indent=2)
            
            # Update metadata
            self.metadata["cached_windows"][cache_key] = {
                "start_ts": start_ts,
                "duration_seconds": duration_seconds,
                "fetched_at": int(time.time())
            }
            self._save_metadata()
            
            print(f"[HistoricalCache] ✅ Cached {len(tick_data)} tick snapshots")
            return tick_data
            
        except Exception as e:
            print(f"[HistoricalCache] ❌ Error fetching from Dune: {e}")
            return []
    
    def get_lp_baseline(
        self,
        pool_address: str,
        start_ts: int,
        duration_seconds: int,
        width_pts: int
    ) -> Optional[Dict]:
        """
        Get real LP performance for baseline comparison.
        
        Args:
            pool_address: Pool contract address
            start_ts: Start timestamp
            duration_seconds: Duration of window
            width_pts: Position width in ticks (for filtering similar positions)
        
        Returns:
            Dict with real LP performance metrics:
            - fees_collected_usd: Total fees earned
            - gas_cost_usd: Estimated gas costs
            - net_pnl_usd: Net PnL (fees - gas)
            - duration_seconds: Actual position duration
            - collect_count: Number of fee collections
        """
        cache_key = f"lp_baseline_{self._cache_key(pool_address, start_ts, duration_seconds)}_{width_pts}"
        cache_file = self._cache_file(cache_key)
        
        # Check cache
        if cache_file.exists():
            try:
                with open(cache_file) as f:
                    data = json.load(f)
                print(f"[HistoricalCache] ✅ LP baseline cache hit")
                return data.get("lp_performance")
            except Exception as e:
                print(f"[HistoricalCache] ⚠️  LP baseline cache read error: {e}")
        
        # Cache miss - fetch from Dune
        if self.dune_client is None:
            print(f"[HistoricalCache] ❌ No Dune client for LP baseline")
            return None
        
        print(f"[HistoricalCache] 📡 Fetching LP baseline from Dune")
        
        try:
            query_id = int(os.getenv('DUNE_LP_PERFORMANCE_QUERY_ID', '0'))
            if query_id == 0:
                print(f"[HistoricalCache] ❌ DUNE_LP_PERFORMANCE_QUERY_ID not set")
                return None
            
            end_ts = start_ts + duration_seconds
            params = {
                'start_timestamp': start_ts,
                'end_timestamp': end_ts,
                'min_width_ticks': int(width_pts * 0.8),  # 20% tolerance
                'max_width_ticks': int(width_pts * 1.2)
            }
            
            lp_positions = self.dune_client.execute_query(query_id, params)
            
            if not lp_positions:
                print(f"[HistoricalCache] ⚠️  No LP positions found for width ~{width_pts}")
                return None
            
            # Use the top-performing position as baseline
            lp_performance = lp_positions[0]
            
            # Cache the result
            cache_data = {
                "pool_address": pool_address,
                "start_ts": start_ts,
                "duration_seconds": duration_seconds,
                "width_pts": width_pts,
                "fetched_at": int(time.time()),
                "lp_performance": lp_performance,
                "num_positions_found": len(lp_positions)
            }
            
            with open(cache_file, 'w') as f:
                json.dump(cache_data, f, indent=2)
            
            print(f"[HistoricalCache] ✅ Cached LP baseline (found {len(lp_positions)} positions)")
            return lp_performance
            
        except Exception as e:
            print(f"[HistoricalCache] ❌ Error fetching LP baseline: {e}")
            return None
    
    def clear_cache(self, older_than_days: int = None):
        """
        Clear cached data.
        
        Args:
            older_than_days: If specified, only clear cache older than this many days
        """
        if older_than_days is None:
            # Clear all
            for cache_file in self.cache_dir.glob("*.json"):
                if cache_file.name != "cache_metadata.json":
                    cache_file.unlink()
            self.metadata = {"last_refresh": None, "cached_windows": {}}
            self._save_metadata()
            print(f"[HistoricalCache] 🗑️  Cleared all cache")
        else:
            # Clear old cache
            cutoff_ts = int(time.time()) - (older_than_days * 86400)
            cleared = 0
            
            for key, meta in list(self.metadata["cached_windows"].items()):
                if meta.get("fetched_at", 0) < cutoff_ts:
                    cache_file = self._cache_file(key)
                    if cache_file.exists():
                        cache_file.unlink()
                    del self.metadata["cached_windows"][key]
                    cleared += 1
            
            self._save_metadata()
            print(f"[HistoricalCache] 🗑️  Cleared {cleared} old cache entries")
    
    def get_cache_stats(self) -> Dict:
        """Get cache statistics."""
        total_windows = len(self.metadata.get("cached_windows", {}))
        total_size_mb = sum(
            f.stat().st_size for f in self.cache_dir.glob("*.json")
        ) / (1024 * 1024)
        
        return {
            "total_windows_cached": total_windows,
            "total_size_mb": round(total_size_mb, 2),
            "cache_dir": str(self.cache_dir),
            "last_refresh": self.metadata.get("last_refresh")
        }


if __name__ == "__main__":
    # Test the cache
    print("Testing Historical Data Cache...")
    print("=" * 60)
    
    cache_dir = Path("scratch/data/historical_cache")
    cache = HistoricalDataCache(cache_dir)
    
    stats = cache.get_cache_stats()
    print(f"\n📊 Cache Stats:")
    print(f"  Windows cached: {stats['total_windows_cached']}")
    print(f"  Total size: {stats['total_size_mb']} MB")
    print(f"  Cache dir: {stats['cache_dir']}")
    
    print("\n✅ Historical data cache initialized")
    print("\nTo use with Dune:")
    print("  1. Set DUNE_API_KEY in environment")
    print("  2. Set DUNE_HISTORICAL_TICKS_QUERY_ID")
    print("  3. Set DUNE_LP_PERFORMANCE_QUERY_ID")
    print("  4. Create DuneClient and pass to HistoricalDataCache")
