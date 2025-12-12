"""
Market Intelligence Layer for Hummingbot Uniswap V3 CLMM

Combines Dune Analytics (micro) and DefiLlama (macro) data to provide
regime-aware trading signals.

IMPORTANT: Cache-first architecture (Phase 2)
- All Dune queries read from cache ONLY (no blocking network calls)
- Scheduler (Phase 3) refreshes cache in background
- Fixed time windows (1h/6h/24h) for consistent caching
- Quality metadata tracked for episode audit

Falls back to mock data if Dune queries aren't configured.
"""

import os
import math
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timezone

# Try to import real clients, fall back to mock
try:
    from .dune_client import DuneClient
    DUNE_AVAILABLE = True
except ImportError:
    DUNE_AVAILABLE = False

try:
    from .defillama_client import DefiLlamaClient
    DEFILLAMA_AVAILABLE = True
except ImportError:
    DEFILLAMA_AVAILABLE = False

# Check if Dune is configured
DUNE_CONFIGURED = (
    os.getenv('DUNE_SWAPS_QUERY_ID', '0') != '0' and
    os.getenv('DUNE_POOL_METRICS_QUERY_ID', '0') != '0'
)

# Import mock client as fallback
from .mock_data_client import MockDataClient
from .smart_cache import SmartCache
from .dune_cache import DuneCache

CACHE_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "market_cache.json")


