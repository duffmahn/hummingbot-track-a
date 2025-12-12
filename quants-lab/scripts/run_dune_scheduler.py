#!/usr/bin/env python3
"""
Dune Scheduler Daemon

Runs the Dune scheduler in the background to refresh cache entries.

Usage:
    python3 scripts/run_dune_scheduler.py [--interval 60] [--workers 3]
"""

import sys
import argparse
import logging
from pathlib import Path

# Add quants-lab to path
QUANTS_LAB_DIR = Path(__file__).parent.parent
sys.path.append(str(QUANTS_LAB_DIR))

from lib.dune_scheduler import DuneScheduler

def main():
    parser = argparse.ArgumentParser(description="Run Dune scheduler daemon")
    parser.add_argument("--interval", type=int, default=60, help="Tick interval in seconds (default: 60)")
    parser.add_argument("--workers", type=int, default=3, help="Max concurrent workers (default: 3)")
    parser.add_argument("--pool-cap", type=int, default=3, help="Max active pools to track (default: 3)")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    parser.add_argument("--once", action="store_true", help="Run single tick and exit (for testing)")
    
    args = parser.parse_args()
    
    # Setup logging
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format='[%(asctime)s] %(levelname)s:%(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    logger = logging.getLogger("DuneSchedulerDaemon")
    
    # Create scheduler
    scheduler = DuneScheduler(
        max_workers=args.workers,
        active_pool_cap=args.pool_cap,
        tick_interval_s=args.interval
    )
    
    if args.once:
        logger.info("Running single tick...")
        stats = scheduler.tick()
        logger.info(f"Tick complete: {stats}")
        sys.exit(0)
    else:
        logger.info("Starting scheduler daemon...")
        logger.info(f"Interval: {args.interval}s, Workers: {args.workers}, Pool cap: {args.pool_cap}")
        try:
            scheduler.run_forever()
        except KeyboardInterrupt:
            logger.info("Shutting down...")
            sys.exit(0)

if __name__ == "__main__":
    main()
