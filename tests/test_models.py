"""Sanity tests for the trained models (direction of effects, valid outputs)."""

import math
from pathlib import Path

import pandas as pd
import pytest

from src.models import dkd, t2dm

ROOT = Path(__file__).resolve().parents[1]

# Ramesh-like patient: kidneys still healthy-ish (eGFR 63, UACR 22), poor control
BASE = {
    "age": 54, "male": 1, "dm_duration_yrs": 9, "hba1c": 8.4, "hba1c_change_1y": 0.3,
    "tir_pct": 52, "sbp": 142, "bmi": 28.1, "egfr": 63, "egfr_slope_1y": -3,
    "log_uacr": math.log(22), "smoker": 0, "family_history": 1, "hypertension": 1,
    "adherence": 0.6, "on_sglt2i": 0, "on_glp1ra": 0, "on_acei_arb": 1, "on_finerenone": 0,
    "on_insulin": 0, "on_sulfonylurea": 0,
}


def test_dkd_onset_output():
    r = dkd.predict_dkd(BASE)
    assert r["kind"] == "onset"
    assert 0 <= r["risk_3y"] <= 1
    assert r["band"] in ("low", "moderate", "high", "very_high")
    assert r["model_version"].startswith("dkd_onset@")
    assert len(r["drivers"]) == 5


def test_dkd_uses_progression_model_when_dkd_present():
    r = dkd.predict_dkd({**BASE, "log_uacr": math.log(85)})
    assert r["kind"] == "progression"


def test_dkd_risk_rises_with_worse_control():
    good = dkd.predict_dkd({**BASE, "hba1c": 6.8, "tir_pct": 75, "sbp": 122})["risk_3y"]
    bad = dkd.predict_dkd({**BASE, "hba1c": 10.5, "tir_pct": 30, "sbp": 165})["risk_3y"]
    assert bad > good


def test_risk_bands_follow_yaml():
    assert dkd.risk_band(0.05) == "low"
    assert dkd.risk_band(0.30) == "high"
    assert dkd.risk_band(0.60) == "very_high"


def test_dkd_current_nhanes_model():
    r = dkd.predict_dkd_current({"age": 54, "male": 1, "hba1c": 8.4, "sbp": 142, "bmi": 28})
    assert 0 <= r["probability"] <= 1


def test_hba1c_forecast_new_drug_lowers_hba1c():
    f = {"hba1c": 8.4, "hba1c_change_3m": 0.1, "gmi_pct": 8.0, "tir_pct": 52, "adherence": 0.6,
         "bmi": 28.1, "egfr": 63, "on_metformin": 1}
    same = t2dm.forecast_hba1c({**f, "new_glucose_drug": 0})
    new = t2dm.forecast_hba1c({**f, "new_glucose_drug": 1})
    assert new["hba1c_3m"] < same["hba1c_3m"]
    lo, hi = same["range_80pct"]
    assert lo <= same["hba1c_3m"] <= hi


def test_glucose_forecast_on_demo_trace():
    path = ROOT / "data" / "synthetic" / "cgm" / "IND-0042.csv"
    if not path.exists():
        pytest.skip("run scripts/build_synthetic_cohort.py first")
    s = pd.read_csv(path, parse_dates=["time"]).iloc[:300]
    r = t2dm.forecast_glucose(s)
    assert r["available"] and 40 <= r["plus_30"] <= 400 and 40 <= r["plus_60"] <= 400


def test_glucose_forecast_falling_trace_warns_hypo():
    times = pd.date_range("2026-01-01 08:00", periods=25, freq="5min")
    falling = pd.DataFrame({"time": times, "glucose": [160 - 4 * i for i in range(25)],
                            "carbs_g": 0, "activity": 0})
    r = t2dm.forecast_glucose(falling)
    assert r["hypo_risk_30m"]  # safety net must fire even if the model expects a rebound
    assert "glucose already below threshold" in r["hypo_reasons"]


def test_falling_trend_warns_before_glucose_is_low():
    times = pd.date_range("2026-01-01 08:00", periods=25, freq="5min")
    g = [140] * 19 + [130, 122, 114, 106, 98, 92]  # dropping ~1.5 mg/dL per minute, now 92
    r = t2dm.forecast_glucose(pd.DataFrame({"time": times, "glucose": g}))
    assert r["hypo_risk_30m"] and "falling trend" in r["hypo_reasons"]


def test_stable_glucose_no_hypo_warning():
    times = pd.date_range("2026-01-01 08:00", periods=25, freq="5min")
    r = t2dm.forecast_glucose(pd.DataFrame({"time": times, "glucose": [130] * 25}))
    assert not r["hypo_risk_30m"]


def test_glucose_forecast_needs_history():
    s = pd.DataFrame({"time": pd.date_range("2026-01-01", periods=3, freq="5min"),
                      "glucose": [120, 121, 122]})
    assert t2dm.forecast_glucose(s)["available"] is False