class MarketIntelligence:
    """Unified market intelligence using cache-first Dune data + DefiLlama (macro)"""
    
    def __init__(self):
        # Default to Dune for real on-chain Uniswap data
        self.data_source = os.getenv("INTEL_DATA_SOURCE", "dune")
        
        if self.data_source == "dune" and DUNE_CONFIGURED and DUNE_AVAILABLE:
            self.dune = DuneClient()
            print("[MarketIntel] Using Dune Analytics for micro data (CACHE-FIRST)")
        elif self.data_source == "chainlink":
            from chainlink_data_client import ChainlinkDataClient
            self.chainlink = ChainlinkDataClient()
            print("[MarketIntel] Using Chainlink on-chain oracles for micro data (REAL)")
        elif self.data_source == "coingecko":
            from real_market_data_client import RealMarketDataClient
            self.gecko = RealMarketDataClient()
            print("[MarketIntel] Using CoinGecko API for micro data (REAL - no setup required)")
        elif self.data_source == "hbot":
            from hummingbot_data_client import HummingbotAPIClient
            self.hbot = HummingbotAPIClient()
            print("[MarketIntel] Using Hummingbot API for micro data (REAL)")
        else:
            from .mock_data_client import MockDataClient
            self.mock = MockDataClient()
        
        # DefiLlama (disabled due to API hang)
        if False:
            self.llama = DefiLlamaClient()
            print("[MarketIntel] Using DefiLlama for macro data (Cached)")
        else:
            print("[MarketIntel] ⚠️  DefiLlama disabled (API Hang)")
            self.llama = None
            
        self.cache = SmartCache(CACHE_FILE)
        
        # Dune cache wrapper (cache-first reads + quality metadata)
        # NOTE: This does NOT fetch from Dune; scheduler (Phase 3) will populate.
        # IMPORTANT: Share the same SmartCache instance so scheduler writes are visible
        self.dune_cache = DuneCache(cache=self.cache)
        self._last_intel_meta: Dict[str, Any] = {}
    
    def _dune_enabled(self) -> bool:
        """Check if Dune cache is available"""
        return self.data_source == "dune" and hasattr(self, "dune_cache")
    
    def _record_meta(self, key: str, quality_obj: Any) -> None:
        """
        Stores quality metadata for episode intel snapshots.
        Works with QualityMetadata pydantic/dataclass object.
        """
        try:
            meta = {
                "quality": getattr(quality_obj, "quality", None),
                "age_s": getattr(quality_obj, "age_s", None),
                "asof": getattr(quality_obj, "asof", None),
            }
        except Exception:
            meta = {"quality": "unknown", "age_s": None, "asof": None}
        
        self._last_intel_meta[key] = meta
    
    def get_last_intel_snapshot(self) -> Dict[str, Any]:
        """
        Harness can call this after invoking intel methods to embed
        EpisodeMetadata.extra["intel_snapshot"].
        """
        return dict(self._last_intel_meta)
    
    def _window_label_minutes(self, window_minutes: int) -> str:
        """Map minutes to fixed window labels (1h/6h/24h)"""
        if window_minutes <= 60:
            return "1h"
        elif window_minutes <= 360:
            return "6h"
        else:
            return "24h"
    
    def _window_label_hours(self, lookback_hours: int) -> str:
        """Map hours to fixed window labels (1h/6h/24h)"""
        if lookback_hours <= 1:
            return "1h"
        elif lookback_hours <= 6:
            return "6h"
        else:
            return "24h"
    
    def _iso_utc_z(self) -> str:
        """Get current UTC timestamp in ISO format with Z suffix"""
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    
    def get_volatility(self, pair: str, window_minutes: int = 60, return_meta: bool = False) -> float:
        """
        Calculate realized volatility from swap data.
        
        IMPORTANT:
        - If INTEL_DATA_SOURCE=dune, this reads swaps from cache ONLY.
        - Uses fixed windows (1h/6h/24h) to maximize cache hit rate.
        - Records quality metadata for episode audit.
        
        Args:
            pair: Trading pair (e.g., 'WETH-USDC')
            window_minutes: Time window in minutes
            return_meta: If True, return (volatility, quality_metadata)
        
        Returns:
            Annualized volatility (e.g., 0.5 = 50%)
        """
        end_ts = int(datetime.now(timezone.utc).timestamp())
        start_ts = end_ts - (window_minutes * 60)
        window_label = self._window_label_minutes(window_minutes)
        
        swaps: List[Dict] = []
        q = None  # quality metadata
        
        # Non-dune sources remain live (same behavior as before)
        if self.data_source == "chainlink":
            swaps = self.chainlink.get_swaps_for_pair(pair, start_ts, end_ts)
        elif self.data_source == "coingecko":
            swaps = self.gecko.get_swaps_for_pair(pair, start_ts, end_ts)
        elif self.data_source == "hbot":
            swaps = self.hbot.get_swaps_for_pair(pair, start_ts, end_ts)
        elif self._dune_enabled():
            # ✅ Cache-first (no network call)
            swaps, q = self.dune_cache.get_with_quality(
                "swaps_for_pair",
                default=[],
                pair=pair,
                window=window_label,
            )
            self._record_meta(f"swaps_for_pair:{pair}:{window_label}", q)
        else:
            swaps = self.mock.get_swaps_for_pair(pair, start_ts, end_ts)
        
        # Filter by dominant pool_id if present (keep existing behavior)
        if swaps and isinstance(swaps, list) and len(swaps) > 0 and 'pool_id' in swaps[0]:
            from collections import Counter
            pool_counts = Counter(s.get('pool_id') for s in swaps if s.get('pool_id'))
            if pool_counts:
                dominant_pool = pool_counts.most_common(1)[0][0]
                swaps = [s for s in swaps if s.get('pool_id') == dominant_pool]
        
        if not swaps or len(swaps) < 10:
            # Safe default: insufficient data => 0 vol
            if return_meta:
                return 0.0, (q if q is not None else {"quality": "missing"})
            return 0.0
        
        # Calculate log returns from sqrt_price_x96
        log_returns = []
        for i in range(1, len(swaps)):
            try:
                s1 = float(swaps[i - 1].get('sqrt_price_x96', 0))
                s2 = float(swaps[i].get('sqrt_price_x96', 0))
            except Exception:
                continue
            
            if s1 > 0 and s2 > 0:
                log_returns.append(2.0 * math.log(s2 / s1))
        
        if not log_returns:
            if return_meta:
                return 0.0, (q if q is not None else {"quality": "missing"})
            return 0.0
        
        variance = sum(r**2 for r in log_returns) / len(log_returns)
        std_dev = math.sqrt(variance)
        
        periods_per_year = (365 * 24 * 60) / max(1, window_minutes)
        annualized_vol = std_dev * math.sqrt(periods_per_year)
        
        # Record volatility meta too (helps audit)
        if q is not None:
            self._record_meta(f"volatility:{pair}:{window_label}", q)
        
        if return_meta:
            return annualized_vol, q
        return annualized_vol
    
    def get_pool_health(self, pool_address: str, pair: str, lookback_hours: int = 1, return_meta: bool = False) -> Dict:
        """
        Comprehensive pool health check.
        
        IMPORTANT:
        - If INTEL_DATA_SOURCE=dune, reads pool_metrics + swaps from cache ONLY.
        - Uses fixed windows (1h/6h/24h) for caching.
        - Records quality metadata for episode audit.
        
        Args:
            pool_address: Pool contract address
            pair: Trading pair (e.g., 'WETH-USDC')
            lookback_hours: Time window in hours
            return_meta: If True, return (result, meta_bundle)
        
        Returns:
            {
                'volatility': float,
                'volume': float,
                'tvl': float,
                'avg_liquidity': float,
                'tvl_trend': 'up'|'down'|'flat',
                'tradeable': bool,
                'reason': str,
                'market_regime': str
            }
        """
        end_ts = int(datetime.now(timezone.utc).timestamp())
        start_ts = end_ts - (lookback_hours * 3600)
        window_label = self._window_label_hours(lookback_hours)
        
        pool_metrics: Dict[str, Any] = {}
        qm = None  # quality metadata for pool_metrics
        
        # Micro: Get pool metrics from appropriate data source
        if self.data_source == "chainlink":
            pool_metrics = self.chainlink.get_pool_metrics(pool_address, start_ts, end_ts)
        elif self.data_source == "coingecko":
            pool_metrics = self.gecko.get_pool_metrics(pool_address, start_ts, end_ts)
        elif self.data_source == "hbot":
            pool_metrics = self.hbot.get_pool_metrics(pool_address, start_ts, end_ts)
        elif self._dune_enabled():
            # ✅ cache-first metrics
            pool_metrics, qm = self.dune_cache.get_with_quality(
                "pool_metrics",
                default={},
                pool_address=pool_address,
                window=window_label,
            )
            self._record_meta(f"pool_metrics:{pool_address}:{window_label}", qm)
        else:
            pool_metrics = self.mock.get_pool_metrics(pool_address, start_ts, end_ts)
        
        metrics_empty = (
            not pool_metrics or
            (float(pool_metrics.get('avg_liquidity', 0) or 0) == 0 and float(pool_metrics.get('total_volume0', 0) or 0) == 0)
        )
        
        # Fallback: calculate from swaps (cache-first for dune)
        swaps_meta = None
        if metrics_empty and self.data_source != "mock":
            swaps: List[Dict] = []
            
            if self._dune_enabled():
                swaps, swaps_meta = self.dune_cache.get_with_quality(
                    "swaps_for_pair",
                    default=[],
                    pair=pair,
                    pool_address=pool_address,
                    window=window_label,
                )
                self._record_meta(f"swaps_for_pair_pool:{pair}:{pool_address}:{window_label}", swaps_meta)
            elif self.data_source == "hbot":
                swaps = self.hbot.get_swaps_for_pair(pair, start_ts, end_ts)
            elif self.data_source == "chainlink":
                swaps = self.chainlink.get_swaps_for_pair(pair, start_ts, end_ts)
            elif self.data_source == "coingecko":
                swaps = self.gecko.get_swaps_for_pair(pair, start_ts, end_ts)
            
            if swaps:
                # Filter by dominant pool_id if present
                if swaps and 'pool_id' in swaps[0]:
                    from collections import Counter
                    pool_counts = Counter(s.get('pool_id') for s in swaps if s.get('pool_id'))
                    if pool_counts:
                        dominant_pool = pool_counts.most_common(1)[0][0]
                        swaps = [s for s in swaps if s.get('pool_id') == dominant_pool]
                
                total_vol_usd = 0.0
                liquidity_values = []
                
                for s in swaps:
                    amount1_usdc = abs(float(s.get('amount1', 0) or 0))
                    
                    # Normalize if V4-ish fields present
                    if 'pool_id' in s or s.get('version') == 'V4':
                        amount1_usdc = amount1_usdc / 1e6
                    
                    total_vol_usd += amount1_usdc
                    
                    if 'liquidity' in s and s.get('liquidity') is not None:
                        liquidity_values.append(float(s['liquidity']))
                
                avg_liq = sum(liquidity_values) / len(liquidity_values) if liquidity_values else 0.0
                
                last_price = 0.0
                try:
                    last_swap = swaps[0]
                    a0 = abs(float(last_swap.get('amount0', 0) or 0))
                    a1 = abs(float(last_swap.get('amount1', 0) or 0))
                    if 'pool_id' in last_swap or last_swap.get('version') == 'V4':
                        a1 = a1 / 1e6
                        a0 = a0 / 1e18
                    if a0 > 0:
                        last_price = a1 / a0
                except Exception:
                    pass
                
                pool_metrics = {
                    'avg_liquidity': avg_liq,
                    'total_volume0': total_vol_usd,
                    'total_volume1': total_vol_usd,
                    'swap_count': len(swaps),
                    'price': last_price,
                    '_derived_from_swaps': True
                }
                
                if swaps_meta is not None:
                    self._record_meta(f"pool_metrics_fallback:{pool_address}:{window_label}", swaps_meta)
        
        # Volatility (cache-first for dune because get_volatility is now cache-first)
        volatility, vq = self.get_volatility(pair, lookback_hours * 60, return_meta=True)
        if vq is not None:
            self._record_meta(f"volatility:{pair}:{self._window_label_minutes(lookback_hours * 60)}", vq)
        
        # Macro: DefiLlama disabled in current code
        tvl = 0.0
        if self.llama:
            def fetch_llama_metrics():
                return self.llama.get_uniswap_chain_metrics('Ethereum')
            uniswap_metrics = self.cache.get("uniswap_eth_metrics", fetch_llama_metrics, ttl_seconds=3600, default={})
            tvl = float(uniswap_metrics.get('tvl', 0) or 0)
        
        volume = float(pool_metrics.get('total_volume0', 0) or 0)
        avg_liquidity = float(pool_metrics.get('avg_liquidity', 0) or 0)
        
        tvl_trend = 'flat'
        regime = self._classify_regime(volatility, avg_liquidity, volume)
        
        tradeable = True
        reason = 'Market conditions favorable'
        
        if volatility > 2.0:
            tradeable = False
            reason = 'Volatility too high'
        elif avg_liquidity < 1e6 and volume < 100000:
            tradeable = False
            reason = 'Liquidity & Volume too low'
        elif volume < 1e4:
            tradeable = False
            reason = 'Volume too low (dead pool)'
        elif tvl > 0 and tvl < 1e8:
            pass  # warn-only behavior preserved
        
        result = {
            'volatility': volatility,
            'volume': volume,
            'tvl': tvl,
            'avg_liquidity': avg_liquidity,
            'tvl_trend': tvl_trend,
            'tradeable': tradeable,
            'reason': reason,
            'market_regime': regime,
            'timestamp': self._iso_utc_z(),
        }
        
        if return_meta:
            meta_bundle = {
                "pool_metrics": qm,
                "swaps_fallback": swaps_meta,
                "volatility": vq,
            }
            return result, meta_bundle
        
        return result
    
    def _classify_regime(self, volatility: float, liquidity: float, volume: float) -> str:
        """
        Classify market regime based on micro/macro signals.
        
        Returns:
            Regime label (e.g., 'low_vol_high_liquidity')
        """
        vol_high = volatility > 1.0
        liq_high = liquidity > 1e7
        vol_str = 'high_vol' if vol_high else 'low_vol'
        liq_str = 'high_liquidity' if liq_high else 'low_liquidity'
        
        return f'{vol_str}_{liq_str}'
    
    # ========== Simple Cache-First Getters ==========
    
    def get_liquidity_heatmap(self, pool_address: str = None) -> List[Dict]:
        """Get liquidity depth heatmap (cache-first)"""
        if not self._dune_enabled() or not pool_address:
            return []
        rows, q = self.dune_cache.get_with_quality("liquidity_depth", default=[], pool_address=pool_address)
        self._record_meta(f"liquidity_depth:{pool_address}", q)
        return rows if isinstance(rows, list) else []
    
    def get_gas_regime(self) -> Dict:
        """Get gas optimization signal (cache-first)"""
        if not self._dune_enabled():
            return {}
        rows, q = self.dune_cache.get_with_quality("gas_regime", default=[])
        self._record_meta("gas_regime", q)
        return rows[0] if isinstance(rows, list) and rows else {}
    
    def get_mev_risk(self, pool_address: str = None) -> Dict:
        """Get MEV sandwich protection data (cache-first)"""
        if not self._dune_enabled() or not pool_address:
            return {
                "pool_address": pool_address,
                "risk_level": "LOW",
                "reason": "MEV risk model not implemented yet; defaulting to LOW."
            }
        rows, q = self.dune_cache.get_with_quality("mev_risk", default=[{"risk_level":"LOW","reason":"No data"}], pool_address=pool_address)
        self._record_meta(f"mev_risk:{pool_address}", q)
        return rows[0] if isinstance(rows, list) and rows else {"risk_level":"LOW","reason":"No data"}
    
    def get_whale_sentiment(self, pair: str = None) -> Dict:
        """Get institutional wallet tracking (cache-first)"""
        if not self._dune_enabled() or not pair:
            return {}
        rows, q = self.dune_cache.get_with_quality("whale_sentiment", default=[], pair=pair)
        self._record_meta(f"whale_sentiment:{pair}", q)
        return rows[0] if isinstance(rows, list) and rows else {}
    
    def get_pool_health_score(self, pool_address: str = None) -> Dict:
        """Get composite pool health score (cache-first)"""
        if not self._dune_enabled() or not pool_address:
            return {}
        rows, q = self.dune_cache.get_with_quality("pool_health_score", default=[], pool_address=pool_address)
        self._record_meta(f"pool_health_score:{pool_address}", q)
        return rows[0] if isinstance(rows, list) and rows else {}
    
    def get_range_hint(self, pool_address: str = None) -> Dict:
        """Get automated rebalancing signal (cache-first)"""
        if not self._dune_enabled() or not pool_address:
            return {}
        rows, q = self.dune_cache.get_with_quality("rebalance_hint", default=[], pool_address=pool_address)
        self._record_meta(f"rebalance_hint:{pool_address}", q)
        return rows[0] if isinstance(rows, list) and rows else {}
    
    def get_dynamic_config(self) -> Dict:
        """Get Dune-optimized Hummingbot configuration (cache-first)"""
        if not self._dune_enabled():
            return {}
        rows, q = self.dune_cache.get_with_quality("hummingbot_config", default=[])
        self._record_meta("hummingbot_config", q)
        return rows[0] if isinstance(rows, list) and rows else {}
    
    def get_market_regime(self, pair: str, pool_address: str) -> Dict:
        """
        Get current market regime with full context.
        
        Returns:
            Dict with regime classification and supporting metrics
        """
        health = self.get_pool_health(pool_address, pair, 1)
        
        return {
            'regime': health['market_regime'],
            'volatility': health['volatility'],
            'liquidity': health['avg_liquidity'],
            'volume': health['volume'],
            'tvl': health['tvl'],
            'timestamp': datetime.now().isoformat()
        }
    
    def trigger_refresh(self, reason: str, pool_address: str = None, pair: str = None):
        """
        Trigger immediate refresh of P0/P1 queries (event-driven).
        
        This writes to the scheduler's trigger file for async processing.
        
        Args:
            reason: Trigger reason (e.g., "out_of_range", "volatility_spike", "gas_drop")
            pool_address: Pool to refresh (if applicable)
            pair: Pair to refresh (if applicable)
        
        Example:
            intel.trigger_refresh("out_of_range", pool_address="0x88e6...")
        """
        try:
            from .dune_scheduler import DuneScheduler
            scheduler = DuneScheduler()
            scheduler.trigger_refresh(reason, pool_address=pool_address, pair=pair)
        except Exception as e:
            logger.warning(f"Failed to trigger refresh: {e}")


if __name__ == "__main__":
    # Test the market intelligence layer
    print("Testing Market Intelligence Layer...")
    print("=" * 60)
    
    intel = MarketIntelligence()
    
    print("\n✅ Market Intelligence layer created successfully (cache-first)")
    print("\nCache-first architecture:")
    print("- All Dune queries read from cache ONLY")
    print("- Scheduler (Phase 3) will refresh cache in background")
    print("- Fixed time windows (1h/6h/24h) for consistent caching")
