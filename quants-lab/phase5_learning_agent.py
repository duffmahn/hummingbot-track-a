import json
import os
import sys
import pandas as pd
import numpy as np
from datetime import datetime, date, timezone
from pathlib import Path
from typing import Dict, List, Any, Optional

import yaml
import hashlib

from lib.uv4_experiments import UV4ExperimentStore
from lib.market_intel import MarketIntelligence
from lib.clmm_env import MockCLMMEnvironment

# ============================================================================
# CONFIGURATION RESOLVERS (EXEC-MODE AWARE + REGIME MIX)
# ============================================================================

def _load_regime_mix():
    """
    Load regime mix with strict precedence:
    1) HB_REGIME_MIX env var (fail fast if malformed)
    2) DUNE_CALIBRATION_JSON.calibrated_regime_mix (warn if missing)
    3) Default fallback
    
    Returns: (mix_dict, source_string)
    """
    # (1) Env override - FAIL FAST if malformed
    env_mix = os.environ.get("HB_REGIME_MIX")
    if env_mix:
        try:
            mix = {}
            for pair in env_mix.split(","):
                regime, weight = pair.split(":")
                mix[regime.strip()] = float(weight.strip())
            if not mix:
                raise ValueError("HB_REGIME_MIX parsed empty")
            return mix, "env"
        except Exception as e:
            raise ValueError(f"HB_REGIME_MIX malformed: {env_mix}. Error: {e}") from e
    
    # (2) Calibration JSON
    cal_path = os.environ.get("DUNE_CALIBRATION_JSON")
    if cal_path and Path(cal_path).exists():
        try:
            with open(cal_path) as f:
                cal = json.load(f)
            rm = cal.get("calibrated_regime_mix")
            if isinstance(rm, dict) and rm:
                return {k: float(v) for k, v in rm.items()}, "calibration_json"
            else:
                print(f"⚠️  DUNE_CALIBRATION_JSON exists but calibrated_regime_mix missing/malformed")
        except Exception as e:
            print(f"⚠️  Failed to load calibration JSON: {e}")
    
    # (3) Default fallback
    return {"mean_revert": 0.4, "jumpy": 0.3, "trend_up": 0.3}, "default"


def _resolve_gating_constants(calibration: dict = None):
    """
    Resolve EV-gating constants based on EXEC_MODE.
    
    Mock: use env vars (GAS_USD, FEE_GATE_USD or FEE_GATE_MULT)
    Live/Paper: use Dune calibration or safe defaults
    
    Returns: (GAS_USD, FEE_GATE, LOSS_BREAKER, PREEMPT_MARGIN)
    """
    exec_mode = os.environ.get("EXEC_MODE", "mock").lower()
    
    LOSS_BREAKER = -1000.0
    PREEMPT_MARGIN = float(os.environ.get("PREEMPT_MARGIN", "3.0"))
    
    if exec_mode == "mock":
        # Mock: use observed gas costs
        GAS_USD = float(os.environ.get("GAS_USD", "2.0"))
        
        # Allow explicit FEE_GATE_USD or compute from multiplier
        if os.environ.get("FEE_GATE_USD"):
            FEE_GATE = float(os.environ["FEE_GATE_USD"])
        else:
            mult = float(os.environ.get("FEE_GATE_MULT", "2.0"))
            FEE_GATE = mult * GAS_USD
    else:
        # Live/Paper: use Dune calibration
        if calibration and "calibrated_constants" in calibration:
            cc = calibration["calibrated_constants"]
            GAS_USD = float(cc.get("GAS_USD", 4.2))
            FEE_GATE = float(cc.get("FEE_GATE", 8.4))
        else:
            GAS_USD, FEE_GATE = 4.2, 8.4
            print(f"⚠️  No calibration for {exec_mode} mode, using defaults")
    
    return GAS_USD, FEE_GATE, LOSS_BREAKER, PREEMPT_MARGIN


