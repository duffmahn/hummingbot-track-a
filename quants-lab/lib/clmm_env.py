import os
import time
import math
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List

from .schemas import Proposal, EpisodeResult, QuoteResult
from .run_context import RunContext
from .clmm_client import GatewayCLMMClient
from .mock_clmm_client import MockCLMMClient


# ============================================================================
# Band-Aware CLMM Simulation Helpers
# ============================================================================

def fee_rate_from_fee_str(fee_str: str) -> float:
    """Convert Uniswap V3 fee string to decimal rate.
    
    Uniswap V3 fee units: hundredths of a bip (1e-6)
    Example: "3000" => 0.003 (0.3%)
    """
    try:
        return int(fee_str) / 1_000_000
    except Exception:
        return 0.003


def pct_to_ticks(pct: float) -> int:
    """Convert percentage to tick count.
    
    tick ≈ ln(1+pct) / ln(1.0001)
    """
    pct = max(0.0, float(pct))
    if pct <= 0:
        return 0
    return int(abs(math.log(1.0 + pct) / math.log(1.0001)))


def snap_to_spacing(tick: int, spacing: int) -> int:
    """Snap tick to nearest valid tick spacing."""
    if spacing <= 0:
        return tick
    return int(round(tick / spacing) * spacing)


def width_pts_to_width_pct(width_pts: float) -> float:
    """Map width_pts to total band width in percent.
    
    Example: 200 pts -> 2.00% total width
    """
    w = max(10.0, float(width_pts))
    return max(0.002, min(w / 10_000.0, 0.50))  # 0.2% .. 50%


def parse_episode_index(episode_id: str) -> int:
    """
    Deterministic episode index extraction.
    Expected format: ep_YYYYMMDD_HHMMSS_<n> or anything ending in _<int>.
    Falls back to 0 if parsing fails.
    """
    try:
        return int(str(episode_id).split("_")[-1])
    except Exception:
        return 0


def derive_episode_seed(run_seed: int, episode_id: str) -> int:
    """Derive a deterministic but unique seed for each episode.
    
    Args:
        run_seed: The run-level seed
        episode_id: Unique episode identifier
        
    Returns:
        A deterministic seed that varies per episode but is reproducible
    """
    import hashlib
    h = hashlib.sha256(f"{run_seed}:{episode_id}".encode()).hexdigest()
    return (int(h[:8], 16) ^ run_seed) & 0x7fffffff


# ============================================================================
# Portfolio State Management (Stateful CLMM)
# ============================================================================

from dataclasses import dataclass, asdict
from pathlib import Path
import json


@dataclass
class PortfolioState:
    """Portfolio state that persists across episodes within a run."""
    position_open: bool = False
    current_band: Optional[Dict[str, Any]] = None  # {lower_tick, upper_tick, width_pts, fee, ...}
    last_tick: Optional[int] = None
    uncollected_fees_usd: float = 0.0
    last_rebalance_episode: Optional[str] = None
    rebalance_count_total: int = 0


def load_portfolio_state(run_dir: Path) -> PortfolioState:
    """Load portfolio state from run directory or return fresh state."""
    state_file = Path(run_dir) / "portfolio_state.json"
    
    if not state_file.exists():
        return PortfolioState()
    
    try:
        with open(state_file, 'r') as f:
            data = json.load(f)
        return PortfolioState(**data)
    except Exception:
        return PortfolioState()


def save_portfolio_state(run_dir: Path, state: PortfolioState) -> None:
    """Save portfolio state to run directory (atomic write)."""
    state_file = Path(run_dir) / "portfolio_state.json"
    temp_file = state_file.with_suffix('.json.tmp')
    
    try:
        # Write to temp file first
        with open(temp_file, 'w') as f:
            json.dump(asdict(state), f, indent=2)
        
        # Atomic rename
        temp_file.replace(state_file)
    except Exception as e:
        if temp_file.exists():
            temp_file.unlink()
        raise e


