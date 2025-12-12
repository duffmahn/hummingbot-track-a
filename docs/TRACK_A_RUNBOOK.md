# Track A Operational Runbook

## What is Track A?

Track A is a production-ready CLMM (Concentrated Liquidity Market Maker) training pipeline for Uniswap V3. It implements a complete learning loop that:

1. **Proposes** pool configurations using a learning agent
2. **Captures intel snapshot** with quality metadata (fresh/stale/missing)
3. **Executes** in mock or real environments
4. **Writes immutable artifacts** (proposal, metadata, result, timings, logs)
5. **Optionally learns** from outcomes (with hygiene gates)

**Key Design Principle:** Episodes never block on external data sources. MarketIntelligence is cache-first, and a background scheduler refreshes the cache using stale-while-revalidate semantics.

## Repository Map

```
scratch/
├── start_training_campaign.sh          # Main campaign runner
├── data/
│   └── runs/                           # All run artifacts
│       └── <run_id>/
│           ├── campaign.log
│           └── episodes/
│               └── <episode_id>/
│                   ├── proposal.json
│                   ├── metadata.json
│                   ├── result.json (or failure.json)
│                   ├── timings.json
│                   └── logs.jsonl
├── quants-lab/
│   ├── phase5_learning_agent.py        # Learning agent (propose + learn)
│   ├── lib/
│   │   ├── market_intel.py             # Cache-first intelligence layer
│   │   ├── dune_cache.py               # Quality-aware cache wrapper
│   │   ├── dune_registry.py            # 25 Dune queries with priorities
│   │   ├── dune_scheduler.py           # Background cache refresh
│   │   ├── agent_harness.py            # Episode executor
│   │   ├── pool_validator.py           # Real-mode health gates
│   │   └── artifacts.py                # Immutable artifact writer
│   ├── schemas/
│   │   └── contracts.py                # Pydantic schemas
│   ├── scripts/
│   │   ├── run_dune_scheduler.py       # Scheduler daemon
│   │   └── run_episode.py              # Episode bridge
│   └── tests/
│       └── test_ci_integration.py      # CI artifact validation
└── .github/workflows/
    └── track-a-ci.yml                  # GitHub Actions CI
```

## Modes & Safety Model

### Environment Modes

| Variable | Values | Purpose |
|----------|--------|---------|
| `HB_ENV` | `mock` \| `real` | Top-level environment selector |
| `MOCK_CLMM` | `true` \| `false` | Force mock execution regardless of HB_ENV |
| `EXEC_MODE` | `mock` \| `real` | Derived execution mode (auto-set by campaign) |

**Execution Logic:**
```bash
if MOCK_CLMM=true:
    EXEC_MODE=mock
elif HB_ENV=real:
    EXEC_MODE=real
else:
    EXEC_MODE=mock
```

### Learning Control

| Variable | Default | Purpose |
|----------|---------|---------|
| `LEARN_FROM_MOCK` | `false` | Allow learning state updates from mock episodes |

**Default:** Learning is disabled for mock episodes to prevent polluting learning state with simulated data.

### Safety Gates (Real Mode)

When `EXEC_MODE=real`:
- ✅ Pool validator runs (chain/network/address validation)
- ✅ Gateway health check (if configured)
- ✅ Explicit risk acknowledgement (if `I_UNDERSTAND_LIVE_RISK` gate enabled)
- ❌ Validation skipped in mock mode

## Quick Start

### Mock Mode (Deterministic, No External Dependencies)

```bash
cd scratch

# Single deterministic episode
HB_ENV=mock \
MOCK_CLMM=true \
EXEC_MODE=mock \
LEARN_FROM_MOCK=false \
INTEL_DATA_SOURCE=mock \
HB_SEED=12345 \
EPISODES=1 \
./start_training_campaign.sh
```

**Expected Output:**
```
📂 RUN_ID: run_20251212_131714
🆔 EPISODE_ID: ep_20251212_131714_1
[MarketIntel] ⚠️  Using MOCK data
✅ Episode complete in 2s
🏆 Campaign Complete!
📁 Run directory: scratch/data/runs/run_20251212_131714
```

**Artifacts Created:**
- `data/runs/run_20251212_131714/campaign.log`
- `data/runs/run_20251212_131714/episodes/ep_20251212_131714_1/`
  - `proposal.json`
  - `metadata.json` (with intel_snapshot + intel_hygiene)
  - `result.json`
  - `timings.json`

### Dune Scheduler (Cache Warming)

**One-Shot Refresh:**
```bash
python3 quants-lab/scripts/run_dune_scheduler.py --once --log-level INFO
```

