"""
Dune Cache - Quality-aware caching with envelopes

Wraps SmartCache to add:
- Cache envelopes with quality metadata
- Staleness computation
- Fixed time windows for time-series queries
- get_with_quality() helper
"""

import os
import json
from typing import Dict, Any, Optional, Tuple, Literal
from datetime import datetime, timezone
from pathlib import Path

from .smart_cache import SmartCache
from .dune_registry import QUERY_REGISTRY, QueryMetadata

QualityLevel = Literal["fresh", "stale", "too_old", "missing"]


class CacheEnvelope:
    """Cache envelope with quality metadata"""
    
    def __init__(self, data: Any, ttl_s: int, source: str = "dune_latest"):
        self.ok = True
        self.data = data
        self.fetched_at = datetime.now(timezone.utc).isoformat()
        self.ttl_s = ttl_s
        self.error = None
        self.source = source
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "data": self.data,
            "fetched_at": self.fetched_at,
            "ttl_s": self.ttl_s,
            "error": self.error,
            "source": self.source
        }
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'CacheEnvelope':
        envelope = cls(d.get("data"), d.get("ttl_s", 600), d.get("source", "dune_latest"))
        envelope.ok = d.get("ok", True)
        envelope.fetched_at = d.get("fetched_at")
        envelope.error = d.get("error")
        return envelope
    
    @classmethod
    def error_envelope(cls, error: str, ttl_s: int = 60) -> 'CacheEnvelope':
        """Create an error envelope"""
        envelope = cls(None, ttl_s, "error")
        envelope.ok = False
        envelope.error = error
        return envelope


class QualityMetadata:
    """Quality metadata for cached data"""
    
    def __init__(self, quality: QualityLevel, age_s: Optional[int], asof: Optional[str]):
        self.quality = quality
        self.age_s = age_s
        self.asof = asof
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "quality": self.quality,
            "age_s": self.age_s,
            "asof": self.asof
        }


