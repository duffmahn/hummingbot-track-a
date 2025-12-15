#!/usr/bin/env python3
"""
Standalone CI Test for Phase 7.1 - Latest Run Selection

Tests the build_run_metrics.py CLI without requiring pytest.
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def test_auto_select_latest_run():
    """Test that CLI auto-selects the newest run by mtime."""
    print("Test 1: Auto-select latest run...")
    
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
            episode_dir = run_dir / "episode_001"
            episode_dir.mkdir()
            
            # Create minimal metadata
            metadata = {
                "episode_id": "episode_001",
                "status": "success",
                "timestamp": "2025-12-12T16:00:00Z",
                "exec_mode": "MOCK"
            }
            (episode_dir / "metadata.json").write_text(json.dumps(metadata))
            
            # Create minimal reward
            reward = {"pnl_usd": 100.0, "fees_usd": 10.0}
            (episode_dir / "reward.json").write_text(json.dumps(reward))
        
        # Set deterministic mtimes: older = 1000, newer = 2000
        os.utime(run_older, (1000, 1000))
        os.utime(run_newer, (2000, 2000))
        
        # Run CLI without --run-id
        script_path = Path(__file__).parent.parent / "scripts" / "build_run_metrics.py"
        result = subprocess.run(
            ["python3", str(script_path), "--runs-dir", str(runs_dir), "--quiet"],
            capture_output=True,
            text=True
        )
        
        # Should succeed
        assert result.returncode == 0, f"CLI failed: {result.stderr}"
        
        # Should have generated metrics for run_newer
        assert (run_newer / "metrics_summary.json").exists(), "metrics_summary.json not created for newer run"
        assert (run_newer / "episode_metrics.jsonl").exists(), "episode_metrics.jsonl not created for newer run"
        
        # Should NOT have generated metrics for run_older
        assert not (run_older / "metrics_summary.json").exists(), "metrics_summary.json incorrectly created for older run"
        
        print("✅ Test 1 PASSED: CLI correctly selected newest run")
        return True


def test_explicit_run_id_override():
    """Test that explicit --run-id overrides latest selection."""
    print("\nTest 2: Explicit run ID override...")
    
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
            episode_dir = run_dir / "episode_001"
            episode_dir.mkdir()
            
            metadata = {
                "episode_id": "episode_001",
                "status": "success",
                "timestamp": "2025-12-12T16:00:00Z",
                "exec_mode": "MOCK"
            }
            (episode_dir / "metadata.json").write_text(json.dumps(metadata))
            
            reward = {"pnl_usd": 100.0, "fees_usd": 10.0}
            (episode_dir / "reward.json").write_text(json.dumps(reward))
        
        # Set mtimes
        os.utime(run_older, (1000, 1000))
        os.utime(run_newer, (2000, 2000))
        
        # Run CLI with explicit --run-id for older run
        script_path = Path(__file__).parent.parent / "scripts" / "build_run_metrics.py"
        result = subprocess.run(
            ["python3", str(script_path), "--runs-dir", str(runs_dir), 
             "--run-id", "run_older", "--quiet"],
            capture_output=True,
            text=True
        )
        
        # Should succeed
        assert result.returncode == 0, f"CLI failed: {result.stderr}"
        
        # Should have generated metrics for run_older
        assert (run_older / "metrics_summary.json").exists(), "metrics_summary.json not created for older run"
        
        # Should NOT have generated metrics for run_newer
        assert not (run_newer / "metrics_summary.json").exists(), "metrics_summary.json incorrectly created for newer run"
        
        print("✅ Test 2 PASSED: Explicit --run-id correctly overrides latest selection")
        return True


def test_no_runs_error():
    """Test that CLI exits with error when no runs exist."""
    print("\nTest 3: No runs error handling...")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        runs_dir = Path(tmpdir) / "runs"
        runs_dir.mkdir()
        
        # Empty runs directory
        script_path = Path(__file__).parent.parent / "scripts" / "build_run_metrics.py"
        result = subprocess.run(
            ["python3", str(script_path), "--runs-dir", str(runs_dir)],
            capture_output=True,
            text=True
        )
        
        # Should fail
        assert result.returncode != 0, "CLI should fail when no runs exist"
        
        # Should have clear error message
        assert "No run directories found" in result.stdout or "No run directories found" in result.stderr, \
            "Missing clear error message"
        
        print("✅ Test 3 PASSED: CLI correctly errors when no runs exist")
        return True


def main():
    """Run all tests."""
    print("=" * 60)
    print("Phase 7.1 CI Test - Latest Run Selection")
    print("=" * 60)
    
    tests = [
        test_auto_select_latest_run,
        test_explicit_run_id_override,
        test_no_runs_error
    ]
    
    passed = 0
    failed = 0
    
    for test_func in tests:
        try:
            if test_func():
                passed += 1
        except AssertionError as e:
            print(f"❌ {test_func.__name__} FAILED: {e}")
            failed += 1
        except Exception as e:
            print(f"❌ {test_func.__name__} ERROR: {e}")
            failed += 1
    
    print("\n" + "=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)
    
    if failed > 0:
        sys.exit(1)
    else:
        print("\n✅ All tests PASSED!")
        sys.exit(0)


if __name__ == "__main__":
    main()
