"""
Dune Scheduler - Non-Blocking Background Cache Refresh

Implements stale-while-revalidate semantics:
- Episodes read from cache (never block)
- Scheduler refreshes stale entries in background
- Bounded concurrency (2-4 workers)
- Active pool scoping (top N pools only)
- Event-driven triggers for P0/P1 queries

Usage:
    scheduler = DuneScheduler()
    scheduler.run_forever()  # Tick every 60s
"""

import os
import time
import json
from typing import Dict, List, Optional, Set
from datetime import datetime, timezone
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging

from .dune_client import DuneClient
from .dune_cache import DuneCache, get_window_key
from .dune_registry import QUERY_REGISTRY, get_enabled_queries, get_pool_scoped_queries

logger = logging.getLogger("DuneScheduler")


class DuneScheduler:
    """Non-blocking Dune cache refresh scheduler"""
    
    def __init__(
        self,
        max_workers: int = None,
        active_pool_cap: int = None,
        tick_interval_s: int = 60
    ):
        """
        Initialize scheduler.
        
        Args:
            max_workers: Concurrent workers (default: 3)
            active_pool_cap: Max pools to track (default: 3)
            tick_interval_s: Seconds between refresh ticks (default: 60)
        """
        self.max_workers = max_workers or int(os.getenv("DUNE_SCHEDULER_WORKERS", "3"))
        self.active_pool_cap = active_pool_cap or int(os.getenv("HB_ACTIVE_POOL_CAP", "3"))
        self.tick_interval_s = tick_interval_s
        
        # Initialize clients
        try:
            self.dune_client = DuneClient()
            self.dune_cache = DuneCache()
            logger.info(f"[DuneScheduler] Initialized (workers={self.max_workers}, pool_cap={self.active_pool_cap})")
        except Exception as e:
            logger.warning(f"[DuneScheduler] Failed to initialize Dune client: {e}")
            self.dune_client = None
            self.dune_cache = None
        
        # Active pools tracking
        self.active_pools: Set[str] = set()
        self._load_active_pools()
        
        # Trigger queue (for event-driven refreshes)
        self.trigger_file = Path(__file__).parent.parent / "data" / "dune_triggers.jsonl"
        self.trigger_file.parent.mkdir(parents=True, exist_ok=True)
    
    def _load_active_pools(self):
        """Load active pools from config or recent runs"""
        # Option 1: From environment
        pools_env = os.getenv("HB_ACTIVE_POOLS", "")
        if pools_env:
            self.active_pools = set(p.strip() for p in pools_env.split(",") if p.strip())
        
        # Option 2: From recent run data (find pools in recent episodes)
        if not self.active_pools:
            try:
                data_dir = Path(__file__).parent.parent / "data" / "runs"
                if data_dir.exists():
                    # Find most recent run
                    runs = sorted(data_dir.glob("run_*"), key=lambda p: p.stat().st_mtime, reverse=True)
                    if runs:
                        latest_run = runs[0]
                        episodes = list((latest_run / "episodes").glob("ep_*"))
                        
                        for ep_dir in episodes[:self.active_pool_cap]:
                            proposal_file = ep_dir / "proposal.json"
                            if proposal_file.exists():
                                try:
                                    with open(proposal_file) as f:
                                        proposal = json.load(f)
                                        pool = proposal.get("pool_address")
                                        if pool:
                                            self.active_pools.add(pool)
                                except Exception:
                                    pass
            except Exception as e:
                logger.debug(f"Could not load active pools from runs: {e}")
        
        # Default pool if none found
        if not self.active_pools:
            default_pool = "0x88e6A0c2dDD26FEEb64F039a2c41296FcB3f5640"  # WETH-USDC V3
            self.active_pools.add(default_pool)
        
        logger.info(f"[DuneScheduler] Active pools: {list(self.active_pools)[:self.active_pool_cap]}")
    
    def _should_refresh(self, query_key: str, **params) -> bool:
        """
        Check if query should be refreshed based on cache quality.
        
        Returns:
            True if stale or missing, False if fresh
        """
        if not self.dune_cache:
            return False
        
        data, quality = self.dune_cache.get_with_quality(query_key, **params)
        
        # Refresh if stale, too_old, or missing
        return quality.quality in ["stale", "too_old", "missing"]
    
    def _fetch_and_cache(self, query_key: str, **params) -> bool:
        """
        Fetch data from Dune and write to cache.
        
        Returns:
            True if successful, False otherwise
        """
        if not self.dune_client or not self.dune_cache:
            return False
        
        query_meta = QUERY_REGISTRY.get(query_key)
        if not query_meta:
            logger.warning(f"Unknown query key: {query_key}")
            return False
        
        try:
            # Get method from DuneClient
            method = getattr(self.dune_client, query_meta.method, None)
            if not method:
                logger.warning(f"Method {query_meta.method} not found on DuneClient")
                return False
            
            # Call method with params
            logger.debug(f"Fetching {query_key} with params {params}")
            data = method(**params)
            
            # Write to cache with envelope
            self.dune_cache.set_with_envelope(query_key, data, source="dune_execute", **params)
            
            logger.info(f"✅ Refreshed {query_key} {params}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to refresh {query_key} {params}: {e}")
            self.dune_cache.set_error(query_key, str(e), **params)
            return False
    
    def _refresh_global_queries(self) -> List[str]:
        """Refresh global-scope queries (no pool parameter)"""
        jobs = []
        
        for query_meta in get_enabled_queries():
            if query_meta.scope == "global":
                if self._should_refresh(query_meta.key):
                    jobs.append((query_meta.key, {}))
        
        return jobs
    
    def _refresh_pool_queries(self) -> List[str]:
        """Refresh pool-scoped queries for active pools"""
        jobs = []
        
        # Limit to top N active pools
        active_pools_list = list(self.active_pools)[:self.active_pool_cap]
        
        for query_meta in get_pool_scoped_queries():
            if not query_meta.enabled_default:
                continue
            
            for pool_address in active_pools_list:
                if self._should_refresh(query_meta.key, pool_address=pool_address):
                    jobs.append((query_meta.key, {"pool_address": pool_address}))
        
        return jobs
    
    def _refresh_windowed_queries(self) -> List[str]:
        """Refresh time-series queries with fixed windows"""
        jobs = []
        
        # For now, use default pair and active pools
        default_pair = "WETH-USDC"
        active_pools_list = list(self.active_pools)[:self.active_pool_cap]
        
        for window in ["1h", "6h", "24h"]:
            # swaps_for_pair (pair + window)
            if self._should_refresh("swaps_for_pair", pair=default_pair, window=window):
                jobs.append(("swaps_for_pair", {"pair": default_pair, "window": window}))
            
            # swaps_for_pair (pair + pool + window)
            for pool in active_pools_list:
                if self._should_refresh("swaps_for_pair", pair=default_pair, pool_address=pool, window=window):
                    jobs.append(("swaps_for_pair", {"pair": default_pair, "pool_address": pool, "window": window}))
            
            # pool_metrics (pool + window)
            for pool in active_pools_list:
                if self._should_refresh("pool_metrics", pool_address=pool, window=window):
                    jobs.append(("pool_metrics", {"pool_address": pool, "window": window}))
        
        return jobs
    
    def _process_triggers(self) -> List[str]:
        """Process event-driven triggers from trigger file"""
        jobs = []
        
        if not self.trigger_file.exists():
            return jobs
        
        try:
            # Read and clear trigger file
            with open(self.trigger_file, 'r') as f:
                lines = f.readlines()
            
            # Clear file
            self.trigger_file.write_text("")
            
            # Process triggers
            for line in lines:
                try:
                    trigger = json.loads(line.strip())
                    query_key = trigger.get("query_key")
                    params = trigger.get("params", {})
                    priority = trigger.get("priority", "P1")
                    
                    # Only process P0/P1 triggers
                    if priority in ["P0", "P1"] and query_key:
                        jobs.append((query_key, params))
                        logger.info(f"📌 Trigger: {query_key} {params} (priority={priority})")
                except Exception as e:
                    logger.warning(f"Invalid trigger line: {e}")
        
        except Exception as e:
            logger.error(f"Failed to process triggers: {e}")
        
        return jobs
    
    def tick(self) -> Dict[str, int]:
        """
        Single refresh tick.
        
        Returns:
            Stats dict with success/failure counts
        """
        if not self.dune_client or not self.dune_cache:
            logger.warning("[DuneScheduler] Dune client not available, skipping tick")
            return {"skipped": 1}
        
        logger.info("[DuneScheduler] ⏰ Tick starting...")
        
        # Collect refresh jobs
        jobs = []
        jobs.extend(self._refresh_global_queries())
        jobs.extend(self._refresh_pool_queries())
        jobs.extend(self._refresh_windowed_queries())
        jobs.extend(self._process_triggers())
        
        if not jobs:
            logger.info("[DuneScheduler] No stale entries, skipping")
            return {"skipped": 1}
        
        logger.info(f"[DuneScheduler] Refreshing {len(jobs)} queries...")
        
        # Execute with bounded concurrency
        stats = {"success": 0, "failed": 0}
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(self._fetch_and_cache, query_key, **params): (query_key, params)
                for query_key, params in jobs
            }
            
            for future in as_completed(futures):
                query_key, params = futures[future]
                try:
                    success = future.result()
                    if success:
                        stats["success"] += 1
                    else:
                        stats["failed"] += 1
                except Exception as e:
                    logger.error(f"Job failed: {query_key} {params}: {e}")
                    stats["failed"] += 1
        
        logger.info(f"[DuneScheduler] ✅ Tick complete: {stats}")
        return stats
    
    def run_forever(self):
        """Run scheduler loop forever (blocking)"""
        logger.info(f"[DuneScheduler] Starting scheduler loop (tick every {self.tick_interval_s}s)")
        
        while True:
            try:
                self.tick()
            except KeyboardInterrupt:
                logger.info("[DuneScheduler] Shutting down...")
                break
            except Exception as e:
                logger.error(f"[DuneScheduler] Tick error: {e}")
            
            time.sleep(self.tick_interval_s)
    
    def trigger_refresh(self, reason: str, query_keys: List[str] = None, pool_address: str = None, pair: str = None):
        """
        Trigger immediate refresh of specific queries (event-driven).
        
        Args:
            reason: Reason for trigger (e.g., "out_of_range", "volatility_spike")
            query_keys: Specific query keys to refresh (default: all P0/P1)
            pool_address: Pool to refresh (if pool-scoped)
            pair: Pair to refresh (if pair-scoped)
        """
        if not query_keys:
            # Default to P0/P1 queries
            query_keys = [q.key for q in get_enabled_queries() if q.priority in ["P0", "P1"]]
        
        # Write triggers to file
        try:
            with open(self.trigger_file, 'a') as f:
                for query_key in query_keys:
                    query_meta = QUERY_REGISTRY.get(query_key)
                    if not query_meta:
                        continue
                    
                    params = {}
                    if query_meta.scope == "pool" and pool_address:
                        params["pool_address"] = pool_address
                    elif query_meta.scope == "pair" and pair:
                        params["pair"] = pair
                    
                    trigger = {
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "reason": reason,
                        "query_key": query_key,
                        "params": params,
                        "priority": query_meta.priority
                    }
                    f.write(json.dumps(trigger) + "\n")
            
            logger.info(f"📌 Triggered refresh: {reason} ({len(query_keys)} queries)")
        except Exception as e:
            logger.error(f"Failed to write triggers: {e}")


if __name__ == "__main__":
    # Test scheduler
    logging.basicConfig(level=logging.INFO)
    
    scheduler = DuneScheduler()
    
    print("Running single tick...")
    stats = scheduler.tick()
    print(f"Stats: {stats}")
