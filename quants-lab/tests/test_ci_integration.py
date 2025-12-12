"""
CI Integration Test for Track A

Validates that a deterministic mock campaign produces all required artifacts
with correct structure, including intel snapshot and hygiene metadata.

This test is designed to run in CI without requiring Dune API keys or Gateway.
"""

import json
import os
from pathlib import Path
import pytest


def find_latest_run_dir():
    """Find the most recent run directory."""
    data_dir = Path(__file__).parent.parent.parent / "data" / "runs"
    
    if not data_dir.exists():
        pytest.fail(
            f"No runs directory found at {data_dir}. "
            "Campaign may not have run. Check CI logs."
        )
    
    run_dirs = sorted(data_dir.glob("run_*"), key=lambda p: p.stat().st_mtime, reverse=True)
    
    if not run_dirs:
        pytest.fail(
            f"No run directories found in {data_dir}. "
            "Campaign completed but created no runs."
        )
    
    return run_dirs[0]


def find_latest_episode_dir(run_dir: Path):
    """Find the most recent episode directory in a run."""
    episodes_dir = run_dir / "episodes"
    
    if not episodes_dir.exists():
        pytest.fail(
            f"No episodes directory found in {run_dir}. "
            "Run directory exists but has no episodes."
        )
    
    episode_dirs = sorted(
        episodes_dir.glob("ep_*"),
        key=lambda p: p.stat().st_mtime,
        reverse=True
    )
    
    if not episode_dirs:
        pytest.fail(
            f"No episode directories found in {episodes_dir}. "
            "Episodes directory exists but is empty."
        )
    
    return episode_dirs[0]


