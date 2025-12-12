
# Quants Lab Agent API (Phase 5)

This document explains the architecture of the **Autonomous Learning Agent**, its data contracts, and file layout.

## 1. Core Contracts (Schemas)

The system relies on strict Pydantic models defined in `schemas/contracts.py`.

### Proposal (`proposal_*.json`)
The Agent outputs a **Proposal** file to drive the Harness.

```json
{
  "episode_id": "auto",
  "generated_at": "2025-12-12T14:44:21Z",
  "status": "active",
  "params": {
    "width_pts": 558,
    "rebalance_threshold_pct": 0.05,
    "spread_bps": 20,
    "order_size": 0.1,
    "refresh_interval": 60
  },
  "metadata": {
    "current_regime": "vol_mid-liq_high",
    "metrics": { "confidence": "high" },
    "agent_version": "v5.4",
    "config_hash": "..."
  }
}
```

### Learning State (`learning_state.json`)
The Agent maintains belief distributions per regime in `data/learning_state.json`.

```json
{
  "version": "1.0",
  "regimes": {
    "vol_mid-liq_high": {
      "params": {
        "width_pts": {
            "mean": 328.0, "std_dev": 50.0,
            "min_val": 5.0, "max_val": 5000.0,
            "sample_count": 10
        }
      },
      "last_updated": "..."
    }
  }
}
```

## 2. File Layout

All data resides in `data/` (or configured root).

```
data/
├── uniswap_v4_runs/             # Historical Episode Records
│   ├── 20251212_100000_WETH_USDC.json  # Full record (Intel + Action + Reward)
├── uniswap_v4_proposals/        # Agent Proposals
│   ├── proposal_latest.json     # Most recent proposal
│   ├── proposal_auto.json       # Auto-loop proposal
├── learning_state.json          # Persistent Belief State
└── agent_config.yml             # Global Safety Config
```

## 3. Libraries & Wrappers

### `UV4ExperimentStore`
Loads historical runs into a Pandas DataFrame for learning.
```python
from lib.uv4_experiments import UV4ExperimentStore
store = UV4ExperimentStore()
df = store.to_dataframe(min_version="v1_realtime")
```

### `MarketIntelligence`
Provides real-time signals and consistent regime classification (`low_vol`, `vol_mid`, etc.).
```python
from lib.market_intel import MarketIntelligence
intel = MarketIntelligence()
regime = intel.get_market_regime(pair, pool)
```

### `HummingbotAPIWrapper`
Health-aware wrapper for live execution and simulation. Use the `data` singleton in agent.
```python
from lib.hummingbot_api_wrapper import hummingbot_api
quote = hummingbot_api.get_v4_quote_safe(..., simulate=True)
```

## 4. Training Loop (CI Verified)

The standard loop (verified by `tests/test_full_training_cycle.py`) is:

1. **Load History**: Agent reads `uniswap_v4_runs/*.json`.
2. **Update Beliefs**: Agent updates `learning_state.json` using Windowed CEM (Top 25% of recent runs).
3. **Sense**: Agent detects current regime (e.g., `vol_mid-liq_high`).
4. **Sample**: Agent samples parameters from belief distributions (clamped to safe ranges).
5. **Propose**: Agent writes `proposal_auto.json`.
6. **Simulate**: Agent (or Harness) runs simulation gate. If failed, marks `used_fallback=True`.
7. **Execute**: Harness executes proposal.
8. **Record**: Harness saves result to `uniswap_v4_runs/`.
