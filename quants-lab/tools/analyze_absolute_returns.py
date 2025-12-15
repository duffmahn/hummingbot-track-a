#!/usr/bin/env python3
"""
Absolute Return Analyzer - Comprehensive metrics analysis for agent runs.

Computes absolute return metrics (not just alpha), breakdown by decision and regime,
regret vs best baseline, and decision audit trail validation.
"""

import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from collections import defaultdict, Counter
from dataclasses import dataclass, asdict


@dataclass
class EpisodeMetrics:
    """Metrics extracted from a single episode."""
    episode_id: str
    regime: str
    action: str
    pnl_usd: float
    fees_usd: float
    gas_cost_usd: float
    net_pnl_usd: float
    out_of_range_pct: float
    rebalance_count: int
    rule_fired: Optional[str]
    prev_alpha: Optional[float]
    prev_oor: Optional[float]
    baselines: Dict[str, Dict[str, float]]
    best_baseline_name: str
    best_baseline_net: float
    regret: float


def load_episode_result(result_path: Path) -> Optional[Dict]:
    """Load and validate episode result.json."""
    try:
        with open(result_path) as f:
            return json.load(f)
    except Exception as e:
        print(f"⚠️  Warning: Could not load {result_path}: {e}", file=sys.stderr)
        return None


def extract_metrics(result: Dict) -> Optional[EpisodeMetrics]:
    """Extract metrics from result.json with tolerant field extraction."""
    try:
        # Basic fields
        episode_id = result.get("episode_id", "unknown")
        pnl_usd = result.get("pnl_usd", 0.0)
        fees_usd = result.get("fees_usd", 0.0)
        gas_cost_usd = result.get("gas_cost_usd", 0.0)
        net_pnl_usd = pnl_usd - gas_cost_usd
        out_of_range_pct = result.get("out_of_range_pct", 0.0)
        rebalance_count = result.get("rebalance_count", 0)
        
        # Regime (try multiple locations)
        regime = "unknown"
        if "position_after" in result:
            regime = result["position_after"].get("regime_name", "unknown")
        
        # Action and decision basis
        params = result.get("params_used", {})
        action = params.get("action", "auto")
        decision_basis = params.get("decision_basis", {})
        rule_fired = decision_basis.get("rule_fired")
        prev_alpha = decision_basis.get("prev_alpha_usd")
        prev_oor = decision_basis.get("prev_oor_pct")
        
        # Baselines
        baselines_data = {}
        baselines_raw = result.get("baselines", {})
        for name, baseline in baselines_raw.items():
            baseline_pnl = baseline.get("pnl_usd", 0.0)
            baseline_gas = baseline.get("gas_cost_usd", 0.0)
            baseline_net = baseline_pnl - baseline_gas
            baselines_data[name] = {
                "pnl_usd": baseline_pnl,
                "fees_usd": baseline.get("fees_usd", 0.0),
                "gas_cost_usd": baseline_gas,
                "net_pnl_usd": baseline_net,
                "out_of_range_pct": baseline.get("out_of_range_pct", 0.0),
                "rebalance_count": baseline.get("rebalance_count", 0)
            }
        
        # Find best baseline
        best_baseline_name = "baseline_hold"
        best_baseline_net = baselines_data.get("baseline_hold", {}).get("net_pnl_usd", 0.0)
        for name, data in baselines_data.items():
            if data["net_pnl_usd"] > best_baseline_net:
                best_baseline_name = name
                best_baseline_net = data["net_pnl_usd"]
        
        # Regret
        regret = best_baseline_net - net_pnl_usd
        
        return EpisodeMetrics(
            episode_id=episode_id,
            regime=regime,
            action=action,
            pnl_usd=pnl_usd,
            fees_usd=fees_usd,
            gas_cost_usd=gas_cost_usd,
            net_pnl_usd=net_pnl_usd,
            out_of_range_pct=out_of_range_pct,
            rebalance_count=rebalance_count,
            rule_fired=rule_fired,
            prev_alpha=prev_alpha,
            prev_oor=prev_oor,
            baselines=baselines_data,
            best_baseline_name=best_baseline_name,
            best_baseline_net=best_baseline_net,
            regret=regret
        )
    except Exception as e:
        print(f"⚠️  Warning: Could not extract metrics: {e}", file=sys.stderr)
        return None


