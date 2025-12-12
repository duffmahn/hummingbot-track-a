import os
import time
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional

from .schemas import Proposal, EpisodeResult, QuoteResult
from .run_context import RunContext
from .clmm_client import GatewayCLMMClient
from .mock_clmm_client import MockCLMMClient

class BaseCLMMEnvironment(ABC):
    """Base class for CLMM execution environments."""
    
    @abstractmethod
    def execute_episode(self, proposal: Proposal, ctx: RunContext) -> EpisodeResult:
        """Execute an episode and return results."""
        pass

class RealCLMMEnvironment(BaseCLMMEnvironment):
    """Real CLMM environment using Gateway."""
    
    def __init__(self, gateway_url: Optional[str] = None):
        self.client = GatewayCLMMClient(base_url=gateway_url)
        
    def execute_episode(self, proposal: Proposal, ctx: RunContext) -> EpisodeResult:
        """Execute episode against real Gateway."""
        start_time = time.time()
        timings = {}
        
        try:
            # Health check
            health_start = time.time()
            health = self.client.health_check()
            timings["health_check_ms"] = (time.time() - health_start) * 1000
            
            if not health["success"]:
                return EpisodeResult(
                    episode_id=proposal.episode_id,
                    run_id=ctx.run_id,
                    status="failed",
                    exec_mode="real",
                    connector_execution=proposal.connector_execution,
                    chain=proposal.chain,
                    network=proposal.network,
                    pool_address=proposal.pool_address,
                    params_used=proposal.params,
                    error="Gateway health check failed",
                    errors=[f"Health check error: {health['error']}"],
                    timings_ms=timings
                )
            
            # Get pool info
            pool_start = time.time()
            pool_info = self.client.pool_info(
                chain=proposal.chain,
                network=proposal.network,
                connector="uniswap",
                pool_address=proposal.pool_address or ""
            )
            timings["pool_info_ms"] = (time.time() - pool_start) * 1000
            
            if not pool_info["success"]:
                return EpisodeResult(
                    episode_id=proposal.episode_id,
                    run_id=ctx.run_id,
                    status="failed",
                    exec_mode="real",
                    connector_execution=proposal.connector_execution,
                    chain=proposal.chain,
                    network=proposal.network,
                    pool_address=proposal.pool_address,
                    params_used=proposal.params,
                    error="Failed to fetch pool info",
                    errors=[f"Pool info error: {pool_info['error']}"],
                    timings_ms=timings
                )
            
            # TODO: Implement actual position management logic
            # For now, return a minimal success result
            
            total_latency = (time.time() - start_time) * 1000
            
            return EpisodeResult(
                episode_id=proposal.episode_id,
                run_id=ctx.run_id,
                status="success",
                exec_mode="real",
                connector_execution=proposal.connector_execution,
                chain=proposal.chain,
                network=proposal.network,
                pool_address=proposal.pool_address,
                params_used=proposal.params,
                latency_ms=total_latency,
                timings_ms=timings
            )
            
        except Exception as e:
            total_latency = (time.time() - start_time) * 1000
            return EpisodeResult(
                episode_id=proposal.episode_id,
                run_id=ctx.run_id,
                status="failed",
                exec_mode="real",
                connector_execution=proposal.connector_execution,
                chain=proposal.chain,
                network=proposal.network,
                pool_address=proposal.pool_address,
                params_used=proposal.params,
                error=str(e),
                errors=[f"Exception: {str(e)}"],
                latency_ms=total_latency,
                timings_ms=timings
            )

class MockCLMMEnvironment(BaseCLMMEnvironment):
    """Mock CLMM environment for testing."""
    
    def __init__(self, seed: Optional[int] = None):
        self.client = MockCLMMClient(seed=seed)
        
    def execute_episode(self, proposal: Proposal, ctx: RunContext) -> EpisodeResult:
        """Execute episode with mock client."""
        start_time = time.time()
        timings = {}
        
        try:
            # Mock health check
            health_start = time.time()
            health = self.client.health_check()
            timings["health_check_ms"] = (time.time() - health_start) * 1000
            
            # Mock pool info
            pool_start = time.time()
            pool_info = self.client.pool_info(
                chain=proposal.chain,
                network=proposal.network,
                connector="uniswap",
                pool_address=proposal.pool_address or "0xmock"
            )
            timings["pool_info_ms"] = (time.time() - pool_start) * 1000
            
            # Mock quote
            quote_start = time.time()
            quote = self.client.quote_position(
                chain=proposal.chain,
                network=proposal.network,
                connector="uniswap",
                token0="0xWETH",
                token1="0xUSDC",
                fee="3000",
                lower_price="1800",
                upper_price="2200"
            )
            timings["quote_ms"] = (time.time() - quote_start) * 1000
            
            # Create simulation result
            simulation = QuoteResult(
                success=quote["success"],
                simulation_success=True,
                amount_out=int(quote["data"].get("amount1", 0)) if quote["success"] else None,
                gas_estimate=int(quote["data"].get("gasEstimate", 0)) if quote["success"] else None,
                latency_ms=quote["latency_ms"],
                source="mock"
            )
            
            total_latency = (time.time() - start_time) * 1000
            
            return EpisodeResult(
                episode_id=proposal.episode_id,
                run_id=ctx.run_id,
                status="success",
                exec_mode="mock",
                connector_execution=proposal.connector_execution,
                chain=proposal.chain,
                network=proposal.network,
                pool_address=proposal.pool_address,
                params_used=proposal.params,
                simulation=simulation,
                pnl_usd=self.client.rng.uniform(-100, 500),  # Mock PnL
                fees_usd=self.client.rng.uniform(10, 100),
                gas_cost_usd=self.client.rng.uniform(5, 50),
                latency_ms=total_latency,
                timings_ms=timings
            )
            
        except Exception as e:
            total_latency = (time.time() - start_time) * 1000
            return EpisodeResult(
                episode_id=proposal.episode_id,
                run_id=ctx.run_id,
                status="failed",
                exec_mode="mock",
                connector_execution=proposal.connector_execution,
                chain=proposal.chain,
                network=proposal.network,
                pool_address=proposal.pool_address,
                params_used=proposal.params,
                error=str(e),
                errors=[f"Mock exception: {str(e)}"],
                latency_ms=total_latency,
                timings_ms=timings
            )

def create_environment(exec_mode: str, seed: Optional[int] = None, gateway_url: Optional[str] = None) -> BaseCLMMEnvironment:
    """Factory function to create the appropriate environment."""
    if exec_mode == "mock":
        return MockCLMMEnvironment(seed=seed)
    elif exec_mode == "real":
        return RealCLMMEnvironment(gateway_url=gateway_url)
    else:
        raise ValueError(f"Unknown exec_mode: {exec_mode}")
