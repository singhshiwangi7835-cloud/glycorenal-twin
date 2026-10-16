"""Loads trained model bundles from models/*.joblib once and keeps them in memory.

If a model file is missing, the error message says which command trains it.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import joblib

MODELS_DIR = Path(__file__).resolve().parents[2] / "models"


class ModelMissing(RuntimeError):
    pass


@lru_cache
def load(name: str) -> dict:
    path = MODELS_DIR / f"{name}.joblib"
    if not path.exists():
        raise ModelMissing(f"{path.name} not found. Run: python scripts/train_models.py")
    return joblib.load(path)


def version(name: str) -> str:
    b = load(name)
    return f"{name}@{b.get('version', 'unknown')}"
