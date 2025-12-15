#!/usr/bin/env python3
"""
Analyzer for Real Data Campaign Results
=======================================

Reads results from a real-data campaign and generates a strategic analysis report.
Focus: Absolute Return (Net PnL), Care Score signal quality, Regime efficacy,
and regret vs baselines.

Usage:
    python3 scripts/analyze_real_data_campaign.py [RUN_DIR]

If RUN_DIR is not provided, finds the latest run under data/runs matching:
- real_data_campaign*
- dune_calibrated*
"""

import sys
import json
import math
import statistics
from pathlib import Path
from collections import defaultdict, Counter
from typing import Any, Dict, List, Optional, Tuple


# -----------------------------
# Helpers
# -----------------------------

def _safe_float(x: Any, default: float = 0.0) -> float:
    try:
        if x is None:
            return default
        return float(x)
    except Exception:
        return default


def _safe_int(x: Any, default: int = 0) -> int:
    try:
        if x is None:
            return default
        return int(x)
    except Exception:
        return default


def _percent(x: float) -> str:
    return f"{x * 100:.1f}%"


def _fmt_usd(x: float) -> str:
    return f"${x:,.2f}"


def _quantile(sorted_vals: List[float], q: float) -> float:
    """q in [0,1]. linear interpolation."""
    if not sorted_vals:
        return float("nan")
    n = len(sorted_vals)
    if n == 1:
        return sorted_vals[0]
    pos = (n - 1) * q
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return sorted_vals[lo]
    w = pos - lo
    return sorted_vals[lo] * (1 - w) + sorted_vals[hi] * w


def _pearson_corr(xs: List[float], ys: List[float]) -> Optional[float]:
    if len(xs) != len(ys) or len(xs) < 3:
        return None
    mx = statistics.mean(xs)
    my = statistics.mean(ys)
    vx = sum((x - mx) ** 2 for x in xs)
    vy = sum((y - my) ** 2 for y in ys)
    if vx <= 0 or vy <= 0:
        return None
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    return cov / math.sqrt(vx * vy)


def _mode_or_median(values: List[float]) -> str:
    """Avoid statistics.mode exceptions on multi-modal data."""
    if not values:
        return "N/A"
    try:
        return str(statistics.mode(values))
    except Exception:
        return str(int(statistics.median(values)))


def _episode_index_from_path(p: Path) -> int:
    # episodes/ep_<...>_<N>/result.json
    try:
        return int(p.parent.name.split("_")[-1])
    except Exception:
        return -1


# -----------------------------
# Loaders
# -----------------------------

def _load_from_results_json(run_dir: Path) -> Optional[List[Dict[str, Any]]]:
    f = run_dir / "results.json"
    if not f.exists():
        return None
    with open(f, "r") as fp:
        data = json.load(fp)
    if isinstance(data, dict) and "results" in data and isinstance(data["results"], list):
        return data["results"]
    if isinstance(data, list):
        return data
    return None


def _load_from_episode_artifacts(run_dir: Path) -> Optional[List[Dict[str, Any]]]:
    episodes_dir = run_dir / "episodes"
    if not episodes_dir.exists():
        return None
    result_paths = sorted(episodes_dir.glob("ep_*/result.json"), key=_episode_index_from_path)
    if not result_paths:
        return None
    out = []
    for rp in result_paths:
        try:
            with open(rp, "r") as f:
                out.append(json.load(f))
        except Exception:
            continue
    return out if out else None


def _load_campaign(run_dir: Path) -> List[Dict[str, Any]]:
    data = _load_from_results_json(run_dir)
    if data is not None:
        return data
    data = _load_from_episode_artifacts(run_dir)
    if data is not None:
        return data
    raise FileNotFoundError(f"No results.json and no episodes/ep_*/result.json found in {run_dir}")


# -----------------------------
# Normalization (schema drift safe)
# -----------------------------

