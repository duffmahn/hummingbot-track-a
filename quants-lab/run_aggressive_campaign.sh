#!/usr/bin/env bash
set -euo pipefail

# ============================================================================
# CRITICAL: Regime mix must be explicitly provided for calibrated runs
# ============================================================================
if [[ -z "${HB_REGIME_MIX:-}" ]]; then
    echo "❌ HB_REGIME_MIX is not set. Refusing to run with default mix."
    echo "   This prevents silent regression to old mix (0.4/0.3/0.3)."
    echo "   Example: export HB_REGIME_MIX='mean_revert:0.49,trend_up:0.36,jumpy:0.14'"
    exit 1
fi
export HB_REGIME_MIX
echo "🔁 HB_REGIME_MIX=$HB_REGIME_MIX"

# ============================================================================
# Aggressive Tuning Campaign: 100 Episodes
# ============================================================================
# Goal: Test whether increased volatility and narrowed baseline bands
#       can produce winner diversity across regimes
# ============================================================================

# Configuration
EPISODE_COUNT="${EPISODE_COUNT:-100}"
RUN_ID="${RUN_ID:-aggressive_tuning_$(date +%Y%m%d_%H%M%S)}"
EXEC_MODE="mock"
SEED=42

# Aggressive Tuning Parameters (already configured in lib/clmm_env.py)
# - sigma_mult: 3.5 (mean_revert regime)
# - baseline_hold_band: 1000 pts (narrowed from 1500)
# - baseline_wide_band: 1000 pts
# - baseline_medium_band: 500 pts
# - baseline_tight_band: 100 pts

# Environment Variables
export RUN_ID="$RUN_ID"
export EXEC_MODE="$EXEC_MODE"
export HB_SEED="$SEED"
export LEARN_FROM_MOCK="true"  # Enable learning from mock episodes

# ✅ CRITICAL: Export regime mix if set (for calibrated campaigns)
if [ -n "${HB_REGIME_MIX:-}" ]; then
    export HB_REGIME_MIX="$HB_REGIME_MIX"
    echo "📊 Using calibrated regime mix: $HB_REGIME_MIX"
fi

# ✅ FIX: Use absolute BASE_DIR for consistency across agent, harness, and artifacts
export BASE_DIR="/home/a/.gemini/antigravity/scratch/data"
export RUNS_DIR="$BASE_DIR/runs"  # For backwards compatibility

export HB_EPISODE_HORIZON_S="21600"  # 6 hours
export HB_STEP_SECONDS="60"
export HB_REBALANCE_COOLDOWN_S="1800"  # 30 minutes

# Regime Configuration: HB_REGIME_MIX already validated and exported at top
# (removed hard-coded default to prevent override)

# Create run directory using absolute path
RUNS_DIR_PATH="$BASE_DIR/runs/$RUN_ID"
mkdir -p "$RUNS_DIR_PATH/episodes"

echo "🚀 Starting Aggressive Tuning Campaign"
echo "   Run ID: $RUN_ID"
echo "   Episodes: $EPISODE_COUNT"
echo "   Exec Mode: $EXEC_MODE"
echo "   Seed: $SEED"
echo "   Base Dir: $BASE_DIR"
echo "   Runs Dir: $RUNS_DIR_PATH"
echo ""

# Run episodes
for i in $(seq 0 $((EPISODE_COUNT - 1))); do
    EPISODE_ID="ep_${RUN_ID}_${i}"
    echo "📊 Episode $((i+1))/$EPISODE_COUNT: $EPISODE_ID"
    
    # Generate proposal
    # Explicitly pass all env vars to prevent subprocess stripping
    env HB_REGIME_MIX="$HB_REGIME_MIX" \
        RUN_ID="$RUN_ID" \
        EXEC_MODE="$EXEC_MODE" \
        HB_SEED="$HB_SEED" \
        BASE_DIR="$BASE_DIR" \
        EPISODE_COUNT="$EPISODE_COUNT" \
        python3 phase5_learning_agent.py --episode-id "$EPISODE_ID" || {
        echo "❌ Agent failed for $EPISODE_ID"
        continue
    }
    
    # Execute episode
    env HB_REGIME_MIX="$HB_REGIME_MIX" \
        RUN_ID="$RUN_ID" \
        EXEC_MODE="$EXEC_MODE" \
        BASE_DIR="$BASE_DIR" \
        python3 scripts/run_episode.py --episode-id "$EPISODE_ID" || {
        echo "❌ Execution failed for $EPISODE_ID"
        continue
    }
    
    echo "✅ Episode $((i+1))/$EPISODE_COUNT complete"
    
    # First-episode verification: ensure regime_mix_source="env"
    if [[ $i -eq 0 ]]; then
        PROPOSAL_JSON="$BASE_DIR/runs/$RUN_ID/episodes/$EPISODE_ID/proposal.json"
        if [[ -f "$PROPOSAL_JSON" ]]; then
            REGIME_SRC=$(python3 - "$PROPOSAL_JSON" <<'PYEOF'
import json, sys
with open(sys.argv[1]) as f:
    data = json.load(f)
db = data.get("params", {}).get("decision_basis", {})
print(db.get("regime_mix_source", ""))
PYEOF
)
            if [[ "$REGIME_SRC" != "env" ]]; then
                echo "❌ CRITICAL: regime_mix_source='$REGIME_SRC' (expected 'env')"
                echo "   HB_REGIME_MIX was not propagated to agent process!"
                exit 1
            fi
            echo "✅ Verified: regime_mix_source='env' in episode 0"
        fi
    fi
    
    echo ""
done

echo ""
echo "🎉 Campaign Complete!"
echo ""
echo "📊 Generating Metrics..."

# Build run metrics
env RUN_ID="$RUN_ID" BASE_DIR="$BASE_DIR" \
    python3 scripts/build_run_metrics.py --run-id "$RUN_ID" || {
    echo "⚠️  Metrics generation failed"
}

echo ""
echo "📈 Results Summary:"
echo "   Run Directory: $RUNS_DIR_PATH"
echo "   Metrics File: $RUNS_DIR_PATH/run_metrics.json"
echo ""
echo "🧪 Next Steps:"
echo "   1. Review run_metrics.json for baseline_policy_win_counts_by_regime"
echo "   2. Check alpha_by_regime for positive values"
echo "   3. Run: python3 tests/test_regime_winner_shifts.py"
echo ""