def simulate_baseline(
    tick_path: List[int],
    *,
    width_pts: float,
    rebalance_threshold_pct: float,
    fee_rate: float,
    position_share: float,
    mid_price_usd: float,
    tick_spacing: int,
    order_size_usd_proxy: float,
    pool_liquidity: float,
    volume_usd: float
) -> Dict[str, Any]:
    """Simulate a baseline strategy on the same tick path as the agent.
    
    Returns dict with: pnl_usd, fees_usd, gas_cost_usd, out_of_range_pct, rebalance_count
    """
    # Compute band
    raw_width_ticks = max(tick_spacing, int(width_pts))
    width_ticks = snap_to_spacing(raw_width_ticks, tick_spacing)
    half_width = max(tick_spacing, width_ticks // 2)
    
    # Start with first tick
    band_center = tick_path[0]
    band_lower = band_center - half_width
    band_upper = band_center + half_width
    
    threshold_ticks = max(
        tick_spacing,
        snap_to_spacing(pct_to_ticks(rebalance_threshold_pct), tick_spacing)
    )
    
    in_range = 0
    rebalance_count = 0
    
    for tick in tick_path:
        # Check if in range
        if band_lower <= tick <= band_upper:
            in_range += 1
        else:
            # Out of range - check if we should rebalance
            if abs(tick - band_center) >= threshold_ticks:
                rebalance_count += 1
                band_center = tick
                band_lower = band_center - half_width
                band_upper = band_center + half_width
    
    steps = len(tick_path)
    in_range_frac = in_range / steps if steps > 0 else 0
    out_range_frac = 1.0 - in_range_frac
    out_of_range_pct = out_range_frac * 100.0
    
    # Volume split
    in_range_volume_usd = volume_usd * in_range_frac
    out_range_volume_usd = volume_usd * out_range_frac
    
    # Fees
    fees_usd = in_range_volume_usd * fee_rate * position_share
    
    # Gas (opening + rebalances)
    gas_cost_usd = 2.0 + rebalance_count * 2.0  # Simplified: always opening
    
    # Missed fees and IL
    missed_fees_usd = out_range_volume_usd * fee_rate * position_share
    tightness = 1.0 / max(width_ticks, 1.0)
    vol_scale = max(0.5, min(3.0, 1.0 + (50.0 / max(half_width, 1)) * 2.0))  # Approximate
    il_penalty_usd = 0.1 * tightness * order_size_usd_proxy * vol_scale
    
    # PnL
    pnl_usd = fees_usd - gas_cost_usd - 0.5 * missed_fees_usd - il_penalty_usd
    
    return {
        "pnl_usd": float(pnl_usd),
        "fees_usd": float(fees_usd),
        "gas_cost_usd": float(gas_cost_usd),
        "out_of_range_pct": float(out_of_range_pct),
        "rebalance_count": int(rebalance_count),
    }


# ✅ DELIVERABLE 1: Baseline Policy Configuration
BASELINE_POLICIES = {
    "baseline_hold":   {"mode": "hold_forever", "width_pts": 1000, "rebalance_threshold_pct": 1.0},  # ✅ AGGRESSIVE: 1500→1000
    "baseline_wide":   {"mode": "fixed",        "width_pts": 1000, "rebalance_threshold_pct": 0.50},  # ✅ AGGRESSIVE: 1500→1000
    "baseline_medium": {"mode": "fixed",        "width_pts": 500,  "rebalance_threshold_pct": 0.10},
    "baseline_tight":  {"mode": "fixed",        "width_pts": 100,  "rebalance_threshold_pct": 0.05},
}


# ✅ DELIVERABLE 1: Regime Engine (deterministic + observable)
REGIME_PRESETS = {
    "low": {
        "sigma_mult": 1.0,
        "drift_per_step": 0.0,
        "jump_prob": 0.0,
        "jump_size_ticks": 0,
        "mean_revert_k": 0.0,
        "volume_mult": 1.0,
        "il_penalty_mult": 0.0,  # ✅ TUNING: no IL penalty in low volatility
    },
    "mid": {
        "sigma_mult": 2.0,
        "drift_per_step": 0.0,
        "jump_prob": 0.0,
        "jump_size_ticks": 0,
        "mean_revert_k": 0.0,
        "volume_mult": 1.2,
        "il_penalty_mult": 0.1,  # ✅ TUNING: light IL penalty
    },
    "high": {
        "sigma_mult": 4.0,  # ✅ AGGRESSIVE: keep high
        "drift_per_step": 0.0,
        "jump_prob": 0.0,
        "jump_size_ticks": 0,
        "mean_revert_k": 0.0,
        "volume_mult": 1.4,
        "il_penalty_mult": 0.3,  # ✅ TUNING: moderate IL penalty
    },
    "trend_up": {
        "sigma_mult": 3.0,  # ✅ AGGRESSIVE: 1.5→3.0 for more movement
        "drift_per_step": 4.0,
        "jump_prob": 0.0,
        "jump_size_ticks": 0,
        "mean_revert_k": 0.0,
        "volume_mult": 1.6,  # ✅ TUNING: increased from 1.3
        "il_penalty_mult": 0.25,  # ✅ TUNING: penalize not following trend
    },
    "trend_down": {
        "sigma_mult": 3.0,  # ✅ AGGRESSIVE: 1.5→3.0 for more movement
        "drift_per_step": -4.0,
        "jump_prob": 0.0,
        "jump_size_ticks": 0,
        "mean_revert_k": 0.0,
        "volume_mult": 1.6,  # ✅ TUNING: increased from 1.3
        "il_penalty_mult": 0.25,  # ✅ TUNING: penalize not following trend
    },
    "mean_revert": {
        "sigma_mult": 2.0,  # ✅ FIXED: 3.5→2.0 for realistic PnL ranges
        "drift_per_step": 0.0,
        "jump_prob": 0.0,
        "jump_size_ticks": 0,
        "mean_revert_k": 0.08,
        "volume_mult": 2.0,  # ✅ TUNING: increased from 1.4
        "il_penalty_mult": 0.4,  # ✅ TUNING: strong penalty for not rebalancing
    },
    "jumpy": {
        "sigma_mult": 2.5,  # ✅ AGGRESSIVE: 1.2→2.5 for more volatility between jumps
        "drift_per_step": 0.0,
        "jump_prob": 0.04,
        "jump_size_ticks": 120,
        "mean_revert_k": 0.0,
        "volume_mult": 2.0,  # ✅ TUNING: increased from 1.6
        "il_penalty_mult": 0.5,  # ✅ TUNING: strongest penalty for jumps
    },
}


def get_regime_cfg(regime_name: str, env_overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Get regime configuration with optional environment variable overrides.
    
    Returns dict with: sigma_mult, drift_per_step, jump_prob, jump_size_ticks, 
                       mean_revert_k, volume_mult, anchor_mode
    """
    # Start with preset or default to low
    if regime_name in REGIME_PRESETS:
        cfg = REGIME_PRESETS[regime_name].copy()
    else:
        cfg = REGIME_PRESETS["low"].copy()
    
    # Apply environment variable overrides
    if env_overrides:
        if "HB_TICK_SIGMA_MULT" in env_overrides:
            cfg["sigma_mult"] = float(env_overrides["HB_TICK_SIGMA_MULT"])
        if "HB_TICK_DRIFT_PER_STEP" in env_overrides:
            cfg["drift_per_step"] = float(env_overrides["HB_TICK_DRIFT_PER_STEP"])
        if "HB_JUMP_PROB" in env_overrides:
            cfg["jump_prob"] = float(env_overrides["HB_JUMP_PROB"])
        if "HB_JUMP_SIZE_TICKS" in env_overrides:
            cfg["jump_size_ticks"] = int(env_overrides["HB_JUMP_SIZE_TICKS"])
        if "HB_MEAN_REVERT_K" in env_overrides:
            cfg["mean_revert_k"] = float(env_overrides["HB_MEAN_REVERT_K"])
        if "HB_VOLUME_MULT" in env_overrides:
            cfg["volume_mult"] = float(env_overrides["HB_VOLUME_MULT"])
    
    # Add anchor mode
    anchor_mode = env_overrides.get("HB_REGIME_ANCHOR", "episode_start_tick") if env_overrides else "episode_start_tick"
    cfg["anchor_mode"] = anchor_mode
    
    return cfg


def generate_tick_path(
    regime_cfg: Dict[str, Any],
    start_tick: int,
    steps: int,
    rng: Any,
    anchor_tick: int,
    sigma_base: float,
) -> tuple:
    """
    Generate deterministic tick path based on regime configuration.
    
    Returns: (tick_path, tick_path_stats)
    """
    sigma_mult = regime_cfg.get("sigma_mult", 1.0)
    drift_per_step = regime_cfg.get("drift_per_step", 0.0)
    jump_prob = regime_cfg.get("jump_prob", 0.0)
    jump_size_ticks = regime_cfg.get("jump_size_ticks", 0)
    mean_revert_k = regime_cfg.get("mean_revert_k", 0.0)
    
    tick_path = [start_tick]
    tick = start_tick
    jump_count = 0
    step_deltas = []
    
    for _ in range(steps):
        # Base random walk
        dt = rng.gauss(0.0, sigma_base * sigma_mult)
        
        # Add drift
        dt += drift_per_step
        
        # Add jumps
        if jump_prob > 0 and rng.random() < jump_prob:
            jump_sign = rng.choice([-1, 1])
            dt += jump_sign * jump_size_ticks
            jump_count += 1
        
        # Add mean reversion
        if mean_revert_k > 0:
            dt += -mean_revert_k * (tick - anchor_tick)
        
        # Update tick
        dt_int = int(dt)
        tick += dt_int
        tick_path.append(tick)
        step_deltas.append(dt_int)
    
    # Compute stats
    import statistics
    tick_path_stats = {
        "start_tick": start_tick,
        "end_tick": tick_path[-1],
        "end_tick_delta": tick_path[-1] - start_tick,
        "min_tick": min(tick_path),
        "max_tick": max(tick_path),
        "mean_step": statistics.mean(step_deltas) if step_deltas else 0.0,
        "std_step": statistics.stdev(step_deltas) if len(step_deltas) > 1 else 0.0,
        "jump_count": jump_count,
    }
    
    return tick_path, tick_path_stats


def load_policy_state(run_dir: Path, policy_name: str) -> PortfolioState:
    """Load portfolio state for a specific baseline policy."""
    state_file = Path(run_dir) / f"portfolio_state_policy_{policy_name}.json"
    try:
        with open(state_file, 'r') as f:
            data = json.load(f)
        return PortfolioState(**data)
    except Exception:
        return PortfolioState()


def save_policy_state(run_dir: Path, policy_name: str, state: PortfolioState) -> None:
    """Save portfolio state for a specific baseline policy (atomic write)."""
    state_file = Path(run_dir) / f"portfolio_state_policy_{policy_name}.json"
    temp_file = state_file.with_suffix('.json.tmp')
    
    try:
        with open(temp_file, 'w') as f:
            json.dump(asdict(state), f, indent=2)
        temp_file.replace(state_file)
    except Exception as e:
        if temp_file.exists():
            temp_file.unlink()
        raise e


def run_stateful_baseline_policy(
    policy_name: str,
    run_dir: Path,
    tick_path: List[int],
    pool_liquidity: float,
    fee_rate: float,
    tick_spacing: int,
    mid_price_usd: float,
    order_size: float,
    episode_horizon_s: int,
    step_seconds: int,
    rebalance_cooldown_s: int,
    regime_name: str,
    regime_cfg: Dict[str, Any],
    vol_scale: float = 1.0,
) -> Dict[str, Any]:
    """
    Runs a stateful baseline policy on the given tick path.
    
    Loads policy state, applies deterministic action rules, simulates on tick_path,
    charges gas only on open/rebalance, accrues fees on holds, saves updated state.
    
    Returns episode metrics: pnl_usd, fees_usd, gas_cost_usd, out_of_range_pct, etc.
    """
    # Load policy configuration
    if policy_name not in BASELINE_POLICIES:
        raise ValueError(f"Unknown policy: {policy_name}")
    
    config = BASELINE_POLICIES[policy_name]
    mode = config["mode"]
    width_pts = config["width_pts"]
    rebalance_threshold_pct = config["rebalance_threshold_pct"]
    
    # Load policy state
    policy_state = load_policy_state(run_dir, policy_name)
    
    # Determine action based on policy mode
    action_applied = "hold"
    needs_rebalance = False
    
    if not policy_state.position_open:
        # First position: must open
        needs_rebalance = True
        action_applied = "open"
    elif mode == "hold_forever":
        # Never rebalance after opening
        needs_rebalance = False
        action_applied = "hold"
    elif mode == "fixed":
        # Check if rebalance threshold breached
        if policy_state.current_band:
            band = policy_state.current_band
            band_lower = band["lower_tick"]
            band_upper = band["upper_tick"]
            current_tick = tick_path[0]  # Starting tick
            
            # Check if out of range
            if current_tick < band_lower or current_tick > band_upper:
                # Check cooldown
                # For simplicity, we'll skip cooldown for baselines in this version
                # (can add later if needed)
                needs_rebalance = True
                action_applied = "rebalance"
            else:
                needs_rebalance = False
                action_applied = "hold"
    
    # Compute band
    current_tick = tick_path[0]
    half_width_ticks = int(width_pts / 2)
    band_center = (current_tick // tick_spacing) * tick_spacing
    band_lower = band_center - half_width_ticks
    band_upper = band_center + half_width_ticks
    
    # Gas cost
    gas_cost_usd = 2.0 if needs_rebalance else 0.0
    
    # Simulate on tick path (same logic as simulate_baseline)
    steps = len(tick_path) - 1
    in_range_steps = 0
    
    for tick in tick_path:
        if band_lower <= tick <= band_upper:
            in_range_steps += 1
    
    in_range_frac = in_range_steps / len(tick_path) if tick_path else 0.0
    out_of_range_pct = (1.0 - in_range_frac) * 100.0
    
    # ✅ GUARD: Prevent USD proxy being passed as order_size (catches double-mult bug)
    if order_size > 50:
        raise ValueError(
            f"order_size={order_size} looks like USD proxy (expected raw size like 0.1). "
            f"Pass raw order_size in ETH/token units, not USD. "
            f"Baseline will apply ORDER_SIZE_USD_MULT internally."
        )
    
    # ✅ FAIRNESS: Volume proxy with regime multiplier (same as agent)
    regime_volume_mult = regime_cfg.get("volume_mult", 1.0)
    volume_usd = pool_liquidity * vol_scale * 0.01 * steps * regime_volume_mult
    in_range_volume_usd = volume_usd * in_range_frac
    
    # ✅ FAIRNESS: Position share with concentration multiplier (same as agent)
    # ✅ FIXED: Realistic position share to prevent fantasy fees
    order_size_usd_proxy = order_size * float(os.environ.get("ORDER_SIZE_USD_MULT", "2000.0"))
    
    LIQUIDITY_PROXY_MULT = float(os.environ.get("LIQUIDITY_PROXY_MULT", "50.0"))
    liquidity_usd_proxy = pool_liquidity * LIQUIDITY_PROXY_MULT
    
    base_position_share = order_size_usd_proxy / (liquidity_usd_proxy + 1e-9)
    
    concentration_mult = (2000.0 / max(float(width_pts), 50.0)) ** 0.5
    concentration_mult = min(float(os.environ.get("CONC_MULT_CAP", "2.0")), max(1.0, concentration_mult))
    
    MAX_POSITION_SHARE = float(os.environ.get("MAX_POSITION_SHARE", "0.0005"))
    position_share = min(MAX_POSITION_SHARE, base_position_share * concentration_mult)
    
    # Fees earned
    fees_usd = in_range_volume_usd * fee_rate * position_share
    
    # Missed fees
    out_range_volume_usd = volume_usd * (1.0 - in_range_frac)
    missed_fees_usd = out_range_volume_usd * fee_rate * position_share
    
    # IL penalty (simplified) - ✅ FIXED: Reduced from 0.1 to 0.01 for realistic PnL
    il_penalty_mult = regime_cfg.get("il_penalty_mult", 0.0)  # ✅ TUNING: regime-dependent IL penalty
    il_penalty_usd = 0.01 * (1.0 / max(width_pts, 1.0)) * order_size_usd_proxy * vol_scale * (1.0 + il_penalty_mult)
    
    # PnL
    pnl_usd = fees_usd - gas_cost_usd - 0.5 * missed_fees_usd - il_penalty_usd
    
    # Update policy state
    policy_state.position_open = True
    policy_state.current_band = {
        "lower_tick": band_lower,
        "upper_tick": band_upper,
        "width_pts": width_pts,
        "fee": "3000",
    }
    policy_state.last_tick = tick_path[-1]
    
    # Uncollected fees (simplified: just track this episode's fees)
    if needs_rebalance:
        policy_state.uncollected_fees_usd = 0.0  # Collected on rebalance
    else:
        policy_state.uncollected_fees_usd += fees_usd
    
    # Save updated state
    save_policy_state(run_dir, policy_name, policy_state)
    
    # Return metrics
    return {
        "pnl_usd": float(pnl_usd),
        "fees_usd": float(fees_usd),
        "gas_cost_usd": float(gas_cost_usd),
        "out_of_range_pct": float(out_of_range_pct),
        "rebalance_count": 1 if needs_rebalance else 0,
        "action_applied": action_applied,
        "in_range_frac": float(in_range_frac),
        "regime_name": regime_name,
        "regime_params": regime_cfg,
    }


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
        """Initialize with optional run-level seed.
        
        Note: The actual RNG will be created per-episode using derive_episode_seed
        to ensure deterministic but varied results across episodes.
        """
        self.run_seed = seed
        
    def execute_episode(self, proposal: Proposal, ctx: RunContext) -> EpisodeResult:
        """Execute episode with stateful portfolio and hold logic."""
        # Derive episode-specific seed for deterministic but varied results
        episode_seed = derive_episode_seed(
            self.run_seed or ctx.seed or 42,
            proposal.episode_id
        )
        
        # Create client with episode-specific seed
        self.client = MockCLMMClient(seed=episode_seed)
        start_time = time.time()
        timings = {}
        
        # Load portfolio state (run-scoped)
        runs_dir = Path(os.environ.get("RUNS_DIR", "scratch/data/runs"))
        if not runs_dir.is_absolute():
            runs_dir = Path.cwd() / runs_dir
        run_dir = runs_dir / ctx.run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        portfolio_state = load_portfolio_state(run_dir)
        
        # Get config knobs
        episode_horizon_s = int(os.environ.get("HB_EPISODE_HORIZON_S", "21600"))  # 6h default
        step_seconds = int(os.environ.get("HB_STEP_SECONDS", "60"))
        rebalance_cooldown_s = int(os.environ.get("HB_REBALANCE_COOLDOWN_S", "1800"))  # 30min
        
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
            
            # Extract pool data
            pool_data = pool_info["data"]
            fee_str = str(pool_data.get("fee", "3000"))
            tick_spacing = int(pool_data.get("tickSpacing", 60))
            
            # ✅ DELIVERABLE 1: Tick continuity - use last simulated tick if available
            if portfolio_state.last_tick is not None:
                current_tick = int(portfolio_state.last_tick)
            else:
                current_tick = int(pool_data.get("tick", 0))
            
            pool_liquidity = float(pool_data.get("liquidity", 1_000_000))
            fee_rate = fee_rate_from_fee_str(fee_str)
            
            # Action params
            mid_price_usd = float(proposal.params.get("mid_price_usd", 2000.0))
            width_pts = float(proposal.params.get("width_pts", 200))
            rebalance_threshold_pct = float(proposal.params.get("rebalance_threshold_pct", 0.05))
            order_size = float(proposal.params.get("order_size", 0.1))
            
            # Save position_before
            position_before = {
                "position_open": portfolio_state.position_open,
                "current_band": portfolio_state.current_band,
                "last_tick": portfolio_state.last_tick,
                "uncollected_fees_usd": portfolio_state.uncollected_fees_usd,
            }
            
            # ✅ DELIVERABLE 2: Explicit action handling
            action = proposal.params.get("action", "auto")
            action_requested = action
            needs_rebalance = False
            is_opening = False
            is_widening = False
            
            # Opening position overrides all actions
            if not portfolio_state.position_open:
                needs_rebalance = True
                is_opening = True
                action_applied = "rebalance_opening"
            elif action == "hold":
                # Explicit hold: keep band, no gas
                needs_rebalance = False
                action_applied = "hold"
            elif action == "rebalance":
                # Explicit rebalance: recenter band, pay gas
                needs_rebalance = True
                action_applied = "rebalance"
            elif action == "widen":
                # Widen band: increase width, pay gas
                needs_rebalance = True
                is_widening = True
                action_applied = "widen"
                # Get target width
                target_width = proposal.params.get("target_width_pts", width_pts * 2)
                width_pts = max(width_pts, target_width)
            elif action == "auto":
                # Backward compatible: auto-detect based on band
                if portfolio_state.current_band:
                    band = portfolio_state.current_band
                    band_lower = band["lower_tick"]
                    band_upper = band["upper_tick"]
                    
                    # If current tick is outside the band, rebalance
                    if current_tick < band_lower or current_tick > band_upper:
                        needs_rebalance = True
                        action_applied = "auto_rebalance"
                    else:
                        action_applied = "auto_hold"
                else:
                    needs_rebalance = True
                    action_applied = "auto_rebalance"
            else:
                # Unknown action: treat as auto
                needs_rebalance = False
                action_applied = "unknown_hold"
            
            # Compute band
            width_pct = width_pts_to_width_pct(width_pts)
            raw_width_ticks = max(tick_spacing, int(width_pts))
            width_ticks = snap_to_spacing(raw_width_ticks, tick_spacing)
            half_width = max(tick_spacing, width_ticks // 2)
            
            if needs_rebalance:
                band_center = current_tick
            elif portfolio_state.current_band:
                # Use existing band center
                band_center = (portfolio_state.current_band["lower_tick"] + portfolio_state.current_band["upper_tick"]) // 2
            else:
                band_center = current_tick
            
            band_lower = band_center - half_width
            band_upper = band_center + half_width
            
            # ✅ DELIVERABLE 1: Regime selection (deterministic)
            episode_index = parse_episode_index(proposal.episode_id)
            schedule = os.environ.get("HB_REGIME_SCHEDULE", "").strip()
            vol_regime = os.environ.get("HB_VOL_REGIME", "low").strip()
            
            # Determine regime for this episode
            if schedule:
                schedule_list = [x.strip() for x in schedule.split(",") if x.strip()]
                regime_name = schedule_list[episode_index % len(schedule_list)] if schedule_list else vol_regime
            else:
                # ✅ FIX: Get regime from proposal metadata (set by agent)
                regime_name = "low"  # default fallback
                if hasattr(proposal, 'metadata') and proposal.metadata:
                    regime_name = proposal.metadata.regime_key or "low"
            
            # Handle mixed regime (deterministic rotation)
            if regime_name == "mixed":
                mixed = ["low", "mid", "high", "trend_up", "trend_down", "mean_revert", "jumpy"]
                regime_name = mixed[episode_index % len(mixed)]
            
            # Get regime configuration
            regime_cfg = get_regime_cfg(regime_name, dict(os.environ))
            
            # ✅ DELIVERABLE 1: Generate tick path with regime
            steps = episode_horizon_s // step_seconds
            sigma_base = max(5.0, 0.15 * half_width)
            anchor_tick = current_tick  # Anchor for mean reversion
            tick_path, tick_path_stats = generate_tick_path(
                regime_cfg, current_tick, steps, self.client.rng, anchor_tick, sigma_base
            )
            
            # Agent simulation on tick_path
            in_range = 0
            rebalance_count_this_episode = 1 if needs_rebalance else 0
            
            for t in tick_path:
                if band_lower <= t <= band_upper:
                    in_range += 1
            
            in_range_frac = in_range / len(tick_path) if len(tick_path) > 0 else 0
            out_range_frac = 1.0 - in_range_frac
            out_of_range_pct = out_range_frac * 100.0
            
            # Volume proxy with regime multiplier
            base_volume_usd = 50_000.0
            liq_scale = max(0.1, min(10.0, pool_liquidity / 2_000_000.0))
            sigma_ticks = sigma_base  # Use sigma_base from regime
            vol_scale = max(0.5, min(3.0, 1.0 + (sigma_ticks / max(half_width, 1)) * 2.0))
            regime_volume_mult = regime_cfg.get("volume_mult", 1.0)
            volume_usd = base_volume_usd * liq_scale * vol_scale * regime_volume_mult
            
            in_range_volume_usd = volume_usd * in_range_frac
            out_range_volume_usd = volume_usd * out_range_frac
            
            # ✅ DELIVERABLE 2: Position share with concentration multiplier (bounded)
            # ✅ FIXED: Realistic position share to prevent fantasy fees
            order_size_usd_proxy = order_size * float(os.environ.get("ORDER_SIZE_USD_MULT", "2000.0"))
            
            LIQUIDITY_PROXY_MULT = float(os.environ.get("LIQUIDITY_PROXY_MULT", "50.0"))
            liquidity_usd_proxy = pool_liquidity * LIQUIDITY_PROXY_MULT
            
            base_position_share = order_size_usd_proxy / (liquidity_usd_proxy + 1e-9)
            
            concentration_mult = (2000.0 / max(float(width_pts), 50.0)) ** 0.5
            concentration_mult = min(float(os.environ.get("CONC_MULT_CAP", "2.0")), max(1.0, concentration_mult))
            
            MAX_POSITION_SHARE = float(os.environ.get("MAX_POSITION_SHARE", "0.0005"))
            position_share = min(MAX_POSITION_SHARE, base_position_share * concentration_mult)
            
            # Fees from in-range volume (incremental)
            fees_this_episode = in_range_volume_usd * fee_rate * position_share
            
            # Gas cost logic
            if is_opening:
                gas_cost_usd = 2.0  # Opening position
            elif needs_rebalance:
                gas_cost_usd = 2.0  # Rebalance
            else:
                gas_cost_usd = 0.0  # HOLD EPISODE ✅
            
            # Missed fees and IL with regime multiplier - ✅ FIXED: Reduced from 0.1 to 0.01
            missed_fees_usd = out_range_volume_usd * fee_rate * position_share
            tightness = 1.0 / max(width_ticks, 1.0)
            il_penalty_mult = regime_cfg.get("il_penalty_mult", 0.0)  # ✅ TUNING: regime-dependent IL penalty
            il_penalty_usd = 0.01 * tightness * order_size_usd_proxy * vol_scale * (1.0 + il_penalty_mult)
            
            # ✅ DELIVERABLE 2: Incremental PnL (not cumulative)
            # PnL is based on THIS episode's fees only
            pnl_usd = fees_this_episode - gas_cost_usd - 0.5 * missed_fees_usd - il_penalty_usd
            
            # Track collection for observability
            fees_collected_this_episode = 0.0
            if needs_rebalance:
                # Collect includes previously uncollected plus this episode
                fees_collected_this_episode = portfolio_state.uncollected_fees_usd + fees_this_episode
            
            # ✅ DELIVERABLE 1: Run stateful baseline policies on same tick path
            baselines = {}
            baseline_actions = {}
            
            # Get run directory for policy state persistence
            runs_dir = Path(os.environ.get("RUNS_DIR", "data/runs"))
            run_dir = runs_dir / ctx.run_id
            
            # Run each stateful baseline policy
            for policy_name in BASELINE_POLICIES.keys():
                policy_result = run_stateful_baseline_policy(
                    policy_name=policy_name,
                    run_dir=run_dir,
                    tick_path=tick_path,
                    pool_liquidity=pool_liquidity,
                    fee_rate=fee_rate,
                    tick_spacing=tick_spacing,
                    mid_price_usd=mid_price_usd,
                    order_size=order_size,  # ✅ FIX: Pass raw order_size, not proxy (baseline will apply multiplier)
                    episode_horizon_s=episode_horizon_s,
                    step_seconds=step_seconds,
                    rebalance_cooldown_s=rebalance_cooldown_s,
                    regime_name=regime_name,
                    regime_cfg=regime_cfg,
                    vol_scale=vol_scale,
                )
                baselines[policy_name] = policy_result
                baseline_actions[policy_name] = policy_result.get("action_applied", "unknown")
            
            # Compute alpha vs best baseline
            best_baseline_name = max(baselines.keys(), key=lambda k: baselines[k]["pnl_usd"])
            best_baseline_pnl = baselines[best_baseline_name]["pnl_usd"]
            
            alpha_usd = pnl_usd - best_baseline_pnl
            alpha_vs = best_baseline_name
            alpha_per_100k_vol = (alpha_usd / max(volume_usd, 1e-9)) * 100_000 if volume_usd > 0 else 0.0
            alpha_per_gas_usd = alpha_usd / max(gas_cost_usd, 1e-9) if gas_cost_usd > 0 else 0.0
            
            # Update portfolio state
            portfolio_state.position_open = True
            portfolio_state.current_band = {
                "lower_tick": band_lower,
                "upper_tick": band_upper,
                "width_pts": width_pts,
                "fee": fee_str,
            }
            portfolio_state.last_tick = tick_path[-1]  # Final tick from path
            
            if needs_rebalance:
                # Collect fees on rebalance
                portfolio_state.uncollected_fees_usd = 0.0
                portfolio_state.last_rebalance_episode = proposal.episode_id
                portfolio_state.rebalance_count_total += 1
            else:
                # Accrue fees
                portfolio_state.uncollected_fees_usd += fees_this_episode
            
            # Save portfolio state
            save_portfolio_state(run_dir, portfolio_state)
            
            # Mock quote for compatibility
            lower_price = mid_price_usd * (1.0 - width_pct / 2.0)
            upper_price = mid_price_usd * (1.0 + width_pct / 2.0)
            
            quote_start = time.time()
            quote = self.client.quote_position(
                chain=proposal.chain,
                network=proposal.network,
                connector="uniswap",
                token0=pool_data["token0"],
                token1=pool_data["token1"],
                fee=fee_str,
                lower_price=str(lower_price),
                upper_price=str(upper_price)
            )
            timings["quote_ms"] = (time.time() - quote_start) * 1000
            
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
                pnl_usd=float(pnl_usd),
                fees_usd=float(fees_this_episode),  # ✅ Incremental fees only
                gas_cost_usd=float(gas_cost_usd),
                out_of_range_pct=float(out_of_range_pct),
                rebalance_count=int(rebalance_count_this_episode),
                latency_ms=total_latency,
                timings_ms=timings,
                position_before=position_before,
                position_after={
                    "position_open": portfolio_state.position_open,
                    "current_band": portfolio_state.current_band,
                    "last_tick": portfolio_state.last_tick,
                    "uncollected_fees_usd": float(portfolio_state.uncollected_fees_usd),
                    # ✅ DELIVERABLE 2: Action observability fields
                    "action_requested": action_requested,
                    "action_applied": action_applied,
                    "band_center_tick": band_center,
                    # ✅ DELIVERABLE 2: Fee observability fields
                    "fees_this_episode_usd": float(fees_this_episode),
                    "fees_collected_this_episode_usd": float(fees_collected_this_episode),
                    # ✅ DELIVERABLE 2: Alpha hygiene fields
                    "best_baseline_pnl_usd": float(best_baseline_pnl),
                    "best_baseline_name": best_baseline_name,
                    "baseline_actions": baseline_actions,
                    # ✅ DELIVERABLE 1: Regime observability fields
                    "regime_name": regime_name,
                    "regime_params": regime_cfg,
                    "tick_path_stats": tick_path_stats,
                    # Other observability fields
                    "in_range_frac": in_range_frac,
                    "volume_usd_proxy": volume_usd,
                    "regime_volume_mult": float(regime_volume_mult),
                    "in_range_volume_usd_proxy": in_range_volume_usd,
                    "out_range_volume_usd_proxy": out_range_volume_usd,
                    "missed_fees_usd_proxy": missed_fees_usd,
                    "il_penalty_usd_proxy": il_penalty_usd,
                    "base_position_share_proxy": float(base_position_share),
                    "concentration_mult": float(concentration_mult),
                    "position_share_proxy": position_share,
                    "fee_rate": fee_rate,
                    "band_lower_tick": band_lower,
                    "band_upper_tick": band_upper,
                    "quote_band": {
                        "mid_price_usd": mid_price_usd,
                        "width_pts": width_pts,
                        "width_pct": width_pct,
                        "lower_price": lower_price,
                        "upper_price": upper_price,
                        "fee": fee_str,
                    }
                },
                # ✅ DELIVERABLE B: Baselines and alpha
                baselines=baselines,
                alpha_usd=float(alpha_usd),
                alpha_vs=alpha_vs,
                alpha_per_100k_vol=float(alpha_per_100k_vol),
                alpha_per_gas_usd=float(alpha_per_gas_usd)
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
    """
    Factory function to create the appropriate environment.
    
    **SINGLE SOURCE OF TRUTH** for environment selection.
    All callers should use this function and log the result.
    
    Feature Flags:
    - USE_REAL_DATA=true: Use RealDataCLMMEnvironment (historical Dune data)
    - REAL_DATA_REQUIRED=true: Fail-fast if real data unavailable (no silent fallback)
    - exec_mode: "mock" or "real" (Gateway)
    
    Improvement 1: Single source of truth with comprehensive logging
    Improvement 4: HB_REGIME_MIX isolation (ignored in real-data mode)
    """
    import logging
    logger = logging.getLogger("create_environment")
    
    # Read all relevant config
    use_real_data = os.getenv("USE_REAL_DATA", "false").lower() == "true"
    real_data_required = os.getenv("REAL_DATA_REQUIRED", "false").lower() == "true"
    regime_mix = os.getenv("HB_REGIME_MIX", "")
    cache_dir = os.getenv("HISTORICAL_DATA_CACHE_DIR", "scratch/data/historical_cache")
    lookback_days = int(os.getenv("HISTORICAL_LOOKBACK_DAYS", "90"))
    
    # Improvement 4: Warn if HB_REGIME_MIX set in real-data mode
    if use_real_data and regime_mix:
        logger.warning(
            "⚠️  HB_REGIME_MIX ignored in real-data mode; "
            "regimes will be derived post-hoc from realized tick path."
        )
    
    # Track fallback state
    fallback_used = False
    fallback_reason = None
    
    if use_real_data:
        # Import RealDataCLMMEnvironment
        try:
            from .real_data_clmm_env import RealDataCLMMEnvironment
        except ImportError as e:
            error_msg = f"RealDataCLMMEnvironment not available: {e}"
            if real_data_required:
                logger.error(f"❌ {error_msg}")
                raise RuntimeError(f"USE_REAL_DATA=true but {error_msg}")
            
            logger.warning(f"⚠️  {error_msg}, falling back to mock")
            fallback_used = True
            fallback_reason = "import_failed"
            env = MockCLMMEnvironment(seed=seed)
            env._fallback_used = fallback_used  # Tag for result.json
            env._fallback_reason = fallback_reason
            return env
        
        # Create real data environment
        env = RealDataCLMMEnvironment()
        
        # Guardrail: Fail-fast if real data required but cache unavailable
        if real_data_required:
            stats = env.cache.get_cache_stats()
            if stats["total_windows_cached"] == 0:
                # Try a test fetch to see if Dune is accessible
                import time
                test_start = int(time.time()) - (7 * 86400)
                test_data = env.cache.get_tick_window(
                    pool_address=env.pool_address,
                    start_ts=test_start,
                    duration_seconds=3600,
                    granularity="hour"
                )
                if not test_data or len(test_data) == 0:
                    error_msg = (
                        "REAL_DATA_REQUIRED=true but no historical data available. "
                        "Check DUNE_API_KEY and query IDs are set correctly."
                    )
                    logger.error(f"❌ {error_msg}")
                    raise RuntimeError(error_msg)
        
        # Improvement 1: Comprehensive logging
        logger.info("=" * 70)
        logger.info("ENVIRONMENT SELECTION (Single Source of Truth)")
        logger.info("=" * 70)
        logger.info(f"Environment Class: RealDataCLMMEnvironment")
        logger.info(f"USE_REAL_DATA: true")
        logger.info(f"REAL_DATA_REQUIRED: {real_data_required}")
        logger.info(f"EXEC_MODE: {exec_mode} (ignored in real-data mode)")
        logger.info(f"Cache Dir: {cache_dir}")
        logger.info(f"Lookback Days: {lookback_days}")
        logger.info(f"Fallback Used: {fallback_used}")
        if regime_mix:
            logger.info(f"HB_REGIME_MIX: '{regime_mix}' (IGNORED - will derive post-hoc)")
        logger.info("=" * 70)
        
        # Tag environment for audit trail
        env._real_data_used = True
        env._fallback_used = fallback_used
        env._fallback_reason = fallback_reason
        
        return env
    
    # Standard environment selection (mock or real Gateway)
    if exec_mode == "mock":
        env = MockCLMMEnvironment(seed=seed)
        logger.info(f"[Environment] Using MockCLMMEnvironment (synthetic data, seed={seed})")
    elif exec_mode == "real":
        env = RealCLMMEnvironment(gateway_url=gateway_url)
        logger.info(f"[Environment] Using RealCLMMEnvironment (Gateway at {gateway_url or 'default'})")
    else:
        raise ValueError(f"Unknown exec_mode: {exec_mode}")
    
    # Tag for audit trail
    env._real_data_used = False
    env._fallback_used = False
    env._fallback_reason = None
    
    return env

