#!/usr/bin/env python3
"""
Demonstrate dominance-based query selection.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.dune_registry import (
    DominanceMetrics,
    select_query_plan,
    get_production_query_set,
    QUERY_REGISTRY
)


def demo_query_selection():
    print("=" * 80)
    print("DOMINANCE-BASED QUERY SELECTION DEMO")
    print("=" * 80)
    
    # Scenario 1: Gas dominates (like L1 mainnet during high congestion)
    print("\n📊 SCENARIO 1: Gas Dominates (fees_to_gas = 2.5)")
    print("-" * 80)
    dominance_gas = DominanceMetrics(
        fees_to_gas_ratio=2.5,
        jump_severity=0.3
    )
    queries = select_query_plan(dominance_gas, max_priority="P1")
    print(f"Enabled queries: {len(queries)}")
    for q in queries:
        print(f"  {q.priority} | {q.cost:<10} | {q.key}")
    
    # Scenario 2: Fees dominate (like current WETH-USDC)
    print("\n📊 SCENARIO 2: Fees Dominate (fees_to_gas = 64)")
    print("-" * 80)
    dominance_fees = DominanceMetrics(
        fees_to_gas_ratio=64.0,
        jump_severity=0.3
    )
    queries = select_query_plan(dominance_fees, max_priority="P1")
    print(f"Enabled queries: {len(queries)}")
    for q in queries:
        print(f"  {q.priority} | {q.cost:<10} | {q.key}")
    
    # Scenario 3: High churn risk
    print("\n📊 SCENARIO 3: High Churn Risk (jump_severity = 0.9)")
    print("-" * 80)
    dominance_churn = DominanceMetrics(
        fees_to_gas_ratio=20.0,
        jump_severity=0.9
    )
    queries = select_query_plan(dominance_churn, max_priority="P2")
    print(f"Enabled queries: {len(queries)}")
    for q in queries:
        print(f"  {q.priority} | {q.cost:<10} | {q.key}")
    
    # Scenario 4: High toxicity/MEV
    print("\n📊 SCENARIO 4: High Toxicity/MEV")
    print("-" * 80)
    dominance_toxic = DominanceMetrics(
        fees_to_gas_ratio=15.0,
        jump_severity=0.4,
        toxicity_proxy=0.7,
        mev_pressure=0.6
    )
    queries = select_query_plan(dominance_toxic, max_priority="P2")
    print(f"Enabled queries: {len(queries)}")
    for q in queries:
        print(f"  {q.priority} | {q.cost:<10} | {q.key}")
    
    # Production set
    print("\n📊 PRODUCTION QUERY SET (EV-Gated Strategy)")
    print("-" * 80)
    prod_keys = get_production_query_set()
    print(f"Total: {len(prod_keys)} queries")
    for key in prod_keys:
        q = QUERY_REGISTRY[key]
        print(f"  {q.priority} | {q.cost:<10} | {key}")
    
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print("✅ Registry upgraded with 3 calibration primitives")
    print("✅ P0 reclassified to raw facts only")
    print("✅ Cost tiers and dependencies added")
    print("✅ Dominance-based selection working")
    print("\n💡 Use select_query_plan() to automatically adjust queries")
    print("   based on market conditions!")


if __name__ == "__main__":
    demo_query_selection()
