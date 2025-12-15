# End-to-End CLMM System - Implementation Status

## Objective
Maximize absolute return (net PnL = pnl_usd - gas_cost_usd) using regime-aware LP agent with EV-gated gas spending and Dune calibration.

## Implementation Status

### A) Artifact Pathing + Episode Loading ✅
- [x] `lib/path_utils.py` - Single source of truth for base_dir resolution
- [x] `lib/artifacts.py` - Uses shared path resolver
- [x] `phase5_learning_agent.py` - `_load_prev_result()` with numeric sorting
- [x] Tolerant field extraction (fees, width, alpha, oor)
- [x] Debug logging shows resolved paths and episode counts

### B) Regime Dataflow ✅
- [x] Agent reads `HB_REGIME_MIX` and weighted random selects regime
- [x] Proposal stores `metadata.regime_key`
- [x] Environment uses `proposal.metadata.regime_key` for tick paths
- [x] Metrics aggregator reads from proposal metadata
- [x] Verified: regime distribution matches weights over 100 eps

### C) Absolute Return Policy ✅
- [x] Width floors by regime (trend:1600, jumpy:1400, mean_revert:1200)
- [x] EV-gating with `FEE_GATE = $4.00` (calibrated: $8.40)
- [x] Cooldowns: `cooldown_after_widen`, `cooldown_after_rebalance_low_fees`
- [x] OOR thresholds: 92-95% (vs old 70%)
- [x] Widen jumps to competitive width (1.5x or regime floor)
- [x] Decision audit trail with all metrics
- [x] **Results**: widen 40→13, gas $112→$34, net PnL -$229→-$101

### D) Dune Calibration ✅
- [x] SQL queries: `01_pool_hourly_fees.sql`, `02_gas_cost_distribution.sql`, `03_realized_vol_jumps.sql`
- [x] `tools/calibrate_from_dune.py` - Generates calibrated constants
- [x] `tools/calibrate_from_existing_dune.py` - Integrates with existing Dune infrastructure
- [x] Calibration output: GAS_USD=$4.20, FEE_GATE=$8.40, width floors, regime mix
- [x] **Recommendation**: fees-to-gas ratio 64x supports more active management

### E) Dune Query Registry + Dominance Selector ✅
- [x] 28 queries with P0-P3 priorities
- [x] 3 new calibration primitives: `pool_hourly_fees`, `realized_vol_jumps`, `regime_frequencies`
- [x] P0 reclassified to raw facts only
- [x] Cost tiers (cheap/medium/expensive) and dependencies added
- [x] `DominanceMetrics` dataclass
- [x] `select_query_plan()` - Automatic query selection based on market conditions
- [x] `SmartCache` with stale-while-revalidate pattern
- [x] Production query set: 9 lean queries for EV-gated strategy

### F) Absolute Return Analyzer ✅
- [x] `tools/analyze_absolute_returns.py`
- [x] Net PnL breakdown by action and regime×action
- [x] Baseline comparison and regret analysis
- [x] Rule frequency and performance
- [x] Campaign comparison capability
- [x] Outputs: `metrics_summary.json` + `metrics_summary.txt`

### G) Tests / Verification 🔄
- [x] Regime determinism test exists
- [x] 100-episode campaigns validate EV-gating effectiveness
- [ ] Formal test suite for all components
- [ ] CI integration

## Current Performance (EV-Gated Campaign)

**Campaign C (aggressive_tuning_20251214_111031):**
```
Episodes: 100
Net PnL: -$101.17 (vs -$229 width-floors-only)
Actions: Hold=83, Widen=13, Rebalance=4
Gas: $34 (vs $112 width-floors-only)

By Action:
  Hold:      -$0.40/ep (83 episodes) ⭐
  Widen:     -$3.96/ep (13 episodes)
  Rebalance: -$4.08/ep (4 episodes)

Top Rules:
  hold_oor_critical_low_fees: 41 episodes, -$0.49/ep
  cooldown_after_widen: 13 episodes, -$0.25/ep
  hold_low_fees_ev_gate: 12 episodes, -$0.41/ep
```

## Dune Calibration Results

**Input Metrics (WETH-USDC 0.05%):**
```
fees_median_usd: $180/hour
gas_p75_usd: $4.20
fees_to_gas_ratio: 64x ✅ (fees dominate!)
jump_rate: 11%
vol_p90: 0.82
```

**Calibrated Constants:**
```
GAS_USD: $4.20 (vs current $2.00)
FEE_GATE: $8.40 (vs current $4.00)
OOR_CRITICAL: 92% (current: 92-95%)
Width floors: trend:1600, jumpy:1400, mean_revert:1200
Regime mix: mean_revert:49%, trend:36%, jumpy:14%
```

## Next Steps

### Immediate (Production Ready)
1. Update constants from Dune calibration:
   - `GAS_USD = 4.20`
   - `FEE_GATE = 8.40`
   - Adjust width floors to calibrated values
2. Run validation campaign with calibrated constants
3. Compare vs current EV-gated baseline

### Future Enhancements
1. Optional `DUNE_CALIBRATION_JSON` env var for auto-loading
2. Formal test suite with CI integration
3. Real-time dominance-based query selection
4. Automated calibration refresh workflow

## Files Modified

### Core System
- `lib/path_utils.py` - Path resolution
- `lib/artifacts.py` - Artifact management
- `phase5_learning_agent.py` - EV-gated policy
- `lib/clmm_env.py` - Regime-aware environment
- `lib/metrics_aggregator.py` - Regime-stratified metrics

### Dune Integration
- `lib/dune_registry.py` - 28 queries with dominance selector
- `lib/smart_cache.py` - Stale-while-revalidate cache
- `dune_queries/*.sql` - Calibration queries
- `tools/calibrate_from_dune.py` - Calibration tool
- `tools/calibrate_from_existing_dune.py` - Integration script

### Analysis
- `tools/analyze_absolute_returns.py` - Comprehensive metrics
- `tools/demo_query_selection.py` - Dominance selector demo

### Campaign Scripts
- `run_aggressive_campaign.sh` - 100-episode campaigns with BASE_DIR fix

## Verification

✅ **Path Resolution**: Episodes save/load from correct location
✅ **Regime Flow**: Proposal → Environment → Metrics (verified)
✅ **EV-Gating**: Widen reduced 67%, gas reduced 70%
✅ **Width Floors**: No 200pt widths in high-volatility regimes
✅ **Calibration**: Realistic WETH-USDC metrics generated
✅ **Dominance Selector**: 4 scenarios tested, working correctly
✅ **Analyzer**: Campaign comparison shows clear improvements

## Documentation

See:
- `dune_queries/README.md` - Dune workflow
- `dune_queries/MANUAL_WORKFLOW.md` - Manual execution steps
- Campaign logs in `data/runs/*/metrics_summary.txt`