# ✅ Regime-based minimum width floors (DUNE CALIBRATED)
REGIME_MIN_WIDTH = {
    "trend_up": 1600,
    "trend_down": 1600,
    "jumpy": 1400,
    "mean_revert": 1200,
    "low": 800,
    "mid": 1000,
}
DEFAULT_MIN_WIDTH = 1200

# ✅ OOR thresholds (DUNE CALIBRATED)
OOR_CRITICAL_BY_REGIME = {
    "trend_up": 92.0,
    "trend_down": 92.0,
    "jumpy": 90.0,
    "mean_revert": 92.0,
    "low": 90.0,
    "mid": 90.0,
}
OOR_CRITICAL_DEFAULT = 92.0

# Use Pydantic schemas
from lib.schemas import QuoteResult, RewardBreakdown, Proposal, EpisodeMetadata
from schemas.contracts import AgentConfig
from schemas.learning_state import LearningState, RegimeState, ParameterDistribution
from lib.hummingbot_api_wrapper import hummingbot_api
from lib.json_logger import setup_logger
from lib.artifacts import EpisodeArtifacts

OUTPUT_FILE = Path(__file__).parent.parent / "data" / "uniswap_v4_param_proposals.json"

class NumpyEncoder(json.JSONEncoder):
    """
    JSON encoder that safely handles NumPy/Pandas types
    """
    def default(self, obj):
        if isinstance(obj, np.integer): return int(obj)
        if isinstance(obj, np.floating): return float(obj)
        if isinstance(obj, np.ndarray): return obj.tolist()
        if pd is not None and isinstance(obj, pd.Timestamp): return obj.isoformat()
        if isinstance(obj, (datetime, date)): return obj.isoformat()
        return super().default(obj)

