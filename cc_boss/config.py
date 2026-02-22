"""Configuration loaded from YAML or CLI args."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class Config:
    repo_path: str = "."
    port: int = 8080
    max_workers: int = 5
    db_path: str = "cc_boss.db"
    progress_file: str = "PROGRESS.md"
    claude_cmd: str = "claude"

    @classmethod
    def load(cls, path: str | Path | None = None) -> Config:
        if path and Path(path).exists():
            with open(path) as f:
                data = yaml.safe_load(f) or {}
            return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
        return cls()

    @classmethod
    def from_cli(cls, **overrides) -> Config:
        cfg = cls.load(overrides.pop("config", None))
        for k, v in overrides.items():
            if v is not None and hasattr(cfg, k):
                setattr(cfg, k, v)
        return cfg
