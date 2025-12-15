# Implementation Plan: Trend-Up Preemption + FEE_GATE Optimization

## Changes Required

### 1. Add Exec-Mode-Aware Gating Constants (Lines 28-48)

```python
# ✅ EV-gated gas action constants (EXEC-MODE AWARE)
# Source: dune_queries/calibration_report.json for live/paper
# Mock uses observed gas costs from simulation
EXEC_MODE = os.environ.get("EXEC_MODE", "mock")

if EXEC_MODE == "mock":
    # Mock environment: use observed gas costs
    GAS_USD = float(os.environ.get("GAS_USD", "2.0"))
    FEE_GATE_MULTIPLIER = float(os.environ.get("FEE_GATE_MULT", "2.0"))
    FEE_GATE = FEE_GATE_MULTIPLIER * GAS_USD
else:
    # Live/Paper: use Dune calibration
    GAS_USD = 4.2
    FEE_GATE = 8.4

LOSS_BREAKER = -1000.0
PREEMPT_MARGIN = 3.0  # Preempt widen at (oor_critical - margin)
```

### 2. Add Calibrated Regime Mix Loading (After line 78)

```python
# Load calibrated regime mix from env or calibration JSON
regime_mix_env = os.environ.get("HB_REGIME_MIX")
if regime_mix_env:
    # Parse from env: "mean_revert:0.49,trend_up:0.36,jumpy:0.14"
    self.regime_mix = {}
    for pair in regime_mix_env.split(","):
        regime, weight = pair.split(":")
        self.regime_mix[regime.strip()] = float(weight)
else:
    # Default mix
    self.regime_mix = {"mean_revert": 0.4, "jumpy": 0.3, "trend_up": 0.3}

self.logger.info(f"🔁 Using regime mix: {self.regime_mix}")
```

### 3. Add Trend-Up Preemption Rule (In learn_and_propose, after line 340)

```python
# ✅ TREND_UP PREEMPTION: Prevent "hold too long then widen burst"
if (current_regime in ["trend_up", "trend_down"] and 
    prev_oor_pct >= (oor_critical - PREEMPT_MARGIN) and
    prev_fees_usd < FEE_GATE and
    prev_action != "widen" and
    prev_alpha > LOSS_BREAKER):
    
    self.logger.info(f"⚡ Trend preemption: OOR={prev_oor_pct:.1f}% approaching critical {oor_critical:.1f}%")
    action = "widen"
    rule_fired = "trend_up_preempt_widen"
    
    # Jump to competitive width
    target_width_pts = max(
        current_width if current_width else 0,
        prev_width_pts * 1.5 if prev_width_pts else 0,
        REGIME_MIN_WIDTH.get(current_regime, DEFAULT_MIN_WIDTH),
        1600 if current_regime in ["trend_up", "trend_down"] else 1400
    )
```

### 4. Update Decision Basis (Add to decision_basis dict)

```python
decision_basis = {
    # ... existing fields ...
    "preempt_margin": PREEMPT_MARGIN,
    "preempt_triggered": rule_fired == "trend_up_preempt_widen",
    "fee_gate_mult": FEE_GATE / GAS_USD if GAS_USD > 0 else 0,
    "exec_mode": EXEC_MODE,
}
```

## Campaign Commands

### FEE_GATE Sweep (3 campaigns, identical seed, calibrated regime mix)

```bash
# Campaign 1: FEE_GATE = $4.00 (baseline best)
export HB_SEED=42
export HB_REGIME_MIX="mean_revert:0.49,trend_up:0.36,jumpy:0.14"
export EXEC_MODE="mock"
export GAS_USD=2.0
export FEE_GATE_MULT=2.0
export EPISODE_COUNT=100
./run_aggressive_campaign.sh 2>&1 | tee campaign_gate_4.0.log

# Campaign 2: FEE_GATE = $6.00 (intermediate)
export FEE_GATE_MULT=3.0
./run_aggressive_campaign.sh 2>&1 | tee campaign_gate_6.0.log

# Campaign 3: FEE_GATE = $8.40 (Dune calibrated)
export FEE_GATE_MULT=4.2
./run_aggressive_campaign.sh 2>&1 | tee campaign_gate_8.4.log
```

### Analysis Commands

```bash
# Get run IDs
RUN_1=$(grep "RUN_ID:" campaign_gate_4.0.log | tail -1 | awk '{print $3}')
RUN_2=$(grep "RUN_ID:" campaign_gate_6.0.log | tail -1 | awk '{print $3}')
RUN_3=$(grep "RUN_ID:" campaign_gate_8.4.log | tail -1 | awk '{print $3}')

# Analyze all three
python3 tools/analyze_absolute_returns.py --run-id $RUN_1 > analysis_gate_4.0.txt
python3 tools/analyze_absolute_returns.py --run-id $RUN_2 > analysis_gate_6.0.txt
python3 tools/analyze_absolute_returns.py --run-id $RUN_3 > analysis_gate_8.4.txt

# Compare
python3 tools/compare_fee_gates.py $RUN_1 $RUN_2 $RUN_3
```

## Comparison Checklist

Compare these metrics across 3 campaigns:

1. **Net PnL** (total and mean) - higher is better
2. **Widen count overall** - target ~10-15
3. **Trend_up widen rate** - target ≤15-20% (vs 31% baseline)
4. **Gas total** - should stay <$50
5. **Hold rate** - should stay >75%
6. **Rule performance:**
   - `trend_up_preempt_widen` mean net PnL
   - `cooldown_after_widen` frequency
7. **Regime distribution** - should match 0.49/0.36/0.14

## Acceptance Criteria

✅ Calibrated regime mix applied (distribution ~49/36/14)
✅ Trend_up widen rate drops from 31% to ≤20%
✅ Net PnL improves toward -$101 baseline
✅ Gas stays controlled (<$50)
✅ New preemption rule appears in decision_basis
