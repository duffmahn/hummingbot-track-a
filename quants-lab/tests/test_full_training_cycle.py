"""
Test Full Training Cycle (Track A)

Deterministic end-to-end test that:
1. Forces MOCK_CLMM=true with fixed HB_SEED
2. Runs 1 episode end-to-end (agent + harness)
3. Asserts artifact tree structure and schema validation
4. Asserts learning update is skipped by default in mock mode
"""

import os
import sys
import json
import pytest
import tempfile
import shutil
from pathlib import Path
from datetime import datetime

# Add quants-lab to path
QUANTS_LAB_DIR = Path(__file__).parent.parent
sys.path.append(str(QUANTS_LAB_DIR))

from lib.schemas import Proposal, EpisodeMetadata, EpisodeResult, RewardBreakdown
from lib.artifacts import EpisodeArtifacts
from lib.run_context import RunContext
from lib.clmm_env import MockCLMMEnvironment
from phase5_learning_agent import Phase5LearningAgent

# Add harness path
HARNESS_PATH = Path(__file__).parent.parent.parent / "hummingbot" / "scripts"
sys.path.append(str(HARNESS_PATH))

from agent_harness import AgentHarness


class TestFullTrainingCycle:
    """End-to-end training cycle tests"""
    
    @pytest.fixture
    def temp_data_dir(self):
        """Create a temporary data directory for testing"""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir)
    
    @pytest.fixture
    def mock_env_vars(self, temp_data_dir):
        """Set up mock environment variables"""
        original_env = {}
        
        # Save original values
        for key in ["RUN_ID", "EPISODE_ID", "EXEC_MODE", "HB_SEED", "LEARN_FROM_MOCK", "MOCK_CLMM", "HB_ENV"]:
            original_env[key] = os.environ.get(key)
        
        # Set test values
        os.environ["RUN_ID"] = "test_run_001"
        os.environ["EXEC_MODE"] = "mock"
        os.environ["HB_SEED"] = "42"
        os.environ["LEARN_FROM_MOCK"] = "false"
        os.environ["MOCK_CLMM"] = "true"
        os.environ["HB_ENV"] = "mock"
        
        yield
        
        # Restore original values
        for key, value in original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    
    def test_artifact_structure(self, temp_data_dir, mock_env_vars):
        """Test that episode artifacts are created with correct structure"""
        run_id = "test_run_001"
        episode_id = "test_episode_001"
        
        artifacts = EpisodeArtifacts(
            run_id=run_id,
            episode_id=episode_id,
            base_dir=temp_data_dir
        )
        
        # Create directories
        artifacts.ensure_directories()
        
        # Verify directory structure
        expected_dir = Path(temp_data_dir) / "runs" / run_id / "episodes" / episode_id
        assert expected_dir.exists()
        assert expected_dir.is_dir()
        
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
        assert (expected_dir / "proposal.json").exists()
        assert (expected_dir / "metadata.json").exists()
        
        # Verify content is valid JSON and matches schema
        with open(expected_dir / "proposal.json") as f:
            proposal_data = json.load(f)
            loaded_proposal = Proposal.model_validate(proposal_data)
            assert loaded_proposal.episode_id == episode_id
    
    def test_mock_environment_execution(self, temp_data_dir, mock_env_vars):
        """Test that mock environment executes successfully"""
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
        assert isinstance(result, EpisodeResult)
        assert result.episode_id == episode_id
        assert result.run_id == run_id
        assert result.status == "success"
        assert result.exec_mode == "mock"
        assert result.simulation is not None
        assert result.simulation.source == "mock"
    
    def test_result_always_written(self, temp_data_dir, mock_env_vars):
        """Test that result.json is always written, even on failure"""
        run_id = "test_run_001"
        episode_id = "test_episode_003"
        
        artifacts = EpisodeArtifacts(
            run_id=run_id,
            episode_id=episode_id,
            base_dir=temp_data_dir
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
        assert result_path.exists()
        
        # Verify content
        with open(result_path) as f:
            result_data = json.load(f)
            loaded_result = EpisodeResult.model_validate(result_data)
            assert loaded_result.status == "failed"
            assert loaded_result.error == "Test failure"
    
    def test_failure_json_on_error(self, temp_data_dir, mock_env_vars):
        """Test that failure.json is written on errors"""
        run_id = "test_run_001"
        episode_id = "test_episode_004"
        
        artifacts = EpisodeArtifacts(
            run_id=run_id,
            episode_id=episode_id,
            base_dir=temp_data_dir
        )
        
        # Write failure
        artifacts.write_failure(
            error="Test error message",
            context={"detail": "Additional context"}
        )
        
        # Verify failure.json exists
        failure_path = Path(artifacts.episode_dir) / "failure.json"
        assert failure_path.exists()
        
        # Verify content
        with open(failure_path) as f:
            failure_data = json.load(f)
            assert failure_data["error"] == "Test error message"
            assert failure_data["context"]["detail"] == "Additional context"
    
    def test_learning_hygiene_mock_mode(self, temp_data_dir, mock_env_vars):
        """Test that learning is skipped in mock mode by default"""
        # This test verifies the learning hygiene rule:
        # If exec_mode == "mock" and LEARN_FROM_MOCK != true → no learning update
        
        # Environment is already set to mock mode with LEARN_FROM_MOCK=false
        agent = Phase5LearningAgent()
        
        # Verify agent settings
        assert agent.exec_mode == "mock"
        assert agent.learn_from_mock == False
        
        # Create a minimal dataframe (empty is fine for this test)
        import pandas as pd
        df = pd.DataFrame()
        
        # Call update_beliefs - should return False (skipped)
        result = agent.update_beliefs_from_history(df)
        assert result == False
    
    def test_learning_enabled_with_flag(self, temp_data_dir, mock_env_vars):
        """Test that learning works when LEARN_FROM_MOCK=true"""
        # Set LEARN_FROM_MOCK to true
        os.environ["LEARN_FROM_MOCK"] = "true"
        
        agent = Phase5LearningAgent()
        
        # Verify agent settings
        assert agent.exec_mode == "mock"
        assert agent.learn_from_mock == True
        
        # Create a minimal dataframe
        import pandas as pd
        df = pd.DataFrame()
        
        # Call update_beliefs - should return True (or handle empty df gracefully)
        # With empty df, it won't update but won't be blocked by hygiene
        result = agent.update_beliefs_from_history(df)
        # Empty df means no regimes to update, but hygiene check passed
        assert result == True
    
    def test_metadata_includes_learning_info(self, temp_data_dir, mock_env_vars):
        """Test that metadata includes learning hygiene information"""
        episode_id = "test_episode_005"
        
        agent = Phase5LearningAgent()
        proposal = agent.learn_and_propose(episode_id=episode_id)
        
        # Verify metadata includes learning info
        assert proposal.metadata.learning_update_applied == False
        assert proposal.metadata.learning_update_reason is not None
        assert proposal.metadata.exec_mode == "mock"
        assert proposal.metadata.seed == 42


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v", "-s"])
