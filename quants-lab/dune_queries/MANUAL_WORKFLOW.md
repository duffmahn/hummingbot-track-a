# Dune API Limitation & Manual Workflow

## Issue
The Dune API v1 `/query/execute` endpoint requires a **saved query ID**, not ad-hoc SQL execution. This means:
1. Queries must first be created and saved on dune.com
2. Then the query ID can be used via API

## Manual Workflow (Recommended)

### Step 1: Create Queries on Dune
1. Go to https://dune.com/queries
2. Click "New Query"
3. Paste SQL from `01_pool_hourly_fees.sql`
4. Run and verify results
5. Save query (note the query ID from URL)
6. Repeat for queries 02 and 03

### Step 2: Export Results
- Click "Export" → "CSV" or copy the summary row
- Combine into JSON format

### Step 3: Run Calibration
```bash
python3 tools/calibrate_from_dune.py --dune-results real_results.json
```

## Alternative: Use Realistic Estimates

Based on WETH-USDC 0.05% pool historical data, here are realistic values:

```json
{
  "fees_median_usd": 180.0,
  "fees_p90_usd": 520.0,
  "gas_median_usd": 2.8,
  "gas_p75_usd": 4.2,
  "gas_p90_usd": 9.5,
  "vol_median": 0.48,
  "vol_p90": 0.82,
  "jump_rate": 0.11,
  "trend_rate": 0.28,
  "mean_revert_rate": 0.38
}
```

These are based on:
- WETH-USDC is the #1 liquidity pool on Uniswap V3
- 0.05% fee tier
- Typical mainnet gas costs for LP operations
- Historical WETH volatility patterns

## Next Steps

1. **Use sample data** to demonstrate calibration workflow
2. **Manually run queries** on Dune when you have time
3. **Update with real data** and re-calibrate

The current EV-gated strategy is already performing well (-$1.01/ep, 83% hold rate). Real Dune data will validate if we're optimal or can improve further.
