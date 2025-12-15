#!/usr/bin/env bash
#
# Three-Way Campaign Comparison
# Tests: Width Floors Only vs EV-Gated (old) vs EV-Gated + Dune Calibration
#
# Usage: ./run_3way_comparison.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Common configuration
export BASE_DIR="/home/a/.gemini/antigravity/scratch/data"
export HB_SEED=42
export EPISODE_COUNT=100
export EXEC_MODE="mock"
export HB_EPISODE_HORIZON_S=3600
export HB_STEP_SECONDS=60
export HB_REBALANCE_COOLDOWN_S=300

TIMESTAMP=$(date +%Y%m%d_%H%M%S)

echo "================================================================================"
echo "THREE-WAY CAMPAIGN COMPARISON - $TIMESTAMP"
echo "================================================================================"
echo ""
echo "Configuration:"
echo "  Episodes: $EPISODE_COUNT"
echo "  Seed: $HB_SEED"
echo "  Base Dir: $BASE_DIR"
echo ""

# ============================================================================
# Campaign A: Width Floors Only (Regression Baseline)
# ============================================================================
echo "================================================================================"
echo "CAMPAIGN A: Width Floors Only (Baseline)"
echo "================================================================================"

export RUN_ID="comparison_a_width_floors_${TIMESTAMP}"
export HB_REGIME_MIX="mean_revert:0.4,jumpy:0.3,trend_up:0.3"

# Temporarily disable EV-gating by setting very low FEE_GATE
# (This requires code change - for now, document this)
echo "⚠️  NOTE: To run Campaign A, temporarily set FEE_GATE=0.1 in phase5_learning_agent.py"
echo "   This effectively disables EV-gating while keeping width floors"
echo ""
read -p "Press Enter when ready to run Campaign A (or Ctrl+C to skip)..."

./run_aggressive_campaign.sh 2>&1 | tee "campaign_a_width_floors_${TIMESTAMP}.log"

echo "✅ Campaign A complete: $RUN_ID"
echo ""

# ============================================================================
# Campaign B: EV-Gated (Current - Old Constants)
# ============================================================================
echo "================================================================================"
echo "CAMPAIGN B: EV-Gated (Current - Old Constants)"
echo "================================================================================"

export RUN_ID="comparison_b_ev_gated_old_${TIMESTAMP}"
export HB_REGIME_MIX="mean_revert:0.4,jumpy:0.3,trend_up:0.3"

echo "⚠️  NOTE: To run Campaign B, set constants in phase5_learning_agent.py:"
echo "   GAS_USD = 2.0"
echo "   FEE_GATE = 4.0"
echo "   REGIME_MIN_WIDTH: trend:1400, jumpy:1200, mean_revert:1000"
echo ""
read -p "Press Enter when ready to run Campaign B (or Ctrl+C to skip)..."

./run_aggressive_campaign.sh 2>&1 | tee "campaign_b_ev_gated_old_${TIMESTAMP}.log"

echo "✅ Campaign B complete: $RUN_ID"
echo ""

# ============================================================================
# Campaign C: EV-Gated + Dune Calibration
# ============================================================================
echo "================================================================================"
echo "CAMPAIGN C: EV-Gated + Dune Calibration"
echo "================================================================================"

export RUN_ID="comparison_c_dune_calibrated_${TIMESTAMP}"
export HB_REGIME_MIX="mean_revert:0.49,trend_up:0.36,jumpy:0.14"  # Calibrated mix

echo "✅ Using Dune-calibrated constants (already in code):"
echo "   GAS_USD = 4.2"
echo "   FEE_GATE = 8.4"
echo "   REGIME_MIN_WIDTH: trend:1600, jumpy:1400, mean_revert:1200"
echo "   REGIME_MIX: mean_revert:49%, trend:36%, jumpy:14%"
echo ""
read -p "Press Enter to run Campaign C..."

./run_aggressive_campaign.sh 2>&1 | tee "campaign_c_dune_calibrated_${TIMESTAMP}.log"

echo "✅ Campaign C complete: $RUN_ID"
echo ""

# ============================================================================
# Analysis
# ============================================================================
echo "================================================================================"
echo "ANALYSIS"
echo "================================================================================"

RUN_A="comparison_a_width_floors_${TIMESTAMP}"
RUN_B="comparison_b_ev_gated_old_${TIMESTAMP}"
RUN_C="comparison_c_dune_calibrated_${TIMESTAMP}"

echo ""
echo "Analyzing Campaign A (Width Floors Only)..."
python3 tools/analyze_absolute_returns.py --run-id "$RUN_A" > "analysis_a_${TIMESTAMP}.txt"

echo "Analyzing Campaign B (EV-Gated Old)..."
python3 tools/analyze_absolute_returns.py --run-id "$RUN_B" > "analysis_b_${TIMESTAMP}.txt"

echo "Analyzing Campaign C (Dune Calibrated)..."
python3 tools/analyze_absolute_returns.py --run-id "$RUN_C" > "analysis_c_${TIMESTAMP}.txt"

echo ""
echo "================================================================================"
echo "COMPARISON SUMMARY"
echo "================================================================================"

python3 << 'EOF'
import json
import sys
from pathlib import Path

runs = {
    "A_width_floors": "$RUN_A",
    "B_ev_gated_old": "$RUN_B",
    "C_dune_calibrated": "$RUN_C"
}

print("\n📊 THREE-WAY COMPARISON\n")
print(f"{'Campaign':<25} {'Net PnL':<12} {'Hold%':<8} {'Widen':<8} {'Gas':<8}")
print("=" * 70)

for name, run_id in runs.items():
    try:
        summary_file = Path(f"$BASE_DIR/runs/{run_id}/metrics_summary.json")
        if summary_file.exists():
            with open(summary_file) as f:
                data = json.load(f)
            
            total_net = data['overall']['total_net_pnl']
            actions = data['by_action']
            hold_count = actions.get('hold', {}).get('count', 0)
            widen_count = actions.get('widen', {}).get('count', 0)
            total_gas = data['overall']['total_gas']
            total_eps = data['overall']['episode_count']
            hold_pct = (hold_count / total_eps * 100) if total_eps > 0 else 0
            
            print(f"{name:<25} ${total_net:<11.2f} {hold_pct:<7.1f}% {widen_count:<8} ${total_gas:<7.2f}")
        else:
            print(f"{name:<25} (not found)")
    except Exception as e:
        print(f"{name:<25} (error: {e})")

print("\n✅ Detailed analysis saved to analysis_*.txt files")
print("\n📁 Run IDs:")
for name, run_id in runs.items():
    print(f"  {name}: {run_id}")
EOF

echo ""
echo "================================================================================"
echo "NEXT STEPS"
echo "================================================================================"
echo ""
echo "1. Review analysis_*.txt files for detailed breakdowns"
echo "2. Check that Dune calibration didn't overfit:"
echo "   - Net PnL improvement persists"
echo "   - Widen stays ~10-20%"
echo "   - Gas remains controlled"
echo "   - No new bad rules dominating"
echo "3. If validation passes, proceed to 500-episode long run"
echo ""