def analyze_run(run_dir: Path, gas_per_rebalance: float = 2.0) -> Dict:
    """Analyze all episodes in a run directory."""
    episodes_dir = run_dir / "episodes"
    
    if not episodes_dir.exists():
        raise ValueError(f"Episodes directory not found: {episodes_dir}")
    
    # Find all result.json files with numeric sorting
    result_paths = list(episodes_dir.glob("ep_*/result.json"))
    
    def _ep_index(p: Path) -> int:
        try:
            return int(p.parent.name.split("_")[-1])
        except Exception:
            return -1
    
    result_paths.sort(key=_ep_index)
    
    print(f"📁 Found {len(result_paths)} episodes in {run_dir.name}")
    
    # Load all episodes
    episodes: List[EpisodeMetrics] = []
    for path in result_paths:
        result = load_episode_result(path)
        if result:
            metrics = extract_metrics(result)
            if metrics:
                episodes.append(metrics)
    
    print(f"✅ Successfully loaded {len(episodes)} episodes")
    
    if not episodes:
        raise ValueError("No valid episodes found")
    
    # A) Overall absolute return
    total_pnl = sum(e.pnl_usd for e in episodes)
    total_fees = sum(e.fees_usd for e in episodes)
    total_gas = sum(e.gas_cost_usd for e in episodes)
    total_net_pnl = sum(e.net_pnl_usd for e in episodes)
    
    action_counts = Counter(e.action for e in episodes)
    hold_count = action_counts.get("hold", 0)
    rebalance_count = action_counts.get("rebalance", 0)
    widen_count = action_counts.get("widen", 0)
    
    gas_saved = (gas_per_rebalance * len(episodes)) - total_gas
    
    net_pnls = [e.net_pnl_usd for e in episodes]
    mean_net_pnl = total_net_pnl / len(episodes)
    median_net_pnl = sorted(net_pnls)[len(net_pnls) // 2]
    
    # B) Breakdown by decision
    by_action = defaultdict(list)
    for e in episodes:
        by_action[e.action].append(e)
    
    action_stats = {}
    for action, eps in by_action.items():
        net_pnls = [e.net_pnl_usd for e in eps]
        action_stats[action] = {
            "count": len(eps),
            "mean_net_pnl": sum(net_pnls) / len(eps),
            "median_net_pnl": sorted(net_pnls)[len(net_pnls) // 2],
            "mean_pnl": sum(e.pnl_usd for e in eps) / len(eps),
            "mean_fees": sum(e.fees_usd for e in eps) / len(eps),
            "mean_gas": sum(e.gas_cost_usd for e in eps) / len(eps),
            "hit_rate": sum(1 for e in eps if e.net_pnl_usd > 0) / len(eps)
        }
    
    # C) Breakdown by regime × decision
    by_regime_action = defaultdict(list)
    for e in episodes:
        key = (e.regime, e.action)
        by_regime_action[key].append(e)
    
    regime_action_stats = {}
    for (regime, action), eps in by_regime_action.items():
        net_pnls = [e.net_pnl_usd for e in eps]
        regime_action_stats[f"{regime}_{action}"] = {
            "regime": regime,
            "action": action,
            "count": len(eps),
            "mean_net_pnl": sum(net_pnls) / len(eps),
            "median_net_pnl": sorted(net_pnls)[len(net_pnls) // 2],
            "mean_pnl": sum(e.pnl_usd for e in eps) / len(eps),
            "mean_fees": sum(e.fees_usd for e in eps) / len(eps),
            "mean_gas": sum(e.gas_cost_usd for e in eps) / len(eps),
            "hit_rate": sum(1 for e in eps if e.net_pnl_usd > 0) / len(eps)
        }
    
    # D) Baseline comparison
    baseline_names = set()
    for e in episodes:
        baseline_names.update(e.baselines.keys())
    
    baseline_stats = {}
    for name in baseline_names:
        baseline_net_pnls = []
        for e in episodes:
            if name in e.baselines:
                baseline_net_pnls.append(e.baselines[name]["net_pnl_usd"])
        
        if baseline_net_pnls:
            baseline_stats[name] = {
                "total_net_pnl": sum(baseline_net_pnls),
                "mean_net_pnl": sum(baseline_net_pnls) / len(baseline_net_pnls),
                "median_net_pnl": sorted(baseline_net_pnls)[len(baseline_net_pnls) // 2]
            }
    
    # Find best baseline overall
    best_baseline_overall = max(baseline_stats.items(), key=lambda x: x[1]["total_net_pnl"])[0] if baseline_stats else None
    
    # Best baseline by regime
    by_regime = defaultdict(list)
    for e in episodes:
        by_regime[e.regime].append(e)
    
    best_baseline_by_regime = {}
    for regime, eps in by_regime.items():
        regime_baseline_means = {}
        for name in baseline_names:
            nets = [e.baselines[name]["net_pnl_usd"] for e in eps if name in e.baselines]
            if nets:
                regime_baseline_means[name] = sum(nets) / len(nets)
        if regime_baseline_means:
            best_baseline_by_regime[regime] = max(regime_baseline_means.items(), key=lambda x: x[1])[0]
    
    # E) Regret analysis
    total_regret = sum(e.regret for e in episodes)
    mean_regret = total_regret / len(episodes)
    
    regret_by_regime = {}
    for regime, eps in by_regime.items():
        regret_by_regime[regime] = sum(e.regret for e in eps) / len(eps)
    
    # Top 10 regret episodes
    top_regret = sorted(episodes, key=lambda e: e.regret, reverse=True)[:10]
    top_regret_data = [
        {
            "episode_id": e.episode_id,
            "regime": e.regime,
            "action": e.action,
            "agent_net": e.net_pnl_usd,
            "best_baseline_name": e.best_baseline_name,
            "best_baseline_net": e.best_baseline_net,
            "regret": e.regret
        }
        for e in top_regret
    ]
    
    # F) Decision audit trail
    missing_decision_basis = sum(1 for e in episodes if e.rule_fired is None)
    rule_counts = Counter(e.rule_fired for e in episodes if e.rule_fired)
    
    # Performance by rule
    by_rule = defaultdict(list)
    for e in episodes:
        if e.rule_fired:
            by_rule[e.rule_fired].append(e)
    
    rule_performance = {}
    for rule, eps in by_rule.items():
        net_pnls = [e.net_pnl_usd for e in eps]
        rule_performance[rule] = {
            "count": len(eps),
            "mean_net_pnl": sum(net_pnls) / len(eps),
            "hit_rate": sum(1 for e in eps if e.net_pnl_usd > 0) / len(eps)
        }
    
    # Compile results
    return {
        "overall": {
            "episodes_total": len(episodes),
            "total_pnl_usd": total_pnl,
            "total_fees_usd": total_fees,
            "total_gas_usd": total_gas,
            "total_net_pnl_usd": total_net_pnl,
            "mean_net_pnl": mean_net_pnl,
            "median_net_pnl": median_net_pnl,
            "hold_count": hold_count,
            "rebalance_count": rebalance_count,
            "widen_count": widen_count,
            "mean_gas_per_episode": total_gas / len(episodes),
            "gas_saved_vs_always_rebalance": gas_saved
        },
        "by_action": action_stats,
        "by_regime_action": regime_action_stats,
        "baselines": {
            "stats": baseline_stats,
            "best_overall": best_baseline_overall,
            "best_by_regime": best_baseline_by_regime
        },
        "regret": {
            "total_regret": total_regret,
            "mean_regret": mean_regret,
            "by_regime": regret_by_regime,
            "top_10_episodes": top_regret_data
        },
        "decision_audit": {
            "missing_decision_basis": missing_decision_basis,
            "rule_counts": dict(rule_counts),
            "rule_performance": rule_performance
        }
    }


def format_report(results: Dict, run_id: str) -> str:
    """Format results as human-readable report."""
    lines = []
    lines.append("=" * 80)
    lines.append(f"ABSOLUTE RETURN ANALYSIS - {run_id}")
    lines.append("=" * 80)
    
    # Overall
    overall = results["overall"]
    lines.append("\n📊 OVERALL SUMMARY")
    lines.append("-" * 80)
    lines.append(f"Episodes: {overall['episodes_total']}")
    lines.append(f"Total Net PnL: ${overall['total_net_pnl_usd']:.2f}")
    lines.append(f"  = PnL ${overall['total_pnl_usd']:.2f} - Gas ${overall['total_gas_usd']:.2f}")
    lines.append(f"Mean Net PnL/Episode: ${overall['mean_net_pnl']:.2f}")
    lines.append(f"Median Net PnL/Episode: ${overall['median_net_pnl']:.2f}")
    lines.append(f"\nActions: Hold={overall['hold_count']}, Rebalance={overall['rebalance_count']}, Widen={overall['widen_count']}")
    lines.append(f"Gas Saved vs Always-Rebalance: ${overall['gas_saved_vs_always_rebalance']:.2f}")
    
    # By Action
    lines.append("\n\n💼 BY ACTION")
    lines.append("-" * 80)
    for action, stats in sorted(results["by_action"].items()):
        lines.append(f"\n{action.upper()} ({stats['count']} episodes):")
        lines.append(f"  Mean Net PnL: ${stats['mean_net_pnl']:.2f}")
        lines.append(f"  Hit Rate: {stats['hit_rate']*100:.1f}%")
        lines.append(f"  Mean Gas: ${stats['mean_gas']:.2f}")
    
    # By Regime × Action
    lines.append("\n\n🌍 BY REGIME × ACTION")
    lines.append("-" * 80)
    for key, stats in sorted(results["by_regime_action"].items()):
        lines.append(f"\n{stats['regime']} / {stats['action']} ({stats['count']} episodes):")
        lines.append(f"  Mean Net PnL: ${stats['mean_net_pnl']:.2f}")
        lines.append(f"  Hit Rate: {stats['hit_rate']*100:.1f}%")
    
    # Baselines
    lines.append("\n\n🏆 BASELINE COMPARISON")
    lines.append("-" * 80)
    lines.append(f"Best Overall: {results['baselines']['best_overall']}")
    for name, stats in sorted(results["baselines"]["stats"].items()):
        lines.append(f"\n{name}:")
        lines.append(f"  Total Net PnL: ${stats['total_net_pnl']:.2f}")
        lines.append(f"  Mean Net PnL: ${stats['mean_net_pnl']:.2f}")
    
    # Regret
    regret = results["regret"]
    lines.append("\n\n💸 REGRET ANALYSIS")
    lines.append("-" * 80)
    lines.append(f"Total Regret: ${regret['total_regret']:.2f}")
    lines.append(f"Mean Regret/Episode: ${regret['mean_regret']:.2f}")
    lines.append(f"\nTop 10 Regret Episodes:")
    for i, ep in enumerate(regret['top_10_episodes'], 1):
        lines.append(f"  {i}. {ep['episode_id']}: ${ep['regret']:.2f}")
        lines.append(f"     {ep['regime']}/{ep['action']}: agent=${ep['agent_net']:.2f}, {ep['best_baseline_name']}=${ep['best_baseline_net']:.2f}")
    
    # Decision Audit
    audit = results["decision_audit"]
    lines.append("\n\n📋 DECISION AUDIT TRAIL")
    lines.append("-" * 80)
    lines.append(f"Missing decision_basis: {audit['missing_decision_basis']}")
    lines.append(f"\nRule Frequency:")
    for rule, count in sorted(audit['rule_counts'].items(), key=lambda x: -x[1])[:10]:
        lines.append(f"  {rule}: {count}")
    lines.append(f"\nRule Performance:")
    for rule, stats in sorted(audit['rule_performance'].items(), key=lambda x: -x[1]['mean_net_pnl'])[:10]:
        lines.append(f"  {rule}: mean_net=${stats['mean_net_pnl']:.2f}, hit_rate={stats['hit_rate']*100:.1f}%")
    
    return "\n".join(lines)


def main():
    """Main entry point."""
    import argparse
    import os
    import sys
    from pathlib import Path
    
    # Add parent directory to path for imports
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from lib.path_utils import resolve_base_dir
    
    parser = argparse.ArgumentParser(description="Analyze absolute returns for an agent run")
    parser.add_argument("--run-id", required=True, help="Run ID to analyze")
    parser.add_argument("--base-dir", help="Base directory (optional, uses env/default)")
    parser.add_argument("--gas-per-rebalance", type=float, default=2.0, help="Gas cost per rebalance")
    
    args = parser.parse_args()
    
    # Resolve base directory
    if args.base_dir:
        base_dir = Path(args.base_dir).resolve()
    else:
        base_dir = resolve_base_dir()
    
    run_dir = base_dir / "runs" / args.run_id
    
    if not run_dir.exists():
        print(f"❌ Run directory not found: {run_dir}", file=sys.stderr)
        sys.exit(1)
    
    print(f"🔍 Analyzing run: {args.run_id}")
    print(f"📁 Run directory: {run_dir}")
    
    # Analyze
    results = analyze_run(run_dir, args.gas_per_rebalance)
    
    # Save JSON
    json_path = run_dir / "metrics_summary.json"
    with open(json_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n✅ Saved JSON: {json_path}")
    
    # Save text report
    report = format_report(results, args.run_id)
    txt_path = run_dir / "metrics_summary.txt"
    with open(txt_path, "w") as f:
        f.write(report)
    print(f"✅ Saved report: {txt_path}")
    
    # Print report
    print("\n" + report)


if __name__ == "__main__":
    main()
