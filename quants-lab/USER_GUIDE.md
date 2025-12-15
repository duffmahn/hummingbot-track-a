# End-to-End CLMM System - User Guide

## Quick Start

### 1. Run a Campaign

```bash
cd /home/a/.gemini/antigravity/scratch/quants-lab

# Set environment
export BASE_DIR="/home/a/.gemini/antigravity/scratch/data"
export HB_REGIME_MIX="mean_revert:0.49,trend_up:0.36,jumpy:0.14"
export EXEC_MODE="mock"

# Run campaign
./run_aggressive_campaign.sh
```

### 2. Analyze Results

```bash
# Get run ID from campaign output or:
RUN_ID=$(ls -t data/runs/ | head -1)

# Run analyzer
python3 tools/analyze_absolute_returns.py --run-id $RUN_ID

# View results
cat data/runs/$RUN_ID/metrics_summary.txt
```

### 3. Calibrate from Dune (Optional)

```bash
# Option A: Use existing Dune infrastructure
python3 tools/calibrate_from_existing_dune.py

# Option B: Manual Dune queries (see dune_queries/MANUAL_WORKFLOW.md)
# 1. Run queries on dune.com
# 2. Export to JSON
# 3. Run calibration
python3 tools/calibrate_from_dune.py --dune-results results.json

# View calibration
cat dune_queries/calibration_report.json
```

## System Architecture

### Data Flow

```
1. Agent reads HB_REGIME_MIX
   ↓
2. Selects regime (weighted random)
   ↓
3. Loads previous episode result
   ↓
4. Applies EV-gating + cooldowns
   ↓
5. Enforces width floors
   ↓
6. Generates proposal with decision_basis
   ↓
7. Environment uses proposal.metadata.regime_key
   ↓
8. Executes episode
   ↓
9. Metrics aggregator reads regime from proposal
   ↓
10. Analyzer computes absolute return metrics
```

### Key Components

**Agent (`phase5_learning_agent.py`):**
- Loads previous episodes with numeric sorting
- EV-gating: Only spend gas if fees justify it
- Cooldowns: Hold after widen/rebalance
- Width floors: Regime-based minimums
- Decision audit trail

**Environment (`lib/clmm_env.py`):**
- Uses proposal regime for tick paths
- Deterministic with seed
- Regime-aware baselines

**Metrics (`lib/metrics_aggregator.py`):**
- Regime-stratified breakdowns
- Episodes/alpha/winners by regime

**Analyzer (`tools/analyze_absolute_returns.py`):**
- Net PnL = pnl_usd - gas_cost_usd
- Action and regime×action breakdowns
- Baseline comparison and regret
- Rule performance analysis

## Configuration

### Environment Variables

```bash
# Required
BASE_DIR="/path/to/data"           # Artifact storage
RUN_ID="campaign_name_timestamp"   # Auto-generated or custom
EXEC_MODE="mock"                    # or "paper" or "live"

# Regime Configuration
HB_REGIME_MIX="mean_revert:0.4,jumpy:0.3,trend_up:0.3"
HB_SEED="42"                        # For determinism

# Optional
DUNE_CALIBRATION_JSON="/path/to/calibration.json"  # Auto-load calibration
EPISODE_COUNT="100"                 # Default in campaign script
```

### Agent Constants (in code)

```python
# Current (hand-tuned)
GAS_USD = 2.0
FEE_GATE = 4.0  # 2 * GAS_USD
LOSS_BREAKER = -1000.0

OOR_CRITICAL_BY_REGIME = {
    "trend_up": 95.0,
    "jumpy": 92.0,
    "mean_revert": 95.0,
    # ...
}

REGIME_MIN_WIDTH = {
    "trend_up": 1400,
    "jumpy": 1200,
    "mean_revert": 1000,
    # ...
}

# Calibrated (from Dune)
GAS_USD = 4.20
FEE_GATE = 8.40
# Width floors: trend:1600, jumpy:1400, mean_revert:1200
```

## Performance Benchmarks

### Campaign Evolution

**A. Width Floors Only:**
- Net PnL: -$229
- Widen: 40 episodes
- Gas: $112
- Hold: 44 episodes (44%)

