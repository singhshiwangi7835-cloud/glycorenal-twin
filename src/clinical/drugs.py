"""Drug name -> drug class, from data/reference/drug_classes.csv (editable by Shiwangi).

A name matches when it contains one of the listed drug words, so combination products
("HYDROCHLOROTHIAZIDE; LOSARTAN") get every class they contain. ACEi and ARB also count as
the combined class `acei_arb` used by the eligibility rules.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import pandas as pd

CSV = Path(__file__).resolve().parents[2] / "data" / "reference" / "drug_classes.csv"


@lru_cache
def _table() -> list[tuple[str, str]]:
    df = pd.read_csv(CSV)
    return [(d.lower().strip(), c.strip()) for d, c in zip(df["drug"], df["drug_class"])]


def classify(drug_name: str) -> set[str]:
    name = str(drug_name).lower()
    classes = {c for word, c in _table() if word in name}
    if classes & {"acei", "arb"}:
        classes.add("acei_arb")
    return classes


def class_flags(drug_names: list[str], classes=("metformin", "sglt2i", "glp1ra", "dpp4i",
                                                  "sulfonylurea", "insulin", "acei_arb",
                                                  "finerenone", "statin")) -> dict[str, int]:
    found = set().union(*(classify(d) for d in drug_names)) if drug_names else set()
    return {f"on_{c}": int(c in found) for c in classes}
