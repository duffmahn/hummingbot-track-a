"""
Strict Data Contracts for Uniswap V3 CLMM Agent

This module defines the immutable Pydantic schemas for:
1. Agent Config (Inputs)
2. Proposals (Agent Output)
3. Execution Results (Harness/Env Output)
4. Reward Signals (Learning Input)

All cross-boundary objects MUST use these models.
"""

from typing import Dict, Optional, Any, List
from pydantic import BaseModel, Field
import datetime

# --- Core Support Models ---

class QuoteResult(BaseModel):
    success: bool
    simulation_success: bool = False
    amount_out: Optional[int] = None
    gas_estimate: Optional[int] = None
    latency_ms: float = 0.0
    error: Optional[str] = None
    source: str = "live"  # "live" or "mock"

class RewardBreakdown(BaseModel):
    total: float
    components: Dict[str, float]

class AgentConfig(BaseModel):
    # Minimal config model for type safety
    simulate_during_training: bool = True
    simulation_required_for_trade: bool = False
    reward_weights: Dict[str, float] = Field(default_factory=dict)
    sim_failure_penalty: float = 5.0
    gas_penalty_factor: float = 0.5
    max_gas_bps_of_notional: float = 50.0
    sim_success_bonus: float = 0.0
    enable_simulation: bool = True

# --- Episode Artifact Models (Strict Spec v1.2) ---

class EpisodeMetadata(BaseModel):
    """
    Bulletproof metadata for reproducibility and hygiene.
    Compatible with legacy formats where new fields might be missing.
    """
    episode_id: str
    run_id: str
    timestamp: str = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z"))

    config_hash: str
    agent_version: str

    used_fallback: bool = False
    exec_mode: str = "unknown"  # "mock" | "real" | "unknown"

    # --- Added for reproducibility and "what worked when" ---
    seed: Optional[int] = None
    regime_key: Optional[str] = None

    # --- Learning hygiene visibility ---
    learning_update_applied: bool = False
    learning_update_reason: Optional[str] = None

    # --- Ops/debug ---
    gateway_health: Optional[str] = None
    gateway_latency_ms: Optional[float] = None
    # --- Notes (flexible) ---
    notes: Optional[str] = None
    extra: Dict[str, Any] = Field(default_factory=dict)  # For intel_snapshot, etc.

class Proposal(BaseModel):
    """
    Agent's proposed action for the episode.
    """
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
    
    # Backward compatibility for legacy usage if strictly needed
    next_run_proposal: Optional[Dict[str, Any]] = None

class EpisodeResult(BaseModel):
    """
    Strict outcome schema for harness/environments.
    Always written to result.json.
    """
    episode_id: str
    run_id: str
    timestamp: str = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z"))

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
    
    # Reward (Calculated post-execution)
    reward: Optional[RewardBreakdown] = None

    # --- Fee Validation Metrics ---
    fees_0: Optional[float] = None
    fees_1: Optional[float] = None
    pool_fees_usd_input_based: Optional[float] = None
    pool_fees_usd_amount_usd_based: Optional[float] = None
