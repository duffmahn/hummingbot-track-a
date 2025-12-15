# Aggressive Tuning Campaign - Logs & Configuration

## 📋 Campaign Configuration

### Script: `run_aggressive_campaign.sh`

```bash
#!/usr/bin/env bash
set -euo pipefail

# Configuration
EPISODE_COUNT=100
RUN_ID="aggressive_tuning_$(date +%Y%m%d_%H%M%S)"
EXEC_MODE="mock"
SEED=42

# Environment Variables
export RUN_ID="$RUN_ID"
export EXEC_MODE="$EXEC_MODE"
export HB_SEED="$SEED"
export LEARN_FROM_MOCK="true"
export RUNS_DIR="data/runs"
export HB_EPISODE_HORIZON_S="21600"  # 6 hours
export HB_STEP_SECONDS="60"
export HB_REBALANCE_COOLDOWN_S="1800"  # 30 minutes

# ⚠️ CRITICAL: Regime Configuration
export HB_REGIME_MIX="mean_revert:0.4,jumpy:0.3,trend_up:0.3"
```

### Aggressive Tuning Parameters (in `lib/clmm_env.py`)

```python
# Baseline Bands (narrowed for aggressive testing)
BASELINE_POLICIES = {
    "baseline_hold":   {"mode": "hold_forever", "width_pts": 1000, ...},  # ← 1500→1000
    "baseline_wide":   {"mode": "fixed",        "width_pts": 1000, ...},  # ← 1500→1000
    "baseline_medium": {"mode": "fixed",        "width_pts": 500,  ...},
    "baseline_tight":  {"mode": "fixed",        "width_pts": 100,  ...},
}

# Regime Volatility (increased for diversity)
REGIME_PRESETS = {
    "mean_revert": {
        "sigma_mult": 3.5,      # ← 2.0→3.5 (stronger oscillations)
        "mean_revert_k": 0.08,
        "volume_mult": 2.0,     # ← 1.4→2.0
        "il_penalty_mult": 0.4,
    },
    "jumpy": {
        "sigma_mult": 2.5,      # ← 1.2→2.5 (more volatility)
        "jump_prob": 0.04,
        "jump_size_ticks": 120,
        "volume_mult": 2.0,     # ← 1.6→2.0
        "il_penalty_mult": 0.5,
    },
    "trend_up": {
        "sigma_mult": 3.0,      # ← 1.5→3.0
        "drift_per_step": 4.0,
        "volume_mult": 1.6,     # ← 1.3→1.6
        "il_penalty_mult": 0.25,
    },
}
```

---

## 📊 Campaign Execution Summary

**Run ID:** `aggressive_tuning_20251213_145220`  
**Episodes:** 100/100 completed ✅  
**Duration:** 104.08 seconds  
**Success Rate:** 100%  

### Environment Variables (Actual)
```
RUN_ID=aggressive_tuning_20251213_145220
EXEC_MODE=mock
HB_SEED=42
LEARN_FROM_MOCK=true
RUNS_DIR=data/runs
HB_EPISODE_HORIZON_S=21600
HB_STEP_SECONDS=60
HB_REBALANCE_COOLDOWN_S=1800
HB_REGIME_MIX=mean_revert:0.4,jumpy:0.3,trend_up:0.3  # ⚠️ NOT APPLIED!
```

---

## 🔍 Sample Episode Logs

### Episode 1 (ep_aggressive_tuning_20251213_145220_0)

