"""
Dune Query Registry - Single Source of Truth for all Dune queries

Defines metadata for all 25 Dune query capabilities including:
- Method name mapping
- Scope (global/pool/pair/wallet/hook)
- TTL and max age
- Priority (P0-P3)
- Default enabled status

P0 = Gating (required for decisions)
P1 = Shaping (improves decisions)
P2 = Risk (protects capital)
P3 = Offline (analytics/backtesting)
"""

from typing import Dict, List, Literal
from dataclasses import dataclass

QueryScope = Literal["global", "pool", "pair", "wallet", "hook"]
QueryPriority = Literal["P0", "P1", "P2", "P3"]


@dataclass
class QueryMetadata:
    """Metadata for a single Dune query"""
    key: str  # Unique identifier
    method: str  # DuneClient method name (e.g., "get_gas_regime")
    scope: QueryScope
    ttl_seconds: int  # How long cache is fresh
    max_age_seconds: int  # Maximum age before considered too old
    priority: QueryPriority
    enabled_default: bool
    description: str


# ============================================================================
# Query Registry - All 25 Dune Queries
# ============================================================================

QUERY_REGISTRY: Dict[str, QueryMetadata] = {
    # ========== P0: Gating (Required for Decisions) ==========
    "gas_regime": QueryMetadata(
        key="gas_regime",
        method="get_gas_regime",
        scope="global",
        ttl_seconds=300,  # 5 min
        max_age_seconds=900,  # 15 min max
        priority="P0",
        enabled_default=True,
        description="Current gas prices and optimal execution windows"
    ),
    
    "pool_health_score": QueryMetadata(
        key="pool_health_score",
        method="get_pool_health_score",
        scope="pool",
        ttl_seconds=600,  # 10 min
        max_age_seconds=1800,  # 30 min max
        priority="P0",
        enabled_default=True,
        description="Composite pool health metric"
    ),
    
    "rebalance_hint": QueryMetadata(
        key="rebalance_hint",
        method="get_rebalance_hint",
        scope="pool",
        ttl_seconds=600,  # 10 min
        max_age_seconds=1800,  # 30 min max
        priority="P0",
        enabled_default=True,
        description="Automated rebalancing signal generator"
    ),
    
    # ========== P1: Shaping (Improves Decisions) ==========
    "dynamic_fee_analysis": QueryMetadata(
        key="dynamic_fee_analysis",
        method="get_dynamic_fee_analysis",
        scope="pool",
        ttl_seconds=1800,  # 30 min
        max_age_seconds=7200,  # 2 hr max
        priority="P1",
        enabled_default=True,
        description="Fee tier performance and volume patterns"
    ),
    
    "fee_tier_optimization": QueryMetadata(
        key="fee_tier_optimization",
        method="get_fee_tier_optimization",
        scope="pool",
        ttl_seconds=3600,  # 1 hr
        max_age_seconds=14400,  # 4 hr max
        priority="P1",
        enabled_default=True,
        description="Fee tier profitability comparison"
    ),
    
    "liquidity_depth": QueryMetadata(
        key="liquidity_depth",
        method="get_liquidity_depth",
        scope="pool",
        ttl_seconds=21600,  # 6 hr (slow query)
        max_age_seconds=86400,  # 24 hr max
        priority="P1",
        enabled_default=True,
        description="Tick-by-tick liquidity distribution heatmap"
    ),
    
    "liquidity_competition": QueryMetadata(
        key="liquidity_competition",
        method="get_liquidity_competition",
        scope="pool",
        ttl_seconds=21600,  # 6 hr
        max_age_seconds=86400,  # 24 hr max
        priority="P1",
        enabled_default=True,
        description="LP concentration and competitive positioning"
    ),
    
    # ========== P2: Risk (Protects Capital) ==========
    "mev_risk": QueryMetadata(
        key="mev_risk",
        method="get_mev_risk",
        scope="pool",
        ttl_seconds=3600,  # 1 hr
        max_age_seconds=14400,  # 4 hr max
        priority="P2",
        enabled_default=True,
        description="MEV sandwich attack frequency and protection"
    ),
    
    "toxic_flow_index": QueryMetadata(
        key="toxic_flow_index",
        method="get_toxic_flow_index",
        scope="pool",
        ttl_seconds=7200,  # 2 hr
        max_age_seconds=28800,  # 8 hr max
        priority="P2",
        enabled_default=True,
        description="Loss-versus-rebalancing (LVR) estimator"
    ),
    
    "jit_liquidity_monitor": QueryMetadata(
        key="jit_liquidity_monitor",
        method="get_jit_liquidity_monitor",
        scope="pool",
        ttl_seconds=3600,  # 1 hr
        max_age_seconds=14400,  # 4 hr max
        priority="P2",
        enabled_default=True,
        description="Just-in-time liquidity attack detection"
    ),
    
    # ========== P3: Offline (Analytics/Backtesting) ==========
    "impermanent_loss_tracker": QueryMetadata(
        key="impermanent_loss_tracker",
        method="get_impermanent_loss_tracker",
        scope="pool",
        ttl_seconds=21600,  # 6 hr
        max_age_seconds=86400,  # 24 hr max
        priority="P3",
        enabled_default=False,  # Disabled by default
        description="Real-time IL calculations and historical trends"
    ),
    
    "cross_dex_migration": QueryMetadata(
        key="cross_dex_migration",
        method="get_cross_dex_migration",
        scope="pool",
        ttl_seconds=21600,  # 6 hr
        max_age_seconds=86400,  # 24 hr max
        priority="P3",
        enabled_default=False,
        description="Liquidity flows between DEXs"
    ),
    
    "correlation_matrix": QueryMetadata(
        key="correlation_matrix",
        method="get_correlation_matrix",
        scope="pool",
        ttl_seconds=86400,  # 24 hr
        max_age_seconds=259200,  # 3 days max
        priority="P3",
        enabled_default=False,
        description="Asset correlation analysis for diversification"
    ),
    
    # ========== Additional Queries (Currently Unused) ==========
    "whale_sentiment": QueryMetadata(
        key="whale_sentiment",
        method="get_whale_sentiment",
        scope="pair",
        ttl_seconds=3600,
        max_age_seconds=14400,
        priority="P2",
        enabled_default=False,
        description="Large wallet activity and whale trades"
    ),
    
    "arbitrage_opportunities": QueryMetadata(
        key="arbitrage_opportunities",
        method="get_arbitrage_opportunities",
        scope="pool",
        ttl_seconds=300,
        max_age_seconds=900,
        priority="P1",
        enabled_default=False,
        description="Cross-pool price discrepancies"
    ),
    
    "hook_analysis": QueryMetadata(
        key="hook_analysis",
        method="get_hook_analysis",
        scope="hook",
        ttl_seconds=3600,
        max_age_seconds=14400,
        priority="P3",
        enabled_default=False,
        description="Uniswap V4 hook usage patterns"
    ),
    
    "hook_gas_performance": QueryMetadata(
        key="hook_gas_performance",
        method="get_hook_gas_performance",
        scope="hook",
        ttl_seconds=3600,
        max_age_seconds=14400,
        priority="P3",
        enabled_default=False,
        description="Hook gas costs and performance benchmarks"
    ),
    
    "yield_farming_opportunities": QueryMetadata(
        key="yield_farming_opportunities",
        method="get_yield_farming_opportunities",
        scope="global",
        ttl_seconds=1800,
        max_age_seconds=7200,
        priority="P3",
        enabled_default=False,
        description="Real-time APR/APY across pools"
    ),
    
    "portfolio_dashboard": QueryMetadata(
        key="portfolio_dashboard",
        method="get_portfolio_dashboard",
        scope="wallet",
        ttl_seconds=600,
        max_age_seconds=1800,
        priority="P3",
        enabled_default=False,
        description="Wallet-level P&L and position summary"
    ),
    
    # Hummingbot Quants Lab Specialized (Q20-Q25)
    "backtesting_data": QueryMetadata(
        key="backtesting_data",
        method="get_backtesting_data",
        scope="global",
        ttl_seconds=86400,
        max_age_seconds=259200,
        priority="P3",
        enabled_default=False,
        description="Historical tick data for strategy backtesting"
    ),
    
    "order_impact": QueryMetadata(
        key="order_impact",
        method="get_order_impact",
        scope="global",
        ttl_seconds=1800,
        max_age_seconds=7200,
        priority="P2",
        enabled_default=False,
        description="Price impact predictions for order sizing"
    ),
    
    "strategy_attribution": QueryMetadata(
        key="strategy_attribution",
        method="get_strategy_attribution",
        scope="global",
        ttl_seconds=3600,
        max_age_seconds=14400,
        priority="P3",
        enabled_default=False,
        description="Performance breakdown by strategy"
    ),
    
    "execution_quality": QueryMetadata(
        key="execution_quality",
        method="get_execution_quality",
        scope="global",
        ttl_seconds=1800,
        max_age_seconds=7200,
        priority="P2",
        enabled_default=False,
        description="Slippage, fill rates, execution metrics"
    ),
    
    "portfolio_allocation": QueryMetadata(
        key="portfolio_allocation",
        method="get_portfolio_allocation",
        scope="global",
        ttl_seconds=3600,
        max_age_seconds=14400,
        priority="P3",
        enabled_default=False,
        description="Optimal capital allocation across pools"
    ),
    
    "hummingbot_config": QueryMetadata(
        key="hummingbot_config",
        method="get_hummingbot_config",
        scope="global",
        ttl_seconds=3600,
        max_age_seconds=14400,
        priority="P3",
        enabled_default=False,
        description="Dynamic Hummingbot configuration generator"
    ),
}


