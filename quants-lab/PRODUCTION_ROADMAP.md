# Production Roadmap - Next Steps

## 1. Apply Dune Calibration ✅

**Status:** Calibration data ready
- Input: `dune_queries/calibration_report.json`
- Calibrated constants available

**Action:** Update agent constants from calibration

## 2. Three-Way Campaign Comparison

Run with identical seeds:

### Campaign A: Width Floors Only (Baseline)
```bash
export HB_SEED=42
export HB_REGIME_MIX="mean_revert:0.4,jumpy:0.3,trend_up:0.3"
# Disable EV-gating in code
./run_aggressive_campaign.sh
```

### Campaign B: EV-Gated (Current)
```bash
export HB_SEED=42
export HB_REGIME_MIX="mean_revert:0.4,jumpy:0.3,trend_up:0.3"
# Current constants: GAS=$2, FEE_GATE=$4
./run_aggressive_campaign.sh
```

### Campaign C: EV-Gated + Dune Calibration
```bash
export HB_SEED=42
export HB_REGIME_MIX="mean_revert:0.49,trend_up:0.36,jumpy:0.14"
export DUNE_CALIBRATION_JSON=/path/to/calibration.json
# Calibrated: GAS=$4.20, FEE_GATE=$8.40
./run_aggressive_campaign.sh
```

**Success Criteria:**
- Net PnL improvement persists
- Widen stays ~10-20%
- Gas remains controlled
- No new bad rules dominating

## 3. Dominance-Based Query Planner

**Configuration:**
```python
# Normal operation
max_priority = "P1"
max_expensive = 1

# High churn / high gas
max_expensive = 0

# Schedule expensive queries
liquidity_depth: TTL=21600s (6hr), not per episode
```

**Budget Enforcement:**
- P0 always: gas_regime, pool_hourly_fees, realized_vol_jumps
- P1 daily: dynamic_fee_analysis, regime_frequencies
- P2 only if risk signals high

## 4. Long-Run Validation (500-1000 episodes)

After calibration passes 3-way comparison:
```bash
export EPISODE_COUNT=500
./run_aggressive_campaign.sh
```

**Purpose:** Tighten confidence intervals on absolute return

## 5. Controlled Narrowing Experiment (mean_revert only)

**Hypothesis:** mean_revert (49% of episodes) might benefit from narrower bands

**Test Matrix:**
```
mean_revert floor: 1200 (current) vs 1000 vs 800
trend/jumpy floors: unchanged (1600/1400)
```

**Success Criteria:**
- Net PnL in mean_revert improves
- Widen/gas don't spike
- Overall net PnL improves

## Go-Live Checklist

### Pre-Production
- [ ] Paper trading / shadow mode first
- [ ] Hard cap: max gas actions per N episodes
- [ ] MEV/toxicity queries only if they change decisions
- [ ] Calibration hash in artifacts for auditability

### Monitoring
- [ ] Real-time net PnL tracking
- [ ] Gas spend alerts
- [ ] Widen frequency monitoring
- [ ] Rule performance dashboard

### Safety Rails
- [ ] Emergency stop on excessive gas
- [ ] Position size limits
- [ ] Drawdown limits
- [ ] Manual override capability

## Implementation Priority

1. **Immediate:** Apply Dune calibration to agent constants
2. **Today:** Run 3-way campaign comparison
3. **This week:** Long-run validation (500 eps)
4. **Next week:** Narrowing experiment
5. **Future:** Production deployment with monitoring
