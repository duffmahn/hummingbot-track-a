# Dune Calibration Queries for CLMM Strategy

## Overview
These queries provide data-driven calibration for the EV-gated hold policy by analyzing real mainnet conditions for the WETH-USDC 0.05% pool over the last 90 days.

## Queries

### 1. Pool Hourly Fees (`01_pool_hourly_fees.sql`)
**Purpose:** Determine if fee budget justifies gas interventions

**Key Outputs:**
- `fees_median_usd`: Median hourly fees available
- `fees_p90_usd`: 90th percentile hourly fees
- `volume_median_usd`: Median hourly volume

**Use:** Calculate `fees_to_gas_ratio = fees_median / gas_median`
- If ratio < 1: Prioritize gas minimization (hold-by-default)
- If ratio > 3: Can afford more active management

### 2. Gas Cost Distribution (`02_gas_cost_distribution.sql`)
**Purpose:** Calibrate FEE_GATE threshold

**Key Outputs:**
- `gas_median_usd`: Median gas cost for LP operations
- `gas_p75_usd`: 75th percentile gas cost
- `gas_p90_usd`: 90th percentile gas cost

**Use:** Set `FEE_GATE = k * gas_p75` where k ≈ 2-3
- Current: `FEE_GATE = 2.0 * $2.00 = $4.00`
- Calibrated: `FEE_GATE = 2.5 * gas_p75_usd`

### 3. Realized Vol & Jumps (`03_realized_vol_jumps.sql`)
**Purpose:** Validate regime mix and OOR thresholds

**Key Outputs:**
- `vol_median`, `vol_p90`: Volatility distribution
- `jump_rate`: Frequency of large price moves
- `trend_rate`, `mean_revert_rate`: Regime frequencies

**Use:** 
- High jump_rate → Increase width floors, raise OOR_CRITICAL
- High mean_revert_rate → Can use narrower bands in those windows
- Validate `HB_REGIME_MIX` matches reality

## Calibration Workflow

1. **Run all 3 queries on Dune**
2. **Extract key metrics** into calibration table
3. **Update strategy constants:**
   ```python
   GAS_USD = gas_p75_usd
   FEE_GATE = 2.5 * GAS_USD
   
   # If fees_to_gas_ratio < 1:
   OOR_CRITICAL_DEFAULT = 95.0  # Very conservative
   
   # If jump_rate > 0.1:
   REGIME_MIN_WIDTH["jumpy"] = 1400
   ```

4. **Run 100-episode campaign** with calibrated values
5. **Compare net PnL** vs current settings

## Expected Results

Based on current EV-gated campaign (-$1.01/ep):
- If `fees_to_gas_ratio > 2`: Expect improvement (can be more active)
- If `fees_to_gas_ratio < 1`: Current strategy is optimal (gas dominates)
- If `jump_rate > 0.15`: Validate width floors are sufficient

## Pool Details
- **Address:** 0x88e6A0c2dDD26FEEb64F039a2c41296FcB3f5640
- **Pair:** WETH-USDC
- **Fee Tier:** 0.05% (500 bps)
- **Chain:** Ethereum Mainnet
- **Time Window:** Last 90 days

## Next Steps
1. Execute queries on Dune Analytics
2. Create calibration report with results
3. Update strategy constants based on data
4. Re-run campaign to validate improvements
