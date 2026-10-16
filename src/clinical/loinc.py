"""LOINC lookup from data/reference/loinc_map.csv (+ loinc_aliases.csv for other codes in use).

variable  <-> LOINC code <-> standard unit. Hospitals and Synthea sometimes use different codes
for the same test (e.g. 38483-4 creatinine in blood); aliases map those onto our variables.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import pandas as pd

REF = Path(__file__).resolve().parents[2] / "data" / "reference"


@lru_cache
def table() -> pd.DataFrame:
    return pd.read_csv(REF / "loinc_map.csv", dtype=str).set_index("variable")


@lru_cache
def _aliases() -> dict[str, str]:
    a = pd.read_csv(REF / "loinc_aliases.csv", dtype=str).fillna("")
    return {c: v for c, v in zip(a["alias_code"], a["variable"])}


@lru_cache(maxsize=None)
def code(variable: str) -> str:
    return table().loc[variable, "loinc_code"]


@lru_cache(maxsize=None)
def unit(variable: str) -> str:
    return table().loc[variable, "unit"]


@lru_cache(maxsize=None)
def display(variable: str) -> str:
    return table().loc[variable, "display_name"]


@lru_cache(maxsize=None)
def variable_for(loinc_code: str) -> str | None:
    """Our variable name for a LOINC code (main map first, then aliases); None if unknown."""
    t = table()
    hit = t.index[t["loinc_code"] == loinc_code]
    if len(hit):
        return hit[0]
    return _aliases().get(loinc_code) or None


def code_to_variable() -> dict[str, str]:
    return {c: v for v, c in table()["loinc_code"].items()}
