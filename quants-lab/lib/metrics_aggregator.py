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
        
        # Timings
        timings_ms = result.get("timings_ms", {}) if result else {}
        health_check_ms = timings_ms.get("health_check_ms")
        pool_info_ms = timings_ms.get("pool_info_ms")
        quote_ms = timings_ms.get("quote_ms")
        
        # Simulation metrics
        simulation = result.get("simulation", {}) if result else {}
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
