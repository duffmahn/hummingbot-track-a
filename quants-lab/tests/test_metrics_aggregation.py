"""
Test Metrics Aggregation

Validates that metrics generation works correctly.
"""

import json
import pytest
from pathlib import Path


def find_latest_run_dir():
    """Find the most recent run directory."""
    data_dir = Path(__file__).parent.parent.parent / "data" / "runs"
    
    if not data_dir.exists():
        pytest.skip("No runs directory found")
    
    run_dirs = sorted(data_dir.glob("run_*"), key=lambda p: p.stat().st_mtime, reverse=True)
    
    if not run_dirs:
        pytest.skip("No run directories found")
    
    return run_dirs[0]


class TestMetricsAggregation:
    """Test metrics aggregation functionality."""
    
    @pytest.fixture(scope="class")
    def latest_run_dir(self):
        """Get the latest run directory for all tests."""
        run_dir = find_latest_run_dir()
        print(f"\n✓ Testing metrics for run: {run_dir}")
        return run_dir
    
    def test_metrics_summary_exists(self, latest_run_dir):
        """Verify metrics_summary.json exists."""
        summary_path = latest_run_dir / "metrics_summary.json"
        assert summary_path.exists(), f"Missing metrics_summary.json in {latest_run_dir}"
        
        with open(summary_path) as f:
            summary = json.load(f)
        
        assert isinstance(summary, dict), "metrics_summary.json must be a dict"
        print(f"✓ metrics_summary.json valid")
    
    def test_metrics_summary_required_fields(self, latest_run_dir):
        """Verify metrics_summary.json has all required fields."""
        summary_path = latest_run_dir / "metrics_summary.json"
        
        with open(summary_path) as f:
            summary = json.load(f)
        
        # Identity fields
        assert "run_id" in summary
        assert "generated_at" in summary
        assert "exec_mode" in summary
        
        # Counts
        assert "total_episodes" in summary
        assert "success_count" in summary
        assert "failure_count" in summary
        assert "other_count" in summary
        
        # Totals
        assert "total_pnl_usd" in summary
        assert "total_fees_usd" in summary
        assert "total_gas_cost_usd" in summary
        
        # Averages
        assert "avg_pnl_usd" in summary
        assert "avg_latency_ms" in summary
        assert "avg_quote_ms" in summary
        assert "avg_intel_fresh_pct" in summary
        
        # Hygiene
        assert "intel_missing_or_too_old_total" in summary
        assert "learning_updates_applied_count" in summary
        assert "learning_updates_skipped_count" in summary
        assert "learning_update_reasons_histogram" in summary
        
        print(f"✓ All required fields present")
        print(f"  Total Episodes: {summary['total_episodes']}")
        print(f"  Success: {summary['success_count']}")
        print(f"  Total PnL: ${summary['total_pnl_usd']}")
    
    def test_episode_metrics_exists(self, latest_run_dir):
        """Verify episode_metrics.jsonl exists."""
        metrics_path = latest_run_dir / "episode_metrics.jsonl"
        assert metrics_path.exists(), f"Missing episode_metrics.jsonl in {latest_run_dir}"
        
        with open(metrics_path) as f:
            lines = [line.strip() for line in f if line.strip()]
        
        assert len(lines) >= 1, "episode_metrics.jsonl must have at least one line"
        print(f"✓ episode_metrics.jsonl valid ({len(lines)} episodes)")
    
    def test_episode_metrics_required_fields(self, latest_run_dir):
        """Verify episode_metrics.jsonl lines have required fields."""
        metrics_path = latest_run_dir / "episode_metrics.jsonl"
        
        with open(metrics_path) as f:
            lines = [line.strip() for line in f if line.strip()]
        
        # Parse first line
        episode_metric = json.loads(lines[0])
        
        # Required fields (may be null but must be present)
        required_fields = [
            "run_id", "episode_id", "timestamp", "exec_mode", "pool_address",
            "status", "pnl_usd", "fees_usd", "gas_cost_usd", "reward",
            "latency_ms", "health_check_ms", "pool_info_ms", "quote_ms",
            "simulation_latency_ms", "simulation_gas_estimate", "used_fallback",
            "intel_fresh", "intel_stale", "intel_missing_or_too_old", "intel_fresh_pct",
            "learning_update_applied", "learning_update_reason"
        ]
        
        for field in required_fields:
            assert field in episode_metric, f"Missing field '{field}' in episode metric"
        
        print(f"✓ All required fields present in episode metrics")
        print(f"  Episode: {episode_metric['episode_id']}")
        print(f"  Status: {episode_metric['status']}")
        print(f"  PnL: ${episode_metric.get('pnl_usd', 0)}")
    
    def test_metrics_consistency(self, latest_run_dir):
        """Verify metrics are consistent between summary and episode metrics."""
        summary_path = latest_run_dir / "metrics_summary.json"
        metrics_path = latest_run_dir / "episode_metrics.jsonl"
        
        with open(summary_path) as f:
            summary = json.load(f)
        
        with open(metrics_path) as f:
            lines = [line.strip() for line in f if line.strip()]
        
        # Episode count should match
        assert summary["total_episodes"] == len(lines), \
            f"Episode count mismatch: summary={summary['total_episodes']}, jsonl={len(lines)}"
        
        # Sum of status counts should equal total
        status_sum = summary["success_count"] + summary["failure_count"] + summary["other_count"]
        assert status_sum == summary["total_episodes"], \
            f"Status counts don't sum to total: {status_sum} != {summary['total_episodes']}"
        
        print(f"✓ Metrics are consistent")


if __name__ == "__main__":
    # Allow running directly for local testing
    pytest.main([__file__, "-v"])
