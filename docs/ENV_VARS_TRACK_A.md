# Track A Environment Variables Reference

## Campaign Control

| Variable | Default | Values | Scope | Purpose | Safety Notes |
|----------|---------|--------|-------|---------|--------------|
| `HB_ENV` | `mock` | `mock` \| `real` | Campaign | Top-level environment selector | Safe to change |
| `MOCK_CLMM` | `false` | `true` \| `false` | Campaign | Force mock execution | Overrides HB_ENV |
| `EXEC_MODE` | (derived) | `mock` \| `real` | Campaign | Actual execution mode | Auto-set by campaign |
| `EPISODES` | `30` | Integer | Campaign | Number of episodes to run | - |
| `START_EPISODE` | `1` | Integer | Campaign | Starting episode number | For resuming |
| `HB_SEED` | (random) | Integer | Campaign | Random seed for reproducibility | Use `12345` for CI |

## Learning Control

| Variable | Default | Values | Scope | Purpose | Safety Notes |
|----------|---------|--------|-------|---------|--------------|
| `LEARN_FROM_MOCK` | `false` | `true` \| `false` | Agent | Allow learning from mock episodes | Keep false to avoid polluting state |

## Data Sources

| Variable | Default | Values | Scope | Purpose | Safety Notes |
|----------|---------|--------|-------|---------|--------------|
| `INTEL_DATA_SOURCE` | (auto) | `dune` \| `mock` \| `chainlink` \| `hbot` | MarketIntel | Data source for market intelligence | Use `mock` for CI |
| `DUNE_API_KEY` | (none) | String | Dune | Dune Analytics API key | Required for real Dune data |

## Scheduler Configuration

| Variable | Default | Values | Scope | Purpose | Safety Notes |
|----------|---------|--------|-------|---------|--------------|
| `DUNE_SCHEDULER_WORKERS` | `3` | Integer (1-10) | Scheduler | Concurrent worker threads | Higher = more Dune API usage |
| `HB_ACTIVE_POOL_CAP` | `3` | Integer | Scheduler | Max pools to track | Limits query explosion |
| `HB_ACTIVE_POOLS` | (auto) | Comma-separated addresses | Scheduler | Explicit pool list | Overrides auto-detection |
| `HB_ACTIVE_PAIRS` | (auto) | Comma-separated pairs | Scheduler | Explicit pair list | E.g., `WETH-USDC,WETH-USDT` |
| `DUNE_TRIGGERS_FILE` | `data/dune_triggers.jsonl` | Path | Scheduler | Event-driven trigger file | - |

## Scheduler CLI Arguments

| Argument | Default | Values | Purpose |
|----------|---------|--------|---------|
| `--interval` | `60` | Seconds | Tick interval between refresh cycles |
| `--workers` | `3` | Integer | Concurrent workers (same as DUNE_SCHEDULER_WORKERS) |
| `--pool-cap` | `3` | Integer | Max active pools (same as HB_ACTIVE_POOL_CAP) |
| `--log-level` | `INFO` | `DEBUG` \| `INFO` \| `WARNING` \| `ERROR` | Logging verbosity |
| `--once` | (flag) | - | Run single tick and exit (for testing) |

## Paths & Directories

| Variable | Default | Values | Scope | Purpose | Safety Notes |
|----------|---------|--------|-------|---------|--------------|
| `DATA_DIR` | `scratch/data` | Path | Campaign | Base data directory | - |
| `AGENT_SCRIPT` | `quants-lab/phase5_learning_agent.py` | Path | Campaign | Agent script path | - |
| `HARNESS_BRIDGE` | `quants-lab/scripts/run_episode.py` | Path | Campaign | Episode runner path | - |
| `PYTHONPATH` | (auto) | Path | All | Python module search path | Auto-set to include quants-lab |

## Validation & Safety Gates

| Variable | Default | Values | Scope | Purpose | Safety Notes |
|----------|---------|--------|-------|---------|--------------|
| `DISABLE_POOL_VALIDATION` | `false` | `true` \| `false` | Campaign | Skip pool validation | ⚠️ Only for testing |
| `I_UNDERSTAND_LIVE_RISK` | (none) | `true` | Campaign | Explicit risk acknowledgement | **Not yet implemented** |

## CI/CD Specific

| Variable | Default | Values | Scope | Purpose | Safety Notes |
|----------|---------|--------|-------|---------|--------------|
| `PYTHONUNBUFFERED` | (none) | `1` | CI | Disable Python output buffering | For real-time logs |

## Common Configurations

### Deterministic CI/Testing
```bash
HB_ENV=mock
MOCK_CLMM=true
EXEC_MODE=mock
LEARN_FROM_MOCK=false
INTEL_DATA_SOURCE=mock
HB_SEED=12345
EPISODES=1
```

### Local Development (Mock)
```bash
HB_ENV=mock
MOCK_CLMM=true
INTEL_DATA_SOURCE=mock
EPISODES=5
```

### Real Mode with Dune (⚠️ Requires Setup)
```bash
HB_ENV=real
MOCK_CLMM=false
INTEL_DATA_SOURCE=dune
DUNE_API_KEY=<your_key>
EPISODES=1
```

### Scheduler Daemon
```bash
# Via environment
DUNE_SCHEDULER_WORKERS=3
HB_ACTIVE_POOL_CAP=3
python3 quants-lab/scripts/run_dune_scheduler.py

# Via CLI (preferred)
python3 quants-lab/scripts/run_dune_scheduler.py \
  --interval 60 \
  --workers 3 \
  --pool-cap 3 \
  --log-level INFO
```

## Execution Mode Decision Tree

```
MOCK_CLMM=true?
├─ Yes → EXEC_MODE=mock
└─ No → HB_ENV=real?
    ├─ Yes → EXEC_MODE=real
    └─ No → EXEC_MODE=mock
```

## Safety Recommendations

| Mode | Recommended Settings | Rationale |
|------|---------------------|-----------|
| CI/Testing | `MOCK_CLMM=true`, `INTEL_DATA_SOURCE=mock`, `HB_SEED=12345` | Deterministic, no external deps |
| Development | `HB_ENV=mock`, `INTEL_DATA_SOURCE=mock` | Safe experimentation |
| Staging | `HB_ENV=real`, `INTEL_DATA_SOURCE=dune`, `LEARN_FROM_MOCK=false` | Real data, no learning |
| Production | **Not yet enabled** | Requires additional safety gates |

## Troubleshooting

**Q: Episodes don't learn from mock runs**
A: This is expected. Set `LEARN_FROM_MOCK=true` only if you want to update learning state from simulated data.

**Q: Intel hygiene shows all missing**
A: Normal in mock mode without scheduler. Run `python3 quants-lab/scripts/run_dune_scheduler.py --once` to populate cache.

**Q: Dune API errors**
A: Check `DUNE_API_KEY` is set. Use `INTEL_DATA_SOURCE=mock` to bypass Dune entirely.

**Q: Module import errors**
A: Ensure running from `scratch/` directory. Campaign auto-sets `PYTHONPATH`.

## See Also

- [Track A Runbook](TRACK_A_RUNBOOK.md) - Operational guide
- [Dune Queries Catalog](../quants-lab/DUNE_QUERIES_CATALOG.md) - Query details