def _extract_fields(d: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize both:
    - custom results.json rows (policy_action, actual_pnl, potential_pnl, potential_fees...)
    - EpisodeResult artifacts (pnl_usd, gas_cost_usd, params_used.decision_basis, position_after.historical_window...)
    """
    # Episode identity
    episode_id = d.get("episode_id") or d.get("episode") or d.get("id") or "unknown"

    # Action
    policy_action = (
        d.get("policy_action")
        or d.get("action")
        or d.get("params_used", {}).get("action")
        or d.get("params", {}).get("action")
        or "unknown"
    )

    # Width
    width_pts = (
        d.get("width_pts")
        or d.get("params_used", {}).get("width_pts")
        or d.get("params", {}).get("width_pts")
        or 0
    )
    width_pts = _safe_int(width_pts, 0)

    # Regime
    regime = (
        d.get("regime")
        or d.get("position_after", {}).get("regime_name")
        or d.get("metadata", {}).get("regime_key")
        or "unknown"
    )

    # Volume (real data metadata may store total_volume_usd)
    vol = (
        d.get("volume_usd")
        or d.get("position_after", {}).get("historical_window", {}).get("total_volume_usd")
        or d.get("position_after", {}).get("total_volume_usd")
        or 0.0
    )
    volume_usd = _safe_float(vol, 0.0)

    # Care score may live in:
    # - d["care_score"]
    # - decision_basis["care_score"]
    # - decision_basis["careScore"] (just in case)
    decision_basis = (
        d.get("decision_basis")
        or d.get("params_used", {}).get("decision_basis")
        or d.get("params", {}).get("decision_basis")
        or {}
    )
    care_score = d.get("care_score")
    if care_score is None:
        care_score = decision_basis.get("care_score", decision_basis.get("careScore"))
    care_score = _safe_float(care_score, float("nan"))

    # Fees / gas / pnl: prefer actual realized values if present
    pnl_usd = d.get("actual_pnl")
    if pnl_usd is None:
        pnl_usd = d.get("pnl_usd")
    pnl_usd = _safe_float(pnl_usd, 0.0)

    fees_usd = d.get("actual_fees")
    if fees_usd is None:
        fees_usd = d.get("fees_usd")
    fees_usd = _safe_float(fees_usd, 0.0)

    gas_usd = d.get("gas_cost")
    if gas_usd is None:
        gas_usd = d.get("gas_cost_usd")
    gas_usd = _safe_float(gas_usd, 0.0)

    # Potential values (ungated) if present
    potential_pnl = _safe_float(d.get("potential_pnl"), float("nan"))
    potential_fees = _safe_float(d.get("potential_fees"), float("nan"))

    # Baselines (artifact schema has baselines dict)
    baselines = d.get("baselines") or {}
    # Best baseline net if present
    best_baseline = d.get("alpha_vs") or d.get("alpha_vs_best") or d.get("position_after", {}).get("best_baseline_name")
    best_baseline = best_baseline or None

    # Historical window metadata (real data)
    hw = d.get("position_after", {}).get("historical_window") or {}
    window_index = hw.get("window_index", d.get("window_index"))
    window_index = _safe_int(window_index, -1)

    # Liquidity / Position Sizing
    position_share = _safe_float(d.get("position_share"), 0.0)
    hit_cap = bool(d.get("hit_max_share_cap", False))
    order_size_mult = _safe_float(d.get("order_size_usd_mult"), 0.0)

    return {
        "episode_id": episode_id,
        "action": policy_action,
        "width_pts": width_pts,
        "regime": regime,
        "volume_usd": volume_usd,
        "care_score": care_score,
        "pnl_usd": pnl_usd,
        "fees_usd": fees_usd,
        "gas_usd": gas_usd,
        "net_pnl": pnl_usd - gas_usd,
        "potential_pnl": potential_pnl,
        "potential_fees": potential_fees,
        "decision_basis": decision_basis,
        "baselines": baselines,
        "best_baseline": best_baseline,
    # Stateful Metrics
    in_range_frac = _safe_float(d.get("in_range_frac"), 0.0)
    has_position = d.get("position_after") is not None
    
    return {
        "episode_id": episode_id,
        "action": policy_action,
        "width_pts": width_pts,
        "regime": regime,
        "volume_usd": volume_usd,
        "care_score": care_score,
        "pnl_usd": pnl_usd,
        "fees_usd": fees_usd,
        "gas_usd": gas_usd,
        "net_pnl": pnl_usd - gas_usd,  # Still calculate net if pnl_usd is gross, but if pnl_usd is net (from stateful runner), this might double count? 
                                       # Runner says: "pnl_usd": actual_pnl + actual_gas (Gross), "net_pnl_usd": actual_pnl.
                                       # So pnl_usd - gas_usd = Net. This logic holds.
        "potential_pnl": potential_pnl,
        "potential_fees": potential_fees,
        "decision_basis": decision_basis,
        "baselines": baselines,
        "best_baseline": best_baseline,
        "window_index": window_index,
        "position_share": position_share,
        "hit_cap": hit_cap,
        "order_size_mult": order_size_mult,
        "in_range_frac": in_range_frac,
        "has_position": has_position
    }


# -----------------------------
# Analysis
# -----------------------------

def analyze_campaign(run_dir: str) -> None:
    run_path = Path(run_dir)

    print(f"Loading campaign from: {run_path.resolve()}")
    raw = _load_campaign(run_path)
    if not raw:
        print("Empty campaign data.")
        return

    rows = [_extract_fields(d) for d in raw]
    total = len(rows)
    print(f"Loaded {total} episodes.")

    # Define what counts as “action”
    # In your system: rebalance + widen spend gas; hold spends none.
    def is_action(a: str) -> bool:
        return a in ("rebalance", "widen")

    actions = [r for r in rows if is_action(r["action"])]
    holds = [r for r in rows if r["action"] == "hold"]
    unknown = [r for r in rows if r["action"] not in ("hold", "rebalance", "widen")]

    # Aggregate
    # extract PnL
    # Prefer standardized net fields, fallback to legacy
    actual_pnls = [r.get("actual_pnl_net", r.get("net_pnl", 0.0)) for r in rows]
    potential_pnls = [r.get("potential_pnl_net", r.get("potential_pnl", float("nan"))) for r in rows]
    
    # Calculate Gating Value
    # Filter for episodes where we had valid potential PnL (skip errors/skips)
    valid_indices = [i for i, r in enumerate(rows) if not math.isnan(potential_pnls[i])]
    
    total_net_pnl = sum(actual_pnls)
    mean_net_pnl = statistics.mean(actual_pnls) if actual_pnls else 0.0
    median_net_pnl = statistics.median(actual_pnls) if actual_pnls else 0.0
    
    # Fees (Gross)
    total_fees = sum([r.get("actual_fees", r.get("fees_usd", 0.0)) for r in rows])
    
    # Action Rate
    all_actions = [r.get("action", "unknown") for r in rows]
    action_rate = len(actions) / total if total else 0.0
    
    # Ungated Potential
    subset_potential = [potential_pnls[i] for i in valid_indices]
    total_potential_pnl = sum(subset_potential) if subset_potential else 0.0
    
    # Value of Gating: sum of actual net PnL for the subset of episodes where potential PnL was available
    # minus the sum of potential PnL for that same subset.
    subset_actual_net_pnl = [actual_pnls[i] for i in valid_indices]
    value_of_gating = sum(subset_actual_net_pnl) - total_potential_pnl

    # Stateful Stats
    in_market = [r for r in rows if r["has_position"]]
    in_market_rate = len(in_market) / total if total else 0.0
    avg_in_range_all = statistics.mean(r["in_range_frac"] for r in in_market) if in_market else 0.0
    
    print("\n" + "=" * 70)
    print("📊 CAMPAIGN PERFORMANCE SUMMARY (ABSOLUTE RETURN)")
    print("=" * 70)
    print(f"Episodes:            {total}")
    print(f"Total Net PnL:       {_fmt_usd(total_net_pnl)}")
    print(f"Mean Net / Episode:  {_fmt_usd(mean_net_pnl)}")
    print(f"In-Market Rate:      {_percent(in_market_rate)}")
    print(f"Avg In-Range (Mkts): {_percent(avg_in_range_all)}")
    print(f"Total Fees:          {_fmt_usd(total_fees)}")
    print(f"Action Rate:         {_percent(action_rate)}  ({len(actions)} actions, {len(holds)} holds)")
    if unknown:
        print(f"⚠️ Unknown actions:   {len(unknown)} (check schema drift)")

    # If potential pnl exists for enough rows, report “value of gating”
    num_valid = len(valid_indices)
    if num_valid >= max(5, total // 5):
        print(f"Total Potential PnL: {_fmt_usd(total_potential_pnl)}")
        print(f"Value of Gating:     {_fmt_usd(value_of_gating)} (actual − potential)")
    else:
        print("Potential PnL:       N/A (not present in enough rows)")

    # Liquidity / Caps Analysis
    print("\n" + "-" * 70)
    print("💧 LIQUIDITY & CAPS (SWEEP DIAGNOSTICS)")
    print("-" * 70)
    capped_count = sum(1 for r in rows if r["hit_cap"])
    avg_mult = statistics.mean(r["order_size_mult"] for r in rows if r["order_size_mult"] > 0) if rows else 0.0
    avg_share = statistics.mean(r["position_share"] for r in rows if r["position_share"] > 0) if rows else 0.0
    max_share = max(r["position_share"] for r in rows) if rows else 0.0
    
    print(f"Order Size Mult:     {avg_mult:,.1f}x")
    print(f"Hit Share Cap:       {capped_count}/{total} episodes ({_percent(capped_count/total)})")
    print(f"Avg Position Share:  {avg_share*100:.4f}%")
    print(f"Max Position Share:  {max_share*100:.4f}%")

    # Care score analysis
    care_pairs = [(r["care_score"], r["net_pnl"], r["action"]) for r in rows if not math.isnan(r["care_score"])]
    print("\n" + "-" * 70)
    print("🎯 CARE SCORE SIGNAL QUALITY")
    print("-" * 70)

    if len(care_pairs) < 10:
        print("Not enough care_score data to analyze.")
    else:
        care_scores_sorted = sorted(cs for cs, _, _ in care_pairs)
        q1 = _quantile(care_scores_sorted, 0.25)
        q2 = _quantile(care_scores_sorted, 0.50)
        q3 = _quantile(care_scores_sorted, 0.75)

        xs = [cs for cs, _, _ in care_pairs]
        ys = [net for _, net, _ in care_pairs]
        corr = _pearson_corr(xs, ys)

        print(f"Care quartiles: Q1={q1:.2f}  Median={q2:.2f}  Q3={q3:.2f}")
        print(f"Pearson corr(care_score, net_pnl): {corr:.3f}" if corr is not None else "Pearson corr: N/A")

        buckets = {
            "Low (<Q1)": [r for r in rows if not math.isnan(r["care_score"]) and r["care_score"] < q1],
            "Mid (Q1-Q3)": [r for r in rows if not math.isnan(r["care_score"]) and q1 <= r["care_score"] <= q3],
            "High (>Q3)": [r for r in rows if not math.isnan(r["care_score"]) and r["care_score"] > q3],
        }

        print(f"{'Bucket':<12} | {'Count':>5} | {'Act%':>6} | {'Avg Vol':>12} | {'Avg Net':>10} | {'Hit%':>6}")
        print("-" * 70)
        for label, items in buckets.items():
            if not items:
                continue
            cnt = len(items)
            act_pct = sum(1 for i in items if is_action(i["action"])) / cnt
            avg_vol = statistics.mean(i["volume_usd"] for i in items) if cnt else 0.0
            avg_net = statistics.mean(i["net_pnl"] for i in items) if cnt else 0.0
            hit = sum(1 for i in items if i["net_pnl"] > 0) / cnt
            print(f"{label:<12} | {cnt:>5} | {_percent(act_pct):>6} | {_fmt_usd(avg_vol):>12} | {_fmt_usd(avg_net):>10} | {_percent(hit):>6}")

        # Missed opportunities: held but net would have been positive in potential_pnl (if present)
        missed = [r for r in rows if r["action"] == "hold" and not math.isnan(r["potential_pnl"]) and r["potential_pnl"] > 0]
        if missed:
            avg_missed_care = statistics.mean(r["care_score"] for r in missed if not math.isnan(r["care_score"]))
            print(f"\nMissed profitable windows (held but potential_pnl>0): {len(missed)}")
            if not math.isnan(avg_missed_care):
                print(f"Avg care_score of missed: {avg_missed_care:.2f}  (consider lowering CARE_SCORE_MIN if these cluster high)")

    # Action performance
    print("\n" + "-" * 70)
    print("🧭 ACTION PERFORMANCE")
    print("-" * 70)
    by_action = defaultdict(list)
    for r in rows:
        by_action[r["action"]].append(r)

    print(f"{'Action':<10} | {'Count':>5} | {'Mean Net':>10} | {'Median Net':>11} | {'Hit%':>6} | {'Mean Gas':>9}")
    print("-" * 70)
    for act in sorted(by_action.keys()):
        items = by_action[act]
        cnt = len(items)
        mean_n = statistics.mean(i["net_pnl"] for i in items)
        med_n = statistics.median(i["net_pnl"] for i in items)
        hit = sum(1 for i in items if i["net_pnl"] > 0) / cnt
        mean_g = statistics.mean(i["gas_usd"] for i in items)
        print(f"{act:<10} | {cnt:>5} | {_fmt_usd(mean_n):>10} | {_fmt_usd(med_n):>11} | {_percent(hit):>6} | {_fmt_usd(mean_g):>9}")

    # Regime × action
    print("\n" + "-" * 70)
    print("🌍 REGIME × ACTION (NET PnL)")
    print("-" * 70)

    regimes = sorted(set(r["regime"] for r in rows))
    for reg in regimes:
        reg_items = [r for r in rows if r["regime"] == reg]
        if not reg_items:
            continue
        print(f"\nRegime: {reg}  (n={len(reg_items)})")
        print(f"{'Action':<10} | {'Count':>5} | {'Act%':>6} | {'Mean Net':>10} | {'Hit%':>6} | {'Mode Width':>10}")
        print("-" * 70)
        for act in ("hold", "rebalance", "widen"):
            items = [r for r in reg_items if r["action"] == act]
            if not items:
                continue
            cnt = len(items)
            act_pct = cnt / len(reg_items)
            mean_n = statistics.mean(i["net_pnl"] for i in items)
            hit = sum(1 for i in items if i["net_pnl"] > 0) / cnt
            widths = [i["width_pts"] for i in items if i["width_pts"] > 0]
            mode_w = _mode_or_median(widths)
            print(f"{act:<10} | {cnt:>5} | {_percent(act_pct):>6} | {_fmt_usd(mean_n):>10} | {_percent(hit):>6} | {mode_w:>10}")

    # Regret vs baseline_hold (if baselines exist)
    print("\n" + "-" * 70)
    print("📉 REGRET VS BASELINES (IF PRESENT)")
    print("-" * 70)

    regret_rows = []
    for r, raw_d in zip(rows, raw):
        baselines = r.get("baselines") or raw_d.get("baselines") or {}
        bh = baselines.get("baseline_hold")
        if isinstance(bh, dict):
            bh_net = _safe_float(bh.get("pnl_usd"), 0.0) - _safe_float(bh.get("gas_cost_usd"), 0.0)
            regret = bh_net - r["net_pnl"]
            regret_rows.append((regret, r["episode_id"], r["regime"], r["action"], r["net_pnl"], bh_net))

    if not regret_rows:
        print("No baselines found in data (expected for some real-data outputs).")
    else:
        total_regret = sum(x[0] for x in regret_rows)
        mean_regret = total_regret / len(regret_rows)
        print(f"Total regret vs baseline_hold: {_fmt_usd(total_regret)} (mean {_fmt_usd(mean_regret)}/ep)")
        top = sorted(regret_rows, key=lambda t: t[0], reverse=True)[:10]
        print("\nTop 10 regret episodes (baseline_hold − agent):")
        print(f"{'Episode':<28} | {'Regime':<12} | {'Action':<9} | {'AgentNet':>9} | {'BHNet':>9} | {'Regret':>9}")
        print("-" * 90)
        for reg, eid, regime, act, agent_net, bh_net in top:
            print(f"{eid:<28} | {regime:<12} | {act:<9} | {_fmt_usd(agent_net):>9} | {_fmt_usd(bh_net):>9} | {_fmt_usd(reg):>9}")

    # Sanity checks
    print("\n" + "=" * 70)
    print("🧪 SANITY CHECKS (REALISM / DIVERSITY)")
    print("=" * 70)

    uniq_windows = len(set(r["window_index"] for r in rows if r["window_index"] >= 0))
    print(f"Unique historical windows (window_index): {uniq_windows}/{total}")

    vol_vals = [r["volume_usd"] for r in rows if r["volume_usd"] > 0]
    if vol_vals:
        print(f"Volume range: min {_fmt_usd(min(vol_vals))}  max {_fmt_usd(max(vol_vals))}  ratio {(max(vol_vals)/max(min(vol_vals),1e-9)):.2f}x")
    else:
        print("Volume range: N/A (volume_usd missing)")

    # Detect suspiciously identical volumes (common cache/param bug symptom)
    if vol_vals:
        vol_counts = Counter(round(v, 2) for v in vol_vals)
        most_common_vol, freq = vol_counts.most_common(1)[0]
        if freq >= max(5, total // 4):
            print(f"⚠️ Many episodes share the same volume ({most_common_vol}) count={freq}. If unexpected, check cache diversity.")
    # Care score diversity
    care_vals = [r["care_score"] for r in rows if not math.isnan(r["care_score"])]
    if care_vals:
        print(f"Care score range: min {min(care_vals):.2f}  max {max(care_vals):.2f}  mean {statistics.mean(care_vals):.2f}")
    else:
        print("Care score range: N/A")

    # Final recommendations (light-touch, based on observed signal)
    print("\n" + "=" * 70)
    print("=" * 70)
    if total_net_pnl < 0:
        print("- Net PnL is negative overall. Next tuning knobs that are safest:")
        print("  • Raise CARE_SCORE_MIN slightly OR make it regime-dependent (e.g., higher in jumpy).")
        print("  • Make FEE_GATE_USD dynamic using gas_regime (P0) instead of fixed gate.")
        print("  • Add toxicity gating if you see downside tails concentrated in specific windows.")
    else:
        print("- Net PnL is positive. Next steps:")
        print("  • Increase action budget slowly: lower CARE_SCORE_MIN a bit in low_vol only.")
        print("  • Validate against LP cohort query (6354561) by matching width/duration buckets.")

    print("\nDone.")


def _find_latest_run() -> Path:
    base_dir = Path("data/runs")
    if not base_dir.exists():
        raise FileNotFoundError("No data/runs directory found.")

    candidates = []
    for d in base_dir.iterdir():
        if not d.is_dir():
            continue
        name = d.name
        if ("real_data_campaign" in name) or ("dune_calibrated" in name):
            candidates.append(d)

    if not candidates:
        raise FileNotFoundError("No real_data_campaign* or dune_calibrated* runs found in data/runs.")

    # lexicographic works if you use timestamps in names
    return sorted(candidates)[-1]


if __name__ == "__main__":
    try:
        if len(sys.argv) > 1:
            run_dir = Path(sys.argv[1])
        else:
            run_dir = _find_latest_run()

        analyze_campaign(str(run_dir))
    except Exception as e:
        print(f"❌ Analyzer failed: {e}")
        sys.exit(1)
