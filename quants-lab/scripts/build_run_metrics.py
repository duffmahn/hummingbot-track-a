#!/usr/bin/env python3
"""
Build Run Metrics CLI Tool

Generates ROI-aware metrics_summary.json for a run.

Usage:
    python3 build_run_metrics.py --run-id run_20251212_162025
    python3 build_run_metrics.py  # auto-selects latest run
"""

import sys
import argparse
import json
from pathlib import Path

# Add quants-lab to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.metrics_aggregator import build_run_metrics, aggregate_run_metrics


def find_latest_run(runs_dir: Path) -> str:
    """Find the most recent run_* directory by modification time."""
    if not runs_dir.exists():
        print(f"❌ Runs directory not found: {runs_dir}")
        sys.exit(1)
    
    # Find all run_* directories
    run_dirs = [d for d in runs_dir.glob("run_*") if d.is_dir()]
    
    if not run_dirs:
        print(f"❌ No run directories found in {runs_dir}")
        print(f"   Expected directories matching pattern: run_*")
        sys.exit(1)
    
    # Sort by modification time, newest first
    latest_run = max(run_dirs, key=lambda p: p.stat().st_mtime)
    
    return latest_run.name


def main():
    parser = argparse.ArgumentParser(description="Build metrics for a Track A run")
    parser.add_argument(
        "--run-id",
        type=str,
        required=False,
        help="Run ID (e.g., run_20251212_162025). If not provided, uses latest run."
    )
    parser.add_argument(
        "--runs-dir",
        type=str,
        default=None,
        help="Runs directory (default: auto-detect as scratch/data/runs)"
    )
    parser.add_argument(
        "--data-dir",
        type=str,
        default=None,
        help="Data directory (default: auto-detect from script location). Deprecated, use --runs-dir."
    )
    parser.add_argument(
        "--latest",
        action="store_true",
        default=False,
        help="Explicitly select latest run (default behavior when --run-id not provided)"
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        default=False,
        help="Reduce output verbosity"
    )
    
    args = parser.parse_args()
    
    # Determine runs directory
    if args.runs_dir:
        runs_dir = Path(args.runs_dir)
    elif args.data_dir:
        runs_dir = Path(args.data_dir) / "runs"
    else:
        # Auto-detect: script is in scratch/quants-lab/scripts/
        script_dir = Path(__file__).parent
        runs_dir = script_dir.parent.parent / "data" / "runs"
    
    # Determine run ID
    if args.run_id:
        run_id = args.run_id
        if not args.quiet:
            print(f"📌 Using explicit run: {run_id}")
    else:
        run_id = find_latest_run(runs_dir)
        if not args.quiet:
            print(f"🔍 Auto-selected latest run: {run_id}")
    
    run_dir = runs_dir / run_id
    
    # Validate run directory exists
    if not run_dir.exists():
        print(f"❌ Run directory not found: {run_dir}")
        sys.exit(1)
    
    if not args.quiet:
        print(f"📊 Building metrics for {run_id}")
        print(f"📁 Run directory: {run_dir}")
    
    
    try:
        # First, ensure basic aggregation (generates episode_metrics.jsonl)
        ep_metrics_path, _ = aggregate_run_metrics(run_dir)
        if not args.quiet:
            print(f"✅ Episode Metrics: {ep_metrics_path}")

        # Build ROI-aware metrics
        metrics = build_run_metrics(run_dir)
        
        # Write to metrics_summary.json
        summary_path = run_dir / "metrics_summary.json"
        with open(summary_path, 'w') as f:
            json.dump(metrics, f, indent=2)
        
        if not args.quiet:
            print(f"✅ Summary: {summary_path}")
        
        # Print summary preview
        if not args.quiet and "error" not in metrics:
            print(f"\n📈 Summary Preview:")
            print(f"  Total Episodes: {metrics['totals']['episodes_total']}")
            print(f"  Success: {metrics['totals']['episodes_success']}")
            print(f"  Failure: {metrics['totals']['episodes_failed']}")
            print(f"  Total PnL: ${metrics['totals']['total_pnl_usd']:.2f}")
            print(f"  Avg Latency: {metrics['performance']['avg_latency_ms']:.2f}ms")
        else:
            # In quiet mode, just print the path
            print(f"{summary_path}")
        
        sys.exit(0)
        
    except Exception as e:
        print(f"❌ Failed to build metrics: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
