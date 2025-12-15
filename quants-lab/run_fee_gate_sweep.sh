#!/usr/bin/env bash
#
# FEE_GATE Sweep: Test 3 different FEE_GATE values with identical seeds
# Goal: Find optimal FEE_GATE for mock environment
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Common configuration
export BASE_DIR="/home/a/.gemini/antigravity/scratch/data"
export HB_SEED=42
export HB_REGIME_MIX="mean_revert:0.49,trend_up:0.36,jumpy:0.14"  # Calibrated mix
export EXEC_MODE="mock"
export EPISODE_COUNT=100
export GAS_USD=2.0

TIMESTAMP=$(date +%Y%m%d_%H%M%S)

echo "================================================================================"
echo "FEE_GATE SWEEP - $TIMESTAMP"
echo "================================================================================"
echo ""
echo "Configuration:"
echo "  Episodes: $EPISODE_COUNT"
echo "  Seed: $HB_SEED"
echo "  Regime Mix: $HB_REGIME_MIX (calibrated)"
echo "  GAS_USD: $GAS_USD"
echo ""

# ============================================================================
# Campaign 1: FEE_GATE = $4.00 (baseline best)
# ============================================================================
echo "================================================================================"
echo "CAMPAIGN 1: FEE_GATE = \$4.00 (2.0x GAS, baseline best)"
echo "================================================================================"

export FEE_GATE_MULT=2.0
export RUN_ID="fee_gate_sweep_4.0_${TIMESTAMP}"

./run_aggressive_campaign.sh 2>&1 | tee "campaign_gate_4.0_${TIMESTAMP}.log"

RUN_1=$RUN_ID
echo "✅ Campaign 1 complete: $RUN_1"
echo ""

# ============================================================================
# Campaign 2: FEE_GATE = $6.00 (intermediate)
# ============================================================================
echo "================================================================================"
echo "CAMPAIGN 2: FEE_GATE = \$6.00 (3.0x GAS, intermediate)"
echo "================================================================================"

export FEE_GATE_MULT=3.0
export RUN_ID="fee_gate_sweep_6.0_${TIMESTAMP}"

./run_aggressive_campaign.sh 2>&1 | tee "campaign_gate_6.0_${TIMESTAMP}.log"

RUN_2=$RUN_ID
echo "✅ Campaign 2 complete: $RUN_2"
echo ""

# ============================================================================
# Campaign 3: FEE_GATE = $8.40 (Dune calibrated)
# ============================================================================
echo "================================================================================"
echo "CAMPAIGN 3: FEE_GATE = \$8.40 (4.2x GAS, Dune calibrated)"
echo "================================================================================"

export FEE_GATE_MULT=4.2
export RUN_ID="fee_gate_sweep_8.4_${TIMESTAMP}"

./run_aggressive_campaign.sh 2>&1 | tee "campaign_gate_8.4_${TIMESTAMP}.log"

RUN_3=$RUN_ID
echo "✅ Campaign 3 complete: $RUN_3"
echo ""

# ============================================================================
# Analysis
# ============================================================================
echo "================================================================================"
echo "ANALYSIS"
echo "================================================================================"

echo ""
echo "Analyzing Campaign 1 (FEE_GATE=\$4.00)..."
python3 tools/analyze_absolute_returns.py --run-id "$RUN_1" > "analysis_gate_4.0_${TIMESTAMP}.txt"

echo "Analyzing Campaign 2 (FEE_GATE=\$6.00)..."
python3 tools/analyze_absolute_returns.py --run-id "$RUN_2" > "analysis_gate_6.0_${TIMESTAMP}.txt"

echo "Analyzing Campaign 3 (FEE_GATE=\$8.40)..."
python3 tools/analyze_absolute_returns.py --run-id "$RUN_3" > "analysis_gate_8.4_${TIMESTAMP}.txt"

echo ""
echo "================================================================================"
echo "COMPARISON"
echo "================================================================================"

python3 tools/compare_fee_gates.py "$RUN_1" "$RUN_2" "$RUN_3"

echo ""
echo "================================================================================"
echo "RESULTS SAVED"
echo "================================================================================"
echo ""
echo "Run IDs:"
echo "  FEE_GATE=\$4.00: $RUN_1"
echo "  FEE_GATE=\$6.00: $RUN_2"
echo "  FEE_GATE=\$8.40: $RUN_3"
echo ""
echo "Analysis files:"
echo "  analysis_gate_4.0_${TIMESTAMP}.txt"
echo "  analysis_gate_6.0_${TIMESTAMP}.txt"
echo "  analysis_gate_8.4_${TIMESTAMP}.txt"
echo ""
echo "Next: Review comparison output to select best FEE_GATE"
echo ""
