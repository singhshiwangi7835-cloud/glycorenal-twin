"""Unit conversions, so every value is stored in one standard unit (see data/reference/loinc_map.csv).

Standard units: glucose mg/dL, creatinine mg/dL, HbA1c %, UACR mg/g, potassium mmol/L.
"""

from __future__ import annotations

GLUCOSE_MMOL_TO_MG = 18.016          # mg/dL = mmol/L x 18.016
CREATININE_UMOL_PER_MG = 88.42       # umol/L = mg/dL x 88.42
UACR_MG_MMOL_TO_MG_G = 8.84          # mg/g = mg/mmol x 8.84


def glucose_mmol_to_mg(mmol_l: float) -> float:
    return round(mmol_l * GLUCOSE_MMOL_TO_MG, 1)


def glucose_mg_to_mmol(mg_dl: float) -> float:
    return round(mg_dl / GLUCOSE_MMOL_TO_MG, 2)


def creatinine_umol_to_mg(umol_l: float) -> float:
    return round(umol_l / CREATININE_UMOL_PER_MG, 3)


def creatinine_mg_to_umol(mg_dl: float) -> float:
    return round(mg_dl * CREATININE_UMOL_PER_MG, 1)


def hba1c_mmol_mol_to_pct(mmol_mol: float) -> float:
    """IFCC (mmol/mol) to NGSP (%): % = 0.09148 x mmol/mol + 2.152."""
    return round(0.09148 * mmol_mol + 2.152, 1)


def hba1c_pct_to_mmol_mol(pct: float) -> float:
    return round((pct - 2.152) / 0.09148, 0)


def uacr_mg_mmol_to_mg_g(mg_mmol: float) -> float:
    return round(mg_mmol * UACR_MG_MMOL_TO_MG_G, 1)


def _clean(unit: str) -> str:
    return unit.strip().lower().replace(" ", "").replace("µ", "u").replace("μ", "u")


# (variable, unit as written) -> converter to the standard unit
_CONVERTERS = {
    ("glucose", "mmol/l"): glucose_mmol_to_mg,
    ("creatinine", "umol/l"): creatinine_umol_to_mg,
    ("hba1c", "mmol/mol"): hba1c_mmol_mol_to_pct,
    ("uacr", "mg/mmol"): uacr_mg_mmol_to_mg_g,
    ("weight", "lb"): lambda v: round(v * 0.45359237, 1),
}


def to_standard(variable: str, value: float, unit: str, standard_unit: str) -> float:
    """Convert `value` in `unit` to the variable's standard unit. Raises if unknown."""
    if _clean(unit) == _clean(standard_unit) or not unit:
        return float(value)
    conv = _CONVERTERS.get((variable, _clean(unit)))
    if conv is None:
        raise ValueError(f"don't know how to convert {variable} from {unit!r} to {standard_unit!r}")
    return conv(float(value))
