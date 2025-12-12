#!/usr/bin/env python3
"""
Pool Configuration Validator for Track A

Validates pool_address, chain, network before episode execution (real mode only).
Writes failure artifacts if validation fails.
"""

import os
import sys
from typing import Dict, Tuple, Optional
from pathlib import Path

# Add quants-lab to path
QUANTS_LAB_DIR = Path(__file__).parent.parent
sys.path.append(str(QUANTS_LAB_DIR))

from schemas.contracts import Proposal

# Recognized chains and networks
VALID_CHAINS = {
    "ethereum": ["mainnet", "sepolia"],
    "arbitrum": ["mainnet"],
    "optimism": ["mainnet"],
    "polygon": ["mainnet"],
    "base": ["mainnet"],
    "avalanche": ["mainnet"],
    "bsc": ["mainnet"],
    "solana": ["mainnet-beta", "devnet"]
}

def validate_pool_config(proposal: Proposal, exec_mode: str) -> Tuple[bool, Optional[str]]:
    """
    Validate pool configuration.
    
    Args:
        proposal: Episode proposal
        exec_mode: Execution mode (mock/real)
        
    Returns:
        (is_valid, error_message)
    """
    # Skip validation in mock mode
    if exec_mode == "mock":
        return True, None
    
    # Check if validation is disabled
    if os.getenv("DISABLE_POOL_VALIDATION", "false").lower() == "true":
        print("[PoolValidator] ⚠️  Validation disabled via DISABLE_POOL_VALIDATION")
        return True, None
    
    # Validate chain
    chain = proposal.chain
    if not chain:
        return False, "Missing chain in proposal"
    
    if chain not in VALID_CHAINS:
        return False, f"Unrecognized chain: {chain}. Valid: {list(VALID_CHAINS.keys())}"
    
    # Validate network
    network = proposal.network
    if not network:
        return False, f"Missing network for chain {chain}"
    
    if network not in VALID_CHAINS[chain]:
        return False, f"Invalid network '{network}' for chain '{chain}'. Valid: {VALID_CHAINS[chain]}"
    
    # Validate pool_address (real mode only)
    pool_address = proposal.pool_address
    if not pool_address:
        return False, "Missing pool_address in proposal (required for real mode)"
    
    # Basic format check (should start with 0x for EVM chains)
    if chain != "solana":
        if not pool_address.startswith("0x"):
            return False, f"Invalid pool_address format: {pool_address} (should start with 0x)"
        
        if len(pool_address) != 42:  # 0x + 40 hex chars
            return False, f"Invalid pool_address length: {pool_address} (should be 42 chars)"
    
    # Validate connector_execution
    connector = proposal.connector_execution
    if connector != "uniswap_v3_clmm":
        return False, f"Invalid connector_execution: {connector} (Track A requires uniswap_v3_clmm)"
    
    return True, None


def validate_and_report(proposal_path: str, run_id: str, episode_id: str, exec_mode: str) -> bool:
    """
    Validate proposal and write failure artifacts if invalid.
    
    Returns:
        True if valid, False if invalid (artifacts written)
    """
    import json
    from lib.artifacts import EpisodeArtifacts
    from lib.schemas import EpisodeMetadata, EpisodeResult
    import datetime
    
    # Load proposal
    try:
        with open(proposal_path) as f:
            proposal_data = json.load(f)
        proposal = Proposal.model_validate(proposal_data)
    except Exception as e:
        print(f"[PoolValidator] ❌ Failed to load proposal: {e}")
        
        # Write failure artifacts
        artifacts = EpisodeArtifacts(
            run_id=run_id,
            episode_id=episode_id,
            base_dir=str(Path(__file__).parent.parent.parent / "data")
        )
        
        metadata = EpisodeMetadata(
            episode_id=episode_id,
            run_id=run_id,
            config_hash="unknown",
            agent_version="v6.0_track_a",
            exec_mode=exec_mode,
            notes="Validation failed: could not load proposal"
        )
        
        result = EpisodeResult(
            episode_id=episode_id,
            run_id=run_id,
            status="failed",
            exec_mode=exec_mode,
            error=f"Proposal validation failed: {str(e)}"
        )
        
        artifacts.write_metadata(metadata)
        artifacts.write_result(result)
        artifacts.write_failure(
            error=f"Proposal validation failed: {str(e)}",
            context={"stage": "validation", "proposal_path": proposal_path}
        )
        
        return False
    
    # Validate
    is_valid, error_msg = validate_pool_config(proposal, exec_mode)
    
    if not is_valid:
        print(f"[PoolValidator] ❌ Validation failed: {error_msg}")
        
        # Write failure artifacts
        artifacts = EpisodeArtifacts(
            run_id=run_id,
            episode_id=episode_id,
            base_dir=str(Path(__file__).parent.parent.parent / "data")
        )
        
        metadata = proposal.metadata
        metadata.notes = f"Validation failed: {error_msg}"
        
        result = EpisodeResult(
            episode_id=episode_id,
            run_id=run_id,
            status="failed",
            exec_mode=exec_mode,
            connector_execution=proposal.connector_execution,
            chain=proposal.chain,
            network=proposal.network,
            pool_address=proposal.pool_address,
            error=error_msg
        )
        
        artifacts.write_metadata(metadata)
        artifacts.write_result(result)
        artifacts.write_failure(
            error=error_msg,
            context={
                "stage": "validation",
                "chain": proposal.chain,
                "network": proposal.network,
                "pool_address": proposal.pool_address,
                "connector": proposal.connector_execution
            }
        )
        
        return False
    
    print(f"[PoolValidator] ✅ Validation passed: {proposal.chain}/{proposal.network} pool={proposal.pool_address}")
    return True


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Validate pool configuration")
    parser.add_argument("--proposal-path", required=True, help="Path to proposal.json")
    parser.add_argument("--run-id", required=True, help="Run ID")
    parser.add_argument("--episode-id", required=True, help="Episode ID")
    parser.add_argument("--exec-mode", required=True, help="Execution mode (mock/real)")
    
    args = parser.parse_args()
    
    is_valid = validate_and_report(
        args.proposal_path,
        args.run_id,
        args.episode_id,
        args.exec_mode
    )
    
    sys.exit(0 if is_valid else 1)
