from __future__ import annotations

from typing import Dict, Optional
from pydantic import BaseModel, Field
from pathlib import Path
from datetime import datetime, timezone
import json, os

class ParameterDistribution(BaseModel):
    name: str
    mean: float
    std_dev: float
    min_val: float
    max_val: float
    sample_count: int = 0

class RegimeState(BaseModel):
    regime: str
    params: Dict[str, ParameterDistribution] = Field(default_factory=dict)
    last_updated: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class LearningState(BaseModel):
    version: str = "1.0"
    regimes: Dict[str, RegimeState] = Field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> "LearningState":
        if path.exists():
            try:
                with open(path, "r") as f:
                    return cls(**json.load(f))
            except Exception as e:
                print(f"Warning: Failed to load learning state: {e}")
        return cls()

    def save(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)

        temp_path = path.with_suffix(path.suffix + ".tmp")
        payload = self.model_dump_json(indent=2)

        with open(temp_path, "w") as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())  # improves durability on crash/power loss

        os.replace(temp_path, path)  # safer than rename across platforms
