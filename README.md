# Hummingbot Track A - Production Training Pipeline

[![Track A CI](https://github.com/duffmahn/hummingbot-track-a/actions/workflows/track-a-ci.yml/badge.svg)](https://github.com/duffmahn/hummingbot-track-a/actions)

Production-ready CLMM (Concentrated Liquidity Market Maker) training pipeline for Uniswap V3 with cache-first architecture, background data refresh, and immutable episode artifacts.

## Quick Start

### Run Mock Campaign (No External Dependencies)

```bash
cd scratch

HB_ENV=mock \
MOCK_CLMM=true \
INTEL_DATA_SOURCE=mock \
HB_SEED=12345 \
EPISODES=1 \
./start_training_campaign.sh
```

### Run Dune Scheduler (Cache Refresh)

```bash
# One-shot refresh
python3 quants-lab/scripts/run_dune_scheduler.py --once

# Daemon mode
python3 quants-lab/scripts/run_dune_scheduler.py --interval 60 --workers 3
```

### Run CI Tests Locally

```bash
# Integration tests
cd quants-lab
pytest -v tests/test_ci_integration.py

# Full CI suite
HB_ENV=mock MOCK_CLMM=true INTEL_DATA_SOURCE=mock HB_SEED=12345 EPISODES=1 \
../start_training_campaign.sh && pytest -v tests/test_ci_integration.py
```

## Features

### ✅ Production-Ready Architecture (Phases 1-5 Complete)

- **Health Gates** - Pool validation, Gateway checks (real mode)
- **Cache-First Intelligence** - Zero blocking Dune calls in episode loop
- **Background Scheduler** - Stale-while-revalidate cache refresh
- **Intel Snapshot** - Quality metadata (fresh/stale/missing) in every episode
- **Immutable Artifacts** - Complete audit trail (proposal, metadata, result, timings)
- **CI/CD Pipeline** - Automated testing with GitHub Actions

### 📊 Episode Artifacts

Every episode produces:
```
data/runs/<run_id>/episodes/<episode_id>/
├── proposal.json       # Agent's pool configuration
├── metadata.json       # Metadata + intel snapshot + hygiene
├── result.json         # Execution outcome
└── timings.json        # Performance metrics
```

**metadata.json includes:**
- `extra.intel_snapshot` - Per-query freshness (fresh/stale/missing)
- `extra.intel_hygiene` - Summary stats (fresh_pct, missing count)
- `extra.intel_inputs` - Pool/pair used for decision

### 🔄 Dune Scheduler

- **Stale-while-revalidate** - Episodes never block on data refresh
- **Bounded concurrency** - 3 workers default (configurable)
- **Active pool scoping** - Top 3 pools (prevents query explosion)
- **Event-driven triggers** - Immediate refresh on out-of-range events
- **25 Dune queries** - P0-P3 priorities (gas, pool health, MEV risk, etc.)

## Documentation

- **[Track A Runbook](docs/TRACK_A_RUNBOOK.md)** - Complete operational guide
- **[Environment Variables](docs/ENV_VARS_TRACK_A.md)** - All configuration options
- **[Dune Queries Catalog](quants-lab/DUNE_QUERIES_CATALOG.md)** - Query details

## Architecture

```
Campaign Runner (start_training_campaign.sh)
    ↓
Learning Agent (phase5_learning_agent.py)
    ├─ Proposes pool configuration
    └─ Optionally learns from outcomes
    ↓
Episode Harness (agent_harness.py)
    ├─ Captures intel snapshot (MarketIntelligence)
    ├─ Executes in MockCLMMEnvironment or GatewayCLMMClient
    └─ Writes immutable artifacts
    ↓
Artifacts (proposal, metadata, result, timings)

Background: Dune Scheduler refreshes cache
```

## Requirements

- Python 3.10+
- Dependencies: `pydantic`, `requests`, `pytest`
- Optional: Dune API key (for real data)
- Optional: Hummingbot Gateway (for real execution)

## Installation

```bash
git clone https://github.com/duffmahn/hummingbot-track-a.git
cd hummingbot-track-a/scratch

# Install dependencies
pip install pydantic requests pytest

# Run mock campaign
HB_ENV=mock MOCK_CLMM=true INTEL_DATA_SOURCE=mock EPISODES=1 \
./start_training_campaign.sh
```

## CI/CD

GitHub Actions runs on every push/PR:
1. ✅ Syntax checks (all files)
2. ✅ Cache-first verification (no blocking calls)
3. ✅ Deterministic mock campaign (HB_SEED=12345)
4. ✅ Integration tests (artifact validation)

**No external dependencies required** - CI runs entirely in mock mode.

## Project Status

| Phase | Status | Description |
|-------|--------|-------------|
| Phase 1 | ✅ Complete | Health gates & validation |
| Phase 2 | ✅ Complete | Cache-first MarketIntelligence |
| Phase 3 | ✅ Complete | Dune scheduler |
| Phase 4 | ✅ Complete | Intel snapshot in metadata |
| Phase 5 | ✅ Complete | CI/CD pipeline |
| Phase 6 | 🚧 In Progress | Documentation |
| Phase 7 | ⏳ Planned | Monitoring & metrics |
| Phase 8 | ⏳ Planned | Safety gates (optional) |

## Contributing

See [TRACK_A_RUNBOOK.md](docs/TRACK_A_RUNBOOK.md) for development workflow and testing procedures.

## License

[Add license information]

## Related Projects

- [Hummingbot](https://github.com/hummingbot/hummingbot) - Algorithmic trading bot
- [Hummingbot Gateway](https://github.com/hummingbot/gateway) - DEX connector middleware
