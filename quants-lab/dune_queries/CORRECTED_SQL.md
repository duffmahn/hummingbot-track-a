# 🔧 CORRECTED SQL - Use These Versions!

## Issue Found
The queries had wrong table names for Dune v2 schema.

## ✅ Corrected Files

### Query 1: Historical Ticks
**File**: [`04_historical_ticks_v2.sql`](file:///home/a/.gemini/antigravity/scratch/quants-lab/dune_queries/04_historical_ticks_v2.sql)

**Key Changes**:
- ✅ Changed `uniswap_v3_ethereum.Pool_evt_Swap` → `uniswap_v3_ethereum.Swap`
- ✅ Fixed column references (`amount0`, `amount1` with proper CAST)
- ✅ Added NULL checks for price calculation

### Query 2: LP Performance  
**File**: [`05_lp_performance_v2.sql`](file:///home/a/.gemini/antigravity/scratch/quants-lab/dune_queries/05_lp_performance_v2.sql)

**Key Changes**:
- ✅ Changed `uniswap_v3_ethereum.Pool_evt_Mint` → `uniswap_v3_ethereum.Mint`
- ✅ Changed `uniswap_v3_ethereum.Pool_evt_Burn` → `uniswap_v3_ethereum.Burn`
- ✅ Changed `uniswap_v3_ethereum.Pool_evt_Collect` → `uniswap_v3_ethereum.Collect`
- ✅ Fixed all column references with proper CAST

## 📝 Update Instructions

### For Query 6354552 (Historical Ticks):
1. Go to https://dune.com/queries/6354552/edit
2. **Delete all existing SQL**
3. Copy **entire contents** of `04_historical_ticks_v2.sql`
4. Paste into Dune editor
5. Verify parameters exist:
   - `start_timestamp` (number)
   - `end_timestamp` (number)
6. Click "Save"

### For Query 6354561 (LP Performance):
1. Go to https://dune.com/queries/6354561/edit
2. **Delete all existing SQL**
3. Copy **entire contents** of `05_lp_performance_v2.sql`
4. Paste into Dune editor
5. Verify parameters exist:
   - `start_timestamp` (number)
   - `end_timestamp` (number)
   - `min_width_ticks` (number)
   - `max_width_ticks` (number)
6. Click "Save"

## ✅ After Updating

Let me know when both queries are updated, and I'll test them again!
