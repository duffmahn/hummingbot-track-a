"""
Test Metrics Aggregation

Validates that metrics generation works correctly.
"""

import json
import os
import pytest
import subprocess
import tempfile
import sys
from pathlib import Path


def find_latest_run_dir():
    """Find the most recent run directory."""
    data_dir = Path(__file__).parent.parent.parent / "data" / "runs"
    
    if not data_dir.exists():
        pytest.skip("No runs directory found")
    
    # Sort by mtime, considering all directories that look like runs
    run_dirs = sorted(
        [d for d in data_dir.iterdir() if d.is_dir() and not d.name.startswith(".")],
        key=lambda p: p.stat().st_mtime, 
        reverse=True
    )
    
    if not run_dirs:
        pytest.skip("No run directories found")
    
    return run_dirs[0]


class TestMetricsAggregation:
    """Test metrics aggregation functionality."""
    
    @pytest.fixture(scope="class")
    def latest_run_dir(self):
        """Create a temporary run with mock data for testing."""
        # Use a temporary directory that persists for the class scope
        # Note: In pytest class fixture, we can't easily use tempfile.TemporaryDirectory 
        # as a context manager if we want to yield. We'll use mkdtemp.
        import shutil
        
        tmpdir = Path(tempfile.mkdtemp())
        try:
            run_dir = tmpdir / "mock_run_123"
            run_dir.mkdir()
            episodes_dir = run_dir / "episodes"
            episodes_dir.mkdir()
            
            # Create a mock episode
            episode_dir = episodes_dir / "ep_001"
            episode_dir.mkdir()
            
            # Metadata
            metadata = {
                "episode_id": "ep_001",
                "run_id": "mock_run_123",
                "timestamp": "2025-12-12T12:00:00Z",
                "status": "success",
                "exec_mode": "mock",
                "extra": {
                    "intel_hygiene": {
                        "fresh": 10, "stale": 0, "missing_or_too_old": 0, "fresh_pct": 1.0
                    }
                },
                "learning_update_applied": True,
                "learning_update_reason": "test"
            }
            (episode_dir / "metadata.json").write_text(json.dumps(metadata))
            
            # Result
            result = {
                "episode_id": "ep_001",
                "status": "success",
                "pnl_usd": 50.0,
                "fees_usd": 5.0,
                "gas_cost_usd": 1.0,
                "fees_0": 2.5,
                "fees_1": 2.5,
                "pool_fees_usd_input_based": 100.0,
                "pool_fees_usd_amount_usd_based": 200.0,
                "pool_fees_usd_two_sided_volume_based": 200.0, # Expecting ~2x
                "timings_ms": {"quote_ms": 10, "pool_info_ms": 10}
            }
            (episode_dir / "result.json").write_text(json.dumps(result))
            
            # Proposal
            proposal = {"pool_address": "0x123"}
            (episode_dir / "proposal.json").write_text(json.dumps(proposal))
            
            # Run aggregation script
            script_path = Path(__file__).parent.parent / "scripts" / "build_run_metrics.py"
            subprocess.run(
                [sys.executable, str(script_path), "--runs-dir", str(tmpdir), "--run-id", "mock_run_123", "--quiet"],
                check=True
            )
            
            yield run_dir
            
        finally:
            shutil.rmtree(tmpdir)
    
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
        
        # Nested structures (ROI-aware)
        assert "totals" in summary
        assert "performance" in summary
        assert "capital_assumptions" in summary
        
        totals = summary["totals"]
        
        # Counts
        assert "episodes_total" in totals
        assert "episodes_success" in totals
        
        # Totals
        assert "total_pnl_usd" in totals
        assert "total_fees_usd" in totals
        assert "total_fees_0" in totals
        assert "total_fees_1" in totals
        
        print(f"✓ All required fields present")
        print(f"  Total Episodes: {totals['episodes_total']}")
        print(f"  Success: {totals['episodes_success']}")
        print(f"  Total PnL: ${totals['total_pnl_usd']}")
    
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
            "run_id", "episode_id", "timestamp", "status", 
            "pnl_usd", "fees_usd", "gas_cost_usd",
            "fees_0", "fees_1", "pool_fees_usd_input_based", "pool_fees_usd_amount_usd_based"
        ]
        
        for field in required_fields:
            assert field in episode_metric, f"Missing field '{field}' in episode metric"
        
        assert episode_metric["fees_0"] == 2.5
        assert episode_metric["fees_1"] == 2.5
        
        print(f"✓ All required fields present in episode metrics")
    
    def test_metrics_consistency(self, latest_run_dir):
        """Verify metrics are consistent between summary and episode metrics."""
        summary_path = latest_run_dir / "metrics_summary.json"
        metrics_path = latest_run_dir / "episode_metrics.jsonl"
        
        with open(summary_path) as f:
            summary = json.load(f)
        
        with open(metrics_path) as f:
            lines = [line.strip() for line in f if line.strip()]
        
        # Episode count should match
        assert summary["totals"]["episodes_total"] == len(lines), \
            f"Episode count mismatch: summary={summary['totals']['episodes_total']}, jsonl={len(lines)}"
        
        print(f"✓ Metrics are consistent")


