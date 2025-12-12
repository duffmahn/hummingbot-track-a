from dataclasses import dataclass, field
from typing import Optional
from .schemas import EpisodeMetadata

@dataclass
class RunContext:
    run_id: str
    episode_id: str
    config_hash: str
    agent_version: str
    exec_mode: str  # "mock" or "real"
    seed: Optional[int]
    started_at: str
    
    # Optional - populated later
    gateway_health: Optional[str] = None
    gateway_latency_ms: Optional[float] = None
    regime_key: Optional[str] = None

    def create_metadata(self) -> EpisodeMetadata:
        """Helper to create initial metadata from context."""
        return EpisodeMetadata(
            episode_id=self.episode_id,
            run_id=self.run_id,
            timestamp=self.started_at,
            config_hash=self.config_hash,
            agent_version=self.agent_version,
            exec_mode=self.exec_mode,
            seed=self.seed,
            regime_key=self.regime_key,
            gateway_health=self.gateway_health,
            gateway_latency_ms=self.gateway_latency_ms
        )
