# Dune Query Setup Guide

## Step 1: Create Queries in Dune UI

### Query 1: Historical Ticks

1. Go to https://dune.com/queries
2. Click "New Query"
3. Copy SQL from [`04_historical_ticks.sql`](file:///home/a/.gemini/antigravity/scratch/quants-lab/dune_queries/04_historical_ticks.sql)
4. Paste into Dune query editor
5. Add parameters:
   - `start_timestamp` (number)
   - `end_timestamp` (number)
   - `granularity` (text, default: "hour")
6. Click "Save" and note the **Query ID** from the URL (e.g., `https://dune.com/queries/12345` → ID is `12345`)

### Query 2: LP Performance

1. Click "New Query" again
2. Copy SQL from [`05_lp_performance.sql`](file:///home/a/.gemini/antigravity/scratch/quants-lab/dune_queries/05_lp_performance.sql)
3. Paste into Dune query editor
4. Add parameters:
   - `start_timestamp` (number)
   - `end_timestamp` (number)
   - `min_width_ticks` (number)
   - `max_width_ticks` (number)
5. Click "Save" and note the **Query ID**

## Step 2: Update Environment Variables

Edit `.env.dune` and add your Query IDs:

```bash
export DUNE_HISTORICAL_TICKS_QUERY_ID="12345"  # Replace with your Query ID
export DUNE_LP_PERFORMANCE_QUERY_ID="67890"    # Replace with your Query ID
export USE_REAL_DATA="true"                     # Enable real data mode
```

## Step 3: Test the Queries

```bash
source .env.dune
python3 - <<'PY'
from lib.dune_client import DuneClient
from lib.historical_data_cache import HistoricalDataCache
from pathlib import Path
import time

# Initialize
client = DuneClient()
cache = HistoricalDataCache(Path("scratch/data/historical_cache"), client)

# Test: Fetch 6 hours of data from 7 days ago
end_ts = int(time.time()) - (7 * 86400)  # 7 days ago
start_ts = end_ts - 21600  # 6 hours before that

print(f"Fetching tick data from {start_ts} to {end_ts}...")
ticks = cache.get_tick_window(
    pool_address="0x88e6A0c2dDD26FEEb64F039a2c41296FcB3f5640",
    start_ts=start_ts,
    duration_seconds=21600
)

print(f"✅ Got {len(ticks)} tick snapshots")
if ticks:
    print(f"First tick: {ticks[0]}")
    print(f"Last tick: {ticks[-1]}")
PY
```

## Step 4: Run Training with Real Data

Once queries are working:

```bash
export USE_REAL_DATA="true"
export EXEC_MODE="real_data"

# Run single episode test
python3 phase5_learning_agent.py --episode-id test_real_data_0

# Run full campaign
bash run_aggressive_campaign.sh
```

## Troubleshooting

### "Query ID not set"
- Make sure you've set `DUNE_HISTORICAL_TICKS_QUERY_ID` and `DUNE_LP_PERFORMANCE_QUERY_ID`
- Run `source .env.dune` before testing

### "Query failed" or "400 Bad Request"
- Check that parameter names in Dune UI match the SQL (case-sensitive)
- Verify parameter types (number vs text)

### "No results returned"
- Try a more recent time window (last 7-30 days)
- Check that WETH-USDC pool address is correct: `0x88e6A0c2dDD26FEEb64F039a2c41296FcB3f5640`

### "Rate limit exceeded"
- Dune has API rate limits
- Use cache to avoid repeated calls
- Consider upgrading Dune plan for higher limits

## Next Steps

After queries are working:
1. Implement `RealDataCLMMEnvironment` (Phase 3)
2. Run validation tests (Phase 4)
3. Compare mock vs real data training (Phase 5)
