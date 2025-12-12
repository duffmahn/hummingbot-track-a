#!/usr/bin/env python3
"""
Build Run Metrics CLI Tool

Generates metrics_summary.json and episode_metrics.jsonl for a run.

Usage:
    python3 build_run_metrics.py --run-id run_20251212_162025
"""

import sys
import argparse
from pathlib import Path

# Add quants-lab to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.metrics_aggregator import aggregate_run_metrics


def main():
    parser = argparse.ArgumentParser(description="Build metrics for a Track A run")
    parser.add_argument(
        "--run-id",
        type=str,
        required=True,
        help="Run ID (e.g., run_20251212_162025)"
    )
    parser.add_argument(
        "--data-dir",
        type=str,
        default=None,
        help="Data directory (default: auto-detect from script location)"
    )
    
    args = parser.parse_args()
    
    # Determine data directory
    if args.data_dir:
        data_dir = Path(args.data_dir)
    else:
        # Auto-detect: script is in scratch/quants-lab/scripts/
        script_dir = Path(__file__).parent
        data_dir = script_dir.parent.parent / "data"
    
    run_dir = data_dir / "runs" / args.run_id
    
    # Validate run directory exists
    if not run_dir.exists():
        print(f"❌ Run directory not found: {run_dir}")
        sys.exit(1)
    
    print(f"📊 Building metrics for {args.run_id}")
    print(f"📁 Run directory: {run_dir}")
    
    try:
        # Aggregate metrics
        ep_metrics_path, summary_path = aggregate_run_metrics(run_dir)
        
        print(f"✅ Episode metrics: {ep_metrics_path}")
        print(f"✅ Summary: {summary_path}")
        
        # Print summary preview
        import json
        with open(summary_path) as f:
            summary = json.load(f)
        
        print(f"\n📈 Summary Preview:")
        print(f"  Total Episodes: {summary.get('total_episodes')}")
        print(f"  Success: {summary.get('success_count')}")
        print(f"  Failure: {summary.get('failure_count')}")
        print(f"  Total PnL: ${summary.get('total_pnl_usd', 0):.2f}")
        print(f"  Avg PnL: ${summary.get('avg_pnl_usd', 0):.2f}")
        print(f"  Avg Latency: {summary.get('avg_latency_ms', 0):.2f}ms")
        
        sys.exit(0)
        
    except Exception as e:
        print(f"❌ Failed to build metrics: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
