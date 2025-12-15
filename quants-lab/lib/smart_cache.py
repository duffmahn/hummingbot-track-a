import os
import json
import time
import logging
from typing import Callable, Any, Dict, Optional
from pathlib import Path

logger = logging.getLogger("SmartCache")

class SmartCache:
    """
    Disk-backed cache with TTL and Stale-While-Revalidate resiliency.
    
    Usage:
        cache = SmartCache("data/cache/market_intel.json")
        data = cache.get("defi_llama_metrics", fetch_func=my_api_call, ttl=3600)
    """
    
    def __init__(self, cache_file: str):
        self.cache_path = Path(cache_file)
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self._memory_cache = {}
        self._load_from_disk()
        
    def _load_from_disk(self):
        if self.cache_path.exists():
            try:
                with open(self.cache_path, 'r') as f:
                    self._memory_cache = json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load cache from {self.cache_path}: {e}")
                self._memory_cache = {}

    def _save_to_disk(self):
        try:
            with open(self.cache_path, 'w') as f:
                json.dump(self._memory_cache, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save cache to {self.cache_path}: {e}")

    def get(self, key: str, fetch_func: Optional[Callable[[], Any]] = None, ttl_seconds: int = 3600, default: Any = None) -> Any:
        """
        Get data from cache or fetch refresh.
        On fetch failure, returns stale data if available.
        """
        now = time.time()
        entry = self._memory_cache.get(key)
        
        # Check if valid cache exists
        if entry:
            age = now - entry.get('ts', 0)
            if age < ttl_seconds:
                # Valid cache hit
                # logger.debug(f"Cache HIT for {key} (age: {age:.0f}s)")
                return entry['data']
            else:
                logger.info(f"Cache STALE for {key} (age: {age:.0f}s > TTL {ttl_seconds}s) – Attempting refresh...")
        else:
            logger.info(f"Cache MISS for {key} – Fetching...")

        # If no fetch function provided, return stale data (best effort) or default
        if fetch_func is None:
            if entry:
                logger.info(f"No fetch_func provided, returning STALE data for {key}")
                return entry['data']
            else:
                return default

        # Fetch new data
        try:
            data = fetch_func()
            
            # Validate data is not empty if strict? (Optional)
            if data is None and entry:
                 logger.warning(f"Fetch returned None for {key}, keeping stale data.")
                 return entry['data']

            # Update cache
            self._memory_cache[key] = {
                'ts': now,
                'data': data
            }
            self._save_to_disk()
            logger.info(f"Cache UPDATED for {key}")
            return data

        except Exception as e:
            logger.warning(f"⚠️ Fetch FAILED for {key}: {e}")
            if entry:
                logger.warning(f"Using STALE data for {key} (age: {now - entry['ts']:.0f}s)")
                return entry['data']
            else:
                # No cache, no fetch -> default
                logger.error(f"No cache and fetch failed for {key}. Returning default.")
                return default if default is not None else {}
    
    def set(self, key: str, value: Any) -> None:
        """
        Direct write to cache (for scheduler use).
        
        Args:
            key: Cache key
            value: Data to cache (will be wrapped with timestamp)
        """
        now = time.time()
        self._memory_cache[key] = {
            'ts': now,
            'data': value
        }
        self._save_to_disk()
        logger.debug(f"Cache SET for {key}")
    
    def set_many(self, items: Dict[str, Any]) -> None:
        """
        Batch write multiple cache entries (more efficient than multiple set() calls).
        
        Args:
            items: Dict of {key: value} pairs to cache
        """
        now = time.time()
        for key, value in items.items():
            self._memory_cache[key] = {
                'ts': now,
                'data': value
            }
        self._save_to_disk()
        logger.debug(f"Cache SET_MANY for {len(items)} keys")

