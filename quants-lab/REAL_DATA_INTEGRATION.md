# Real Data Integration - Complete Implementation Guide

## ✅ Implementation Complete

The `RealDataCLMMEnvironment` is now fully integrated with **3 critical guardrails** and **feature flag control**.

---

## Feature Flags

### Primary Control
```bash
export USE_REAL_DATA="true"   # Enable real historical data from Dune
export USE_REAL_DATA="false"  # Use synthetic mock data (default)
```

### Fail-Fast Mode
```bash
export REAL_DATA_REQUIRED="true"   # Crash if Dune cache missing (no silent fallback)
export REAL_DATA_REQUIRED="false"  # Fallback to mock if real data unavailable (default)
```

### Environment Selection Logic
```
if USE_REAL_DATA=true:
    → RealDataCLMMEnvironment (historical Dune data)
    if REAL_DATA_REQUIRED=true and no data:
        → CRASH with error message
else:
    if EXEC_MODE=mock:
        → MockCLMMEnvironment (synthetic data)
    elif EXEC_MODE=real:
        → RealCLMMEnvironment (Gateway)
```

---

## Critical Guardrails

### Guardrail A: Cache Schema Validation
**Purpose**: Prevent silent failures from missing/corrupt cache data

**Implementation**: [`lib/real_data_clmm_env.py:118-128`](file:///home/a/.gemini/antigravity/scratch/quants-lab/lib/real_data_clmm_env.py#L118-L128)

```python
# Ensure required fields are present in tick data
required_fields = ['tick', 'timestamp']
for i, snapshot in enumerate(tick_data):
    missing = [f for f in required_fields if f not in snapshot or snapshot[f] is None]
    if missing:
        raise ValueError(
            f"Cache schema validation failed: snapshot {i} missing fields {missing}"
        )
```

**What it prevents**:
- Corrupt cache files
- Missing columns from Dune query changes
- Silent degradation to partial data

---

### Guardrail B: Stable Units Contract
**Purpose**: Prevent double-multiplication bug regression

**Implementation**: [`lib/real_data_clmm_env.py:173-180`](file:///home/a/.gemini/antigravity/scratch/quants-lab/lib/real_data_clmm_env.py#L173-L180)

```python
# Ensure we pass raw order_size to baselines (not USD proxy)
if order_size > 50:  # Sanity check: raw order_size should be small (e.g., 0.1 ETH)
    raise ValueError(
        f"GUARDRAIL B VIOLATION: order_size={order_size} appears to be USD proxy"
    )
```

**What it prevents**:
- Passing USD proxy instead of raw order_size
- Baseline simulations with inflated position sizes
- Regression of the $400k position bug

---

### Guardrail C: Enhanced Historical Window Metadata
**Purpose**: Make every regression instantly debuggable

**Implementation**: [`lib/real_data_clmm_env.py:199-216`](file:///home/a/.gemini/antigravity/scratch/quants-lab/lib/real_data_clmm_env.py#L199-L216)

```python
historical_window = {
    "start_ts": start_ts,
    "end_ts": end_ts,
    "start_datetime": "2025-12-07T08:04:45",
    "end_datetime": "2025-12-07T14:04:45",
    "source": "dune_cache",
    "dataset_version": "v1",
    "tick_snapshots": 7,
    "total_volume_usd": 15000000.0,
    "avg_volume_per_snapshot": 2142857.14,
    "tick_range": {
        "min": 79948,
        "max": 80184,
        "start": 80184,
        "end": 80007
    }
}
```

**Stored in**: `result.json → position_after.historical_window`

**What it enables**:
- Instant identification of which historical window was used
- Debugging PnL discrepancies by checking tick range
- Tracking cache version for schema migrations

---

## Determinism Guarantees

### Window Selection
- **Deterministic**: Same `episode_id` → same historical window
- **Method**: MD5 hash of `episode_id` → window index
- **Distribution**: Uniform across last 90 days

### Fairness
- ✅ Agent and baselines run on **exact same tick path**
- ✅ Agent and baselines use **exact same volume data**
- ✅ No lookahead: episode *t* uses only data from window *t*

### Regime Labeling
- **Real data mode**: `regime_name = "real_data"` (not synthetic)
- **Future enhancement**: Derive regime from realized vol/jumps **after** loading window
- **Current**: No forced regime mix in real data runs

---

## End-to-End Verification Sequence

### 1. Single Episode Smoke Test
```bash
export USE_REAL_DATA="true"
export REAL_DATA_REQUIRED="true"
export EPISODE_COUNT="1"
export RUN_ID="test_real_data_smoke"

python3 phase5_learning_agent.py --episode-id test_real_001
python3 scripts/run_episode.py --episode-id test_real_001
```

**Verify**:
- [ ] `result.json` contains `historical_window` metadata
- [ ] Fees calculated from real volume fields
- [ ] All baselines populated
- [ ] **Determinism**: Rerun same episode_id → identical results

### 2. 10 Episode Mini-Run
```bash
export USE_REAL_DATA="true"
export EPISODE_COUNT="10"
export RUN_ID="test_real_data_mini"

bash run_aggressive_campaign.sh
```

**Verify**:
- [ ] Action mix (hold/rebalance) works correctly
- [ ] Gas logic consistent
- [ ] Analyzer runs unchanged
- [ ] No crashes or silent fallbacks

### 3. 100 Episode Campaign
```bash
export USE_REAL_DATA="true"
export EPISODE_COUNT="100"
export RUN_ID="real_data_campaign_001"

bash run_aggressive_campaign.sh
```

**Compare**:
- [ ] Net PnL distributions (real vs mock)
- [ ] Baseline ordering sanity
- [ ] Regime labels distribution (derived)
- [ ] Training convergence

---

## Configuration Reference

### Required Environment Variables
```bash
# Dune API
export DUNE_API_KEY="your_api_key"
export DUNE_HISTORICAL_TICKS_QUERY_ID="6354552"
export DUNE_LP_PERFORMANCE_QUERY_ID="6354561"

# Real Data Control
export USE_REAL_DATA="true"
export REAL_DATA_REQUIRED="true"  # Optional: fail-fast mode

# Cache
export HISTORICAL_DATA_CACHE_DIR="scratch/data/historical_cache"
export HISTORICAL_LOOKBACK_DAYS="90"  # Default: 90 days

# Episode Config (same as mock)
export HB_EPISODE_HORIZON_S="21600"  # 6 hours
export HB_STEP_SECONDS="60"
export HB_REBALANCE_COOLDOWN_S="1800"
```

### Optional Overrides
```bash
# Position sizing (same as mock)
export MAX_POSITION_SHARE="0.0005"
export LIQUIDITY_PROXY_MULT="50.0"
export ORDER_SIZE_USD_MULT="2000.0"
export CONC_MULT_CAP="2.0"
```

---

## Troubleshooting

### Error: "No historical tick data found"
**Cause**: Dune cache empty or query failed

**Fix**:
1. Check `DUNE_API_KEY` is set
2. Verify query IDs: `DUNE_HISTORICAL_TICKS_QUERY_ID`, `DUNE_LP_PERFORMANCE_QUERY_ID`
3. Test queries manually in Dune UI
4. Check cache: `ls -lh scratch/data/historical_cache/`

### Error: "GUARDRAIL B VIOLATION: order_size=200 appears to be USD proxy"
**Cause**: Proposal passing USD value instead of raw ETH amount

**Fix**:
1. Check `proposal.order_size` in `proposal.json`
2. Should be small value like `0.1` (ETH), not `200` (USD)
3. Verify agent is not pre-multiplying by `ORDER_SIZE_USD_MULT`

### Error: "Cache schema validation failed: missing fields ['tick']"
**Cause**: Dune query not updated or corrupt cache

**Fix**:
1. Update Dune query with corrected SQL
2. Clear cache: `rm -rf scratch/data/historical_cache/*.json`
3. Re-fetch data

---

## Files Modified

### Core Implementation
- [`lib/real_data_clmm_env.py`](file:///home/a/.gemini/antigravity/scratch/quants-lab/lib/real_data_clmm_env.py) - New environment class
- [`lib/clmm_env.py`](file:///home/a/.gemini/antigravity/scratch/quants-lab/lib/clmm_env.py#L1104-L1157) - Updated `create_environment()` factory
- [`lib/historical_data_cache.py`](file:///home/a/.gemini/antigravity/scratch/quants-lab/lib/historical_data_cache.py) - Cache layer

### Dune Queries
- [`dune_queries/04_historical_ticks_FIXED.sql`](file:///home/a/.gemini/antigravity/scratch/quants-lab/dune_queries/04_historical_ticks_FIXED.sql) - Query ID 6354552
- [`dune_queries/05_lp_performance.sql`](file:///home/a/.gemini/antigravity/scratch/quants-lab/dune_queries/05_lp_performance.sql) - Query ID 6354561

### Environment Config
- `.env.dune` - Dune API credentials and query IDs

---

## Next Steps

1. **Run smoke test** (1 episode) to verify integration
2. **Test determinism** by running same episode_id twice
3. **Run 10-episode mini-campaign** to validate end-to-end
4. **Compare mock vs real** training outcomes (100 episodes each)
5. **Implement regime derivation** from realized vol/jumps (future enhancement)

---

## Success Criteria

✅ **Integration Complete** when:
- [ ] Single episode runs without errors
- [ ] `result.json` contains complete `historical_window` metadata
- [ ] Determinism verified (same episode_id → identical results)
- [ ] All 3 guardrails tested and working
- [ ] 10-episode campaign completes successfully
- [ ] Analyzer processes real data results correctly
