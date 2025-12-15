#!/usr/bin/env python3
"""
Calibrate strategy parameters from Dune query results.

Usage:
    python3 tools/calibrate_from_dune.py --dune-results calibration_data.json

Expected JSON format:
{
    "fees_median_usd": 150.0,
    "fees_p90_usd": 450.0,
    "gas_median_usd": 2.5,
    "gas_p75_usd": 4.0,
    "gas_p90_usd": 8.0,
    "vol_median": 0.45,
    "vol_p90": 0.85,
    "jump_rate": 0.12,
    "trend_rate": 0.25,
    "mean_revert_rate": 0.35
}
"""

import json
import argparse
from pathlib import Path


def calibrate_strategy(dune_results: dict) -> dict:
    """Generate calibrated strategy parameters from Dune results."""
    
    # Extract key metrics
    fees_median = dune_results.get("fees_median_usd", 150.0)
    fees_p90 = dune_results.get("fees_p90_usd", 450.0)
    gas_median = dune_results.get("gas_median_usd", 2.5)
    gas_p75 = dune_results.get("gas_p75_usd", 4.0)
    gas_p90 = dune_results.get("gas_p90_usd", 8.0)
    vol_median = dune_results.get("vol_median", 0.45)
    vol_p90 = dune_results.get("vol_p90", 0.85)
    jump_rate = dune_results.get("jump_rate", 0.12)
    trend_rate = dune_results.get("trend_rate", 0.25)
    mean_revert_rate = dune_results.get("mean_revert_rate", 0.35)
    
    # Calculate derived metrics
    fees_to_gas_ratio = fees_median / max(gas_median, 0.01)
    gas_tail_risk = gas_p90 / max(gas_median, 0.01)
    
    # Calibrate GAS_USD (use P75 for conservative estimate)
    calibrated_gas = gas_p75
    
    # Calibrate FEE_GATE based on fees-to-gas ratio
    if fees_to_gas_ratio < 1.0:
        # Gas dominates - very conservative
        fee_gate_multiplier = 3.0
    elif fees_to_gas_ratio < 2.0:
        # Gas significant - conservative
        fee_gate_multiplier = 2.5
    else:
        # Fees justify more activity
        fee_gate_multiplier = 2.0
    
    calibrated_fee_gate = fee_gate_multiplier * calibrated_gas
    
    # Calibrate OOR_CRITICAL based on jump rate
    if jump_rate > 0.15:
        # High jump rate - very conservative
        oor_critical_base = 95.0
        oor_critical_jumpy = 92.0
    elif jump_rate > 0.10:
        # Moderate jump rate - current settings
        oor_critical_base = 92.0
        oor_critical_jumpy = 90.0
    else:
        # Low jump rate - can be more aggressive
        oor_critical_base = 90.0
        oor_critical_jumpy = 88.0
    
    # Calibrate width floors based on volatility
    if vol_p90 > 0.80:
        # High volatility - wider floors
        width_trend = 1600
        width_jumpy = 1400
        width_mean_revert = 1200
    elif vol_p90 > 0.60:
        # Moderate volatility - current settings
        width_trend = 1400
        width_jumpy = 1200
        width_mean_revert = 1000
    else:
        # Low volatility - can use narrower
        width_trend = 1200
        width_jumpy = 1000
        width_mean_revert = 800
    
    # Calibrate regime mix based on observed frequencies
    total_rate = trend_rate + jump_rate + mean_revert_rate
    if total_rate > 0:
        regime_mix = {
            "trend_up": round(trend_rate / total_rate, 2),
            "jumpy": round(jump_rate / total_rate, 2),
            "mean_revert": round(mean_revert_rate / total_rate, 2)
        }
    else:
        regime_mix = {"trend_up": 0.3, "jumpy": 0.3, "mean_revert": 0.4}
    
    # Generate calibration report
    calibration = {
        "input_metrics": {
            "fees_median_usd": fees_median,
            "fees_p90_usd": fees_p90,
            "gas_median_usd": gas_median,
            "gas_p75_usd": gas_p75,
            "gas_p90_usd": gas_p90,
            "vol_median": vol_median,
            "vol_p90": vol_p90,
            "jump_rate": jump_rate,
            "fees_to_gas_ratio": fees_to_gas_ratio,
            "gas_tail_risk": gas_tail_risk
        },
        "calibrated_constants": {
            "GAS_USD": calibrated_gas,
            "FEE_GATE": calibrated_fee_gate,
            "LOSS_BREAKER": -1000.0,  # Keep constant
            "OOR_CRITICAL_DEFAULT": oor_critical_base,
            "OOR_CRITICAL_BY_REGIME": {
                "trend_up": oor_critical_base,
                "trend_down": oor_critical_base,
                "jumpy": oor_critical_jumpy,
                "mean_revert": oor_critical_base,
                "low": oor_critical_base - 2.0,
                "mid": oor_critical_jumpy
            },
            "REGIME_MIN_WIDTH": {
                "trend_up": width_trend,
                "trend_down": width_trend,
                "jumpy": width_jumpy,
                "mean_revert": width_mean_revert,
                "low": 800,
                "mid": 1000
            }
        },
        "calibrated_regime_mix": regime_mix,
        "recommendations": []
    }
    
    # Add recommendations
    if fees_to_gas_ratio < 1.0:
        calibration["recommendations"].append(
            "⚠️  Fees-to-gas ratio < 1.0: Gas dominates. Prioritize hold-by-default and minimize interventions."
        )
    elif fees_to_gas_ratio > 3.0:
        calibration["recommendations"].append(
            "✅ Fees-to-gas ratio > 3.0: Fee budget supports more active management. Consider lowering OOR thresholds slightly."
        )
    
    if jump_rate > 0.15:
        calibration["recommendations"].append(
            "⚠️  High jump rate (>15%): Use wider bands and higher OOR thresholds to avoid churn."
        )
    
    if gas_tail_risk > 3.0:
        calibration["recommendations"].append(
            f"⚠️  Gas tail risk {gas_tail_risk:.1f}x: P90 gas is {gas_tail_risk:.1f}x median. Enforce strict cooldowns."
        )
    
    return calibration