```
📊 Episode 1/100: ep_aggressive_tuning_20251213_145220_0
WARNING:lib.hummingbot_data_client:Failed to initialize DuneClient: DUNE_API_KEY not found
[HummingbotAPIClient] Connecting to Gateway at http://localhost:15888
[MockDataClient] ⚠️  Using MOCK data - not real market data!
[MarketIntel] ⚠️  DefiLlama disabled (API Hang)

{"timestamp": "2025-12-13T19:52:20.915288Z", "level": "INFO", "name": "Phase5Agent", 
 "message": "Phase 5 Agent Initialized", "config_hash": "manual", "state_version": "1.0"}

INFO:Phase5Agent:🤖 Phase 5 Learning Agent Starting...
INFO:Phase5Agent:🧠 Updating parameter beliefs from history...
INFO:Phase5Agent:🧠 Updated belief for low_vol_high_liquidity (3 params)
INFO:Phase5Agent:🧠 Updated belief for vol_mid-liq_high (2 params)
INFO:Phase5Agent:💾 Proposal saved to .../episodes/ep_aggressive_tuning_20251213_145220_0/proposal.json

INFO:AgentHarness:Intel snapshot captured: 7 queries
INFO:AgentHarness:🚀 Executing Episode ep_aggressive_tuning_20251213_145220_0 in MockCLMMEnvironment
INFO:AgentHarness:✅ Episode ep_aggressive_tuning_20251213_145220_0 completed successfully

[DuneCache] Error reading cache for gas_regime: SmartCache.get() missing 1 required positional argument
[DuneCache] Error reading cache for mev_risk: SmartCache.get() missing 1 required positional argument
[DuneCache] Error reading cache for rebalance_hint: SmartCache.get() missing 1 required positional argument

✅ Episode 1/100 complete
```

### Episode 1 Reward Breakdown

```json
{
    "total": -361.71,
    "components": {
        "alpha": -360.50,           // ← Agent lost vs baseline_hold
        "net_pnl_ctx": -0.31,
        "rebalance_penalty": -0.50,
        "oor_penalty": -0.35,
        "latency_penalty": -0.05,
        "pnl_recon_error": 0.0
    }
}
```

---

## 🐛 Critical Bug: Regime Assignment Not Working

### Expected Regime Distribution
Based on `HB_REGIME_MIX="mean_revert:0.4,jumpy:0.3,trend_up:0.3"`:
- **mean_revert:** 40 episodes
- **jumpy:** 30 episodes
- **trend_up:** 30 episodes

### Actual Regime Distribution
From `metrics_summary.json`:
```json
"episodes_by_regime": {
  "low": 100  // ⚠️ ALL episodes classified as "low" regime!
}
```

### Impact
- All 100 episodes ran with `sigma_mult=1.0` (low volatility)
- Aggressive parameters (`sigma_mult=3.5`, narrowed bands) were **never tested**
- `baseline_hold` naturally dominates in low volatility
- Winner diversity test fails: only 1 winner across all regimes

---

## 📈 Results Summary (from metrics_summary.json)

### Overall Metrics
| Metric | Value |
|--------|-------|
| Total PnL | -$194.47 |
| Total Fees | $54.43 |
| Total Gas | $200.00 |
| ROI | -97.23% |
| Mean OOR% | 55.87% |
| Alpha Win Rate | **0.0%** |

### Winner Distribution
```json
"baseline_policy_win_counts": {
  "baseline_hold": 100  // ← 100% dominance
},
"baseline_policy_win_counts_by_regime": {
  "low": {
    "baseline_hold": 100  // ← All in "low" regime
  }
}
```

### Agent Behavior
```json
"hold_episodes": 0,
"rebalance_episodes": 100,  // ← Agent rebalanced EVERY episode
"mean_gas_cost_usd": 2.0,
"mean_alpha_per_gas_usd": -763.27
```

---

## 🔧 Diagnostic Findings

### 1. Agent Learning from Wrong Regimes
```
INFO:Phase5Agent:🧠 Updated belief for low_vol_high_liquidity (3 params)
INFO:Phase5Agent:🧠 Updated belief for vol_mid-liq_high (2 params)
```
- Agent is learning from `low_vol_high_liquidity` and `vol_mid-liq_high`
- These are **NOT** the configured regimes (mean_revert, jumpy, trend_up)
- Suggests regime classification happens elsewhere (not from `HB_REGIME_MIX`)

