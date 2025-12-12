#!/usr/bin/env python3
"""
Write failure artifacts when agent/harness crashes before normal artifact writing.
Usage: write_failure_artifact.py --run-id RUN --episode-id EP --stage agent|harness --error "msg" [--exec-mode mock] [--config-hash hash] [--agent-version v1]
"""

import sys
import argparse
from pathlib import Path

# Add quants-lab to path
QUANTS_LAB_DIR = Path(__file__).parent.parent
sys.path.append(str(QUANTS_LAB_DIR))

from lib.artifacts import EpisodeArtifacts
from lib.schemas import EpisodeMetadata, EpisodeResult
import datetime
import os

def main():
    parser = argparse.ArgumentParser(description="Write failure artifacts for crashed episodes")
    parser.add_argument("--run-id", required=True, help="Run ID")
    parser.add_argument("--episode-id", required=True, help="Episode ID")
    parser.add_argument("--stage", required=True, choices=["agent", "harness"], help="Which stage failed")
    parser.add_argument("--error", required=True, help="Error message")
    parser.add_argument("--exec-mode", default="unknown", help="Execution mode")
    parser.add_argument("--config-hash", default="unknown", help="Config hash")
    parser.add_argument("--agent-version", default="unknown", help="Agent version")
    parser.add_argument("--exit-code", type=int, default=1, help="Exit code")
    
    args = parser.parse_args()
    
    # Create artifacts manager
    artifacts = EpisodeArtifacts(
        run_id=args.run_id,
        episode_id=args.episode_id,
        base_dir=str(Path(__file__).parent.parent.parent / "data")
    )
    
    # Ensure directory exists
    artifacts.ensure_directories()
    
    # Create metadata
    metadata = EpisodeMetadata(
        episode_id=args.episode_id,
        run_id=args.run_id,
        config_hash=args.config_hash,
        agent_version=args.agent_version,
        exec_mode=args.exec_mode,
        notes=f"Failed at {args.stage} stage"
    )
    
    # Create result
    result = EpisodeResult(
        episode_id=args.episode_id,
        run_id=args.run_id,
        status="failed",
        exec_mode=args.exec_mode,
        error=args.error
    )
    
    # Write artifacts
    artifacts.write_metadata(metadata)
    artifacts.write_result(result)
    artifacts.write_failure(
        error=args.error,
        context={
            "stage": args.stage,
            "exit_code": args.exit_code,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()
        }
    )
    
    print(f"✅ Failure artifacts written to {artifacts.episode_dir}")

if __name__ == "__main__":
    main()
