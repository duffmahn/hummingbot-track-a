"""
Shared path resolution utilities for consistent artifact directory handling.
"""
import os
from pathlib import Path
from typing import Optional


def resolve_base_dir(env_var_name: Optional[str] = None) -> Path:
    """
    Resolve the base directory for artifacts with consistent logic.
    
    Priority:
    1. Environment variable (BASE_DIR or ARTIFACTS_BASE_DIR)
    2. File-relative default (.../scratch/data)
    
    Args:
        env_var_name: Optional specific env var to check first
    
    Returns:
        Absolute Path to base directory
    """
    # Check environment variables
    env_base = None
    if env_var_name:
        env_base = os.environ.get(env_var_name)
    
    if not env_base:
        env_base = os.environ.get("BASE_DIR") or os.environ.get("ARTIFACTS_BASE_DIR")
    
    if env_base:
        return Path(env_base).expanduser().resolve()
    
    # Default: resolve relative to this file's location
    # path_utils.py is at .../scratch/quants-lab/lib/path_utils.py
    # parents[2] = .../scratch
    return Path(__file__).resolve().parents[2] / "data"
