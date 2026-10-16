"""Track B: diabetic kidney disease (DKD) risk in 3 years.

`predict_dkd(features)` picks the right model:
  - kidneys healthy now (eGFR >= 60 and UACR < 30)  -> dkd_onset
  - DKD now                                         -> dkd_progression
and returns the calibrated risk, a risk band (thresholds in clinical_rules.yaml -> risk_bands),
the model version and the factors pushing the risk up or down (XGBoost SHAP contributions).

Feature names: see src/pipeline/cohort.DKD_FEATURES. Missing optional values are allowed
(XGBoost treats them as unknown).
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import xgboost as xgb

from src.clinical.rules import clinical_rules
from src.models.registry import load, version

LABELS = {
    "age": "Age", "male": "Male sex", "dm_duration_yrs": "Years with diabetes", "hba1c": "HbA1c",
    "hba1c_change_1y": "HbA1c change over 1 year", "tir_pct": "Time in range", "sbp": "Systolic BP",
    "bmi": "BMI", "egfr": "eGFR", "egfr_slope_1y": "eGFR change over 1 year",
    "log_uacr": "Albuminuria (UACR)", "smoker": "Smoking", "family_history": "Family history of CKD",
    "hypertension": "Hypertension", "adherence": "Medicine adherence", "on_sglt2i": "On SGLT2i",
    "on_glp1ra": "On GLP-1 RA", "on_acei_arb": "On ACEi/ARB", "on_finerenone": "On finerenone",
    "on_insulin": "On insulin", "on_sulfonylurea": "On sulfonylurea",
}


def risk_band(p: float) -> str:
    b = clinical_rules()["risk_bands"]
    if p < b["low_below"]:
        return "low"
    if p < b["moderate_below"]:
        return "moderate"
    if p < b["high_below"]:
        return "high"
    return "very_high"


def has_dkd_now(features: dict) -> bool:
    return features["egfr"] < 60 or math.exp(features["log_uacr"]) >= 30


def _frame(features: dict, names: list[str]) -> pd.DataFrame:
    return pd.DataFrame([{n: features.get(n, np.nan) for n in names}], dtype=float)


def predict_dkd(features: dict, top: int = 5) -> dict:
    kind = "progression" if has_dkd_now(features) else "onset"
    b = load(f"dkd_{kind}")
    X = _frame(features, b["features"])
    raw = float(b["model"].predict_proba(X)[0, 1])
    risk = float(b["calibrator"].predict([raw])[0])

    contrib = b["model"].get_booster().predict(xgb.DMatrix(X), pred_contribs=True)[0][:-1]
    drivers = sorted(
        [{"feature": f, "label": LABELS.get(f, f), "value": features.get(f),
          "contribution": round(float(c), 3)} for f, c in zip(b["features"], contrib)],
        key=lambda d: -abs(d["contribution"]))[:top]
    return {
        "kind": kind,
        "outcome": ("DKD within 3 years" if kind == "onset"
                    else "kidney disease worsening within 3 years"),
        "risk_3y": round(risk, 3),
        "band": risk_band(risk),
        "model_version": version(f"dkd_{kind}"),
        "drivers": drivers,  # contribution in log-odds: > 0 raises risk, < 0 lowers it
    }


def predict_dkd_current(features: dict) -> dict:
    """Supporting NHANES model: probability of having DKD now from non-kidney data."""
    b = load("dkd_current")
    p = float(b["model"].predict_proba(_frame(features, b["features"]))[0, 1])
    return {"probability": round(p, 3), "model_version": version("dkd_current")}