class TestLatestRunSelection:
    """Test CLI's latest run selection functionality."""
    
    def test_cli_selects_latest_run(self):
        """Verify CLI auto-selects the newest run by mtime."""
        with tempfile.TemporaryDirectory() as tmpdir:
            runs_dir = Path(tmpdir) / "runs"
            runs_dir.mkdir()
            
            # Create two fake runs
            run_older = runs_dir / "run_older"
            run_newer = runs_dir / "run_newer"
            run_older.mkdir()
            run_newer.mkdir()
            
            # Create minimal episode artifacts for both
            for run_dir in [run_older, run_newer]:
                episodes_dir = run_dir / "episodes"
                episodes_dir.mkdir()
                episode_dir = episodes_dir / "ep_001"
                episode_dir.mkdir()
                
                # Create minimal metadata
                metadata = {
                    "episode_id": "episode_001",
                    "status": "success",
                    "timestamp": "2025-12-12T16:00:00Z",
                    "exec_mode": "MOCK"
                }
                (episode_dir / "metadata.json").write_text(json.dumps(metadata))
                
                # Create result.json (REQUIRED for aggregator)
                result_data = {
                    "episode_id": "episode_001",
                    "status": "success",
                    "pnl_usd": 100.0,
                    "fees_usd": 10.0,
                    "fees_0": 5.0,
                    "fees_1": 5.0,
                    "pool_fees_usd_input_based": 1000.0,
                    "pool_fees_usd_amount_usd_based": 1000.0,
                    "gas_cost_usd": 0.5,
                    "timestamp": "2025-12-12T16:00:00Z"
                }
                (episode_dir / "result.json").write_text(json.dumps(result_data))

                # Create minimal reward
                reward = {"pnl_usd": 100.0, "fees_usd": 10.0}
                (episode_dir / "reward.json").write_text(json.dumps(reward))
            
            # Set deterministic mtimes: older = 1000, newer = 2000
            os.utime(run_older, (1000, 1000))
            os.utime(run_newer, (2000, 2000))
            
            # Run CLI without --run-id
            script_path = Path(__file__).parent.parent / "scripts" / "build_run_metrics.py"
            result = subprocess.run(
                [sys.executable, str(script_path), "--runs-dir", str(runs_dir), "--quiet"],
                capture_output=True,
                text=True
            )
            
            # Should succeed
            assert result.returncode == 0, f"CLI failed: {result.stderr}"
            
            # Should have generated metrics for run_newer
            assert (run_newer / "metrics_summary.json").exists()
            assert (run_newer / "episode_metrics.jsonl").exists()
            
            # Verify content has new fields
            with open(run_newer / "episode_metrics.jsonl") as f:
                ep_metric = json.loads(f.readline())
            assert "fees_0" in ep_metric
            assert "pool_fees_usd_amount_usd_based" in ep_metric
            assert ep_metric["fees_0"] == 5.0
            
            # Should NOT have generated metrics for run_older
            assert not (run_older / "metrics_summary.json").exists()
            
            print(f"✓ CLI correctly selected newest run")
    
    def test_cli_explicit_run_id_overrides_latest(self):
        """Verify explicit --run-id overrides latest selection."""
        with tempfile.TemporaryDirectory() as tmpdir:
            runs_dir = Path(tmpdir) / "runs"
            runs_dir.mkdir()
            
            # Create two fake runs
            run_older = runs_dir / "run_older"
            run_newer = runs_dir / "run_newer"
            run_older.mkdir()
            run_newer.mkdir()
            
            # Create minimal episode artifacts for both
            for run_dir in [run_older, run_newer]:
                episodes_dir = run_dir / "episodes"
                episodes_dir.mkdir()
                episode_dir = episodes_dir / "ep_001"
                episode_dir.mkdir()
                
                metadata = {
                    "episode_id": "episode_001",
                    "status": "success",
                    "timestamp": "2025-12-12T16:00:00Z",
                    "exec_mode": "MOCK"
                }
                (episode_dir / "metadata.json").write_text(json.dumps(metadata))
                
                # Create result.json
                result_data = {
                    "episode_id": "episode_001",
                    "status": "success",
                    "pnl_usd": 100.0,
                    "fees_usd": 10.0,
                    "fees_0": 5.0,
                    "fees_1": 5.0,
                    "pool_fees_usd_input_based": 1000.0,
                    "pool_fees_usd_amount_usd_based": 1000.0,
                    "gas_cost_usd": 0.5,
                    "timestamp": "2025-12-12T16:00:00Z"
                }
                (episode_dir / "result.json").write_text(json.dumps(result_data))
                
                reward = {"pnl_usd": 100.0, "fees_usd": 10.0}
                (episode_dir / "reward.json").write_text(json.dumps(reward))
            
            # Set mtimes
            os.utime(run_older, (1000, 1000))
            os.utime(run_newer, (2000, 2000))
            
            # Run CLI with explicit --run-id for older run
            script_path = Path(__file__).parent.parent / "scripts" / "build_run_metrics.py"
            result = subprocess.run(
                [sys.executable, str(script_path), "--runs-dir", str(runs_dir), 
                 "--run-id", "run_older", "--quiet"],
                capture_output=True,
                text=True
            )
            
            # Should succeed
            assert result.returncode == 0, f"CLI failed: {result.stderr}"
            
            # Should have generated metrics for run_older
            assert (run_older / "metrics_summary.json").exists()
            assert (run_older / "episode_metrics.jsonl").exists()
            
            # Should NOT have generated metrics for run_newer
            assert not (run_newer / "metrics_summary.json").exists()
            
            print(f"✓ Explicit --run-id correctly overrides latest selection")
    
    def test_cli_no_runs_error(self):
        """Verify CLI exits with error when no runs exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            runs_dir = Path(tmpdir) / "runs"
            runs_dir.mkdir()
            
            # Empty runs directory
            script_path = Path(__file__).parent.parent / "scripts" / "build_run_metrics.py"
            result = subprocess.run(
                [sys.executable, str(script_path), "--runs-dir", str(runs_dir)],
                capture_output=True,
                text=True
            )
            
            # Should fail
            assert result.returncode != 0, "CLI should fail when no runs exist"
            
            # Should have clear error message
            assert "No run directories found" in result.stdout or "No run directories found" in result.stderr
            
            print(f"✓ CLI correctly errors when no runs exist")


if __name__ == "__main__":
    # Allow running directly for local testing
    pytest.main([__file__, "-v"])

