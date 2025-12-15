"""
Dune-Calibrated EV-Gated Regime LP Policy V3.1 (Amortized Tightening & Piggyback)

A production-style policy that answers: "When should I care and act?"
Features:
- Policy V3 base (Regime gates, Economic Focusing, Churn Brake)
- Amortized Tightening: Tighten if (edge * expected_hold) > gas
- Piggyback Optimization: When paying gas anyway, pick best width
- Debug Logging: Captures missed tightening potential
"""

import os
from typing import Dict, Any, Optional

def _gas_usd(gas_regime: str) -> float:
    return {
        "low": 2.0,
        "medium": 5.0,
        "high": 15.0,
        "extreme": 50.0
    }.get(gas_regime, 5.0)

def _width_from_position(pos: Dict[str, Any]) -> int:
    try:
        return int(pos["tick_upper"]) - int(pos["tick_lower"])
    except Exception:
        return 0

def _est_in_range_frac(tick_path: list, center_tick: int, width_pts: int) -> float:
    if not tick_path: 
        return 0.0
    half = max(1, width_pts // 2)
    lo, hi = center_tick - half, center_tick + half
    return sum(lo <= t <= hi for t in tick_path) / len(tick_path)

def _position_share_proxy(width_pts: int, order_size: float = 0.1) -> float:
    """
    Keep this consistent with env._compute_position_share so gates are meaningful.
    """
    ORDER_SIZE_USD_MULT = float(os.getenv("ORDER_SIZE_USD_MULT", "2000.0"))
    pool_liquidity = float(os.getenv("POOL_LIQUIDITY_PROXY", "1000000.0"))
    liquidity_proxy_mult = float(os.getenv("LIQUIDITY_PROXY_MULT", "50.0"))
    conc_cap = float(os.getenv("CONC_MULT_CAP", "2.0"))
    cap = float(os.environ.get("MAX_POSITION_SHARE", "0.0005"))

    order_usd = float(order_size) * ORDER_SIZE_USD_MULT
    liq_usd = pool_liquidity * liquidity_proxy_mult
    base = order_usd / (liq_usd + 1e-9)

    conc = (2000.0 / max(float(width_pts), 50.0)) ** 0.5
    conc = min(conc_cap, max(1.0, conc))

    return max(0.0, min(cap, base * conc))

def dune_stateful_focus_policy_v3_1(
    *,
    tick_path: list,
    volume_usd: float,
    derived_regime: str,
    derived_regime_features: Dict[str, Any],
    fee_rate: float,
    gas_regime: str,
    order_size: float,
    toxic_flow_index: Optional[float] = None,
    mev_risk: Optional[float] = None,
    current_position: Optional[Dict[str, Any]] = None,
    cooldown_active: bool = False,
    toxic_threshold: float = 0.7,
) -> Dict[str, Any]:
    """
    Returns decision dict with action, width, care_score, etc.
    """

    gas_usd = _gas_usd(gas_regime)

    # --- toxicity ---
    is_toxic = False
    if toxic_flow_index is not None and toxic_flow_index > toxic_threshold:
        is_toxic = True
    if mev_risk is not None and mev_risk > toxic_threshold:
        is_toxic = True

    # --- regime-dependent gates ---
    gates = {
        "mean_revert": {"care_enter": 0.7, "fee_enter": 1.0, "care_focus": 1.5, "fee_focus": 2.0},
        "low_vol":     {"care_enter": 0.9, "fee_enter": 1.5, "care_focus": 1.6, "fee_focus": 2.5},
        "trend_up":    {"care_enter": 1.1, "fee_enter": 2.0, "care_focus": 1.7, "fee_focus": 3.0},
        "trend_down":  {"care_enter": 1.1, "fee_enter": 2.0, "care_focus": 1.7, "fee_focus": 3.0},
        "jumpy":       {"care_enter": 1.8, "fee_enter": 3.0, "care_focus": 2.2, "fee_focus": 4.0},
        "unknown":     {"care_enter": 1.2, "fee_enter": 2.5, "care_focus": 1.8, "fee_focus": 3.5},
    }
    g = gates.get(derived_regime, gates["unknown"])

    # --- focusing ladder ---
    ladder = {
        "mean_revert": {"enter": 2000, "focus1": 1400, "focus2": 900, "focus3": 700},
        "low_vol":     {"enter": 1200, "focus1": 900,  "focus2": 800},
        "trend_up":    {"enter": 1400, "focus1": 1100, "focus2": 900},
        "trend_down":  {"enter": 1400, "focus1": 1100, "focus2": 900},
        "jumpy":       {"enter": 2200, "focus1": 2000, "focus2": 2000},
        "unknown":     {"enter": 1500, "focus1": 1200, "focus2": 1000},
    }
    w = ladder.get(derived_regime, ladder["unknown"])

    # --- stability signal ---
    std_step = float(derived_regime_features.get("std_step", 0.0))
    jump_count = float(derived_regime_features.get("jump_count", 0.0))
    directionality = float(derived_regime_features.get("directionality_ratio", 0.0))
    stable_now = (jump_count <= 1) and (std_step < 80) and (directionality < 0.55)

    last_in_range = None
    episodes_since_rebal = 0
    if current_position is not None:
        if "_last_in_range_frac" in current_position:
            last_in_range = float(current_position["_last_in_range_frac"])
        episodes_since_rebal = int(current_position.get("_episodes_since_rebalance", 0))

    stable_confirmed = stable_now and (last_in_range is None or last_in_range >= 0.80)

    # --- economics helpers ---
    center = tick_path[0] if tick_path else 0
    
    def calc_potential(width_pts):
        p_in = _est_in_range_frac(tick_path, center, width_pts)
        sh = _position_share_proxy(width_pts, order_size)
        fees = float(volume_usd) * float(fee_rate) * sh * p_in
        return fees, p_in

    # Optimize Choice Helper (Piggyback)
    def pick_best_width(candidate_names):
        best_w = w[candidate_names[0]]
        best_fees = 0.0
        best_name = candidate_names[0]
        
        for name in candidate_names:
            if name not in w: continue
            cand_w = w[name]
            fees, p_in = calc_potential(cand_w)
            
            # Safe entry constraint: don't pick dangerously tight widths for entry in jumpy
            if derived_regime == "jumpy" and p_in < 0.90: continue
            if p_in < 0.75: continue # General safety floor
            
            # Maximize Fees
            if fees > best_fees:
                best_fees = fees
                best_w = cand_w
                best_name = name
        return best_w, best_fees, best_name


    # Current stats
    fees_curr = 0.0
    p_curr = 0.0
    cur_w = 0 
    if current_position:
        cur_w = max(50, _width_from_position(current_position))
        fees_curr, p_curr = calc_potential(cur_w)

    # Entry stats
    fees_enter, p_enter = calc_potential(w["enter"])
    care_score_enter = fees_enter / max(gas_usd, 0.1)
    top_care_score = care_score_enter

    decision_basis = {
        "derived_regime": derived_regime,
        "expected_fees_curr": round(fees_curr, 4),
        "gas_usd": round(gas_usd, 2),
        "care_score": round(top_care_score, 4),
        "stable_confirmed": stable_confirmed,
        "episodes_since_rebal": episodes_since_rebal,
        "cooldown_active": cooldown_active,
        "is_toxic": is_toxic,
        "gates": g,
        "candidates": {} # Populated below
    }

    # Populate candidates debug
    for k in ["enter", "focus1", "focus2", "focus3"]:
        if k in w:
            f, p = calc_potential(w[k])
            decision_basis["candidates"][k] = {"fees": round(f,4), "p_in": round(p,3)}

    # --- Hard Stops ---
    if cooldown_active:
        return {"action": "hold", "width_pts": None, "care_score": top_care_score, "decision_basis": {**decision_basis, "action_reason": "Cooldown"}}
    if is_toxic:
        if current_position:
            return {"action": "hold", "width_pts": None, "care_score": top_care_score, "decision_basis": {**decision_basis, "action_reason": "Toxic -> hold"}}
        return {"action": "hold", "width_pts": None, "care_score": top_care_score, "decision_basis": {**decision_basis, "action_reason": "Toxic -> stay out"}}

    # --- 1. ENTER Logic (Piggyback) ---
    if current_position is None:
        if fees_enter >= g["fee_enter"] and care_score_enter >= g["care_enter"]:
            # Piggyback: Try to pick a better entry width if possible, but default to 'enter' logic safety
            # Check focus1 as potential better entry if very stable? 
            # For simplicity & safety, sticking to "enter" tier or focus1 if strictly better
            best_w, chosen_fees, name = pick_best_width(["enter", "focus1"])
            
            return {"action": "enter", "width_pts": int(best_w), "care_score": top_care_score,
                    "decision_basis": {**decision_basis, "action_reason": f"Enter ({name}) - gate passed"}}
        return {"action": "hold", "width_pts": None, "care_score": top_care_score,
                "decision_basis": {**decision_basis, "action_reason": "Stay out (gate not met)"}}

    # --- 2. EXISTING POSITION Logic ---
    current_tick = tick_path[-1] if tick_path else 0
    tl = int(current_position.get("tick_lower", 0))
    tu = int(current_position.get("tick_upper", 0))
    in_range_now = (tl <= current_tick <= tu)

    # A) Out of Range -> Rebalance (Piggyback)
    if not in_range_now:
        # Since we pay gas anyway, pick BEST valid width
        cands = ["enter", "focus1", "focus2", "focus3"] if derived_regime != "jumpy" else ["enter", "focus1"]
        best_w, best_fees, best_name = pick_best_width(cands)
        
        care_target = best_fees / max(gas_usd, 0.1)
        
        if best_fees >= g["fee_enter"] and care_target >= g["care_enter"]:
            return {"action": "rebalance", "width_pts": int(best_w), "care_score": care_target,
                    "decision_basis": {**decision_basis, "action_reason": f"OOR -> Rebalance to {best_name}"}}
        return {"action": "hold", "width_pts": None, "care_score": care_target,
                "decision_basis": {**decision_basis, "action_reason": "OOR -> not worth gas"}}

    # B) In Range -> Tighten (Amortized)
    # B) In Range -> Tighten (Amortized)
    # Candidate check
    candidates = [k for k in ["focus3", "focus2", "focus1"] if k in w]  # tightest first

    # Estimate how long we expect to hold before next rebalance (amortize gas)
    # Prefer a stateful streak if you have it; otherwise fall back to last_in_range_frac.
    streak = 0
    if current_position is not None:
        streak = int(current_position.get("_episodes_in_range", 0) or current_position.get("_episodes_since_rebalance", 0) or 0)

    # Horizon grows with demonstrated stability, but capped (tune caps per regime if you want)
    base_cap = 6 if derived_regime != "jumpy" else 3
    hold_horizon = max(1, min(base_cap, 1 + streak))

    # If you want to be stricter, require stability_now/stable_confirmed here too
    for cand_key in candidates:
        cand_w = int(w[cand_key])
        cur_w = max(50, _width_from_position(current_position))

        # Only tighten, never widen here (widening happens if OOR)
        if cand_w >= cur_w:
            continue

        fees_cand, p_cand = calc_potential(cand_w)
        care_cand = fees_cand / max(gas_usd, 0.1)

        # 1) High prob of staying in range
        min_p = 0.90 if derived_regime == "jumpy" else 0.80
        if p_cand < min_p:
            continue

        # 2) Clears focus gates
        if care_cand < g["care_focus"] or fees_cand < g["fee_focus"]:
            continue

        # 3) Amortized edge: (per-episode incremental fees) * expected hold episodes > gas buffer
        delta_per_ep = float(fees_cand) - float(fees_curr)
        delta_total = delta_per_ep * hold_horizon

        buffer = 1.2  # keep your safety margin
        if delta_total > (gas_usd * buffer):
            return {
                "action": "rebalance",
                "width_pts": cand_w,
                "care_score": care_cand,
                "decision_basis": {
                    **decision_basis,
                    "action_reason": f"Tighten -> {cand_key} (Δ/ep ${delta_per_ep:.2f}, horizon {hold_horizon}, Δtot ${delta_total:.2f})",
                    "tighten_debug": {
                        "fees_curr": round(float(fees_curr), 4),
                        "fees_cand": round(float(fees_cand), 4),
                        "p_cand": round(float(p_cand), 4),
                        "min_p": min_p,
                        "hold_horizon": hold_horizon,
                        "delta_per_ep": round(delta_per_ep, 4),
                        "delta_total": round(delta_total, 4),
                        "gas_usd": round(float(gas_usd), 4),
                        "buffer": buffer,
                    },
                },
            }

    return {"action": "hold", "width_pts": None, "care_score": top_care_score,
            "decision_basis": {**decision_basis, "action_reason": "In range -> hold"}}


def create_dune_calibrated_proposal(
    episode_id: str,
    tick_path: list,
    volume_usd: float,
    derived_regime: str,
    derived_regime_features: Dict[str, Any],
    intel_snapshot: Optional[Dict] = None,
    current_position: Optional[Dict] = None,
    cooldown_active: bool = False,
    order_size: float = 10.0
) -> Dict[str, Any]:
    """
    Create a proposal using the Dune-Calibrated EV-Gated policy V3.1.
    """
    
    # Extract intel if available
    fee_rate = 0.0005  # WETH-USDC 0.05%
    gas_regime = "medium"
    toxic_flow_index = None
    mev_risk = None
    
    if intel_snapshot:
        gas_data = intel_snapshot.get("gas_regime", {})
        if isinstance(gas_data, dict):
            gas_regime = gas_data.get("data", {}).get("regime", "medium")
        
        toxic_data = intel_snapshot.get("toxic_flow_index", {})
        if isinstance(toxic_data, dict):
            toxic_flow_index = toxic_data.get("data", {}).get("index")
        
        mev_data = intel_snapshot.get("mev_risk", {})
        if isinstance(mev_data, dict):
            mev_risk = mev_data.get("data", {}).get("risk_score")
    
    # Get policy decision (V3.1)
    decision = dune_stateful_focus_policy_v3_1(
        tick_path=tick_path,
        volume_usd=volume_usd,
        derived_regime=derived_regime,
        derived_regime_features=derived_regime_features,
        fee_rate=fee_rate,
        gas_regime=gas_regime,
        order_size=order_size,
        toxic_flow_index=toxic_flow_index,
        mev_risk=mev_risk,
        current_position=current_position,
        cooldown_active=cooldown_active,
        toxic_threshold=float(os.getenv("TOXIC_THRESHOLD", "0.7")),
    )
    
    policy_action = decision["action"]
    width_pts = int(decision["width_pts"] or 0)

    # Convert to proposal format
    proposal = {
        "episode_id": episode_id,
        "action": policy_action,
        "order_size": order_size,
        "width_pts": width_pts if policy_action in ("enter", "rebalance") else 0,
        "rebalance_threshold_pct": 10.0,
        "decision_basis": decision["decision_basis"],
        "care_score": float(decision["care_score"]),
        "policy_name": "stateful_focus_v3_1"
    }
    
    return proposal