def main():
    parser = argparse.ArgumentParser(description="Calibrate strategy from Dune results")
    parser.add_argument("--dune-results", required=True, help="Path to Dune results JSON")
    parser.add_argument("--output", default="calibration_report.json", help="Output file")
    
    args = parser.parse_args()
    
    # Load Dune results
    with open(args.dune_results) as f:
        dune_results = json.load(f)
    
    # Calibrate
    calibration = calibrate_strategy(dune_results)
    
    # Save report
    with open(args.output, "w") as f:
        json.dump(calibration, f, indent=2)
    
    # Print summary
    print("=" * 80)
    print("STRATEGY CALIBRATION REPORT")
    print("=" * 80)
    
    print("\n📊 INPUT METRICS:")
    for key, value in calibration["input_metrics"].items():
        print(f"  {key}: {value}")
    
    print("\n⚙️  CALIBRATED CONSTANTS:")
    print(f"  GAS_USD: ${calibration['calibrated_constants']['GAS_USD']:.2f}")
    print(f"  FEE_GATE: ${calibration['calibrated_constants']['FEE_GATE']:.2f}")
    print(f"  OOR_CRITICAL_DEFAULT: {calibration['calibrated_constants']['OOR_CRITICAL_DEFAULT']:.1f}%")
    
    print("\n📏 WIDTH FLOORS:")
    for regime, width in calibration['calibrated_constants']['REGIME_MIN_WIDTH'].items():
        print(f"  {regime}: {width} pts")
    
    print("\n🌍 REGIME MIX:")
    for regime, weight in calibration['calibrated_regime_mix'].items():
        print(f"  {regime}: {weight*100:.0f}%")
    
    print("\n💡 RECOMMENDATIONS:")
    for rec in calibration["recommendations"]:
        print(f"  {rec}")
    
    print(f"\n✅ Full report saved to: {args.output}")


if __name__ == "__main__":
    main()
