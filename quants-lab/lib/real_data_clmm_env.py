"""
Real Data CLMM Environment

Uses historical tick data from Dune Analytics instead of synthetic mock data.
Enables validation against real LP performance.
"""

import os
from pathlib import Path
from typing import Dict, Any, Optional, List
from .historical_data_cache import HistoricalDataCache
from .dune_client import DuneClient
from .schemas import Proposal, EpisodeResult
from .run_context import RunContext


class RealDataCLMMEnvironment:
    """
    CLMM environment that replays real historical tick data from Dune.
    
    Features:
    - Uses cached historical tick paths instead of synthetic generation
    - Calculates fees from real volume data
    - Validates baselines against real LP performance
    - Deterministic replay based on historical time windows
    """
    
    def __init__(self, cache_dir: Optional[Path] = None, dune_client: Optional[DuneClient] = None):
        """
        Initialize real data environment.
        
        Args:
            cache_dir: Directory for historical data cache
            dune_client: Optional DuneClient for fetching data (uses env if None)
        """
        if cache_dir is None:
            cache_dir = Path(os.getenv("HISTORICAL_DATA_CACHE_DIR", "scratch/data/historical_cache"))
        
        # Initialize Dune client if not provided
        if dune_client is None and os.getenv("DUNE_API_KEY"):
            try:
                dune_client = DuneClient()
            except Exception as e:
                print(f"[RealDataEnv] Warning: Could not initialize DuneClient: {e}")
        
        self.cache = HistoricalDataCache(cache_dir, dune_client)
        self.pool_address = "0x88e6A0c2dDD26FEEb64F039a2c41296FcB3f5640"  # WETH-USDC 0.05%
        
        print(f"[RealDataEnv] Initialized with cache: {cache_dir}")
    
    def _select_historical_window(self, episode_id: str) -> tuple[int, int, int]:
        """
        Select a historical time window for this episode.
        
        Strategy:
        - Divide last 90 days into 6-hour windows
        - Rotate through windows deterministically based on episode_id
        - Ensures diverse market conditions across episodes
        
        Returns:
            (start_timestamp, end_timestamp, window_index) tuple
        
        Improvement 3: Return window_index for determinism tracking
        """
        import time
        import hashlib
        
        EPISODE_DURATION_S = int(os.getenv("HB_EPISODE_HORIZON_S", "21600"))  # 6 hours default
        LOOKBACK_DAYS = int(os.getenv("HISTORICAL_LOOKBACK_DAYS", "90"))
        
        # Use episode_id hash to deterministically select window
        episode_hash = int(hashlib.md5(episode_id.encode()).hexdigest(), 16)
        
        # Allow deterministic time mocking for CI/QA
        mock_time = os.getenv("HB_MOCK_CURRENT_TIME")
        if mock_time:
            now = int(mock_time)
        else:
            now = int(time.time())
            
        # Quantize to hour boundary to prevent "sliding window" cache misses
        # If we don't do this, running the script 1s later shifts the window by 1s,
        # creating a new cache entry every time.
        now = (now // 3600) * 3600
        
        lookback_start = now - (LOOKBACK_DAYS * 86400)
        
        # Calculate number of available windows
        num_windows = (LOOKBACK_DAYS * 86400) // EPISODE_DURATION_S
        
        # Hash episode ID to ensure consistent window selection
        episode_hash = int(hashlib.sha256(episode_id.encode()).hexdigest(), 16)
        
        # Select window deterministically
        window_index = episode_hash % num_windows
        start_ts = lookback_start + (window_index * EPISODE_DURATION_S)
        end_ts = start_ts + EPISODE_DURATION_S
        
        return start_ts, end_ts, window_index
    
    def _in_range(self, tick: int, pos: dict) -> bool:
        return pos["tick_lower"] <= tick <= pos["tick_upper"]

    def _make_position(self, center_tick: int, width_pts: int) -> dict:
        half = max(1, int(width_pts // 2))
        return {"tick_lower": int(center_tick - half), "tick_upper": int(center_tick + half)}

    def _compute_position_share(self, order_size: float, width_pts: int) -> float:
        # Convert to USD proxy
        ORDER_SIZE_USD_MULT = float(os.getenv("ORDER_SIZE_USD_MULT", "2000.0"))
        order_size_usd_proxy = order_size * ORDER_SIZE_USD_MULT

        # Liquidity proxy (bigger => smaller share)
        pool_liquidity = float(os.getenv("POOL_LIQUIDITY_PROXY", "1000000.0"))
        liquidity_proxy_mult = float(os.getenv("LIQUIDITY_PROXY_MULT", "50.0"))
        liquidity_usd_proxy = pool_liquidity * liquidity_proxy_mult

        base_share = order_size_usd_proxy / (liquidity_usd_proxy + 1e-9)

        # Concentration multiplier
        conc = (2000.0 / max(float(width_pts), 50.0)) ** 0.5
        conc_cap = float(os.getenv("CONC_MULT_CAP", "2.0"))
        conc = min(conc_cap, max(1.0, conc))

        share = base_share * conc

        # Hard cap
        cap = float(os.environ.get("MAX_POSITION_SHARE", "0.0005"))
        return max(0.0, min(cap, share))

    def execute_episode(self, proposal: Proposal, ctx: RunContext) -> EpisodeResult:
        """
        Execute episode using real historical data.
        
        Args:
            proposal: Agent's proposed action
            ctx: Run context with episode metadata
        
        Returns:
            EpisodeResult with performance metrics
        """
        from datetime import datetime
        import hashlib
        import json
        
        # Select historical time window (Improvement 3: includes window_index)
        override_ts = proposal.params.get("historical_window_start_ts")
        if override_ts:
            start_ts = int(override_ts)
            end_ts = start_ts + 21600 # 6 hours
            if proposal.metadata.extra.get("window_index") is not None:
                window_index = proposal.metadata.extra.get("window_index") 
            else:
                 window_index = -1 
        else:
            start_ts, end_ts, window_index = self._select_historical_window(ctx.episode_id)

        # Fetch the tick data for this window
        tick_data = self.cache.get_tick_window(
            pool_address=self.pool_address,
            start_ts=start_ts,
            duration_seconds=end_ts - start_ts,
            granularity="hour"
        )

        duration_s = end_ts - start_ts
        
        print(f"[RealDataEnv] Episode {ctx.episode_id}")
        print(f"  Window Index: {window_index}")
        print(f"  Historical window: {datetime.fromtimestamp(start_ts)} to {datetime.fromtimestamp(end_ts)}")
        
        if not tick_data or len(tick_data) == 0:
            raise ValueError(f"No historical tick data found for window {start_ts} to {end_ts}")
        
        print(f"  Got {len(tick_data)} tick snapshots")
        
        # GUARDRAIL A: Schema validation for new fee fields
        required_fields = ['fees_usd', 'pool_fees_usd_from_inputs', 'pool_fees_usd_two_sided']
        # Check first snapshot as proxy
        if tick_data and not all(f in tick_data[0] for f in required_fields):
             # Fallback note: if fields missing, maybe old cache?
             # Ideally we should raise or warn. For now, let's warn loudly and fallback 
             missing = [f for f in required_fields if f not in tick_data[0]]
             print(f"  ⚠️ CRITICAL: Cache missing accurate fee fields {missing}! using fallback logic.")
             use_fallback_fee_logic = True
        else:
             use_fallback_fee_logic = False

        # Initialize fee accumulators
        fees_0 = 0.0  # USDC
        fees_1 = 0.0  # WETH

        # Extract tick path and volume
        tick_path = [int(t.get('tick', 0)) for t in tick_data]
        vol_path = [float(t.get('volume_usd_two_sided', 0.0)) for t in tick_data]
        total_volume_usd = sum(vol_path)
        
        # Get pool parameters
        fee_rate = float(os.getenv("FEE_RATE", "0.0005"))
        
        # Determine position BEFORE action
        pos_before = proposal.params.get("current_position") # Passed from runner

        # Apply action to get pos_after
        gas_cost_usd = 0.0
        action = proposal.params.get("action", "hold") # "enter", "rebalance", "hold", "exit"
        width_pts = int(proposal.params.get("width_pts", 1500))
        center_tick = tick_path[0] # deterministic start

        GAS_USD = float(os.getenv("GAS_USD", "2.0"))

        if action == "enter":
            gas_cost_usd = GAS_USD
            pos_after = self._make_position(center_tick, width_pts)
        elif action == "rebalance":
            gas_cost_usd = GAS_USD
            pos_after = self._make_position(center_tick, width_pts)
        elif action == "exit":
            gas_cost_usd = GAS_USD
            pos_after = None
        else: # hold
            pos_after = pos_before # Keep existing

        # Now compute fees earned WITH pos_after
        fees_usd = 0.0
        in_range_steps = 0
        position_share = 0.0
        
        # Cross-check accumulators
        ep_pool_fees_usd = 0.0 # From fees_usd column
        ep_pool_fees_from_inputs = 0.0 # From calculated inputs
        ep_pool_fees_two_sided = 0.0 # From volume_usd (approx 2x)
        
        if pos_after is not None:
            order_size = float(proposal.params.get("order_size", 0.1))
            position_share = self._compute_position_share(order_size=order_size, width_pts=width_pts)

            for i, t in enumerate(tick_data):
                tick_val = int(t.get('tick', 0))
                
                # New Logic: Use pre-computed fees_usd from Dune
                if not use_fallback_fee_logic:
                    snapshot_fees_usd = float(t.get('fees_usd', 0.0))
                    
                    ep_pool_fees_usd += snapshot_fees_usd
                    ep_pool_fees_from_inputs += float(t.get('pool_fees_usd_from_inputs', 0.0))
                    ep_pool_fees_two_sided += float(t.get('pool_fees_usd_two_sided', 0.0))
                    
                    if self._in_range(tick_val, pos_after):
                        in_range_steps += 1
                        
                        # --- HUMMINGBOT-STYLE ACCOUNTING (Native first, derived USD) ---
                        # 1. Accumulate native fees (Token0/Token1)
                        snapshot_fees_0 = float(t.get('fees_usdc', 0.0))
                        snapshot_fees_1 = float(t.get('fees_weth', 0.0))
                        
                        fees_0_earned = snapshot_fees_0 * position_share
                        fees_1_earned = snapshot_fees_1 * position_share
                        
                        fees_0 += fees_0_earned
                        fees_1 += fees_1_earned
                        
                        # 2. Derive USD (Per snapshot to avoid average price drift)
                        weth_usd = float(t.get('weth_usd', 0.0))
                        
                        # GUARDRAIL: Inverted price check
                        if weth_usd != 0 and weth_usd < 10:
                            # Critical data error - we must not trust this cache. 
                            # Failing fast is better than accruing 1/1000th of the value.
                            raise ValueError(f"CRITICAL: weth_usd looks inverted (<10): {weth_usd}. Expected ~2000-4000.")
                            
                        # USD = Fees0 (USDC) + Fees1 (WETH) * Price
                        fees_usd += fees_0_earned + (fees_1_earned * weth_usd)

                else:
                    # Fallback logic (volume * fee_rate)
                    vol_usd = float(t.get('volume_usd', 0.0))
                    snapshot_fees_usd = vol_usd * fee_rate
                    ep_pool_fees_usd += snapshot_fees_usd
                    
                    if self._in_range(tick_val, pos_after):
                        in_range_steps += 1
                        fees_usd += snapshot_fees_usd * position_share
                        # In fallback, fees_0/fees_1 remain 0 because we don't have granular data

            # Cross-check Logging (Removed, replaced by rigorous block below)
            pass

        # 2. WETH_USD sanity checks
        weth_usds = [float(t.get('weth_usd', 0)) for t in tick_data]
        avg_weth_usd = sum(weth_usds) / len(weth_usds) if weth_usds else 0
        min_weth_usd = min(weth_usds) if weth_usds else 0
        max_weth_usd = max(weth_usds) if weth_usds else 0

        if not use_fallback_fee_logic:
             pass 
             # We already computed fees_usd incrementally in the loop above.
             # Verification:
             # avg_weth_usd = sum(weth_usds) / len(weth_usds)
             # simple_fees_usd = fees_0 + fees_1 * avg_weth_usd
             # The incremental fees_usd is MORE accurate.

        # Gross PnL = Fees (ignores IL for now per instruction "keep it simple first")
        # Net PnL = Gross - Gas
        net_pnl_usd = fees_usd - gas_cost_usd

        # --- RIGOROUS FEE VERIFICATION ---
        # 1. Ratio Check
        # --- RIGOROUS FEE VERIFICATION ---

        # Integrity check: Dune fees_usd vs independently reconstructed USD fees from inputs
        ratio_integrity = ep_pool_fees_usd / (ep_pool_fees_from_inputs + 1e-9)

        # Volume-bias check: if amount_usd is two-sided, this should be ~2.0
        ratio_two_sided_over_input = ep_pool_fees_two_sided / (ep_pool_fees_usd + 1e-9)
        ratio_input_over_two_sided = ep_pool_fees_usd / (ep_pool_fees_two_sided + 1e-9)

        print(f"    Pool Fees (fees_usd):              ${ep_pool_fees_usd:,.2f}")
        print(f"    Pool Fees (from_inputs USD):       ${ep_pool_fees_from_inputs:,.2f}")
        print(f"    Pool Fees (two_sided amount_usd):  ${ep_pool_fees_two_sided:,.2f}")

        print(f"    Ratio fees_usd / from_inputs:      {ratio_integrity:.4f}  (expect ~1.0)")
        print(f"    Ratio two_sided / fees_usd:        {ratio_two_sided_over_input:.4f}  (expect ~2.0)")
        print(f"    Ratio fees_usd / two_sided:        {ratio_input_over_two_sided:.4f}  (expect ~0.5)")

        if ep_pool_fees_usd > 1.0 and not (0.95 <= ratio_integrity <= 1.05):
            print("    ⚠️ WARNING: fees_usd != reconstructed inputs (check weth_usd units / column mapping).")

        if ep_pool_fees_usd > 1.0 and not (1.8 <= ratio_two_sided_over_input <= 2.2):
            print("    ⚠️ WARNING: amount_usd-based fees not ~2x; query may have changed or amount_usd is not two-sided.")
        

             
        print(f"    LP Fees Earned: ${fees_usd:.4f} (Share: {position_share:.8f})")
        
        # Cross check LP USD
        # If we derived fees_usd from fees_0/1 via avg_price, this check is circular/tautological 
        # but confirms logic consistency.
        # However, pool fees check is still valid.
        pass
        # lp_usd_proxy = fees_0 + (fees_1 * avg_weth_usd)
        # print(f"    LP Maths Check: fees_0 + fees_1*price = ${lp_usd_proxy:.4f} vs fees_usd ${fees_usd:.4f}")
        # if abs(lp_usd_proxy - fees_usd) > max(0.1, fees_usd * 0.1):
        #      print(f"    ⚠️ WARNING: Significant deviation in LP fee math check!")
        
        # Improvement 3: Dataset fingerprint
        cache_manifest = {
            "tick_data_length": len(tick_data),
            "first_tick": tick_data[0] if tick_data else None,
            "last_tick": tick_data[-1] if tick_data else None,
            "total_volume": total_volume_usd
        }
        dataset_fingerprint = hashlib.sha256(
            json.dumps(cache_manifest, sort_keys=True).encode()
        ).hexdigest()[:12]
        
        # Improvement 5: Derive regime
        derived_regime, regime_features = self._derive_regime_label(tick_path)
        
        # ✅ DELIVERABLE 1: Run stateful baseline policies on same tick path
        from .clmm_env import (
            BASELINE_POLICIES, 
            run_stateful_baseline_policy, 
            get_regime_cfg,
            load_portfolio_state,
            save_portfolio_state,
            PortfolioState
        )
        
        # Load portfolio state (run-scoped)
        runs_dir = Path(os.environ.get("RUNS_DIR", "scratch/data/runs"))
        if not runs_dir.is_absolute():
            runs_dir = Path.cwd() / runs_dir
        run_dir = runs_dir / ctx.run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        
        portfolio_state = load_portfolio_state(run_dir)
        
        # Determine position BEFORE action from STATE
        pos_before = None
        if portfolio_state.position_open and portfolio_state.current_band:
            # Map PortfolioState band to internal format if needed
            # PortfolioState: {lower_tick, upper_tick, width_pts, fee}
            # Internal: {tick_lower, tick_upper}
            pos_before = {
                "tick_lower": portfolio_state.current_band["lower_tick"],
                "tick_upper": portfolio_state.current_band["upper_tick"]
            }

        # Apply action to get pos_after
        gas_cost_usd = 0.0
        action = proposal.params.get("action", "hold") # "enter", "rebalance", "hold", "exit"
        width_pts = int(proposal.params.get("width_pts", 1500))
        center_tick = tick_path[0] # deterministic start

        GAS_USD = float(os.getenv("GAS_USD", "2.0"))
        
        # Flag to track if we need to update state
        update_state = False

        if action == "enter":
            gas_cost_usd = GAS_USD
            pos_after = self._make_position(center_tick, width_pts)
            update_state = True
        elif action == "rebalance":
            gas_cost_usd = GAS_USD
            pos_after = self._make_position(center_tick, width_pts)
            update_state = True
        elif action == "exit":
            gas_cost_usd = GAS_USD
            pos_after = None
            update_state = True
        else: # hold
            pos_after = pos_before # Keep existing
            # If we held, but had no position, ensure pos_after is None
            if not portfolio_state.position_open:
                pos_after = None

        # Now compute fees earned WITH pos_after
        fees_usd = 0.0
        in_range_steps = 0
        position_share = 0.0
        
        # Cross-check accumulators
        ep_pool_fees_usd = 0.0 # From fees_usd column
        ep_pool_fees_from_inputs = 0.0 # From calculated inputs
        ep_pool_fees_two_sided = 0.0 # From volume_usd (approx 2x)
        
        if pos_after is not None:
            order_size = float(proposal.params.get("order_size", 0.1))
            # Use width from pos_after for share calculation if possible
            current_width = width_pts
            if action == "hold" and portfolio_state.current_band:
                 current_width = portfolio_state.current_band.get("width_pts", width_pts)
            
            position_share = self._compute_position_share(order_size=order_size, width_pts=current_width)

            for i, t in enumerate(tick_data):
                tick_val = int(t.get('tick', 0))
                
                # New Logic: Use pre-computed fees_usd from Dune
                if not use_fallback_fee_logic:
                    snapshot_fees_usd = float(t.get('fees_usd', 0.0))
                    
                    ep_pool_fees_usd += snapshot_fees_usd
                    ep_pool_fees_from_inputs += float(t.get('pool_fees_usd_from_inputs', 0.0))
                    ep_pool_fees_two_sided += float(t.get('pool_fees_usd_two_sided', 0.0))
                    
                    if self._in_range(tick_val, pos_after):
                        in_range_steps += 1
                        
                        # --- HUMMINGBOT-STYLE ACCOUNTING (Native first, derived USD) ---
                        # 1. Accumulate native fees (Token0/Token1)
                        snapshot_fees_0 = float(t.get('fees_usdc', 0.0))
                        snapshot_fees_1 = float(t.get('fees_weth', 0.0))
                        
                        fees_0_earned = snapshot_fees_0 * position_share
                        fees_1_earned = snapshot_fees_1 * position_share
                        
                        fees_0 += fees_0_earned
                        fees_1 += fees_1_earned
                        
                        # 2. Derive USD (Per snapshot to avoid average price drift)
                        weth_usd = float(t.get('weth_usd', 0.0))
                        
                        # GUARDRAIL: Inverted price check
                        if weth_usd != 0 and weth_usd < 10:
                            # Critical data error - we must not trust this cache. 
                            # Failing fast is better than accruing 1/1000th of the value.
                            raise ValueError(f"CRITICAL: weth_usd looks inverted (<10): {weth_usd}. Expected ~2000-4000.")
                            
                        # USD = Fees0 (USDC) + Fees1 (WETH) * Price
                        fees_usd += fees_0_earned + (fees_1_earned * weth_usd)

                else:
                    # Fallback logic (volume * fee_rate)
                    vol_usd = float(t.get('volume_usd', 0.0))
                    snapshot_fees_usd = vol_usd * fee_rate
                    ep_pool_fees_usd += snapshot_fees_usd
                    
                    if self._in_range(tick_val, pos_after):
                        in_range_steps += 1
                        fees_usd += snapshot_fees_usd * position_share
                        # In fallback, fees_0/fees_1 remain 0 because we don't have granular data

            pass
        
        # Update Portfolio State
        if pos_after:
            portfolio_state.position_open = True
            # Update band if action changed it
            if update_state:
                portfolio_state.current_band = {
                    "lower_tick": pos_after["tick_lower"],
                    "upper_tick": pos_after["tick_upper"],
                    "width_pts": width_pts,
                    "fee": "500" # 0.05%
                }
            portfolio_state.last_tick = tick_path[-1]
            portfolio_state.uncollected_fees_usd += fees_usd
        else:
            portfolio_state.position_open = False
            portfolio_state.current_band = None
            portfolio_state.last_tick = tick_path[-1]
            portfolio_state.uncollected_fees_usd = 0.0 # Reset
            
        save_portfolio_state(run_dir, portfolio_state)

        # 2. WETH_USD sanity checks
        weth_usds = [float(t.get('weth_usd', 0)) for t in tick_data]
        avg_weth_usd = sum(weth_usds) / len(weth_usds) if weth_usds else 0
        min_weth_usd = min(weth_usds) if weth_usds else 0
        max_weth_usd = max(weth_usds) if weth_usds else 0

        if not use_fallback_fee_logic:
             pass 

        # Gross PnL = Fees (ignores IL for now per instruction "keep it simple first")
        # Net PnL = Gross - Gas
        net_pnl_usd = fees_usd - gas_cost_usd

        # --- RIGOROUS FEE VERIFICATION ---
        # 1. Ratio Check
        # --- RIGOROUS FEE VERIFICATION ---

        # Integrity check: Dune fees_usd vs independently reconstructed USD fees from inputs
        ratio_integrity = ep_pool_fees_usd / (ep_pool_fees_from_inputs + 1e-9)

        # Volume-bias check: if amount_usd is two-sided, this should be ~2.0
        ratio_two_sided_over_input = ep_pool_fees_two_sided / (ep_pool_fees_usd + 1e-9)
        ratio_input_over_two_sided = ep_pool_fees_usd / (ep_pool_fees_two_sided + 1e-9)

        print(f"    Pool Fees (fees_usd):              ${ep_pool_fees_usd:,.2f}")
        print(f"    Pool Fees (from_inputs USD):       ${ep_pool_fees_from_inputs:,.2f}")
        print(f"    Pool Fees (two_sided amount_usd):  ${ep_pool_fees_two_sided:,.2f}")

        print(f"    Ratio fees_usd / from_inputs:      {ratio_integrity:.4f}  (expect ~1.0)")
        print(f"    Ratio two_sided / fees_usd:        {ratio_two_sided_over_input:.4f}  (expect ~2.0)")
        print(f"    Ratio fees_usd / two_sided:        {ratio_input_over_two_sided:.4f}  (expect ~0.5)")

        if ep_pool_fees_usd > 1.0 and not (0.95 <= ratio_integrity <= 1.05):
            print("    ⚠️ WARNING: fees_usd != reconstructed inputs (check weth_usd units / column mapping).")

        if ep_pool_fees_usd > 1.0 and not (1.8 <= ratio_two_sided_over_input <= 2.2):
            print("    ⚠️ WARNING: amount_usd-based fees not ~2x; query may have changed or amount_usd is not two-sided.")
        

             
        print(f"    LP Fees Earned: ${fees_usd:.4f} (Share: {position_share:.8f})")
        
        # Cross check LP USD
        pass
        
        # Improvement 3: Dataset fingerprint
        cache_manifest = {
            "tick_data_length": len(tick_data),
            "first_tick": tick_data[0] if tick_data else None,
            "last_tick": tick_data[-1] if tick_data else None,
            "total_volume": total_volume_usd
        }
        dataset_fingerprint = hashlib.sha256(
            json.dumps(cache_manifest, sort_keys=True).encode()
        ).hexdigest()[:12]
        
        baselines = {}
        baseline_actions = {}
        
        # Get derived regime config for baseline simulation parameters
        regime_cfg = get_regime_cfg(derived_regime, dict(os.environ))
        
        # Run each stateful baseline policy
        for policy_name in BASELINE_POLICIES.keys():
            # Use same params as mock env for consistency
            episode_horizon_s = int(os.environ.get("HB_EPISODE_HORIZON_S", "21600"))
            step_seconds = 3600  # Hourly data implies 3600s steps
            rebalance_cooldown_s = int(os.environ.get("HB_REBALANCE_COOLDOWN_S", "1800"))
            
            # Vol scale approximation from features
            vol_scale = 1.0 
            if "std_step" in regime_features:
                vol_scale = max(0.5, min(3.0, 1.0 + (regime_features["std_step"] / 100.0)))

            policy_result = run_stateful_baseline_policy(
                policy_name=policy_name,
                run_dir=run_dir,
                tick_path=tick_path,
                pool_liquidity=float(os.getenv("POOL_LIQUIDITY_PROXY", "1000000.0")), # Proxy liquidity
                fee_rate=fee_rate,
                tick_spacing=60, # WETH/USDC 0.05%
                mid_price_usd=2000.0, # Proxy
                order_size=float(proposal.params.get("order_size", 0.1)),
                episode_horizon_s=duration_s,
                step_seconds=step_seconds,
                rebalance_cooldown_s=rebalance_cooldown_s,
                regime_name=derived_regime,
                regime_cfg=regime_cfg,
                vol_scale=vol_scale,
            )
            baselines[policy_name] = policy_result
            baseline_actions[policy_name] = policy_result.get("action_applied", "unknown")
        
        # Compute alpha vs best baseline
        best_baseline_name = max(baselines.keys(), key=lambda k: baselines[k]["pnl_usd"])
        best_baseline_pnl = baselines[best_baseline_name]["pnl_usd"]
        
        alpha_usd = net_pnl_usd - best_baseline_pnl
        alpha_vs = best_baseline_name
        
        # Alpha metrics
        alpha_per_100k_vol = (alpha_usd / max(total_volume_usd, 1e-9)) * 100_000 if total_volume_usd > 0 else 0.0
        alpha_per_gas_usd = alpha_usd / max(gas_cost_usd, 1e-9) if gas_cost_usd > 0 else 0.0

        # Metadata
        historical_window = {
            "start_ts": start_ts,
            "end_ts": end_ts,
            "total_volume_usd": total_volume_usd,
            "tick_range": {
                "min": min(tick_path),
                "max": max(tick_path),
                "start": tick_path[0],
                "end": tick_path[-1]
            },
            "window_index": window_index,
            "dataset_fingerprint": dataset_fingerprint,
            "derived_regime": derived_regime,
            "order_size_usd_mult": float(os.getenv("ORDER_SIZE_USD_MULT", "2000.0")),
            "position_share": position_share,
            "max_position_share": float(os.getenv("MAX_POSITION_SHARE", "0.0005"))
        }

        # Create result
        result = EpisodeResult(
            run_id=ctx.run_id,
            status="success",
            episode_id=ctx.episode_id,
            pnl_usd=net_pnl_usd,
            fees_usd=fees_usd,
            gas_cost_usd=gas_cost_usd,
            out_of_range_pct=1.0 - (in_range_steps / len(tick_path)) if tick_path else 1.0,
            rebalance_count=1 if action in ["enter", "rebalance", "exit"] else 0, # Rough proxy
            alpha_usd=float(alpha_usd),
            best_baseline_name=best_baseline_name,
            baselines=baselines, 
            baseline_actions=baseline_actions,
            alpha_vs=alpha_vs, # Added field
            alpha_per_100k_vol=float(alpha_per_100k_vol), # Added field
            alpha_per_gas_usd=float(alpha_per_gas_usd), # Added field
            position_after={
                "regime_name": "real_data",
                "historical_window": historical_window,
                "current_position": pos_after,
                "width_pts": width_pts if pos_after else None,
                "position_share": position_share if pos_after else 0.0,
                "in_range_steps": in_range_steps,
                "num_steps": len(tick_path),
                "in_range_frac": (in_range_steps / len(tick_path)) if tick_path else 0.0,
                "total_volume_usd": total_volume_usd,
                # New observability fields
                "best_baseline_pnl_usd": float(best_baseline_pnl),
                "best_baseline_name": best_baseline_name,
            },
            
            # Fee Validation Metrics
            fees_0=fees_0,
            fees_1=fees_1,
            pool_fees_usd_input_based=ep_pool_fees_usd,
            pool_fees_usd_amount_usd_based=ep_pool_fees_two_sided
        )
        
        return result
    
    def _derive_regime_label(self, tick_path: List[int]) -> tuple[str, Dict[str, Any]]:
        """
        Derive regime label from realized tick path.
        
        Improvement 5: Post-hoc regime classification based on realized features.
        
        Returns:
            (regime_name, regime_features) tuple
        """
        import numpy as np
        
        if len(tick_path) < 2:
            return "unknown", {}
        
        # Calculate features
        tick_arr = np.array(tick_path)
        tick_diffs = np.diff(tick_arr)
        
        end_tick_delta = tick_path[-1] - tick_path[0]
        std_step = float(np.std(tick_diffs))
        mean_step = float(np.mean(tick_diffs))
        
        # Jump detection (steps > 2 std devs)
        jump_threshold = 2.0 * std_step if std_step > 0 else 100
        jump_count = int(np.sum(np.abs(tick_diffs) > jump_threshold))
        
        # Directionality
        up_steps = int(np.sum(tick_diffs > 0))
        down_steps = int(np.sum(tick_diffs < 0))
        total_steps = len(tick_diffs)
        directionality_ratio = abs(up_steps - down_steps) / total_steps if total_steps > 0 else 0
        
        features = {
            "end_tick_delta": int(end_tick_delta),
            "std_step": round(std_step, 2),
            "mean_step": round(mean_step, 2),
            "jump_count": jump_count,
            "directionality_ratio": round(directionality_ratio, 3),
            "up_steps": up_steps,
            "down_steps": down_steps
        }
        
        # Classify regime
        if jump_count > len(tick_path) * 0.1:  # >10% jumps
            regime = "jumpy"
        elif directionality_ratio > 0.6:
            regime = "trend_up" if end_tick_delta > 0 else "trend_down"
        elif std_step < 20:  # Low volatility
            regime = "low_vol"
        else:
            regime = "mean_revert"
        
        return regime, features
