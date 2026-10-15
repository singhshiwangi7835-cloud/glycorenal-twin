"""Loads the editable clinical config: config/clinical_rules.yaml and config/alerts.yaml.

Values are cached; restart the API after editing the YAML files.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"


@lru_cache
def clinical_rules() -> dict:
    with open(CONFIG_DIR / "clinical_rules.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


@lru_cache
def alert_rules() -> dict:
    with open(CONFIG_DIR / "alerts.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)
