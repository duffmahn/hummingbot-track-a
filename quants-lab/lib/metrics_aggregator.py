"""
Metrics Aggregator for Track A

Parses episode artifacts and generates:
- episode_metrics.jsonl (one line per episode)
- metrics_summary.json (run-level rollup)

Robust to missing fields/files, never breaks campaign.
"""

import json
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime


class MetricsAggregator:
    """Aggregates episode metrics from artifact files."""
    
    def __init__(self, run_dir: Path):
        self.run_dir = Path(run_dir)
        self.episodes_dir = self.run_dir / "episodes"
        
    def collect_episode_metrics(self) -> List[Dict[str, Any]]:
        """Collect metrics from all episodes in run."""
        if not self.episodes_dir.exists():
            return []
        
        episode_dirs = sorted(self.episodes_dir.glob("ep_*"))
        metrics = []
        
        for ep_dir in episode_dirs:
            try:
                ep_metrics = self._extract_episode_metrics(ep_dir)
                if ep_metrics:
                    metrics.append(ep_metrics)
            except Exception as e:
                print(f"⚠️  Failed to extract metrics from {ep_dir.name}: {e}")
                continue
        
        return metrics
    
    def _extract_episode_metrics(self, ep_dir: Path) -> Optional[Dict[str, Any]]:
        """Extract metrics from a single episode directory."""
        episode_id = ep_dir.name
        
        # Load artifacts (best effort)
        proposal = self._load_json(ep_dir / "proposal.json")
        metadata = self._load_json(ep_dir / "metadata.json")
        result = self._load_json(ep_dir / "result.json")
        failure = self._load_json(ep_dir / "failure.json")
        reward = self._load_json(ep_dir / "reward.json")
        logs = self._load_jsonl(ep_dir / "logs.jsonl")
        
        if not metadata:
            # Can't proceed without at least metadata
            return None
        
        # Determine status
        if result:
            status = result.get("status", "unknown")
        elif failure:
            status = "failure"
        else:
            status = "unknown"
        
        # Extract from result.json (canonical source)
        pnl_usd = result.get("pnl_usd") if result else None
        fees_usd = result.get("fees_usd") if result else None
        gas_cost_usd = result.get("gas_cost_usd") if result else None
        latency_ms = result.get("latency_ms") if result else None
        used_fallback = result.get("used_fallback", False) if result else False
        
        # Fee Validation
        fees_0 = result.get("fees_0", 0.0) if result else 0.0
        fees_1 = result.get("fees_1", 0.0) if result else 0.0
        pool_fees_usd_input_based = result.get("pool_fees_usd_input_based") if result else None
        pool_fees_usd_amount_usd_based = result.get("pool_fees_usd_amount_usd_based") if result else None
        
        # Timings
        timings_ms = result.get("timings_ms") if result else {}
        if timings_ms is None: timings_ms = {}
        health_check_ms = timings_ms.get("health_check_ms")
        pool_info_ms = timings_ms.get("pool_info_ms")
        quote_ms = timings_ms.get("quote_ms")
        
        # Simulation metrics
        simulation = result.get("simulation") if result else {}
        if simulation is None: simulation = {}
        simulation_latency_ms = simulation.get("latency_ms")
        simulation_gas_estimate = simulation.get("gas_estimate")
        
        # Reward (from logs.jsonl or reward.json)
        reward_value = None
        if logs:
            for log_entry in reversed(logs):
                if log_entry.get("event") == "episode_complete":
                    reward_value = log_entry.get("payload", {}).get("reward")
                    # Also use pnl_usd from logs if missing from result
                    if pnl_usd is None:
                        pnl_usd = log_entry.get("payload", {}).get("pnl_usd")
                    break
        
        if reward_value is None and reward:
            reward_value = reward.get("total")
        
        # Intel hygiene from metadata
        extra = metadata.get("extra", {})
        intel_hygiene = extra.get("intel_hygiene", {})
        intel_fresh = intel_hygiene.get("fresh", 0)
        intel_stale = intel_hygiene.get("stale", 0)
        intel_missing_or_too_old = intel_hygiene.get("missing_or_too_old", 0)
        intel_fresh_pct = intel_hygiene.get("fresh_pct", 0.0)
        
        # Learning metadata
        learning_update_applied = metadata.get("learning_update_applied", False)
        learning_update_reason = metadata.get("learning_update_reason")
        
        # Build episode metric
        return {
            "run_id": metadata.get("run_id"),
            "episode_id": episode_id,
            "timestamp": metadata.get("timestamp"),
            "exec_mode": metadata.get("exec_mode"),
            "pool_address": result.get("pool_address") if result else proposal.get("pool_address") if proposal else None,
            "status": status,
            "pnl_usd": pnl_usd,
            "fees_usd": fees_usd,
            "gas_cost_usd": gas_cost_usd,
            "reward": reward_value,
            "latency_ms": latency_ms,
            "health_check_ms": health_check_ms,
            "pool_info_ms": pool_info_ms,
            "quote_ms": quote_ms,
            "simulation_latency_ms": simulation_latency_ms,
            "simulation_gas_estimate": simulation_gas_estimate,
            "used_fallback": used_fallback,
            "intel_fresh": intel_fresh,
            "intel_stale": intel_stale,
            "intel_missing_or_too_old": intel_missing_or_too_old,
            "intel_fresh_pct": intel_fresh_pct,
            "learning_update_applied": learning_update_applied,
            "learning_update_reason": learning_update_reason,
            "fees_0": fees_0,
            "fees_1": fees_1,
            "pool_fees_usd_input_based": pool_fees_usd_input_based,
            "pool_fees_usd_amount_usd_based": pool_fees_usd_amount_usd_based # Map from result field "pool_fees_usd_amount_usd_based" which we populated in env with two sided value
        }
    
    def build_summary(self, episode_metrics: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Build run-level summary from episode metrics."""
        if not episode_metrics:
            return {
                "run_id": self.run_dir.name,
                "generated_at": datetime.utcnow().isoformat() + "Z",
                "total_episodes": 0,
                "error": "No episode metrics found"
            }
        
        # Derive exec_mode (use majority or first)
        exec_modes = [m.get("exec_mode") for m in episode_metrics if m.get("exec_mode")]
        exec_mode = max(set(exec_modes), key=exec_modes.count) if exec_modes else "unknown"
        
        # Counts
        total_episodes = len(episode_metrics)
        success_count = sum(1 for m in episode_metrics if m.get("status") == "success")
        failure_count = sum(1 for m in episode_metrics if m.get("status") == "failure")
        other_count = total_episodes - success_count - failure_count
        
        # Totals
        total_pnl_usd = sum(m.get("pnl_usd", 0) or 0 for m in episode_metrics)
        total_fees_usd = sum(m.get("fees_usd", 0) or 0 for m in episode_metrics)
        total_gas_cost_usd = sum(m.get("gas_cost_usd", 0) or 0 for m in episode_metrics)
        total_fees_0 = sum(m.get("fees_0") or 0.0 for m in episode_metrics)
        total_fees_1 = sum(m.get("fees_1") or 0.0 for m in episode_metrics)
        
        # Averages (over successful episodes)
        successful = [m for m in episode_metrics if m.get("status") == "success"]
        avg_pnl_usd = sum(m.get("pnl_usd", 0) or 0 for m in successful) / len(successful) if successful else 0
        
        # Average latency (over episodes with value)
        latencies = [m.get("latency_ms") for m in episode_metrics if m.get("latency_ms") is not None]
        avg_latency_ms = sum(latencies) / len(latencies) if latencies else 0
        
        # Average quote_ms
        quote_times = [m.get("quote_ms") for m in episode_metrics if m.get("quote_ms") is not None]
        avg_quote_ms = sum(quote_times) / len(quote_times) if quote_times else 0
        
        # Average intel fresh %
        fresh_pcts = [m.get("intel_fresh_pct", 0) for m in episode_metrics]
        avg_intel_fresh_pct = sum(fresh_pcts) / len(fresh_pcts) if fresh_pcts else 0
        
        # Hygiene
        intel_missing_or_too_old_total = sum(m.get("intel_missing_or_too_old", 0) for m in episode_metrics)
        learning_updates_applied_count = sum(1 for m in episode_metrics if m.get("learning_update_applied"))
        learning_updates_skipped_count = sum(1 for m in episode_metrics if not m.get("learning_update_applied"))
        
        # Learning update reasons histogram
        learning_update_reasons_histogram = {}
        for m in episode_metrics:
            reason = m.get("learning_update_reason")
            if reason:
                learning_update_reasons_histogram[reason] = learning_update_reasons_histogram.get(reason, 0) + 1
        
        return {
            "run_id": episode_metrics[0].get("run_id") or self.run_dir.name,
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "exec_mode": exec_mode,
            "total_episodes": total_episodes,
            "success_count": success_count,
            "failure_count": failure_count,
            "other_count": other_count,
            "total_pnl_usd": round(total_pnl_usd, 2),
            "total_fees_usd": round(total_fees_usd, 2),
            "total_fees_0": total_fees_0,
            "total_fees_1": total_fees_1,
            "total_gas_cost_usd": round(total_gas_cost_usd, 2),
            "avg_pnl_usd": round(avg_pnl_usd, 2),
            "avg_latency_ms": round(avg_latency_ms, 2),
            "avg_quote_ms": round(avg_quote_ms, 2),
            "avg_intel_fresh_pct": round(avg_intel_fresh_pct, 2),
            "intel_missing_or_too_old_total": intel_missing_or_too_old_total,
            "learning_updates_applied_count": learning_updates_applied_count,
            "learning_updates_skipped_count": learning_updates_skipped_count,
            "learning_update_reasons_histogram": learning_update_reasons_histogram,
        }
    
    def write_episode_metrics(self, metrics: List[Dict[str, Any]]) -> Path:
        """Write episode metrics to JSONL file."""
        output_path = self.run_dir / "episode_metrics.jsonl"
        
        with open(output_path, 'w') as f:
            for metric in metrics:
                f.write(json.dumps(metric) + '\n')
        
        return output_path
    
    def write_summary(self, summary: Dict[str, Any]) -> Path:
        """Write metrics summary to JSON file."""
        output_path = self.run_dir / "metrics_summary.json"
        
        with open(output_path, 'w') as f:
            json.dump(summary, f, indent=2)
        
        return output_path
    
    def _load_json(self, path: Path) -> Optional[Dict[str, Any]]:
        """Load JSON file, return None if missing or invalid."""
        try:
            if path.exists():
                with open(path) as f:
                    return json.load(f)
        except Exception:
            pass
        return None
    
    def _load_jsonl(self, path: Path) -> List[Dict[str, Any]]:
        """Load JSONL file, return empty list if missing or invalid."""
        try:
            if path.exists():
                with open(path) as f:
                    return [json.loads(line) for line in f if line.strip()]
        except Exception:
            pass
        return []


def aggregate_run_metrics(run_dir: Path) -> tuple[Path, Path]:
    """
    Aggregate metrics for a run.
    
    Returns:
        (episode_metrics_path, summary_path)
    """
    aggregator = MetricsAggregator(run_dir)
    
    # Collect episode metrics
    episode_metrics = aggregator.collect_episode_metrics()
    
    # Build summary
    summary = aggregator.build_summary(episode_metrics)
    
    # Write outputs
    ep_metrics_path = aggregator.write_episode_metrics(episode_metrics)
    summary_path = aggregator.write_summary(summary)
    
    return ep_metrics_path, summary_path


def build_run_metrics(run_dir: Path) -> Dict[str, Any]:
    """
    Build ROI-aware run metrics with capital inference and exposure calculation.
    
    Phase 7 deliverable: comprehensive metrics including:
    - Starting capital (inferred or explicit)
    - Exposure duration
    - Fee capture efficiency (opportunity-aware)
    - Volume-normalized performance
    - ROI and annualized returns (proxy in mock mode)
    
    Returns:
        Dict with all metrics for metrics_summary.json
    """
    import os
    import statistics
    
    run_dir = Path(run_dir)
    episodes_dir = run_dir / "episodes"
    
    if not episodes_dir.exists():
        return {
            "run_id": run_dir.name,
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "error": "No episodes directory found"
        }
    
    # Load all episode artifacts
    episodes = []
    episode_dirs = sorted(episodes_dir.glob("ep_*"))
    
    for ep_dir in episode_dirs:
        try:
            result_file = ep_dir / "result.json"
            proposal_file = ep_dir / "proposal.json"
            reward_file = ep_dir / "reward.json"
            
            if not result_file.exists():
                continue
            
            with open(result_file) as f:
                result = json.load(f)
            
            proposal = None
            if proposal_file.exists():
                with open(proposal_file) as f:
                    proposal = json.load(f)
            
            reward = None
            if reward_file.exists():
                with open(reward_file) as f:
                    reward = json.load(f)
            
            episodes.append({
                "episode_id": result.get("episode_id"),
                "result": result,
                "proposal": proposal,
                "reward": reward
            })
        except Exception as e:
            print(f"⚠️  Failed to load {ep_dir.name}: {e}")
            continue
    
    if not episodes:
        return {
            "run_id": run_dir.name,
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "error": "No valid episodes found"
        }
    
    # === CAPITAL INFERENCE ===
    starting_capital_usd = None
    capital_inference_method = None
    episode_capitals = []
    
    # Check env var first
    if "HB_START_CAPITAL_USD" in os.environ:
        try:
            starting_capital_usd = float(os.environ["HB_START_CAPITAL_USD"])
            capital_inference_method = "env_var"
        except ValueError:
            pass
    
    # Fallback: infer from proposals
    if starting_capital_usd is None:
        for ep in episodes:
            proposal = ep.get("proposal")
            result = ep.get("result")
            
            if not proposal:
                continue
            
            params = proposal.get("params", {})
            order_size = params.get("order_size", 0.1)  # default 0.1
            
            # Get mid price from result.position_after or default
            mid_price_usd = 2000.0  # default
            if result and result.get("position_after"):
                quote_band = result["position_after"].get("quote_band", {})
                mid_price_usd = quote_band.get("mid_price_usd", 2000.0)
            
            capital_usd_episode = max(1.0, order_size * mid_price_usd)
            episode_capitals.append(capital_usd_episode)
        
        if episode_capitals:
            starting_capital_usd = statistics.median(episode_capitals)
            capital_inference_method = "median_inferred"
        else:
            starting_capital_usd = 200.0  # fallback default
            capital_inference_method = "default_fallback"
    
    # === DURATION CALCULATION ===
    # Wall clock
    timestamps = [ep["result"].get("timestamp") for ep in episodes if ep["result"].get("timestamp")]
    if timestamps:
        try:
            first_ts = datetime.fromisoformat(timestamps[0].replace("Z", "+00:00"))
            last_ts = datetime.fromisoformat(timestamps[-1].replace("Z", "+00:00"))
            run_duration_s = (last_ts - first_ts).total_seconds()
        except:
            run_duration_s = 0
    else:
        run_duration_s = 0
    
    # Exposure duration
    episode_exposure_s = int(os.environ.get("HB_EPISODE_EXPOSURE_S", "3600"))  # default 1 hour
    exposure_s = len(episodes) * episode_exposure_s
    exposure_method = "HB_EPISODE_EXPOSURE_S"
    
    # === CORE TOTALS ===
    episodes_total = len(episodes)
    episodes_success = sum(1 for ep in episodes if ep["result"].get("status") == "success")
    episodes_failed = episodes_total - episodes_success
    
    total_pnl_usd = sum(ep["result"].get("pnl_usd", 0) for ep in episodes)
    total_fees_usd = sum(ep["result"].get("fees_usd", 0) for ep in episodes)
    total_gas_usd = sum(ep["result"].get("gas_cost_usd", 0) for ep in episodes)
    total_fees_0 = sum(ep["result"].get("fees_0", 0) or 0 for ep in episodes)
    total_fees_1 = sum(ep["result"].get("fees_1", 0) or 0 for ep in episodes)
    
    # Latency
    latencies = [ep["result"].get("latency_ms") for ep in episodes if ep["result"].get("latency_ms") is not None]
    avg_latency_ms = statistics.mean(latencies) if latencies else 0
    p95_latency_ms = statistics.quantiles(latencies, n=20)[18] if len(latencies) >= 20 else (max(latencies) if latencies else 0)
    
    # OOR
    oor_values = [ep["result"].get("out_of_range_pct", 0) for ep in episodes]
    mean_out_of_range_pct = statistics.mean(oor_values) if oor_values else 0
    max_out_of_range_pct = max(oor_values) if oor_values else 0
    
    # === FEE CAPTURE EFFICIENCY ===
    total_fee_opportunity_usd = 0
    episode_capture_effs = []
    
    for ep in episodes:
        result = ep["result"]
        fees_earned = result.get("fees_usd", 0)
        
        pa = result.get("position_after", {})
        missed = pa.get("missed_fees_usd_proxy", 0)
        
        fee_opportunity = fees_earned + missed
        total_fee_opportunity_usd += fee_opportunity
        
        if fee_opportunity > 0:
            capture_eff = fees_earned / fee_opportunity
            episode_capture_effs.append(capture_eff)
    
    capture_efficiency = total_fees_usd / total_fee_opportunity_usd if total_fee_opportunity_usd > 0 else 0
    mean_capture_efficiency = statistics.mean(episode_capture_effs) if episode_capture_effs else 0
    
    # === VOLUME-NORMALIZED ===
    total_volume_usd_proxy = sum(
        ep["result"].get("position_after", {}).get("volume_usd_proxy", 0)
        for ep in episodes
    )
    pnl_per_100k_vol = (total_pnl_usd / total_volume_usd_proxy * 100_000) if total_volume_usd_proxy > 0 else 0
    
    # ✅ DELIVERABLE 5: Alpha and baseline metrics
    alpha_values = [ep["result"].get("alpha_usd") for ep in episodes if ep["result"].get("alpha_usd") is not None]
    total_alpha_usd = sum(alpha_values) if alpha_values else 0
    mean_alpha_usd = statistics.mean(alpha_values) if alpha_values else 0
    alpha_win_rate = sum(1 for a in alpha_values if a > 0) / len(alpha_values) if alpha_values else 0
    
    # Hold episodes (gas == 0)
    hold_episodes = sum(1 for ep in episodes if ep["result"].get("gas_cost_usd", 0) == 0)
    
    # Rebalance episodes (gas > 0)
    rebalance_episodes = sum(1 for ep in episodes if ep["result"].get("gas_cost_usd", 0) > 0)
    
    # Gas metrics
    gas_values = [ep["result"].get("gas_cost_usd", 0) for ep in episodes]
    mean_gas_cost_usd = statistics.mean(gas_values) if gas_values else 0
    
    # Alpha per gas (only for episodes with gas > 0)
    alpha_per_gas_values = []
    for ep in episodes:
        alpha = ep["result"].get("alpha_usd")
        gas = ep["result"].get("gas_cost_usd", 0)
        if alpha is not None and gas > 0:
            alpha_per_gas_values.append(alpha / gas)
    mean_alpha_per_gas_usd = statistics.mean(alpha_per_gas_values) if alpha_per_gas_values else None
    
    # ✅ DELIVERABLE 4: Baseline policy win counts (histogram of alpha_vs)
    baseline_policy_win_counts = {}
    for ep in episodes:
        alpha_vs = ep["result"].get("alpha_vs")
        if alpha_vs:
            baseline_policy_win_counts[alpha_vs] = baseline_policy_win_counts.get(alpha_vs, 0) + 1
    
    # ✅ DELIVERABLE 4: Hold episode rate
    hold_episode_rate = hold_episodes / len(episodes) if episodes else 0.0
    
    # ✅ DELIVERABLE 4: Alpha per hour
    exposure_hours = exposure_s / 3600.0 if exposure_s else 0.0
    alpha_per_hour_usd = (total_alpha_usd / exposure_hours) if exposure_hours > 0 else None
    
    # ✅ DELIVERABLE 4: Alpha per rebalance episode
    alpha_per_rebalance_episode_usd = (
        (total_alpha_usd / rebalance_episodes) if rebalance_episodes > 0 else None
    )
    
    # ✅ DELIVERABLE 5: Regime-stratified metrics
    from collections import defaultdict, Counter
    
    episodes_by_regime = Counter()
    alpha_vals_by_regime = defaultdict(list)
    alpha_win_by_regime = defaultdict(int)
    alpha_total_by_regime = defaultdict(float)
    baseline_wins_by_regime = defaultdict(lambda: Counter())
    agent_action_counts_by_regime = defaultdict(lambda: Counter())
    gas_vals_by_regime = defaultdict(list)
    
    for ep in episodes:
        # ✅ FIX: Get regime from proposal.metadata.regime_key
        proposal = ep.get("proposal") or {}
        metadata = proposal.get("metadata", {})
        regime = metadata.get("regime_key", "unknown")
        
        # Fallback to old location for backwards compatibility
        if regime == "unknown":
            regime = ep["result"].get("position_after", {}).get("regime_name", "unknown")
        
        episodes_by_regime[regime] += 1
        
        # Alpha by regime
        alpha = ep["result"].get("alpha_usd")
        if alpha is not None:
            alpha_vals_by_regime[regime].append(alpha)
            alpha_total_by_regime[regime] += alpha
            if alpha > 0:
                alpha_win_by_regime[regime] += 1
        
        # Baseline wins by regime
        alpha_vs = ep["result"].get("alpha_vs")
        if alpha_vs:
            baseline_wins_by_regime[regime][alpha_vs] += 1
        
        # Agent action by regime
        action = ep["result"].get("position_after", {}).get("action_applied", "unknown")
        # Normalize action
        if "hold" in action.lower():
            action_norm = "hold"
        elif "widen" in action.lower():
            action_norm = "widen"
        elif "rebalance" in action.lower() or "open" in action.lower():
            action_norm = "rebalance"
        else:
            action_norm = "other"
        agent_action_counts_by_regime[regime][action_norm] += 1
        
        # Gas by regime
        gas = ep["result"].get("gas_cost_usd", 0)
        gas_vals_by_regime[regime].append(float(gas))
    
    # Compute regime metrics
    alpha_by_regime = {}
    for regime, vals in alpha_vals_by_regime.items():
        alpha_by_regime[regime] = {
            "mean": statistics.mean(vals) if vals else 0.0,
            "median": statistics.median(vals) if vals else 0.0,
            "win_rate": alpha_win_by_regime[regime] / episodes_by_regime[regime] if episodes_by_regime[regime] > 0 else 0.0,
            "total": alpha_total_by_regime[regime],
        }
    
    baseline_policy_win_counts_by_regime = {
        regime: dict(counter) for regime, counter in baseline_wins_by_regime.items()
    }
    
    agent_action_rate_by_regime = {}
    for regime, counter in agent_action_counts_by_regime.items():
        total = episodes_by_regime[regime]
        agent_action_rate_by_regime[regime] = {
            action: count / total for action, count in counter.items()
        }
    
    mean_gas_by_regime = {
        regime: statistics.mean(vals) if vals else 0.0
        for regime, vals in gas_vals_by_regime.items()
    }
    
    # === ROI METRICS ===
    roi = total_pnl_usd / starting_capital_usd if starting_capital_usd > 0 else 0
    fees_roi = total_fees_usd / starting_capital_usd if starting_capital_usd > 0 else 0
    gas_roi = total_gas_usd / starting_capital_usd if starting_capital_usd > 0 else 0
    
    # Annualized (proxy)
    apr_pnl = None
    apr_fees = None
    if exposure_s > 0:
        seconds_per_year = 365 * 24 * 3600
        apr_pnl = roi * (seconds_per_year / exposure_s)
        apr_fees = fees_roi * (seconds_per_year / exposure_s)
    
    # === EPISODE TABLE ===
    episode_table = []
    for ep in episodes:
        result = ep["result"]
        fees_earned = result.get("fees_usd", 0)
        pa = result.get("position_after", {})
        missed = pa.get("missed_fees_usd_proxy", 0)
        fee_opportunity = fees_earned + missed
        capture_eff = (fees_earned / fee_opportunity) if fee_opportunity > 0 else None
        
        episode_table.append({
            "episode_id": result.get("episode_id"),
            "pnl_usd": result.get("pnl_usd"),
            "fees_usd": fees_earned,
            "gas_cost_usd": result.get("gas_cost_usd"),  # ✅ DELIVERABLE D
            "missed_fees_usd": missed,
            "capture_efficiency": capture_eff,
            "out_of_range_pct": result.get("out_of_range_pct"),
            "alpha_usd": result.get("alpha_usd"),  # ✅ DELIVERABLE D
            "alpha_vs": result.get("alpha_vs"),  # ✅ DELIVERABLE D
        })
    
    # === BUILD OUTPUT ===
    exec_mode = episodes[0]["result"].get("exec_mode", "unknown")
    
    return {
        "run_id": run_dir.name,
        "exec_mode": exec_mode,
        "generated_at": datetime.utcnow().isoformat() + "Z",
        
        "capital_assumptions": {
            "starting_capital_usd": round(starting_capital_usd, 2),
            "capital_inference_method": capital_inference_method,
            "episode_capitals": [round(c, 2) for c in episode_capitals] if episode_capitals else None
        },
        
        "duration": {
            "run_duration_s": round(run_duration_s, 2),
            "exposure_s": exposure_s,
            "exposure_method": exposure_method,
            "episodes_count": episodes_total
        },
        
        "totals": {
            "episodes_total": episodes_total,
            "episodes_success": episodes_success,
            "episodes_failed": episodes_failed,
            "total_pnl_usd": round(total_pnl_usd, 2),
            "total_fees_usd": round(total_fees_usd, 2),
            "total_fees_0": total_fees_0,
            "total_fees_1": total_fees_1,
            "total_gas_usd": round(total_gas_usd, 2),
            "total_fee_opportunity_usd": round(total_fee_opportunity_usd, 2),
            "total_volume_usd_proxy": round(total_volume_usd_proxy, 2)
        },
        
        "roi_metrics": {
            "roi": round(roi, 6),
            "fees_roi": round(fees_roi, 6),
            "gas_roi": round(gas_roi, 6),
            "apr_pnl": round(apr_pnl, 6) if apr_pnl is not None else None,
            "apr_fees": round(apr_fees, 6) if apr_fees is not None else None,
            "apr_note": "proxy only - mock mode" if exec_mode == "mock" else "based on actual exposure"
        },
        
        "performance": {
            "capture_efficiency": round(capture_efficiency, 4),
            "mean_capture_efficiency": round(mean_capture_efficiency, 4),
            "pnl_per_100k_vol": round(pnl_per_100k_vol, 2),
            "mean_out_of_range_pct": round(mean_out_of_range_pct, 2),
            "max_out_of_range_pct": round(max_out_of_range_pct, 2),
            "avg_latency_ms": round(avg_latency_ms, 2),
            "p95_latency_ms": round(p95_latency_ms, 2),
            # ✅ DELIVERABLE 5: Alpha and baseline metrics
            "total_alpha_usd": round(total_alpha_usd, 2),
            "mean_alpha_usd": round(mean_alpha_usd, 2),
            "alpha_win_rate": round(alpha_win_rate, 4),
            "hold_episodes": hold_episodes,
            "rebalance_episodes": rebalance_episodes,
            "mean_gas_cost_usd": round(mean_gas_cost_usd, 2),
            "mean_alpha_per_gas_usd": round(mean_alpha_per_gas_usd, 2) if mean_alpha_per_gas_usd is not None else None,
            # ✅ DELIVERABLE 4: New metrics
            "baseline_policy_win_counts": baseline_policy_win_counts,
            "hold_episode_rate": round(hold_episode_rate, 4),
            "alpha_per_hour_usd": round(alpha_per_hour_usd, 2) if alpha_per_hour_usd is not None else None,
            "alpha_per_rebalance_episode_usd": round(alpha_per_rebalance_episode_usd, 2) if alpha_per_rebalance_episode_usd is not None else None,
            # ✅ DELIVERABLE 5: Regime-stratified metrics
            "episodes_by_regime": dict(episodes_by_regime),
            "alpha_by_regime": alpha_by_regime,
            "baseline_policy_win_counts_by_regime": baseline_policy_win_counts_by_regime,
            "agent_action_rate_by_regime": agent_action_rate_by_regime,
            "mean_gas_by_regime": mean_gas_by_regime,
        },
        
        "episode_table": episode_table
    }
