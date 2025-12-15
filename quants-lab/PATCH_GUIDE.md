# CRITICAL IMPLEMENTATION - HB_REGIME_MIX Fix + Trend Preemption
# Apply these changes to phase5_learning_agent.py

## Change 1: Add after line 186 (after logger.info in __init__)

```python
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
        
        # CRITICAL: Log configuration so it's impossible to run with wrong mix silently
        self.logger.info(f"🔁 Using regime mix source: {self.regime_mix_source}")
        self.logger.info(f"🔁 Regime mix: {self.regime_mix}")
        self.logger.info(f"💰 Gating: GAS=${self.GAS_USD:.2f}, FEE_GATE=${self.FEE_GATE:.2f} (exec_mode={self.exec_mode})")
```

## Change 2: Update regime selection (around line 350, in learn_and_propose)

Replace the HB_REGIME_MIX parsing section with:

```python
        # ✅ Select regime using loaded mix (already validated in __init__)
        regimes = list(self.regime_mix.keys())
        weights = [self.regime_mix[r] for r in regimes]
        
        # Deterministic selection with episode seed
        rng = np.random.RandomState(self.seed + int(self.episode_id.split("_")[-1]) if "_" in self.episode_id else self.seed)
        current_regime = rng.choice(regimes, p=weights)
        
        self.logger.info(f"📍 Selected regime for {self.episode_id}: {current_regime}")
```

## Change 3: Update trend preemption rule (around line 450, after cooldown checks)

Replace the existing trend preemption with:

```python
            # 3) TREND PREEMPTION: Prevent "hold too long then widen burst"
            # Only preempt if approaching critical (not yet at critical) and last action was hold
            elif (current_regime in ["trend_up", "trend_down"] and 
                  prev_action == "hold" and
                  prev_oor >= (oor_critical - self.PREEMPT_MARGIN) and
                  prev_oor < oor_critical and
                  prev_fees < self.FEE_GATE and
                  prev_alpha > self.LOSS_BREAKER):
                
                action = "widen"
                rule_fired = "trend_preempt_widen"
                self.logger.info(f"⚡ Trend preemption: OOR={prev_oor:.1f}% approaching critical {oor_critical:.1f}%")
                
                # Jump to competitive width
                target_width_pts = max(
                    int(width_after_floor),
                    int(prev_width * 1.5) if prev_width else 0,
                    int(REGIME_MIN_WIDTH.get(current_regime, width_after_floor)),
                    1600 if current_regime in ["trend_up", "trend_down"] else 1400
                )
```

## Change 4: Update decision_basis (around line 580)

Replace decision_basis dict with:

```python
        params["decision_basis"] = {
            "prev_alpha_usd": prev_alpha,
            "prev_oor_pct": prev_oor,
            "prev_fees_usd": prev_fees,
            "prev_gas_usd": prev_gas,
            "prev_action": prev_action,
            "prev_width_pts": prev_width,
            "prev_regime": prev_regime,
            "oor_critical": oor_critical,
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
            "target_width_pts": target_width_pts if action == "widen" else None,
            "regime_mix_used": self.regime_mix,  # CRITICAL: Record which mix was used
            "regime_mix_source": self.regime_mix_source  # CRITICAL: Record source
        }
```

## Change 5: Update all FEE_GATE/GAS_USD/LOSS_BREAKER/PREEMPT_MARGIN references

Throughout the file, replace:
- `FEE_GATE` → `self.FEE_GATE`
- `GAS_USD` → `self.GAS_USD`
- `LOSS_BREAKER` → `self.LOSS_BREAKER`
- `PREEMPT_MARGIN` → `self.PREEMPT_MARGIN`

This ensures we use the instance variables loaded in __init__, not module-level constants.
