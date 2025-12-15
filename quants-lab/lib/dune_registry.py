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

from typing import Dict, List, Literal, Optional
from dataclasses import dataclass, field

QueryScope = Literal["global", "pool", "pair", "wallet", "hook"]
QueryPriority = Literal["P0", "P1", "P2", "P3"]
QueryCost = Literal["cheap", "medium", "expensive"]


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
    cost: QueryCost = "medium"  # Execution cost tier
    depends_on: List[str] = field(default_factory=list)  # Query dependencies


# ============================================================================
# Query Registry - All Dune Queries
# ============================================================================

QUERY_REGISTRY: Dict[str, QueryMetadata] = {
    # ========== P0: Raw Facts (Gate Gas Spending) ==========
    # P0 = "raw facts" that directly gate whether to spend gas
    
    "gas_regime": QueryMetadata(
        key="gas_regime",
        method="get_gas_regime",
        scope="global",
        ttl_seconds=300,  # 5 min
        max_age_seconds=900,  # 15 min max
        priority="P0",
        enabled_default=True,
        description="Current gas prices and optimal execution windows",
        cost="cheap",
        depends_on=[]
    ),
    
    "pool_hourly_fees": QueryMetadata(
        key="pool_hourly_fees",
        method="get_pool_hourly_fees",
        scope="pool",
        ttl_seconds=1800,  # 30 min
        max_age_seconds=7200,  # 2 hr max
        priority="P0",
        enabled_default=True,
        description="Pool fee budget per hour/day (volume × fee tier)",
        cost="cheap",
        depends_on=[]
    ),
    
    "realized_vol_jumps": QueryMetadata(
        key="realized_vol_jumps",
        method="get_realized_vol_jumps",
        scope="pair",
        ttl_seconds=1800,  # 30 min
        max_age_seconds=7200,  # 2 hr max
        priority="P0",
        enabled_default=True,
        description="Realized vol + jump rate; maps to regime severity",
        cost="cheap",
        depends_on=[]
    ),
    
    
    # ========== P1: Shaping (Improves Decisions) ==========
    # P1 = derived signals and suggestions that improve but don't gate decisions
    
    "pool_health_score": QueryMetadata(
        key="pool_health_score",
        method="get_pool_health_score",
        scope="pool",
        ttl_seconds=600,  # 10 min
        max_age_seconds=1800,  # 30 min max
        priority="P1",  # Moved from P0 - composite, not raw fact
        enabled_default=True,
        description="Composite pool health metric",
        cost="medium",
        depends_on=["pool_hourly_fees", "realized_vol_jumps"]
    ),
    
    "rebalance_hint": QueryMetadata(
        key="rebalance_hint",
        method="get_rebalance_hint",
        scope="pool",
        ttl_seconds=600,  # 10 min
        max_age_seconds=1800,  # 30 min max
        priority="P1",  # Moved from P0 - suggestion engine, not fact
        enabled_default=True,
        description="Automated rebalancing signal generator",
        cost="medium",
        depends_on=["pool_hourly_fees", "gas_regime"]
    ),
    
    "regime_frequencies": QueryMetadata(
        key="regime_frequencies",
        method="get_regime_frequencies",
        scope="pair",
        ttl_seconds=21600,  # 6 hr
        max_age_seconds=86400,  # 24 hr max
        priority="P1",
        enabled_default=True,
        description="Observed regime mix weights over rolling windows",
        cost="medium",
        depends_on=["realized_vol_jumps"]
    ),
    

    "dynamic_fee_analysis": QueryMetadata(
        key="dynamic_fee_analysis",
        method="get_dynamic_fee_analysis",
        scope="pool",
        ttl_seconds=1800,  # 30 min
        max_age_seconds=7200,  # 2 hr max
        priority="P1",
        enabled_default=True,
        description="Fee tier performance and volume patterns",
        cost="medium",
        depends_on=["pool_hourly_fees"]
    ),
    
    "fee_tier_optimization": QueryMetadata(
        key="fee_tier_optimization",
        method="get_fee_tier_optimization",
        scope="pool",
        ttl_seconds=3600,  # 1 hr
        max_age_seconds=14400,  # 4 hr max
        priority="P1",
        enabled_default=False,  # Disabled - only for research
        description="Fee tier profitability comparison",
        cost="medium",
        depends_on=["dynamic_fee_analysis"]
    ),
    
    "liquidity_depth": QueryMetadata(
        key="liquidity_depth",
        method="get_liquidity_depth",
        scope="pool",
        ttl_seconds=21600,  # 6 hr (slow query)
        max_age_seconds=86400,  # 24 hr max
        priority="P1",
        enabled_default=True,
        description="Tick-by-tick liquidity distribution heatmap",
        cost="expensive",  # Slow query
        depends_on=[]
    ),
    
    "liquidity_competition": QueryMetadata(
        key="liquidity_competition",
        method="get_liquidity_competition",
        scope="pool",
        ttl_seconds=21600,  # 6 hr
        max_age_seconds=86400,  # 24 hr max
        priority="P1",
        enabled_default=False,  # Disabled - only for research
        description="LP concentration and competitive positioning",
        cost="expensive",
        depends_on=["liquidity_depth"]
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
        description="MEV sandwich attack frequency and protection",
        cost="medium",
        depends_on=[]
    ),
    
    "toxic_flow_index": QueryMetadata(
        key="toxic_flow_index",
        method="get_toxic_flow_index",
        scope="pool",
        ttl_seconds=7200,  # 2 hr
        max_age_seconds=28800,  # 8 hr max
        priority="P2",
        enabled_default=True,
        description="Loss-versus-rebalancing (LVR) estimator",
        cost="medium",
        depends_on=[]
    ),
    
    "jit_liquidity_monitor": QueryMetadata(
        key="jit_liquidity_monitor",
        method="get_jit_liquidity_monitor",
        scope="pool",
        ttl_seconds=3600,  # 1 hr
        max_age_seconds=14400,  # 4 hr max
        priority="P2",
        enabled_default=True,
        description="Just-in-time liquidity attack detection",
        cost="medium",
        depends_on=[]
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


@dataclass
class DominanceMetrics:
    """Market dominance metrics that determine what to care about"""
    fees_to_gas_ratio: float  # median_hourly_pool_fees / gas_p75
    jump_severity: float  # jump_rate + vol_p90/vol_p50
    toxicity_proxy: float = 0.0  # toxic_flow_index if available
    mev_pressure: float = 0.0  # mev_risk / jit_liquidity_monitor


def select_query_plan(
    dominance: DominanceMetrics,
    max_priority: QueryPriority = "P1",
    max_expensive: int = 1,
    cache_timestamps: Optional[Dict[str, float]] = None
) -> List[QueryMetadata]:
    """
    Select queries to run based on dominance metrics.
    
    Automatically enables/disables queries based on what matters most:
    - If fees_to_gas < 5: gas dominates → focus on P0 raw facts
    - If fees_to_gas > 20: fees dominate → enable deep shaping
    - If jump_severity high: churn risk → wider floors, higher OOR
    - If toxicity/mev high: adverse selection → risk queries
    
    Args:
        dominance: Market dominance metrics
        max_priority: Maximum priority to include (P0, P1, P2, P3)
        max_expensive: Maximum number of expensive queries to run
        cache_timestamps: Optional cache timestamps to check freshness
    
    Returns:
        List of queries to execute, ordered by priority
    """
    import time
    
    # Start with enabled defaults
    enabled = set(q.key for q in get_enabled_queries())
    
    # Adjust based on dominance
    if dominance.fees_to_gas_ratio < 5.0:
        # Gas dominates - focus on P0 raw facts only
        enabled = {q.key for q in QUERY_REGISTRY.values() if q.priority == "P0"}
        # Disable expensive shaping
        enabled.discard("liquidity_depth")
        enabled.discard("liquidity_competition")
        
    elif dominance.fees_to_gas_ratio > 20.0:
        # Fees dominate - can afford more active management
        # Enable deep shaping when jump rate is low
        if dominance.jump_severity < 0.5:
            enabled.add("liquidity_depth")
            enabled.add("dynamic_fee_analysis")
    
    if dominance.jump_severity > 0.8:
        # High churn risk - focus on volatility/regime data
        enabled.add("realized_vol_jumps")
        enabled.add("regime_frequencies")
        # Disable expensive queries
        enabled.discard("liquidity_depth")
        enabled.discard("liquidity_competition")
    
    if dominance.toxicity_proxy > 0.5 or dominance.mev_pressure > 0.5:
        # High adverse selection - enable risk queries
        enabled.add("toxic_flow_index")
        enabled.add("mev_risk")
        enabled.add("jit_liquidity_monitor")
    
    # Filter by priority ceiling
    priority_order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
    max_priority_level = priority_order[max_priority]
    
    queries = [
        q for q in QUERY_REGISTRY.values()
        if q.key in enabled and priority_order[q.priority] <= max_priority_level
    ]
    
    # Check freshness if cache timestamps provided
    if cache_timestamps:
        now = time.time()
        queries = [
            q for q in queries
            if q.key not in cache_timestamps or
            (now - cache_timestamps[q.key]) > q.ttl_seconds
        ]
    
    # Enforce expensive query budget
    expensive_queries = [q for q in queries if q.cost == "expensive"]
    if len(expensive_queries) > max_expensive:
        # Keep only the highest priority expensive queries
        expensive_queries.sort(key=lambda q: priority_order[q.priority])
        queries = [q for q in queries if q.cost != "expensive"] + expensive_queries[:max_expensive]
    
    # Sort by priority, then by cost (cheap first)
    cost_order = {"cheap": 0, "medium": 1, "expensive": 2}
    queries.sort(key=lambda q: (priority_order[q.priority], cost_order[q.cost]))
    
    return queries


def get_production_query_set() -> List[str]:
    """
    Get the lean production query set for EV-gated strategy.
    
    Based on current strategy (hold-by-default + EV gates):
    - P0: gas_regime, pool_hourly_fees, realized_vol_jumps
    - P1: dynamic_fee_analysis, liquidity_depth (rare), regime_frequencies
    - P2: toxic_flow_index, mev_risk, jit_liquidity_monitor (if trading mainnet)
    """
    return [
        # P0 - always on
        "gas_regime",
        "pool_hourly_fees",
        "realized_vol_jumps",
        # P1 - daily/6-hour
        "dynamic_fee_analysis",
        "liquidity_depth",  # expensive; run rarely
        "regime_frequencies",
        # P2 - only if mainnet
        "toxic_flow_index",
        "mev_risk",
        "jit_liquidity_monitor",
    ]



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