def get_enabled_queries() -> List[QueryMetadata]:
    """Get list of queries enabled by default"""
    return [q for q in QUERY_REGISTRY.values() if q.enabled_default]


def get_queries_by_priority(priority: QueryPriority) -> List[QueryMetadata]:
    """Get all queries of a specific priority"""
    return [q for q in QUERY_REGISTRY.values() if q.priority == priority]


def get_queries_by_scope(scope: QueryScope) -> List[QueryMetadata]:
    """Get all queries of a specific scope"""
    return [q for q in QUERY_REGISTRY.values() if q.scope == scope]


def get_pool_scoped_queries() -> List[QueryMetadata]:
    """Get all queries that need pool_address parameter"""
    return get_queries_by_scope("pool")


if __name__ == "__main__":
    print("Dune Query Registry Summary")
    print("=" * 60)
    
    for priority in ["P0", "P1", "P2", "P3"]:
        queries = get_queries_by_priority(priority)
        enabled = [q for q in queries if q.enabled_default]
        print(f"\n{priority}: {len(queries)} total, {len(enabled)} enabled by default")
        for q in enabled:
            print(f"  ✅ {q.key} ({q.scope}, TTL={q.ttl_seconds}s)")
    
    print(f"\n\nTotal: {len(QUERY_REGISTRY)} queries defined")
    print(f"Enabled by default: {len(get_enabled_queries())}")
    print(f"Pool-scoped: {len(get_pool_scoped_queries())}")