**B. EV-Gated + Cooldowns:**
- Net PnL: -$101 ✅ **56% better**
- Widen: 13 episodes ✅ **67% reduction**
- Gas: $34 ✅ **70% reduction**
- Hold: 83 episodes (83%) ✅ **Dominant**

### Rule Performance (Campaign B)

```
Best Rules (by mean net PnL):
1. cooldown_after_rebalance_low_fees: -$0.25 (4 eps)
2. cooldown_after_widen: -$0.25 (13 eps)
3. trend_up_winning_in_range_ev_gated: -$0.25 (7 eps)
4. hold_low_fees_ev_gate: -$0.41 (12 eps)
5. hold_oor_critical_low_fees: -$0.49 (41 eps)

Worst Rules:
1. first_episode: -$4.37 (1 ep)
2. widen_oor_critical_ev_ok: -$4.06 (6 eps)
3. loss_breaker_rebalance: -$3.98 (3 eps)
4. loss_breaker_widen: -$3.88 (7 eps)
```

## Dune Calibration

### Metrics (WETH-USDC 0.05%)

```
Pool Fees:
  Median: $180/hour
  P90: $520/hour

Gas Costs:
  Median: $2.80
  P75: $4.20
  P90: $9.50

Volatility:
  Median: 0.48
  P90: 0.82
  Jump rate: 11%

Dominance:
  Fees-to-gas ratio: 64x ✅ (fees dominate!)
  Gas tail risk: 3.4x (P90/median)
```

### Recommendations

1. **Increase FEE_GATE** to $8.40 (from $4.00)
   - Matches real gas costs (P75)
   - Still allows activity in high-fee environment

2. **Widen width floors** to calibrated values
   - trend_up: 1600 pts (from 1400)
   - mean_revert: 1200 pts (from 1000)

3. **Adjust regime mix** to observed frequencies
   - mean_revert: 49% (from 40%)
   - trend_up: 36% (from 30%)
   - jumpy: 14% (from 30%)

4. **Consider more active management**
   - Fees-to-gas ratio of 64x supports it
   - Could lower OOR thresholds slightly (92% → 88-90%)
   - Test narrower bands in low-vol periods

## Troubleshooting

### Episodes not found
```bash
# Check BASE_DIR is set correctly
echo $BASE_DIR

# Verify run directory exists
ls -la $BASE_DIR/runs/

# Check episode paths
ls -la $BASE_DIR/runs/$RUN_ID/episodes/
```

### Analyzer fails
```bash
# Ensure run completed
grep "Campaign Complete" campaign_*.log

# Check result.json files exist
find $BASE_DIR/runs/$RUN_ID/episodes -name "result.json" | wc -l

# Run with debug
python3 tools/analyze_absolute_returns.py --run-id $RUN_ID 2>&1 | tee debug.log
```

### Dune calibration
```bash
# Check existing Dune infrastructure
python3 -c "from lib.dune_registry import QUERY_REGISTRY; print(len(QUERY_REGISTRY))"

# Test calibration with sample data
python3 tools/calibrate_from_dune.py --dune-results dune_queries/sample_results.json
```

## Files Reference

### Core
- `phase5_learning_agent.py` - Agent with EV-gating
- `lib/clmm_env.py` - Regime-aware environment
- `lib/artifacts.py` - Episode artifact management
- `lib/path_utils.py` - Path resolution
- `lib/metrics_aggregator.py` - Regime-stratified metrics

### Dune
- `lib/dune_registry.py` - 28 queries with dominance selector
- `lib/smart_cache.py` - Stale-while-revalidate cache
- `dune_queries/*.sql` - Calibration queries
- `tools/calibrate_from_dune.py` - Calibration tool

### Analysis
- `tools/analyze_absolute_returns.py` - Comprehensive metrics
- `tools/demo_query_selection.py` - Dominance selector demo

### Campaigns
- `run_aggressive_campaign.sh` - 100-episode campaigns

## Next Steps

1. **Apply Dune calibration** - Update constants and run validation
2. **Formal test suite** - Comprehensive unit/integration tests
3. **CI integration** - Automated testing on commits
4. **Real-time calibration** - Auto-refresh from Dune scheduler
5. **Production deployment** - Live trading with calibrated params
