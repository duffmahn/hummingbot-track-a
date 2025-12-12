#!/usr/bin/env python3
"""
Manual Test Script for Track A Full Training Cycle
Runs without pytest dependency
"""

import os
import sys
import json
import tempfile
import shutil
from pathlib import Path
from datetime import datetime

# Add quants-lab to path
QUANTS_LAB_DIR = Path(__file__).parent.parent
sys.path.append(str(QUANTS_LAB_DIR))

from lib.schemas import Proposal, EpisodeMetadata, EpisodeResult
from lib.artifacts import EpisodeArtifacts
from lib.run_context import RunContext
from lib.clmm_env import MockCLMMEnvironment

def test_artifact_structure():
    """Test that episode artifacts are created with correct structure"""
    print("\n🧪 Test: Artifact Structure")
    
    temp_dir = tempfile.mkdtemp()
    try:
        run_id = "test_run_001"
        episode_id = "test_episode_001"
        
        artifacts = EpisodeArtifacts(
            run_id=run_id,
            episode_id=episode_id,
            base_dir=temp_dir
        )
        
        # Create directories
        artifacts.ensure_directories()
        
        # Verify directory structure
        expected_dir = Path(temp_dir) / "runs" / run_id / "episodes" / episode_id
        assert expected_dir.exists(), f"Episode directory not created: {expected_dir}"
        
        # Write test artifacts
        test_proposal = Proposal(
            episode_id=episode_id,
            generated_at=datetime.utcnow().isoformat() + "Z",
            status="active",
            connector_execution="uniswap_v3_clmm",
            chain="ethereum",
            network="mainnet",
            params={"width_pts": 200},
            metadata=EpisodeMetadata(
                episode_id=episode_id,
                run_id=run_id,
                config_hash="test_hash",
                agent_version="test_v1",
                exec_mode="mock",
                seed=42
            )
        )
        
        artifacts.write_proposal(test_proposal)
        artifacts.write_metadata(test_proposal.metadata)
        
        # Verify files exist
        assert (expected_dir / "proposal.json").exists(), "proposal.json not created"
        assert (expected_dir / "metadata.json").exists(), "metadata.json not created"
        
        # Verify content is valid JSON and matches schema
        with open(expected_dir / "proposal.json") as f:
            proposal_data = json.load(f)
            loaded_proposal = Proposal.model_validate(proposal_data)
            assert loaded_proposal.episode_id == episode_id
        
        print("✅ PASS: Artifact structure test")
        return True
        
    except Exception as e:
        print(f"❌ FAIL: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        shutil.rmtree(temp_dir)

def test_mock_environment_execution():
    """Test that mock environment executes successfully"""
    print("\n🧪 Test: Mock Environment Execution")
    
    try:
        run_id = "test_run_001"
        episode_id = "test_episode_002"
        
        # Create proposal
        proposal = Proposal(
            episode_id=episode_id,
            generated_at=datetime.utcnow().isoformat() + "Z",
            status="active",
            connector_execution="uniswap_v3_clmm",
            chain="ethereum",
            network="mainnet",
            pool_address="0xtest",
            params={"width_pts": 200},
            metadata=EpisodeMetadata(
                episode_id=episode_id,
                run_id=run_id,
                config_hash="test_hash",
                agent_version="test_v1",
                exec_mode="mock",
                seed=42
            )
        )
        
        # Create context
        ctx = RunContext(
            run_id=run_id,
            episode_id=episode_id,
            config_hash="test_hash",
            agent_version="test_v1",
            exec_mode="mock",
            seed=42,
            started_at=datetime.utcnow().isoformat() + "Z"
        )
        
        # Execute in mock environment
        env = MockCLMMEnvironment(seed=42)
        result = env.execute_episode(proposal, ctx)
        
        # Verify result
        assert isinstance(result, EpisodeResult), "Result is not EpisodeResult"
        assert result.episode_id == episode_id, f"Episode ID mismatch: {result.episode_id}"
        assert result.run_id == run_id, f"Run ID mismatch: {result.run_id}"
        assert result.status == "success", f"Status not success: {result.status}"
        assert result.exec_mode == "mock", f"Exec mode not mock: {result.exec_mode}"
        assert result.simulation is not None, "Simulation is None"
        assert result.simulation.source == "mock", f"Simulation source not mock: {result.simulation.source}"
        
        print("✅ PASS: Mock environment execution test")
        return True
        
    except Exception as e:
        print(f"❌ FAIL: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_result_always_written():
    """Test that result.json is always written, even on failure"""
    print("\n🧪 Test: Result Always Written")
    
    temp_dir = tempfile.mkdtemp()
    try:
        run_id = "test_run_001"
        episode_id = "test_episode_003"
        
        artifacts = EpisodeArtifacts(
            run_id=run_id,
            episode_id=episode_id,
            base_dir=temp_dir
        )
        
        # Write a failed result
        failed_result = EpisodeResult(
            episode_id=episode_id,
            run_id=run_id,
            status="failed",
            exec_mode="mock",
            error="Test failure"
        )
        
        artifacts.write_result(failed_result)
        
        # Verify result.json exists
        result_path = Path(artifacts.episode_dir) / "result.json"
        assert result_path.exists(), "result.json not created"
        
        # Verify content
        with open(result_path) as f:
            result_data = json.load(f)
            loaded_result = EpisodeResult.model_validate(result_data)
            assert loaded_result.status == "failed", f"Status not failed: {loaded_result.status}"
            assert loaded_result.error == "Test failure", f"Error mismatch: {loaded_result.error}"
        
        print("✅ PASS: Result always written test")
        return True
        
    except Exception as e:
        print(f"❌ FAIL: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        shutil.rmtree(temp_dir)

def test_failure_json_on_error():
    """Test that failure.json is written on errors"""
    print("\n🧪 Test: Failure JSON on Error")
    
    temp_dir = tempfile.mkdtemp()
    try:
        run_id = "test_run_001"
        episode_id = "test_episode_004"
        
        artifacts = EpisodeArtifacts(
            run_id=run_id,
            episode_id=episode_id,
            base_dir=temp_dir
        )
        
        # Write failure
        artifacts.write_failure(
            error="Test error message",
            context={"detail": "Additional context"}
        )
        
        # Verify failure.json exists
        failure_path = Path(artifacts.episode_dir) / "failure.json"
        assert failure_path.exists(), "failure.json not created"
        
        # Verify content
        with open(failure_path) as f:
            failure_data = json.load(f)
            assert failure_data["error"] == "Test error message", f"Error mismatch: {failure_data['error']}"
            assert failure_data["context"]["detail"] == "Additional context", f"Context mismatch"
        
        print("✅ PASS: Failure JSON on error test")
        return True
        
    except Exception as e:
        print(f"❌ FAIL: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        shutil.rmtree(temp_dir)

def main():
    """Run all tests"""
    print("=" * 60)
    print("Track A: Full Training Cycle Tests")
    print("=" * 60)
    
    tests = [
        test_artifact_structure,
        test_mock_environment_execution,
        test_result_always_written,
        test_failure_json_on_error,
    ]
    
    results = []
    for test in tests:
        results.append(test())
    
    print("\n" + "=" * 60)
    print(f"Results: {sum(results)}/{len(results)} tests passed")
    print("=" * 60)
    
    if all(results):
        print("\n🎉 All tests passed!")
        return 0
    else:
        print("\n❌ Some tests failed")
        return 1

if __name__ == "__main__":
    sys.exit(main())
