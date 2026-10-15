"""KDIGO CKD staging (GFR category x albuminuria category) and heat-map risk colour.

GFR categories (mL/min/1.73m^2): G1 >=90, G2 60-89, G3a 45-59, G3b 30-44, G4 15-29, G5 <15
Albuminuria (UACR, mg/g):       A1 <30,  A2 30-300, A3 >300
Cut-offs, the risk grid and colours come from config/clinical_rules.yaml -> kdigo.
"""

from __future__ import annotations

from src.clinical.rules import clinical_rules

G_ORDER = ["G1", "G2", "G3a", "G3b", "G4", "G5"]
A_ORDER = ["A1", "A2", "A3"]

RISK_COLOUR_NAME = {"low": "green", "moderate": "yellow", "high": "orange", "very_high": "red"}


def _cfg() -> dict:
    return clinical_rules()["kdigo"]


def gfr_category(egfr: float) -> str:
    for g in G_ORDER:  # checked from G1 down; each value is the category's lower bound
        if egfr >= _cfg()["gfr_categories"][g]:
            return g
    return "G5"


def albuminuria_category(uacr_mg_g: float) -> str:
    a = _cfg()["albuminuria_categories"]
    if uacr_mg_g < a["A2_from"]:
        return "A1"
    if uacr_mg_g <= a["A3_above"]:
        return "A2"
    return "A3"


def kdigo_stage(egfr: float, uacr_mg_g: float) -> dict:
    g = gfr_category(egfr)
    a = albuminuria_category(uacr_mg_g)
    risk = _cfg()["risk_grid"][g][A_ORDER.index(a)]
    return {
        "g_stage": g,
        "a_stage": a,
        "stage": f"{g}-{a}",
        "risk": risk,
        "colour": RISK_COLOUR_NAME[risk],
        "colour_hex": _cfg()["colours"][risk],
        # CKD is present if eGFR < 60 or albuminuria >= A2
        "has_ckd": g not in ("G1", "G2") or a != "A1",
    }


def stage_worsened(old: dict, new: dict) -> bool:
    """True if either the G or the A category moved to a worse level."""
    return (
        G_ORDER.index(new["g_stage"]) > G_ORDER.index(old["g_stage"])
        or A_ORDER.index(new["a_stage"]) > A_ORDER.index(old["a_stage"])
    )
