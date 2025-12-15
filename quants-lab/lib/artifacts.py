import os
import json
import fcntl
from typing import Any, Optional, Dict
from pydantic import BaseModel
from pathlib import Path

from .schemas import Proposal, EpisodeMetadata, EpisodeResult, RewardBreakdown
from .path_utils import resolve_base_dir

class EpisodeArtifacts:
    """
    Handles immutable episode artifact folder creation and atomic writing of:
    - proposal.json
    - metadata.json
    - timings.json
    - logs.jsonl
    - result.json
    - reward.json
    - failure.json
    """
    
    def __init__(self, run_id: str, episode_id: str, base_dir: Optional[str] = None):
        self.run_id = run_id
        self.episode_id = episode_id
        
        # ✅ Use shared path resolution utility
        if base_dir is None:
            self.base_dir = resolve_base_dir()
        else:
            self.base_dir = Path(base_dir).expanduser().resolve()
        
        # Structure: <base_dir>/runs/<run_id>/episodes/<episode_id>/
        self.episode_dir = str(self.base_dir / "runs" / run_id / "episodes" / episode_id)
        
    def ensure_directories(self):
        """Creates the episode directory if it doesn't exist."""
        os.makedirs(self.episode_dir, exist_ok=True)
        
    def _write_json(self, filename: str, data: Any):
        """Atomic JSON write with strict Pydantic encoding if applicable."""
        filepath = os.path.join(self.episode_dir, filename)
        
        # Convert Pydantic models to dicts
        if isinstance(data, BaseModel):
            content = data.model_dump(mode='json')
        else:
            content = data
            
        # Atomic write pattern: write to tmp, fsync, rename
        tmp_path = filepath + ".tmp"
        with open(tmp_path, 'w') as f:
            json.dump(content, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
            
        os.rename(tmp_path, filepath)

    def write_proposal(self, proposal: Proposal):
        self.ensure_directories()
        self._write_json("proposal.json", proposal)
        
    def write_metadata(self, metadata, merge_existing: bool = True):
        """
        Write metadata.json with optional merge of existing data.
        
        Args:
            metadata: EpisodeMetadata object or dict
            merge_existing: If True, merge with existing metadata (preserves intel_snapshot)
        """
        self.ensure_directories()
        filepath = os.path.join(self.episode_dir, "metadata.json")
        
        # Convert to dict
        if hasattr(metadata, "model_dump"):
            obj = metadata.model_dump()
        elif hasattr(metadata, "dict"):
            obj = metadata.dict()
        else:
            obj = dict(metadata)
        
        # Merge with existing if requested
        if merge_existing and os.path.exists(filepath):
            try:
                with open(filepath, 'r') as f:
                    existing = json.load(f)
                
                # Shallow merge for top-level fields
                merged = {**existing, **obj}
                
                # Deep merge for 'extra' dict
                existing_extra = existing.get("extra") or {}
                new_extra = obj.get("extra") or {}
                merged_extra = self._deep_merge(existing_extra, new_extra)
                merged["extra"] = merged_extra
                
                obj = merged
            except Exception as e:
                # If merge fails, just use new data
                pass
        
        self._write_json("metadata.json", obj)
    
    def _deep_merge(self, dst: Dict[str, Any], src: Dict[str, Any]) -> Dict[str, Any]:
        """Deep merge two dicts, preferring src values"""
        result = dict(dst)
        for k, v in (src or {}).items():
            if isinstance(v, dict) and isinstance(result.get(k), dict):
                result[k] = self._deep_merge(result[k], v)
            else:
                result[k] = v
        return result
        
    def write_result(self, result: EpisodeResult):
        self.ensure_directories()
        self._write_json("result.json", result)
        
    def write_reward(self, reward: RewardBreakdown):
        self.ensure_directories()
        self._write_json("reward.json", reward)
        
    def write_timings(self, timings: Dict[str, float]):
        self.ensure_directories()
        self._write_json("timings.json", timings)

    def write_failure(self, error: str, context: Optional[Dict[str, Any]] = None):
        """Writes failure.json. Should be called on exceptions or failed status."""
        self.ensure_directories()
        data = {
            "error": error,
            "context": context or {}
        }
        self._write_json("failure.json", data)

    def log_event(self, event_name: str, payload: Dict[str, Any]):
        """Append to logs.jsonl using internal locking (simple) or just append."""
        self.ensure_directories()
        filepath = os.path.join(self.episode_dir, "logs.jsonl")
        
        entry = {
            "event": event_name,
            "payload": payload,
            # Could add timestamp here if not in payload
        }
        
        with open(filepath, 'a') as f:
            # Simple flock to prevent interleaved writes if multiple processes (unlikely for strict episode scope but good practice)
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                f.write(json.dumps(entry) + "\n")
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)