### 2. Regime Assignment Logic Missing
The `HB_REGIME_MIX` environment variable is set but **not being read** by:
- `phase5_learning_agent.py` (hardcodes `current_regime = "vol_mid-liq_low"`)
- `lib/agent_harness.py` (needs investigation)
- `lib/clmm_env.py` (has regime presets but no assignment logic)

### 3. DuneCache Errors (Non-Critical)
```
[DuneCache] Error reading cache for gas_regime: SmartCache.get() missing 1 required positional argument
```
- These are warnings, not failures
- Related to Phase 2/3 Dune integration
- Don't affect episode execution

---

## 🎯 Root Cause Analysis

### Where Regime Should Be Assigned

**Expected Flow:**
1. Campaign script sets `HB_REGIME_MIX="mean_revert:0.4,jumpy:0.3,trend_up:0.3"`
2. Agent/Harness reads environment variable
3. For each episode, randomly selects regime based on weights
4. Passes regime to `MockCLMMEnvironment` for tick path generation
5. Metrics aggregator records regime for analysis

**Actual Flow:**
1. Campaign script sets `HB_REGIME_MIX` ✅
2. Agent hardcodes `current_regime = "vol_mid-liq_low"` ❌
3. Metrics aggregator sees all episodes as "low" regime ❌
4. Aggressive parameters never applied ❌

### Files to Investigate
1. **`phase5_learning_agent.py:203`** - Hardcoded regime
2. **`lib/agent_harness.py`** - Should read `HB_REGIME_MIX`
3. **`lib/metrics_aggregator.py`** - How is regime extracted?

---

## 📝 Recommended Fixes

### Fix 1: Agent Should Read HB_REGIME_MIX

**File:** `phase5_learning_agent.py`

```python
# Current (line 203):
current_regime = "vol_mid-liq_low"  # ❌ Hardcoded

# Should be:
import random
regime_mix_str = os.environ.get("HB_REGIME_MIX", "low:1.0")
regime_weights = {}
for pair in regime_mix_str.split(","):
    regime, weight = pair.split(":")
    regime_weights[regime] = float(weight)

# Randomly select regime based on weights
regimes = list(regime_weights.keys())
weights = list(regime_weights.values())
current_regime = random.choices(regimes, weights=weights, k=1)[0]
```

### Fix 2: Pass Regime to Environment

**File:** `lib/agent_harness.py`

```python
# Should pass regime to MockCLMMEnvironment
env = MockCLMMEnvironment(seed=seed, regime=current_regime)
```

### Fix 3: Environment Uses Regime for Tick Path

**File:** `lib/clmm_env.py` (MockCLMMEnvironment.execute_episode)

```python
# Use regime to get config
regime_cfg = get_regime_cfg(self.regime)
tick_path, tick_path_stats = generate_tick_path(
    regime_cfg=regime_cfg,
    start_tick=current_tick,
    steps=steps,
    rng=rng,
    anchor_tick=current_tick,
    sigma_base=10.0
)
```

---

## 🧪 Verification Plan

After fixes:
1. Re-run campaign with same config
2. Check `metrics_summary.json` for regime distribution
3. Verify `baseline_policy_win_counts_by_regime` shows diversity
4. Run `test_regime_winner_shifts.py` (should pass with ≥2 winners)

---

## 📁 Artifacts

- **Campaign Script:** `run_aggressive_campaign.sh`
- **Full Log:** `aggressive_campaign.log` (3333 lines, 304KB)
- **Metrics:** `/home/a/.gemini/antigravity/scratch/data/runs/aggressive_tuning_20251213_145220/metrics_summary.json`
- **Episodes:** 100 episode directories with proposal.json, reward.json, metadata.json
- **Walkthrough:** `/home/a/.gemini/antigravity/brain/358cb939-09a4-4e04-83d5-2e8728dfe623/walkthrough.md`
