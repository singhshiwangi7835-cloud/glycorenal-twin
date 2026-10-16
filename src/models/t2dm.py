"""Track A: type 2 diabetes short-term glucose and 3-month HbA1c.

forecast_glucose(series)  -> glucose in 30 and 60 min, hypo / hyper warnings
forecast_hba1c(features)  -> HbA1c in 3 months with an 80% range

Glucose series: 5-minute rows with time, glucose, and optionally carbs_g and activity (steps).
Warning thresholds come from config/alerts.yaml -> glucose.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.clinical.rules import alert_rules
from src.models.features import glucose_frame
from src.models.registry import load, version

HYPO_WARN_MARGIN = 10  # warn when the forecast is within 10 mg/dL of the hypo threshold


def forecast_glucose(series: pd.DataFrame) -> dict:
    """Forecast from the most recent reading. Needs at least 30 minutes of CGM history."""
    s = series.copy()
    if "activity" not in s and "steps" in s:
        s = s.rename(columns={"steps": "activity"})
    s = s.dropna(subset=["glucose"]).sort_values("time").tail(25)  # last 2 h + now
    if len(s) < 7:
        return {"available": False, "reason": "need at least 30 minutes of CGM readings"}
    b = load("glucose_forecast")
    row = glucose_frame(s).iloc[[-1]][b["features"]]
    g30 = float(b["models"]["30"].predict(row)[0])
    g60 = float(b["models"]["60"].predict(row)[0])
    g = alert_rules()["glucose"]
    low, high = g["low_warning_below"], g["high_warning_above"]
    now = float(s["glucose"].iloc[-1])
    # Safety net: the model can miss a steady fall it never saw in training, so a hypo warning
    # also fires if glucose is already low or the last-15-minute trend crosses the threshold.
    trend_30 = now + (now - float(s["glucose"].iloc[-4])) / 15 * 30 if len(s) >= 4 else now
    reasons = []
    if now < low:
        reasons.append("glucose already below threshold")
    if trend_30 < low + HYPO_WARN_MARGIN:
        reasons.append("falling trend")
    if g30 < low + HYPO_WARN_MARGIN:
        reasons.append("model forecast")
    return {
        "available": True,
        "now": now,
        "at": str(s["time"].iloc[-1]),
        "plus_30": round(g30), "plus_60": round(g60),
        "trend_30": round(trend_30),
        "hypo_risk_30m": bool(reasons),
        "hypo_reasons": reasons,
        "hyper_risk_60m": g60 > high,
        "model_version": version("glucose_forecast"),
    }


def forecast_hba1c(features: dict) -> dict:
    """features: see src/pipeline/cohort.HBA1C_FEATURES (missing values allowed)."""
    b = load("hba1c_forecast")
    X = pd.DataFrame([{n: features.get(n, np.nan) for n in b["features"]}], dtype=float)
    pred = float(b["model"].predict(X)[0])
    lo, hi = b["residual_q10_q90"]
    return {"hba1c_3m": round(pred, 1), "range_80pct": [round(pred + lo, 1), round(pred + hi, 1)],
            "model_version": version("hba1c_forecast")}
