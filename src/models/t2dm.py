"""Track A: type 2 diabetes short-term glucose and 3-month HbA1c.

forecast_glucose(series)  -> glucose in 30 and 60 min, hypo / hyper warnings
forecast_spike(series)    -> probability of a spike above the line within 90 min (needs days of history
                             for the habit features; works with less, just less personal)
forecast_hba1c(features)  -> HbA1c in 3 months with an 80% range

Glucose series: 5-minute rows with time, glucose, and optionally carbs_g and activity (steps).
Warning thresholds come from config/alerts.yaml -> glucose.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.clinical.rules import alert_rules
from src.models.features import glucose_frame, habit_features
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


def forecast_spike(series: pd.DataFrame) -> dict:
    """Spike early warning from up to 7 days of CGM + meals (alerts.yaml -> spike_forecast)."""
    cfg = alert_rules()["spike_forecast"]
    horizon, line = int(cfg["horizon_minutes"]), float(cfg["spike_above"])
    s = series.dropna(subset=["glucose"])
    if "activity" not in s and "steps" in s:
        s = s.rename(columns={"steps": "activity"})
    if len(s) < 7:
        return {"available": False, "reason": "need at least 30 minutes of CGM readings"}
    b = load("glucose_spike_90m")
    s = s.sort_values("time")
    # recent pattern: the last 2 h of readings, one row per reading (as forecast_glucose; in demo mode
    # readings arrive every few seconds, each standing for 5 minutes); habits: previous 7 days by clock time
    last = glucose_frame(s.tail(25)).iloc[[-1]].copy()
    for k, v in habit_features(s, s["time"].iloc[-1], horizon, line).items():
        last[k] = v
    now = float(last["g_now"].iloc[0])
    out = {"available": True, "now": round(now), "at": str(last["time"].iloc[0]), "horizon_minutes": horizon,
           "spike_above": line, "model_version": version("glucose_spike_90m")}
    if now >= line:
        return {**out, "probability": None, "spike_likely": False, "already_high": True, "reasons": []}
    p = float(b["model"].predict_proba(last[b["features"]])[0, 1])
    r = last.iloc[0]
    reasons = []
    if r["carbs_2h"] > 0:
        reasons.append(f"meal of {r['carbs_2h']:.0f} g carbs in the last 2 h")
    if pd.notna(r["habit_carbs_next_90m"]) and r["habit_carbs_next_90m"] >= 30:
        reasons.append(f"usually eats about {r['habit_carbs_next_90m']:.0f} g carbs in the next 90 min")
    if pd.notna(r["habit_spike_rate_next_90m"]) and r["habit_spike_rate_next_90m"] >= 0.3:
        reasons.append(f"went above {line:.0f} at this time on {r['habit_spike_rate_next_90m']:.0%} of recent days")
    if r["slope_30"] >= 1:
        reasons.append(f"rising {r['slope_30'] * 30:.0f} mg/dL in 30 min")
    return {**out, "probability": round(p, 2), "spike_likely": p >= float(cfg["alert_probability_at_least"]),
            "already_high": False, "reasons": reasons,
            "habit": {"carbs_next_90m": None if pd.isna(r["habit_carbs_next_90m"]) else round(float(r["habit_carbs_next_90m"])),
                      "peak_next_90m": None if pd.isna(r["habit_peak_next_90m"]) else round(float(r["habit_peak_next_90m"]))}}


def forecast_hba1c(features: dict) -> dict:
    """features: see src/pipeline/cohort.HBA1C_FEATURES (missing values allowed)."""
    b = load("hba1c_forecast")
    X = pd.DataFrame([{n: features.get(n, np.nan) for n in b["features"]}], dtype=float)
    pred = float(b["model"].predict(X)[0])
    lo, hi = b["residual_q10_q90"]
    return {"hba1c_3m": round(pred, 1), "range_80pct": [round(pred + lo, 1), round(pred + hi, 1)],
            "model_version": version("hba1c_forecast")}
