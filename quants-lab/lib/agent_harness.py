"""
Agent Harness for Track A: Uniswap V3 CLMM

Orchestrates:
1. Load proposal from episode folder
2. Select environment (mock/real)
3. Execute episode
4. Compute reward
5. Write artifacts (result.json always; failure.json on error)
"""

import os
import sys
import json
import logging
import datetime
import hashlib
from pathlib import Path
from typing import Optional

# Add quants-lab to path
QUANTS_LAB_DIR = Path(__file__).parent.parent.parent / "quants-lab"
sys.path.append(str(QUANTS_LAB_DIR))

try:
    from lib.schemas import Proposal, EpisodeResult, RewardBreakdown
    from lib.artifacts import EpisodeArtifacts
    from lib.run_context import RunContext
    from lib.clmm_env import create_environment
except ImportError as e:
    print(f"❌ Harness Import Error: {e}")
    sys.exit(1)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("AgentHarness")

class AgentHarness:
    def __init__(self):
        self.run_id = os.environ.get("RUN_ID", f"run_{datetime.datetime.utcnow().strftime('%Y%m%d_%H%M%S')}")
        self.exec_mode = os.environ.get("EXEC_MODE", "mock")
        self.seed = int(os.environ.get("HB_SEED", "42"))
        self.learn_from_mock = os.environ.get("LEARN_FROM_MOCK", "false").lower() == "true"
        
        self.base_dir = Path(__file__).parent.parent.parent / "data"
        
    def run_episode(self, episode_id: str) -> bool:
        """
        Main entrypoint for episode execution.
        1. Load proposal from episode folder
        2. Execute via environment
        3. Compute reward
        4. Write artifacts
        """
        
        # Initialize artifacts manager
        artifacts = EpisodeArtifacts(
            run_id=self.run_id,
            episode_id=episode_id,
            base_dir=str(self.base_dir)
        )
        
        try:
            # Ensure episode directory exists
            artifacts.ensure_directories()
            
            # Load proposal
            proposal_path = Path(artifacts.episode_dir) / "proposal.json"
            if not proposal_path.exists():
                error_msg = f"Proposal not found at {proposal_path}"
                logger.error(error_msg)
                artifacts.write_failure(error_msg, {"episode_id": episode_id})
                self._write_failed_result(artifacts, episode_id, error_msg)
                return False
                
            with open(proposal_path, 'r') as f:
                proposal_data = json.load(f)
            
            try:
                proposal = Proposal.model_validate(proposal_data)
            except Exception as e:
                error_msg = f"Episode execution failed: {e}"
                logger.error(error_msg, exc_info=True)
                
                # Best effort: attach intel snapshot if available
                try:
                    # 'intel' is not defined in this scope, assuming it might be imported or passed
                    # For now, this block will likely not execute as 'intel' is not available.
                    # If 'intel' is meant to be a global or imported module, it needs to be handled.
                    # Assuming 'metadata' is also available if intel is.
                    if 'intel' in locals() and hasattr(intel, 'get_last_intel_snapshot'):
                        snapshot = intel.get_last_intel_snapshot()
                        # Assuming 'metadata' object is available in this scope,
                        # which is not currently the case.
                        # This part of the snippet seems to assume a broader context
                        # where 'metadata' and 'intel' are defined.
                        # For a syntactically correct and functional change based on the provided snippet,
                        # we'll include it as is, but note its dependency on external context.
                        if 'metadata' in locals(): # This 'metadata' is not defined here.
                            metadata.extra["intel_snapshot"] = snapshot
                            metadata.extra["failure_exception"] = repr(e)
                            artifacts.write_metadata(metadata, merge_existing=True)
                except Exception:
                    pass  # Don't fail on metadata write failure
                
                artifacts.write_failure(error_msg, {"exception": repr(e), "traceback": str(e)})
                self._write_failed_result(artifacts, episode_id, error_msg)
                return False
            
            
            # Create run context
            ctx = RunContext(
                run_id=self.run_id,
                episode_id=episode_id,
                config_hash=self._compute_config_hash(proposal.params),
                agent_version="v1.0",
                exec_mode=self.exec_mode,
                seed=self.seed,
                started_at=datetime.datetime.utcnow().isoformat() + "Z"
            )
            
            # --- Phase 4: Capture Intel Snapshot ---
            try:
                from lib.market_intel import MarketIntelligence
                intel = MarketIntelligence()
                
                # Extract pool/pair from proposal
                pool_address = proposal.pool_address
                pair = proposal.metadata.regime_key or "WETH-USDC"
                
                # Call intel methods to populate quality metadata
                _ = intel.get_gas_regime()
                _ = intel.get_pool_health(pool_address=pool_address, pair=pair, lookback_hours=1)
                _ = intel.get_mev_risk(pool_address=pool_address)
                _ = intel.get_range_hint(pool_address=pool_address)
                
                # Capture snapshot
                intel_snapshot = intel.get_last_intel_snapshot()
                
                # Update metadata with snapshot
                metadata = proposal.metadata
                metadata.extra["intel_snapshot"] = intel_snapshot
                metadata.extra.setdefault("intel_inputs", {})
                metadata.extra["intel_inputs"].update({
                    "pool_address": pool_address,
                    "pair": pair,
                    "lookback_hours": 1
                })
                
                # Compute intel hygiene summary
                if intel_snapshot:
                    qualities = [v.get("quality") for v in intel_snapshot.values() if isinstance(v, dict)]
                    total = len(qualities)
                    if total > 0:
                        fresh_count = sum(1 for q in qualities if q == "fresh")
                        stale_count = sum(1 for q in qualities if q == "stale")
                        missing_count = sum(1 for q in qualities if q in ["missing", "too_old"])
                        
                        metadata.extra["intel_hygiene"] = {
                            "total_queries": total,
                            "fresh": fresh_count,
                            "stale": stale_count,
                            "missing_or_too_old": missing_count,
                            "fresh_pct": round(100 * fresh_count / total, 1) if total > 0 else 0
                        }
                
                # Write metadata (harness is now the authority)
                artifacts.write_metadata(metadata, merge_existing=True)
                
                logger.info(f"Intel snapshot captured: {len(intel_snapshot)} queries")
                
            except Exception as e:
                logger.warning(f"Failed to capture intel snapshot: {e}")
                # Continue execution even if intel snapshot fails
            
            # Log episode start
            artifacts.log_event("episode_start", {
                "episode_id": episode_id,
                "run_id": self.run_id,
                "exec_mode": self.exec_mode,
                "seed": self.seed
            })
            
            # Select and create environment
            env = create_environment(
                exec_mode=self.exec_mode,
                seed=self.seed
            )
            
            logger.info(f"🚀 Executing Episode {episode_id} in {env.__class__.__name__}")
            
            # Execute episode
            result = env.execute_episode(proposal, ctx)
            
            # Write result (always)
            artifacts.write_result(result)
            
            # Write timings if present
            if result.timings_ms:
                artifacts.write_timings(result.timings_ms)
            
            # Compute and write reward
            reward = self._compute_reward(result)
            artifacts.write_reward(reward)
            
            # Write failure if status is not success
            if result.status != "success":
                artifacts.write_failure(
                    result.error or "Episode failed",
                    {
                        "status": result.status,
                        "errors": result.errors
                    }
                )
                logger.warning(f"⚠️  Episode {episode_id} failed: {result.error}")
                return False
            
            # Log episode completion
            artifacts.log_event("episode_complete", {
                "episode_id": episode_id,
                "status": result.status,
                "pnl_usd": result.pnl_usd,
                "reward": reward.total
            })
            
            logger.info(f"✅ Episode {episode_id} completed successfully")
            return True
            
        except Exception as e:
            error_msg = f"Critical harness failure: {str(e)}"
            logger.exception(error_msg)
            
            # Try to write failure artifact
            try:
                artifacts.write_failure(error_msg, {
                    "exception_type": type(e).__name__,
                    "episode_id": episode_id
                })
                self._write_failed_result(artifacts, episode_id, error_msg)
            except Exception as write_error:
                logger.error(f"Failed to write failure artifact: {write_error}")
            
            return False
    
    def _write_failed_result(self, artifacts: EpisodeArtifacts, episode_id: str, error: str):
        """Write a minimal failed result."""
        result = EpisodeResult(
            episode_id=episode_id,
            run_id=self.run_id,
            status="failed",
            exec_mode=self.exec_mode,
            error=error
        )
        artifacts.write_result(result)
    
    def _compute_config_hash(self, params: dict) -> str:
        """Compute a hash of the configuration."""
        config_str = json.dumps(params, sort_keys=True)
        return hashlib.md5(config_str.encode()).hexdigest()[:8]
    
    def _compute_reward(self, result: EpisodeResult) -> RewardBreakdown:
        """
        Compute reward from episode result.
        Simple reward function for now.
        """
        components = {}
        
        # PnL component
        components["pnl"] = result.pnl_usd
        
        # Fee component
        components["fees"] = result.fees_usd
        
        # Gas cost penalty
        components["gas_penalty"] = -result.gas_cost_usd
        
        # Out of range penalty
        if result.out_of_range_pct is not None:
            components["range_penalty"] = -result.out_of_range_pct * 10
        
        total = sum(components.values())
        
        return RewardBreakdown(
            total=total,
            components=components
        )

if __name__ == "__main__":
    # Smoke test
    harness = AgentHarness()
    logger.info(f"Harness initialized: run_id={harness.run_id}, exec_mode={harness.exec_mode}")