class DuneCache:
    """Quality-aware Dune cache with envelopes"""
    
    def __init__(self, cache: 'SmartCache' = None, cache_file: str = None):
        """
        Initialize DuneCache.
        
        Args:
            cache: Existing SmartCache instance to share (recommended)
            cache_file: Path to cache file (only used if cache not provided)
        """
        if cache is not None:
            # Share existing SmartCache instance (preferred for scheduler)
            self.cache = cache
        else:
            # Create new SmartCache instance
            if cache_file is None:
                cache_file = os.path.join(
                    os.path.dirname(os.path.dirname(__file__)),
                    "data",
                    "dune_cache.json"
                )
            self.cache = SmartCache(cache_file)
    
    def _build_key(self, query_key: str, **params) -> str:
        """
        Build cache key with standardized format.
        
        For time-series queries, use fixed windows instead of raw timestamps.
        """
        parts = [f"dune:{query_key}"]
        
        # Add parameters in sorted order for consistency
        for k, v in sorted(params.items()):
            if v is not None:
                parts.append(f"{k}:{v}")
        
        return ":".join(parts)
    
    def _compute_quality(
        self,
        envelope: CacheEnvelope,
        ttl_s: int,
        max_age_s: int
    ) -> Tuple[QualityLevel, int]:
        """
        Compute quality level and age.
        
        Returns:
            (quality_level, age_seconds)
        """
        if not envelope or not envelope.ok:
            return "missing", None
        
        # Parse fetched_at
        try:
            fetched_dt = datetime.fromisoformat(envelope.fetched_at.replace('Z', '+00:00'))
            now = datetime.now(timezone.utc)
            age_s = int((now - fetched_dt).total_seconds())
        except Exception:
            return "missing", None
        
        # Determine quality
        if age_s <= ttl_s:
            return "fresh", age_s
        elif age_s <= max_age_s:
            return "stale", age_s
        else:
            return "too_old", age_s
    
    def get_with_quality(
        self,
        query_key: str,
        default: Any = None,
        max_age_s: Optional[int] = None,
        **params
    ) -> Tuple[Any, QualityMetadata]:
        """
        Get cached data with quality metadata.
        
        Args:
            query_key: Query key from registry
            default: Default value if missing/too old
            max_age_s: Override max age from registry
            **params: Query parameters (pool_address, pair, etc.)
            
        Returns:
            (data, quality_metadata)
        """
        # Get query metadata from registry
        if query_key not in QUERY_REGISTRY:
            return default, QualityMetadata("missing", None, None)
        
        query_meta = QUERY_REGISTRY[query_key]
        ttl_s = query_meta.ttl_seconds
        max_age = max_age_s if max_age_s is not None else query_meta.max_age_seconds
        
        # Build cache key
        cache_key = self._build_key(query_key, **params)
        
        # Try to get from cache
        try:
            cached = self.cache.get(cache_key, default=None)
            
            if cached is None:
                return default, QualityMetadata("missing", None, None)
            
            # Parse envelope
            envelope = CacheEnvelope.from_dict(cached)
            
            # Compute quality
            quality, age_s = self._compute_quality(envelope, ttl_s, max_age)
            
            # Return data if not too old
            if quality != "too_old":
                return envelope.data, QualityMetadata(quality, age_s, envelope.fetched_at)
            else:
                return default, QualityMetadata("too_old", age_s, envelope.fetched_at)
                
        except Exception as e:
            print(f"[DuneCache] Error reading cache for {query_key}: {e}")
            return default, QualityMetadata("missing", None, None)
    
    def set_with_envelope(
        self,
        query_key: str,
        data: Any,
        source: str = "dune_execute",
        **params
    ):
        """
        Set cache with envelope.
        
        Args:
            query_key: Query key from registry
            data: Data to cache
            source: Data source (dune_execute, dune_latest, etc.)
            **params: Query parameters
        """
        if query_key not in QUERY_REGISTRY:
            print(f"[DuneCache] Warning: Unknown query key {query_key}")
            return
        
        query_meta = QUERY_REGISTRY[query_key]
        
        # Create envelope
        envelope = CacheEnvelope(data, query_meta.ttl_seconds, source)
        
        # Build cache key
        cache_key = self._build_key(query_key, **params)
        
        # Store in cache
        try:
            self.cache.set(cache_key, envelope.to_dict())
        except Exception as e:
            print(f"[DuneCache] Error writing cache for {query_key}: {e}")
    
    def set_error(self, query_key: str, error: str, **params):
        """Set error envelope in cache"""
        if query_key not in QUERY_REGISTRY:
            return
        
        envelope = CacheEnvelope.error_envelope(error)
        cache_key = self._build_key(query_key, **params)
        
        try:
            self.cache.set(cache_key, envelope.to_dict())
        except Exception as e:
            print(f"[DuneCache] Error writing error envelope: {e}")


# ============================================================================
# Time Window Helpers (for swaps and pool metrics)
# ============================================================================

def get_window_key(window: Literal["1h", "6h", "24h"]) -> Tuple[int, int]:
    """
    Get start_ts and end_ts for a fixed window.
    
    Returns:
        (start_ts, end_ts) in Unix seconds
    """
    now = int(datetime.now(timezone.utc).timestamp())
    
    if window == "1h":
        return now - 3600, now
    elif window == "6h":
        return now - 21600, now
    elif window == "24h":
        return now - 86400, now
    else:
        raise ValueError(f"Unknown window: {window}")


def build_swaps_cache_key(pair: str, pool: str, window: str) -> str:
    """Build cache key for swaps query with fixed window"""
    return f"dune:swaps:pair:{pair}:pool:{pool}:window:{window}"


def build_metrics_cache_key(pool: str, window: str) -> str:
    """Build cache key for pool metrics with fixed window"""
    return f"dune:pool_metrics:pool:{pool}:window:{window}"


if __name__ == "__main__":
    # Test cache envelope
    print("Testing DuneCache...")
    
    cache = DuneCache()
    
    # Test set/get
    cache.set_with_envelope(
        "gas_regime",
        {"median_gwei": 25, "fast_gwei": 35},
        source="test"
    )
    
    data, quality = cache.get_with_quality("gas_regime")
    print(f"Data: {data}")
    print(f"Quality: {quality.to_dict()}")
    
    # Test with pool parameter
    cache.set_with_envelope(
        "pool_health_score",
        {"score": 85, "status": "healthy"},
        source="test",
        pool_address="0xtest"
    )
    
    data, quality = cache.get_with_quality("pool_health_score", pool_address="0xtest")
    print(f"\nPool data: {data}")
    print(f"Pool quality: {quality.to_dict()}")
    
    print("\n✅ DuneCache tests complete")