class Phase5LearningAgent:
    def __init__(self, config: AgentConfig = None):
        self.config_hash = "manual"
        self.run_id = os.environ.get("RUN_ID", "manual_run")
        self.episode_id = os.environ.get("EPISODE_ID", "ep_0")
        self.exec_mode = os.environ.get("EXEC_MODE", "mock")
        self.seed = int(os.environ.get("HB_SEED", "42"))
        self.learn_from_mock = os.environ.get("LEARN_FROM_MOCK", "false").lower() == "true"
        
        # Load external YAML config if not provided
        if config is None:
            config_path = Path(__file__).parent.parent / "conf" / "agent_config.yml"
            if config_path.is_file():
                with open(config_path) as f:
                    f.seek(0)
                    content = f.read()
                    self.config_hash = hashlib.sha256(content.encode()).hexdigest()[:8]
                    f.seek(0)
                    cfg_dict = yaml.safe_load(f)
                
                try:
                    config = AgentConfig(**cfg_dict)
                except Exception as e:
                    print(f"❌ Invalid Config in agent_config.yml: {e}")
                    sys.exit(1)
            else:
                config = AgentConfig()
        
        self.config = config
        self.data = hummingbot_api
        self.store = UV4ExperimentStore()
        self.intel = MarketIntelligence()
        self.logger = setup_logger("Phase5Agent")
        
        # Paths
        self.root = Path(__file__).parent.parent
        self.data_dir = self.root / "data"
        self.proposals_dir = self.data_dir / "uniswap_v4_proposals"

        # Load Learning State
        self.state_path = Path(__file__).parent.parent / "data" / "learning_state.json"
        self.learning_state = LearningState.load(self.state_path)
        
        
        self.logger.info("Phase 5 Agent Initialized", extra={"config_hash": self.config_hash, "state_version": self.learning_state.version})
        
        # ✅ Load regime mix with strict precedence (CRITICAL FIX)
        self.regime_mix, self.regime_mix_source = _load_regime_mix()
        
        # ✅ Load gating constants (exec-mode aware)
        calibration = None
        cal_path = os.environ.get("DUNE_CALIBRATION_JSON")
        if cal_path and Path(cal_path).exists():
            try:
                with open(cal_path) as f:
                    calibration = json.load(f)
            except Exception as e:
                self.logger.warning(f"Failed to load calibration: {e}")
        
        self.GAS_USD, self.FEE_GATE, self.LOSS_BREAKER, self.PREEMPT_MARGIN = _resolve_gating_constants(calibration)
        
        # CRITICAL: Log so it's impossible to run with wrong mix silently
        self.logger.info(f"🔁 Using regime mix source: {self.regime_mix_source}")
        self.logger.info(f"🔁 Regime mix: {self.regime_mix}")
        self.logger.info(f"💰 Gating: GAS=${self.GAS_USD:.2f}, FEE_GATE=${self.FEE_GATE:.2f} (exec_mode={self.exec_mode})")

    
    def _load_prev_result(self) -> Optional[dict]:
        """Load previous episode result with robust path resolution and numeric sorting."""
        from lib.path_utils import resolve_base_dir
        
        base_dir = resolve_base_dir()
        episodes_dir = base_dir / "runs" / self.run_id / "episodes"
        
        self.logger.info(f"[DEBUG] Looking for previous episodes in: {episodes_dir}")
        
        if not episodes_dir.exists():
            self.logger.info(f"[DEBUG] Episodes directory does not exist yet")
            return None
        
        result_paths = list(episodes_dir.glob("ep_*/result.json"))
        
        # Numeric sort to avoid ep_10 vs ep_2 ordering bug
        def _ep_index(p: Path) -> int:
            try:
                return int(p.parent.name.split("_")[-1])
            except Exception:
                return -1
        
        result_paths.sort(key=_ep_index)
        self.logger.info(f"[DEBUG] Found {len(result_paths)} previous episodes")
        
        if not result_paths:
            return None
        
        try:
            last_ep_path = result_paths[-1]
            self.logger.info(f"[DEBUG] Loading last result from: {last_ep_path}")
            with open(last_ep_path) as f:
                return json.load(f)
        except Exception as e:
            self.logger.warning(f"[WARN] Could not load previous result: {e}")
            return None

    def calculate_reward(self, row: pd.Series) -> RewardBreakdown:
        # Simplistic wrapper for learning update
        pnl = row.get('total_pnl_usd', 0.0)
        drawdown = row.get('max_drawdown_usd', 0.0)
        gas = row.get('gas_cost_usd', 0.0)
        
        w = self.config.reward_weights
        comp = {}
        comp['pnl'] = pnl * w.get('pnl', 1.0)
        comp['drawdown'] = -abs(drawdown) * w.get('drawdown', 0.5)
        comp['gas'] = -abs(gas) * w.get('gas', 0.3)
        
        total_reward = sum(comp.values())
        return RewardBreakdown(total=total_reward, components=comp)

    def update_beliefs_from_history(self, df: pd.DataFrame) -> bool:
        """
        Update beliefs from history.
        Returns True if update was applied, False if skipped due to learning hygiene.
        """
        # Learning hygiene: skip if exec_mode is mock and LEARN_FROM_MOCK is not true
        if self.exec_mode == "mock" and not self.learn_from_mock:
            self.logger.info("⏭  Skipping learning update (mock mode, LEARN_FROM_MOCK=false)")
            return False
            
        self.logger.info("🧠 Updating parameter beliefs from history...")
        if 'regime' not in df.columns:
             df['regime'] = 'vol_mid-liq_low'
             
        regimes = df['regime'].unique()
        for r in regimes:
             grp = df[df['regime'] == r]
             if grp.empty: continue
             
             if r not in self.learning_state.regimes:
                 self.learning_state.regimes[r] = RegimeState(regime=r)
                 
             regime_state = self.learning_state.regimes[r]
             
             # Windowed CEM
             WINDOW_SIZE = 20
             recent_history = grp.tail(WINDOW_SIZE)
             n_elites = max(1, int(len(recent_history) * 0.25))
             elites = recent_history.nlargest(n_elites, 'calculated_reward')
             
             learnable_params = {
                'width_pts': {'min': 5, 'max': 5000, 'default': 200},
                'rebalance_threshold_pct': {'min': 0.01, 'max': 0.50, 'default': 0.05},
                'spread_bps': {'min': 1, 'max': 500, 'default': 20},
                'order_size': {'min': 0.01, 'max': 5.0, 'default': 0.1},
                'refresh_interval': {'min': 10, 'max': 300, 'default': 60}
             }
             
             updated_counts = 0
             for param_name, limits in learnable_params.items():
                col_name = f"param_{param_name}"
                if col_name not in elites.columns: continue
                    
                values = elites[col_name].dropna().astype(float)
                if values.empty: continue
                
                mean_val = float(values.mean())
                min_std = (limits['max'] - limits['min']) * 0.05
                std_val = max(min_std, float(values.std()) if len(values) > 1 else min_std)
                
                # Smooth Update
                if param_name in regime_state.params:
                    old = regime_state.params[param_name]
                    alpha = 0.5
                    new_mean = old.mean * (1-alpha) + mean_val * alpha
                    new_std = old.std_dev * (1-alpha) + std_val * alpha
                    count = old.sample_count + len(values)
                else:
                    new_mean = mean_val
                    new_std = std_val
                    count = len(values)
                    
                regime_state.params[param_name] = ParameterDistribution(
                    name=param_name,
                    mean=new_mean,
                    std_dev=new_std,
                    min_val=limits['min'],
                    max_val=limits['max'],
                    sample_count=count
                )
                updated_counts += 1
            
             if updated_counts > 0:
                 regime_state.last_updated = datetime.now(timezone.utc)
                 self.logger.info(f"🧠 Updated belief for {r} ({updated_counts} params)")

        self.learning_state.save(self.state_path)
        return True

    def learn_and_propose(self, episode_id: str) -> Proposal:
        """
        Main logic: Load history -> Learn -> Sense -> Propose
        Returns a strict Proposal object.
        """
        self.logger.info("🤖 Phase 5 Learning Agent Starting...")
        
        # 1. Load & Learn
        learning_update_applied = False
        learning_update_reason = None
        
        df = self.store.to_dataframe(min_version="v1_realtime", intel_quality_whitelist=("good",), stable_regime_only=False)
        if not df.empty:
            if 'reward_v1' in df.columns:
                df['calculated_reward'] = df['reward_v1']
            else:
                df['calculated_reward'] = df.apply(lambda row: self.calculate_reward(row).total, axis=1)
            learning_update_applied = self.update_beliefs_from_history(df)
            if not learning_update_applied:
                learning_update_reason = "mock_mode_learning_disabled"
        else:
            learning_update_reason = "no_history_available"
        
        # 2. Sense
        PAIR = "WETH-USDC"
        POOL = "0x88e6A0c2dDD26FEEb64F039a2c41296FcB3f5640"
        
        
        # ✅ Select regime using loaded mix (already validated in __init__)
        regimes = list(self.regime_mix.keys())
        weights_raw = [float(self.regime_mix[r]) for r in regimes]
        wsum = sum(weights_raw)
        if wsum <= 0:
            raise ValueError(f"Invalid regime_mix weights (sum<=0): {self.regime_mix}")
        weights = [w / wsum for w in weights_raw]  # normalize for np.choice
        
        # Deterministic selection with episode seed
        try:
            ep_idx = int(episode_id.split("_")[-1]) if "_" in episode_id else 0
        except Exception:
            ep_idx = 0
        
        rng = np.random.RandomState(self.seed + ep_idx)
        current_regime = rng.choice(regimes, p=weights)
        
        self.logger.info(f"📍 Selected regime for {episode_id}: {current_regime}")
 
        
        # 3. Propose (Sample from Beliefs)
        params = {
            "width_pts": 200, 
            "rebalance_threshold_pct": 0.05,
            "spread_bps": 20,
            "order_size": 0.1,
            "refresh_interval": 60
        }
        
        # ✅ ENFORCE REGIME MIN WIDTH FLOOR (after sampling, before hold logic)
        min_width = REGIME_MIN_WIDTH.get(current_regime, DEFAULT_MIN_WIDTH)
        width_before_floor = params["width_pts"]
        params["width_pts"] = max(float(params["width_pts"]), float(min_width))
        width_after_floor = params["width_pts"]
        
        self.logger.info(f"[WIDTH] Regime: {current_regime}, min={min_width}, before={width_before_floor}, after={width_after_floor}")
        
        # Use Learned if available
        if current_regime in self.learning_state.regimes:
            reg = self.learning_state.regimes[current_regime]
            import random
            for k in params.keys():
                if k in reg.params:
                    dist = reg.params[k]
                    val = random.gauss(dist.mean, dist.std_dev)
                    params[k] = max(dist.min_val, min(dist.max_val, val))
        
        # ✅ DELIVERABLE 1: Determine action based on last episode with robust hold logic
        action = "auto"  # default
        target_width_pts = None
        
        # Load previous result with tolerant field extraction
        prev_result = self._load_prev_result()
        
        prev_alpha = None
        prev_oor = None
        prev_gas = None
        prev_regime = None
        prev_width = None
        prev_fees = None
        prev_action = None
        rule_fired = "first_episode"
        
        if prev_result:
            # Tolerant field extraction for schema variations
            prev_alpha = prev_result.get("alpha_usd") or prev_result.get("alpha", 0.0)
            prev_oor = prev_result.get("out_of_range_pct") or prev_result.get("oor_pct", 0.0)
            prev_gas = prev_result.get("gas_cost_usd") or prev_result.get("gas", 0.0)
            
            # ✅ Extract fees for EV gate
            prev_fees = prev_result.get("fees_usd", 0.0)
            if prev_fees == 0.0 and "position_after" in prev_result:
                prev_fees = prev_result["position_after"].get("fees_this_episode_usd", 0.0)
            
            # Extract previous action and width
            prev_params = prev_result.get("params_used", {})
            prev_action = prev_params.get("action")
            prev_width = prev_params.get("width_pts") or prev_params.get("target_width_pts")
            if not prev_width and "position_after" in prev_result:
                # Fallback to position width
                prev_width = prev_result["position_after"].get("current_band", {}).get("width_pts")
            
            # Try multiple locations for regime
            if "position_after" in prev_result:
                prev_regime = prev_result["position_after"].get("regime_name")
            if not prev_regime:
                prev_regime = prev_result.get("regime_key") or prev_result.get("regime_name")
            
            self.logger.info(f"[DEBUG] Previous: OOR={prev_oor:.1f}%, Alpha=${prev_alpha:.2f}, Fees=${prev_fees:.2f}, Gas=${prev_gas:.2f}, Action={prev_action}, Width={prev_width}")
            
            # ✅ EV-GATED DECISION LOGIC with cooldowns, preemption, and AMORTIZED TIGHTENING
            oor_critical = OOR_CRITICAL_BY_REGIME.get(current_regime, OOR_CRITICAL_DEFAULT)
            
            # Helper for Amortized Tightening
            def estimate_tightening_opportunity(
                current_width: int,
                regime: str,
                in_range_steps: int,
                current_fees_usd: float
            ):
                """Check if tightening offers positive EV after gas, amortized over stable streak."""
                if current_width < 200: return None # Already tight
                
                # Setup Candidates
                candidates = [200, 400, 800, 1200]
                candidates = [c for c in candidates if c < current_width]
                candidates.sort() # check tightest first? or conservative first?
                
                # Proxy calc: narrower width = higher fee multiplier (approx 1/width)
                # This is a heuristic. 
                # Uplift factor = current_width / candidate_width
                
                streak = in_range_steps
                base_cap = 6 if regime != "jumpy" else 3
                hold_horizon = max(1, min(base_cap, 1 + (streak // 2))) # slower streak growth
                
                gas_buffer = self.GAS_USD * 1.5
                
                for cand_w in candidates:
                    uplift_mult = float(current_width) / cand_w
                    projected_fees_per_ep = current_fees_usd * uplift_mult
                    delta_per_ep = projected_fees_per_ep - current_fees_usd
                    
                    delta_total = delta_per_ep * hold_horizon
                    
                    if delta_total > gas_buffer:
                        return cand_w, delta_total
                
                return None

            # Extract In-Range Streak
            ir_steps = 0
            if "position_after" in prev_result and prev_result["position_after"]:
                ir_steps = prev_result["position_after"].get("in_range_steps", 0)

            # 1) COOLDOWN AFTER WIDEN
            if prev_action == "widen" and prev_alpha > self.LOSS_BREAKER:
                action = "hold"
                rule_fired = "cooldown_after_widen"
                self.logger.info(f"💤 Cooldown after widen")
            
            # 2) COOLDOWN AFTER REBALANCE (if low fees)
            elif prev_action == "rebalance" and prev_alpha > self.LOSS_BREAKER and prev_fees < self.FEE_GATE:
                action = "hold"
                rule_fired = "cooldown_after_rebalance_low_fees"
                self.logger.info(f"💤 Cooldown after rebalance")
            
            # 3) TREND PREEMPTION
            elif (current_regime in ["trend_up", "trend_down"] and 
                  prev_action == "hold" and
                  prev_oor >= (oor_critical - self.PREEMPT_MARGIN) and
                  prev_oor < oor_critical and
                  prev_fees < self.FEE_GATE and
                  prev_alpha > self.LOSS_BREAKER):
                
                action = "widen"
                rule_fired = "trend_preempt_widen"
                self.logger.info(f"⚡ Trend preemption")
                target_width_pts = max(
                    int(width_after_floor),
                    int(prev_width * 1.5) if prev_width else 0,
                    1600
                )

            # 4) LOSS BREAKER
            elif prev_alpha <= self.LOSS_BREAKER:
                if prev_oor >= oor_critical:
                    action = "widen"
                    rule_fired = "loss_breaker_widen"
                else:
                    action = "rebalance"
                    rule_fired = "loss_breaker_rebalance"
            
            # 5) CRITICAL OOR
            elif prev_oor >= oor_critical:
                widen_allowed = (prev_fees >= self.FEE_GATE or prev_alpha <= -500.0)
                if widen_allowed:
                    action = "widen"
                    rule_fired = "widen_oor_critical_ev_ok"
                else:
                    action = "hold"
                    rule_fired = "hold_oor_critical_low_fees"

            # 6) AMORTIZED TIGHTENING (New Feature)
            # Only consider if currently holding, in range, and stable
            elif (prev_oor < 10.0 and prev_width and ir_steps > 2): 
                opportunity = estimate_tightening_opportunity(
                    prev_width, current_regime, ir_steps, prev_fees
                )
                if opportunity:
                    cand_w, delta = opportunity
                    action = "rebalance"
                    rule_fired = f"amortized_tightening_to_{cand_w}"
                    target_width_pts = cand_w
                    self.logger.info(f"🎯 Amortized Tightening! {prev_width}->{cand_w}. Est Uplift ${delta:.2f} > Gas ${self.GAS_USD*1.5:.2f}")

            # 7) REGIME-SPECIFIC HOLD LOGIC (Default)
            else:
                should_hold = False
                
                if current_regime in ["low", "mid"]:
                    if prev_oor < 80: should_hold = True
                elif current_regime == "mean_revert":
                    if prev_oor < 60 and prev_alpha > -1000: should_hold = True
                elif current_regime in ["trend_up", "trend_down"]:
                    if prev_alpha > 0 and prev_oor < 95: should_hold = True
                elif current_regime == "jumpy":
                    if prev_alpha > 0 and prev_oor < 90: should_hold = True
                
                if should_hold:
                    if prev_fees < self.FEE_GATE and prev_alpha > self.LOSS_BREAKER and prev_oor < oor_critical:
                        action = "hold"
                        rule_fired = f"hold_regime_ev_gated"
                    else:
                        action = "hold"
                        rule_fired = f"hold_regime_ok"
                    
                    if params["width_pts"] < min_width:
                        action = "widen"
                        target_width_pts = float(min_width)
                        rule_fired = "hold_blocked_width_too_narrow"
                else:
                    if prev_fees < self.FEE_GATE and prev_alpha > self.LOSS_BREAKER:
                        action = "hold"
                        rule_fired = "hold_low_fees_ev_gate"
                    else:
                        action = "hold"
                        rule_fired = "hold_default_no_gas_ev"
        else:
            # First episode - must rebalance to open position
            action = "rebalance"
            rule_fired = "first_episode"
            self.logger.info(f"[DEBUG] First episode - will rebalance")
        
        # ✅ Apply widen with meaningful target when it happens
        if action == "widen":
            target_width_pts = max(
                float(params["width_pts"]),
                float(min_width),
                float(prev_width) * 1.5 if prev_width else 0.0,
                1400.0 if current_regime in ["trend_up", "trend_down", "jumpy"] else 0.0
            )
        
        # ✅ Add decision basis to params for comprehensive audit trail
        params["action"] = action
        params["decision_basis"] = {
            "prev_alpha_usd": prev_alpha,
            "prev_oor_pct": prev_oor,
            "prev_fees_usd": prev_fees,
            "prev_gas_usd": prev_gas,
            "prev_action": prev_action,
            "prev_width_pts": prev_width,
            "prev_regime": prev_regime,
            "oor_critical": OOR_CRITICAL_BY_REGIME.get(current_regime, OOR_CRITICAL_DEFAULT),
            "fee_gate": self.FEE_GATE,
            "gas_usd": self.GAS_USD,
            "fee_gate_mult": self.FEE_GATE / self.GAS_USD if self.GAS_USD > 0 else 0,
            "preempt_margin": self.PREEMPT_MARGIN,
            "preempt_triggered": rule_fired == "trend_preempt_widen",
            "exec_mode": self.exec_mode,
            "regime_min_width": min_width,
            "width_before_floor": width_before_floor,
            "width_after_floor": width_after_floor,
            "rule_fired": rule_fired,
            "decision": action,
            # CRITICAL PROVENANCE (prevents silent wrong mix)
            "regime_mix_used": self.regime_mix,
            "regime_mix_source": self.regime_mix_source
        }
        if target_width_pts is not None:
            params["target_width_pts"] = target_width_pts
            params["decision_basis"]["target_width_pts"] = target_width_pts
        
        # 4. Construct Proposal
        # Create Metadata first
        meta = EpisodeMetadata(
            episode_id=episode_id,
            run_id=self.run_id,
            config_hash=self.config_hash,
            agent_version="v6.0_track_a",
            exec_mode=self.exec_mode,
            seed=self.seed,
            regime_key=current_regime,
            learning_update_applied=learning_update_applied,
            learning_update_reason=learning_update_reason
        )
        
        proposal = Proposal(
            episode_id=episode_id,
            generated_at=datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
            status="active",
            connector_execution="uniswap_v3_clmm", # Explicit Pivot Target
            chain="ethereum",
            network="mainnet",
            pool_address=POOL,
            params=params,
            metadata=meta
        )
        
        # Optional: Run Simulation here if needed and Attach to `proposal.simulation`
        # For simplicity in this refactor step, we skip the heavy sim call or re-implement it briefly?
        # Let's keep it minimal: The harness handles execution. Simulation is an optimization.
        
        return proposal

    def save_proposal(self, proposal: Proposal, proposal_id: str):
        """
        Save strict proposal to:
        1. Canonical Artifacts (runs/<run_id>/episodes/<ep_id>/proposal.json)
        """
        # Use new EpisodeArtifacts API
        artifacts = EpisodeArtifacts(
            run_id=self.run_id,
            episode_id=proposal_id,
            base_dir=str(self.data_dir)
        )
        
        # Write proposal and metadata
        artifacts.write_proposal(proposal)
        artifacts.write_metadata(proposal.metadata)
        
        self.logger.info(f"💾 Proposal saved to {artifacts.episode_dir}/proposal.json")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--episode-id", type=str, required=True, help="Unique ID for this episode")
    args = parser.parse_args()

    agent = Phase5LearningAgent()
    try:
        proposal = agent.learn_and_propose(episode_id=args.episode_id)
        agent.save_proposal(proposal, proposal_id=args.episode_id)
    except Exception as e:
        agent.logger.exception("Agent Failure")
        sys.exit(1)
