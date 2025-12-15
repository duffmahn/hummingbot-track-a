import sys
import os
import argparse
from pathlib import Path

# Add parent directory (quants-lab) to path
QUANTS_LAB_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(QUANTS_LAB_DIR))

def main():
    parser = argparse.ArgumentParser(description="Run a single episode")
    parser.add_argument("--episode-id", type=str, required=True, help="Episode ID to execute")
    args = parser.parse_args()

    # Import harness
    try:
        from lib.agent_harness import AgentHarness
    except ImportError as e:
        print(f"❌ Failed to import agent_harness: {e}")
        sys.exit(1)

    # Get environment variables
    run_id = os.environ.get("RUN_ID")
    episode_id = args.episode_id
    
    if not run_id:
        print("❌ RUN_ID environment variable not set")
        sys.exit(1)
    
    print(f"📂 RUN_ID: {run_id}")
    print(f"🆔 EPISODE_ID: {episode_id}")
    
    # Instantiate and Run
    try:
        harness = AgentHarness()
        success = harness.run_episode(episode_id)
        
        sys.exit(0 if success else 1)
        
    except Exception as e:
        print(f"❌ Harness Exception: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
