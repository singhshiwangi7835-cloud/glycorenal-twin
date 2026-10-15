"""KDIGO CKD staging (GFR category x albuminuria category) and risk colour.

GFR categories (mL/min/1.73m^2): G1 >=90, G2 60-89, G3a 45-59, G3b 30-44, G4 15-29, G5 <15
Albuminuria (UACR, mg/g):       A1 <30,  A2 30-300, A3 >300
Risk heat map follows the KDIGO prognosis grid (green / yellow / orange / red).
"""

from __future__ import annotations

G_ORDER = ["G1", "G2", "G3a", "G3b", "G4", "G5"]
A_ORDER = ["A1", "A2", "A3"]

# KDIGO prognosis heat map: rows = G stage, cols = A stage
_RISK_GRID = {
    "G1": ["low", "moderate", "high"],
    "G2": ["low", "moderate", "high"],
    "G3a": ["moderate", "high", "very_high"],
    "G3b": ["high", "very_high", "very_high"],
    "G4": ["very_high", "very_high", "very_high"],
    "G5": ["very_high", "very_high", "very_high"],
}

RISK_COLOUR = {
    "low": "green",
    "moderate": "yellow",
    "high": "orange",
    "very_high": "red",
}


def gfr_category(egfr: float) -> str:
    if egfr >= 90:
        return "G1"
    if egfr >= 60:
        return "G2"
    if egfr >= 45:
        return "G3a"
    if egfr >= 30:
        return "G3b"
    if egfr >= 15:
        return "G4"
    return "G5"


def albuminuria_category(uacr_mg_g: float) -> str:
    if uacr_mg_g < 30:
        return "A1"
    if uacr_mg_g <= 300:
        return "A2"
    return "A3"


def kdigo_stage(egfr: float, uacr_mg_g: float) -> dict:
    g = gfr_category(egfr)
    a = albuminuria_category(uacr_mg_g)
    risk = _RISK_GRID[g][A_ORDER.index(a)]
    return {
        "g_stage": g,
        "a_stage": a,
        "stage": f"{g}-{a}",
        "risk": risk,
        "colour": RISK_COLOUR[risk],
        # CKD is present if eGFR < 60 or albuminuria >= A2
        "has_ckd": g not in ("G1", "G2") or a != "A1",
    }


def stage_worsened(old: dict, new: dict) -> bool:
    """True if either the G or the A category moved to a worse level."""
    return (
        G_ORDER.index(new["g_stage"]) > G_ORDER.index(old["g_stage"])
        or A_ORDER.index(new["a_stage"]) > A_ORDER.index(old["a_stage"])
    )
