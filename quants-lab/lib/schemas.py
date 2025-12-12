import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field

# --- QuoteResult ---
class QuoteResult(BaseModel):
    success: bool
    simulation_success: bool = False
    amount_out: Optional[int] = None
    gas_estimate: Optional[int] = None
    latency_ms: float = 0.0
    error: Optional[str] = None
    source: str = "live"  # "live" or "mock"

# --- EpisodeMetadata ---
class EpisodeMetadata(BaseModel):
    episode_id: str
    run_id: str
    timestamp: str = Field(default_factory=lambda: datetime.datetime.utcnow().isoformat() + "Z")

    config_hash: str
    agent_version: str

    used_fallback: bool = False
    exec_mode: str = "unknown"  # "mock" | "real" | "unknown"

    # --- Added for reproducibility and “what worked when” ---
    seed: Optional[int] = None
    regime_key: Optional[str] = None

    # --- Learning hygiene visibility ---
    learning_update_applied: bool = False
    learning_update_reason: Optional[str] = None

    # --- Ops/debug ---
    gateway_health: Optional[str] = None
    gateway_latency_ms: Optional[float] = None
    notes: Optional[str] = None
    extra: Dict[str, Any] = Field(default_factory=dict)

# --- Proposal ---
class Proposal(BaseModel):
    episode_id: str
    generated_at: str
    status: str  # "active", "skipped"
    skip_reason: Optional[str] = None

    connector_execution: str = "uniswap_v3_clmm"
    chain: str = "ethereum"
    network: str = "mainnet"
    pool_address: Optional[str] = None

    params: Dict[str, Any]  # width, thresholds, notional, cooldown, etc.

    simulation: Optional[QuoteResult] = None
    metadata: EpisodeMetadata

# --- EpisodeResult ---
class EpisodeResult(BaseModel):
    episode_id: str
    run_id: str
    timestamp: str = Field(default_factory=lambda: datetime.datetime.utcnow().isoformat() + "Z")

    status: str  # "success" | "failed" | "skipped"
    exec_mode: str = "unknown"  # "mock" | "real" | "unknown"

    connector_execution: str = "uniswap_v3_clmm"
    chain: str = "ethereum"
    network: str = "mainnet"
    pool_address: Optional[str] = None

    params_used: Dict[str, Any] = Field(default_factory=dict)
    used_fallback: bool = False

    simulation: Optional[QuoteResult] = None

    # outcome metrics (keep minimal but consistent)
    pnl_usd: float = 0.0
    fees_usd: float = 0.0
    gas_cost_usd: float = 0.0
    out_of_range_pct: Optional[float] = None
    rebalance_count: int = 0

    position_before: Optional[Dict[str, Any]] = None
    position_after: Optional[Dict[str, Any]] = None

    error: Optional[str] = None
    errors: List[str] = Field(default_factory=list)

    latency_ms: Optional[float] = None
    timings_ms: Dict[str, float] = Field(default_factory=dict)

# --- RewardBreakdown ---
class RewardBreakdown(BaseModel):
    total: float
    components: Dict[str, float]
