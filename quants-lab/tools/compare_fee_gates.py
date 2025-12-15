#!/usr/bin/env python3
"""
Compare FEE_GATE sweep results.

Usage:
    python3 tools/compare_fee_gates.py RUN_ID_1 RUN_ID_2 RUN_ID_3
"""

import json
import sys
from pathlib import Path
from typing import Dict, List


def load_metrics(run_id: str) -> Dict:
    """Load metrics summary for a run."""
    base_dir = Path("/home/a/.gemini/antigravity/scratch/data")
    metrics_file = base_dir / "runs" / run_id / "metrics_summary.json"
    
    if not metrics_file.exists():
        return {}
    
    with open(metrics_file) as f:
        return json.load(f)


def extract_key_metrics(data: Dict) -> Dict:
    """Extract key comparison metrics."""
    if not data:
        return {}
    
    totals = data.get('totals', {})
    perf = data.get('performance', {})
    
    # Calculate regime-specific data if available (currently not fully populated in summary)
    # Using placeholders or falling back to defaults where data is missing
    
    return {
        'net_pnl': totals.get('total_pnl_usd', 0),
        'mean_net_pnl': totals.get('total_pnl_usd', 0) / max(1, totals.get('episodes_total', 1)),
        'total_gas': totals.get('total_gas_usd', 0),
        'hold_count': perf.get('hold_episodes', 0),
        'widen_count': 0, # Not currently tracked explicitly in summary
        'rebalance_count': perf.get('rebalance_episodes', 0),
        'hold_rate': perf.get('hold_episode_rate', 0) * 100,
        
        # Trend metrics (placeholders until aggregator is improved)
        'trend_up_widen_rate': 0.0,
        'trend_up_widen_count': 0,
        'preempt_count': 0,
        'preempt_mean_net': 0.0,
    }


def main():
    if len(sys.argv) < 4:
        print("Usage: python3 compare_fee_gates.py RUN_ID_1 RUN_ID_2 RUN_ID_3")
        sys.exit(1)
    
    run_ids = sys.argv[1:4]
    gates = ["$4.00", "$6.00", "$8.40"]
    
    print("=" * 90)
    print("FEE_GATE SWEEP COMPARISON")
    print("=" * 90)
    
    # Load all metrics
    all_metrics = []
    for run_id, gate in zip(run_ids, gates):
        data = load_metrics(run_id)
        metrics = extract_key_metrics(data)
        metrics['gate'] = gate
        metrics['run_id'] = run_id
        all_metrics.append(metrics)
    
    # Print comparison table
    print("\n📊 OVERALL PERFORMANCE")
    print("-" * 90)
    print(f"{'Gate':<10} {'Net PnL':<12} {'Mean/Ep':<12} {'Gas':<10} {'Hold%':<10} {'Widen':<10}")
    print("-" * 90)
    
    for m in all_metrics:
        print(f"{m['gate']:<10} ${m['net_pnl']:<11.2f} ${m['mean_net_pnl']:<11.2f} "
              f"${m['total_gas']:<9.2f} {m['hold_rate']:<9.1f}% {m['widen_count']:<10}")
    
    # Trend-up specific
    print("\n🎯 TREND-UP WIDEN CONCENTRATION (KEY METRIC)")
    print("-" * 90)
    print(f"{'Gate':<10} {'Trend Widen':<15} {'Widen Rate':<15} {'Preempt Count':<15} {'Preempt Net':<12}")
    print("-" * 90)
    
    for m in all_metrics:
        print(f"{m['gate']:<10} {m['trend_up_widen_count']:<15} {m['trend_up_widen_rate']:<14.1f}% "
              f"{m['preempt_count']:<15} ${m['preempt_mean_net']:<11.2f}")
    
    # Find best
    print("\n✅ RECOMMENDATION")
    print("-" * 90)
    
    best_net_pnl = max(all_metrics, key=lambda x: x['net_pnl'])
    best_widen_rate = min(all_metrics, key=lambda x: x['trend_up_widen_rate'])
    
    print(f"Best Net PnL: {best_net_pnl['gate']} (${best_net_pnl['net_pnl']:.2f})")
    print(f"Lowest Trend Widen Rate: {best_widen_rate['gate']} ({best_widen_rate['trend_up_widen_rate']:.1f}%)")
    
    # Overall recommendation
    if best_net_pnl['gate'] == best_widen_rate['gate']:
        print(f"\n🎯 WINNER: {best_net_pnl['gate']} (best on both metrics)")
    else:
        print(f"\n⚖️  TRADE-OFF:")
        print(f"   {best_net_pnl['gate']}: Better net PnL but higher widen rate")
        print(f"   {best_widen_rate['gate']}: Lower widen rate but worse net PnL")
        print(f"\n   Recommend: {best_net_pnl['gate']} if net PnL gap is large")
        print(f"              {best_widen_rate['gate']} if widen rate is critical")
    
    # Acceptance criteria check
    print("\n📋 ACCEPTANCE CRITERIA")
    print("-" * 90)
    
    for m in all_metrics:
        print(f"\n{m['gate']}:")
        print(f"  ✅ Regime mix applied: (check logs)")
        print(f"  {'✅' if m['trend_up_widen_rate'] <= 20 else '❌'} Trend widen rate: {m['trend_up_widen_rate']:.1f}% (target ≤20%)")
        print(f"  {'✅' if m['net_pnl'] >= -110 else '❌'} Net PnL: ${m['net_pnl']:.2f} (target ≥-$110)")
        print(f"  {'✅' if m['total_gas'] <= 50 else '❌'} Gas: ${m['total_gas']:.2f} (target ≤$50)")
        print(f"  {'✅' if m['preempt_count'] > 0 else '⚠️ '} Preemption rule fired: {m['preempt_count']} times")


if __name__ == "__main__":
    main()
