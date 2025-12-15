#!/usr/bin/env python3
"""
Quick verification script to test the baseline fee fix.
Compares baseline_hold fees before and after the order_size fix.
"""
import json
from pathlib import Path

def analyze_run(run_path):
    """Analyze a single run's baseline fees."""
    episodes_dir = Path(run_path) / "episodes"
    if not episodes_dir.exists():
        print(f"❌ Episodes directory not found: {episodes_dir}")
        return
    
    print(f"\n📊 Analyzing run: {Path(run_path).name}")
    print("=" * 100)
    print(f"{'Ep':<4} {'Regime':<12} {'BH Fees':<12} {'BH Net':<12} {'BH OOR%':<10} {'Status':<10}")
    print("-" * 100)
    
    realistic_count = 0
    unrealistic_count = 0
    
    for ep_dir in sorted(episodes_dir.glob("ep_*")):
        result_file = ep_dir / "result.json"
        if not result_file.exists():
            continue
            
        with open(result_file) as f:
            d = json.load(f)
        
        # Extract episode number
        ep_num = ep_dir.name.split("_")[-1]
        
        # Get baseline_hold metrics
        bh = (d.get('baselines', {}) or {}).get('baseline_hold', {}) or {}
        bh_fees = bh.get('fees_usd', 0)
        bh_net = bh.get('pnl_usd', 0) - bh.get('gas_cost_usd', 0)
        bh_oor = bh.get('out_of_range_pct', 0)
        
        # Get regime
        pos_after = d.get('position_after', {}) or {}
        regime = pos_after.get('regime_name', 'unknown')
        
        # Realistic check (looser thresholds)
        realistic = '✅' if (abs(bh_net) < 100 and bh_fees < 20) else '❌'
        
        if realistic == '✅':
            realistic_count += 1
        else:
            unrealistic_count += 1
        
        print(f"{ep_num:<4} {regime:<12} ${bh_fees:>9.2f} ${bh_net:>9.2f} {bh_oor:>8.1f}% {realistic:<10}")
    
    print("-" * 100)
    print(f"✅ Realistic: {realistic_count} episodes")
    print(f"❌ Unrealistic: {unrealistic_count} episodes")
    print(f"📈 Pass Rate: {realistic_count / (realistic_count + unrealistic_count) * 100:.1f}%")

if __name__ == "__main__":
    # Analyze the existing run (before fix)
    print("\n🔍 BEFORE FIX (aggressive_tuning_20251214_130419)")
    analyze_run("/home/a/.gemini/antigravity/scratch/data/runs/aggressive_tuning_20251214_130419")
    
    print("\n" + "=" * 100)
    print("\n📝 EXPECTED AFTER FIX:")
    print("   - Baseline_hold fees should be < $20 for all episodes")
    print("   - Mean revert episodes should show ✅ instead of ❌")
    print("   - Pass rate should be ~100% instead of ~40%")
    print("\n💡 TO VERIFY FIX:")
    print("   Run a new campaign with the fixed code and compare results")