class TestCIIntegration:
    """CI integration tests for Track A productionization sprint."""
    
    @pytest.fixture(scope="class")
    def latest_episode_dir(self):
        """Get the latest episode directory for all tests."""
        run_dir = find_latest_run_dir()
        episode_dir = find_latest_episode_dir(run_dir)
        print(f"\n✓ Testing episode: {episode_dir}")
        return episode_dir
    
    def test_proposal_exists(self, latest_episode_dir):
        """Verify proposal.json exists."""
        proposal_path = latest_episode_dir / "proposal.json"
        assert proposal_path.exists(), f"Missing proposal.json in {latest_episode_dir}"
        
        # Validate it's valid JSON
        with open(proposal_path) as f:
            proposal = json.load(f)
        
        assert isinstance(proposal, dict), "proposal.json must be a dict"
        assert "pool_address" in proposal, "proposal must have pool_address"
        print(f"✓ proposal.json valid (pool: {proposal.get('pool_address', 'N/A')[:10]}...)")
    
    def test_metadata_exists(self, latest_episode_dir):
        """Verify metadata.json exists and has required structure."""
        metadata_path = latest_episode_dir / "metadata.json"
        assert metadata_path.exists(), f"Missing metadata.json in {latest_episode_dir}"
        
        with open(metadata_path) as f:
            metadata = json.load(f)
        
        assert isinstance(metadata, dict), "metadata.json must be a dict"
        assert "episode_id" in metadata, "metadata must have episode_id"
        assert "run_id" in metadata, "metadata must have run_id"
        print(f"✓ metadata.json valid (episode: {metadata.get('episode_id', 'N/A')})")
    
    def test_result_or_failure_exists(self, latest_episode_dir):
        """Verify either result.json or failure.json exists."""
        result_path = latest_episode_dir / "result.json"
        failure_path = latest_episode_dir / "failure.json"
        
        has_result = result_path.exists()
        has_failure = failure_path.exists()
        
        assert has_result or has_failure, (
            f"Neither result.json nor failure.json found in {latest_episode_dir}. "
            "Episode must produce one of these artifacts."
        )
        
        if has_result:
            with open(result_path) as f:
                result = json.load(f)
            assert isinstance(result, dict), "result.json must be a dict"
            print(f"✓ result.json exists (status: {result.get('status', 'N/A')})")
        
        if has_failure:
            with open(failure_path) as f:
                failure = json.load(f)
            print(f"⚠️  failure.json exists: {failure.get('error', 'Unknown error')}")
    
    def test_intel_snapshot_present(self, latest_episode_dir):
        """Verify metadata contains extra.intel_snapshot (optional in mock mode)."""
        metadata_path = latest_episode_dir / "metadata.json"
        
        with open(metadata_path) as f:
            metadata = json.load(f)
        
        # Check extra field exists
        assert "extra" in metadata, "metadata must have 'extra' field"
        extra = metadata["extra"]
        assert isinstance(extra, dict), "metadata.extra must be a dict"
        
        # Intel snapshot is optional in mock mode (scheduler not running)
        # Just verify structure if present
        if "intel_snapshot" in extra:
            intel_snapshot = extra["intel_snapshot"]
            assert isinstance(intel_snapshot, dict), "intel_snapshot must be a dict"
            print(f"✓ Intel snapshot present with {len(intel_snapshot)} queries")
        else:
            print(f"⚠️  Intel snapshot not present (expected in mock mode without scheduler)")
    
    def test_intel_hygiene_present(self, latest_episode_dir):
        """Verify metadata contains extra.intel_hygiene (optional in mock mode)."""
        metadata_path = latest_episode_dir / "metadata.json"
        
        with open(metadata_path) as f:
            metadata = json.load(f)
        
        extra = metadata.get("extra", {})
        
        # Intel hygiene is optional in mock mode (scheduler not running)
        if "intel_hygiene" not in extra:
            print(f"⚠️  Intel hygiene not present (expected in mock mode without scheduler)")
            return
        
        hygiene = extra["intel_hygiene"]
        assert isinstance(hygiene, dict), "intel_hygiene must be a dict"
        
        # Verify required fields if present
        required_fields = ["total_queries", "fresh", "stale", "missing_or_too_old", "fresh_pct"]
        for field in required_fields:
            assert field in hygiene, f"intel_hygiene must have '{field}' field"
        
        # Verify types
        assert isinstance(hygiene["total_queries"], int), "total_queries must be int"
        assert isinstance(hygiene["fresh"], int), "fresh must be int"
        assert isinstance(hygiene["stale"], int), "stale must be int"
        assert isinstance(hygiene["missing_or_too_old"], int), "missing_or_too_old must be int"
        assert isinstance(hygiene["fresh_pct"], (int, float)), "fresh_pct must be numeric"
        
        print(f"✓ intel_hygiene valid:")
        print(f"  Total queries: {hygiene['total_queries']}")
        print(f"  Fresh: {hygiene['fresh']}")
        print(f"  Fresh %: {hygiene['fresh_pct']}")
    
    def test_intel_snapshot_structure(self, latest_episode_dir):
        """Verify intel_snapshot entries have correct quality metadata structure (if present)."""
        metadata_path = latest_episode_dir / "metadata.json"
        
        with open(metadata_path) as f:
            metadata = json.load(f)
        
        extra = metadata.get("extra", {})
        intel_snapshot = extra.get("intel_snapshot", {})
        
        # Skip if not present (mock mode)
        if not intel_snapshot:
            print(f"⚠️  Intel snapshot empty (expected in mock mode)")
            return
        
        # Check at least one entry has proper structure
        sample_key = list(intel_snapshot.keys())[0]
        sample_entry = intel_snapshot[sample_key]
        
        assert isinstance(sample_entry, dict), f"Intel entry '{sample_key}' must be a dict"
        assert "quality" in sample_entry, f"Intel entry must have 'quality' field"
        
        # Quality should be one of: fresh, stale, too_old, missing
        valid_qualities = ["fresh", "stale", "too_old", "missing"]
        assert sample_entry["quality"] in valid_qualities, (
            f"Quality must be one of {valid_qualities}, got: {sample_entry['quality']}"
        )
        
        print(f"✓ Intel snapshot structure valid (sample: {sample_key} = {sample_entry['quality']})")


if __name__ == "__main__":
    # Allow running directly for local testing
    pytest.main([__file__, "-v"])