**Daemon Mode (Background):**
```bash
python3 quants-lab/scripts/run_dune_scheduler.py \
  --interval 60 \
  --workers 3 \
  --pool-cap 3 \
  --log-level INFO
```

**Notes:**
- Scheduler is **optional** for mock/CI mode
- Scheduler is **required** for real mode with fresh Dune data
- Cold cache produces `missing_or_too_old` in `intel_hygiene`
- Scheduler uses stale-while-revalidate (episodes never block)

### Real Mode (⚠️ Use with Caution)

**Status:** Real mode requires additional configuration (Gateway, Dune API key, wallet setup).

```bash
# NOT YET FULLY ENABLED
# Requires: DUNE_API_KEY, Gateway running, wallet configured
HB_ENV=real \
MOCK_CLMM=false \
LEARN_FROM_MOCK=false \
INTEL_DATA_SOURCE=dune \
EPISODES=1 \
./start_training_campaign.sh
```

## Artifact Contract

### Run Directory Structure

Every campaign creates:
```
data/runs/<run_id>/
├── campaign.log                    # Full campaign output
└── episodes/
    └── <episode_id>/
        ├── proposal.json           # Agent's pool configuration
        ├── metadata.json           # Episode metadata + intel snapshot
        ├── result.json             # Execution outcome (OR failure.json)
        ├── timings.json            # Performance metrics
        └── logs.jsonl              # Structured logs (optional)
```

### Invariants (Always True)

✅ **For every episode:**
- `proposal.json` exists
- `metadata.json` exists
- At least one of `result.json` OR `failure.json` exists

✅ **metadata.json structure:**
```json
{
  "episode_id": "ep_...",
  "run_id": "run_...",
  "exec_mode": "mock|real",
  "extra": {
    "intel_snapshot": {
      "gas_regime": {"quality": "missing", "age_s": null, "asof": null},
      "pool_metrics:0x...:1h": {"quality": "fresh", "age_s": 45, ...},
      ...
    },
    "intel_inputs": {
      "pool_address": "0x...",
      "pair": "WETH-USDC",
      "lookback_hours": 1
    },
    "intel_hygiene": {
      "total_queries": 7,
      "fresh": 2,
      "stale": 1,
      "missing_or_too_old": 4,
      "fresh_pct": 28.6
    }
  }
}
```

✅ **Failure mode:**
- `failure.json` written with error details
- `metadata.json` still written (best effort intel snapshot)
- Campaign continues to next episode (no `set -e`)

## Intel Snapshot & Hygiene

### Quality Levels

| Quality | Meaning | Action Required |
|---------|---------|-----------------|
| `fresh` | age < TTL | ✅ Safe to use |
| `stale` | TTL < age < max_age | ⚠️ Usable but refresh recommended |
| `too_old` | age > max_age | ❌ Should not use for decisions |
| `missing` | No cache entry | ❌ Run scheduler or check Dune key |

### Intel Hygiene Interpretation

**Example:**
```json
{
  "total_queries": 7,
  "fresh": 5,
  "stale": 1,
  "missing_or_too_old": 1,
  "fresh_pct": 71.4
}
```

**What to do:**
- `fresh_pct >= 80%` → ✅ Good decision context
- `fresh_pct < 50%` → ⚠️ Run scheduler, check Dune API key
- `missing_or_too_old > 0` → Check which queries failed in `intel_snapshot`

**In CI/Mock Mode:**
- Expected: `fresh=0`, `missing_or_too_old=N` (no scheduler running)
- This is normal for deterministic testing

## Health Gates & Validation

### Pool Validator (Real Mode Only)

**When:** After agent proposes, before execution
**What:** Validates pool address, chain, network
**Failure:** Writes `failure.json` and skips execution

```bash
# Triggered automatically in real mode
python3 quants-lab/lib/pool_validator.py \
  --proposal-path data/runs/<run_id>/episodes/<ep_id>/proposal.json \
  --run-id <run_id> \
  --episode-id <ep_id> \
  --exec-mode real
```

### Gateway Health Check (Real Mode Only)

**When:** Campaign start (if Gateway configured)
**What:** Checks Gateway `/` endpoint
**Failure:** Warning logged, continues (may use mock client)

## Common Failures & Fixes

| Symptom | Cause | Fix |
|---------|-------|-----|
| `Gateway not healthy` | Gateway not running or wrong port | Start Gateway: `cd hummingbot_gateway && pnpm start` |
| `Dune API key missing` | `DUNE_API_KEY` not set | Set in `.env` or export before campaign |
| `intel missing_or_too_old` | Scheduler not running or cold cache | Run `python3 quants-lab/scripts/run_dune_scheduler.py --once` |
| `proposal.json missing` | Agent crashed before writing | Check `campaign.log` and `failure.json` for traceback |
| `No episodes directory` | Agent failed before harness ran | Check `campaign.log` for Python import errors |
| `ModuleNotFoundError` | PYTHONPATH not set | Run from `scratch/` directory or set `PYTHONPATH=scratch/quants-lab` |
| `Relative path drift` | Running from wrong directory | Always run campaign from `scratch/` |
| `CI fails on checkout` | Git submodule issues | Submodules excluded in .gitignore (fixed in Phase 5) |

## Recovery & Operations

### Resume After Crash

Campaign creates new `RUN_ID` each time. To continue training:
```bash
# Just run campaign again - it creates a new run
./start_training_campaign.sh
```

### Find Latest Run

```bash
ls -td data/runs/run_* | head -1
```

### Inspect Episode Artifacts

```bash
LATEST_RUN=$(ls -td data/runs/run_* | head -1)
LATEST_EP=$(ls -td $LATEST_RUN/episodes/ep_* | head -1)

# View proposal
cat $LATEST_EP/proposal.json | jq .

# View intel snapshot
cat $LATEST_EP/metadata.json | jq .extra.intel_snapshot

# View intel hygiene
cat $LATEST_EP/metadata.json | jq .extra.intel_hygiene
```

### Clean Old Runs (Optional)

```bash
# Keep last 10 runs
cd data/runs
ls -t | tail -n +11 | xargs rm -rf
```

## CI/CD

### What CI Runs

GitHub Actions workflow (`.github/workflows/track-a-ci.yml`):
1. ✅ Syntax checks (all Phase 1-5 files)
2. ✅ Cache-first verification (grep for blocking calls)
3. ✅ Deterministic mock campaign (HB_SEED=12345, 1 episode)
4. ✅ Integration tests (artifact validation)

### Run CI Checks Locally

```bash
# Syntax checks
python3 -m py_compile quants-lab/lib/*.py
python3 -m py_compile quants-lab/schemas/*.py

# Cache-first verification
grep -n "self\.dune\.get_" quants-lab/lib/market_intel.py
# Should return empty

# Mock campaign
HB_ENV=mock MOCK_CLMM=true EXEC_MODE=mock LEARN_FROM_MOCK=false \
INTEL_DATA_SOURCE=mock HB_SEED=12345 EPISODES=1 \
./start_training_campaign.sh

# Integration tests
cd quants-lab
pytest -v tests/test_ci_integration.py
```

### CI Test Details

**File:** `quants-lab/tests/test_ci_integration.py`

**7 Test Cases:**
1. `test_proposal_exists` - Validates proposal.json
2. `test_metadata_exists` - Validates metadata.json
3. `test_result_or_failure_exists` - Ensures outcome recorded
4. `test_intel_snapshot_present` - Verifies intel_snapshot in metadata
5. `test_intel_hygiene_present` - Validates intel_hygiene fields
6. `test_intel_snapshot_structure` - Checks quality metadata format
7. Artifact discovery - Finds latest run/episode automatically

## Troubleshooting Decision Tree

```
Episode fails?
├─ Check campaign.log for errors
├─ Check failure.json for error details
└─ Common issues:
    ├─ Import errors → Check PYTHONPATH
    ├─ Gateway errors → Start Gateway or use mock
    └─ Dune errors → Check API key or use mock

Intel hygiene poor?
├─ fresh_pct < 50%?
│   ├─ Run scheduler: python3 quants-lab/scripts/run_dune_scheduler.py --once
│   └─ Check DUNE_API_KEY set
└─ Check intel_snapshot for specific missing queries

CI fails?
├─ Check GitHub Actions logs
├─ Run locally: pytest -v quants-lab/tests/test_ci_integration.py
└─ Common issues:
    ├─ No episodes directory → Agent import error
    └─ Submodule errors → Fixed in Phase 5
```

## Advanced: Event-Driven Triggers

Trigger immediate refresh of P0/P1 queries:

```python
from lib.market_intel import MarketIntelligence

intel = MarketIntelligence()
intel.trigger_refresh(
    reason="out_of_range",
    pool_address="0x88e6A0c2dDD26FEEb64F039a2c41296FcB3f5640"
)
```

This writes to `data/dune_triggers.jsonl` for scheduler to process.

## See Also

- [Environment Variables Reference](ENV_VARS_TRACK_A.md)
- [Dune Queries Catalog](../quants-lab/DUNE_QUERIES_CATALOG.md)
- [CI Integration Test](../quants-lab/tests/test_ci_integration.py)
