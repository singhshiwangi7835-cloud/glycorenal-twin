"""Personal (progressive) twin: learns the patient's own parameters; more data -> more personal."""

import math
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from src.twin import personal_glucose as pg
from src.twin import personal_kidney as pk
from tests.conftest import login

TRUE = {"peak_minutes": 70, "basal": 160.0, "dawn": 20.0, "carb_sensitivity": 2.2, "activity": 0.5}


def _synthetic_patient(days: int, seed: int = 0):
    """CGM generated FROM the twin's own equations with known parameters (+ sensor noise)."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2026-01-01", periods=days * 288, freq="5min", tz="UTC")
    exc = np.zeros(len(idx))
    for d in range(days):  # one 15-minute walk a day at 18:00 UTC
        i = d * 288 + 216
        exc[i:i + 3] = 25
    df = pd.DataFrame({"glucose": np.nan, "hr": 70 + exc, "exc": exc}, index=idx)
    meals = [{"time": idx[0] + pd.Timedelta(days=d, hours=h), "carbs": float(rng.uniform(40, 110))}
             for d in range(days) for h in (3, 8, 14)]
    df["glucose"] = pg._predict(TRUE, df, meals) + rng.normal(0, 5, len(idx))
    return df, meals


def test_glucose_twin_recovers_the_patients_own_parameters():
    df, meals = _synthetic_patient(10)
    fit = pg._fit(df, meals, 0.0)
    assert fit["peak_minutes"] == 70
    assert abs(fit["carb_sensitivity"] - 2.2) < 0.15
    assert abs(fit["basal"] - 160) < 8
    assert abs(fit["activity"] - 0.5) < 0.2


def test_more_data_moves_the_twin_from_population_to_patient():
    pop = pg.population_params()["carb_sensitivity"]
    df, meals = _synthetic_patient(10, seed=3)
    little = pg._fit(df.iloc[:60], meals, 0.0)      # 5 hours of data
    lots = pg._fit(df, meals, 0.0)                   # 10 days
    assert abs(lots["carb_sensitivity"] - 2.2) < abs(little["carb_sensitivity"] - 2.2)
    assert abs(little["carb_sensitivity"] - pop) < abs(lots["carb_sensitivity"] - pop)


def test_kidney_twin_learns_a_faster_decline_from_results():
    now = datetime(2026, 10, 1, tzinfo=timezone.utc)
    f = {"hba1c": 7.0, "sbp": 125, "log_uacr": math.log(10), "age": 50, "smoker": 0, "bmi": 24, "dm_duration_yrs": 5}

    def state(points):
        return {"features": {"dkd": f, "hba1c": {}},
                "history": {"egfr": [{"time": (now - timedelta(days=365 * y)).isoformat(), "value": v} for y, v in points],
                            "uacr": []}}
    one = pk.build(state([(0, 80)]), now)
    many = pk.build(state([(3, 104), (2, 96), (1, 88), (0, 80)]), now)   # really falling 8 per year
    assert abs(one["slope"] - one["population_slope"]) < 0.5            # one result: population view
    assert many["slope"] < -6                                            # four results: the patient's own decline
    width = lambda k: k["slope_80pct"][1] - k["slope_80pct"][0]  # noqa: E731
    assert width(many) < width(one)                                      # and more certain
    assert many["learning"][-1]["slope"] < many["learning"][0]["slope"]


def test_sglt2i_slows_the_patients_own_decline():
    now = datetime(2026, 10, 1, tzinfo=timezone.utc)
    f = {"hba1c": 8.5, "sbp": 145, "log_uacr": math.log(120), "age": 58, "smoker": 0, "bmi": 27,
         "dm_duration_yrs": 10, "tir_pct": 50}
    st = {"features": {"dkd": f, "hba1c": {"hba1c": 8.5}},
          "history": {"egfr": [{"time": (now - timedelta(days=365 * y)).isoformat(), "value": v}
                               for y, v in [(2, 72), (1, 66), (0, 61)]], "uacr": []}}
    k = pk.build(st, now, options=["sglt2i"])
    assert k["with_options"]["slope"] > k["slope"]           # less negative
    t_now, t_plan = k["projection"]["years_to"]["45"], k["with_options"]["projection"]["years_to"]["45"]
    assert t_plan is None or t_plan > t_now


def test_personal_twin_api_and_permissions(client):
    doc, pat = login(client, "dr.mehta", "doctor123"), login(client, "priya", "patient123")
    r = client.get("/patients/IND-0215/twin/personal", headers=doc).json()
    assert 0 <= r["maturity"]["score"] <= 100
    assert r["glucose"]["available"] and r["glucose"]["accuracy"]["mae"] < 25
    assert r["kidney"]["available"] and r["kidney"]["results_used"] >= 2
    assert client.get("/patients/IND-0215/twin/personal?options=sglt2i", headers=pat).status_code == 403
    assert client.get("/patients/IND-0215/twin/personal?options=steps_plus_2000", headers=pat).status_code == 200
    assert client.get("/patients/IND-0042/twin/personal", headers=pat).status_code == 403


def test_meal_what_if_on_the_patients_twin(client):
    pat = login(client, "priya", "patient123")
    rice = client.post("/patients/IND-0215/twin/personal/what-if", headers=pat,
                       json={"items": [{"food": "Steamed white rice", "servings": 2}]}).json()
    small = client.post("/patients/IND-0215/twin/personal/what-if", headers=pat,
                        json={"items": [{"food": "Steamed white rice", "servings": 0.5}]}).json()
    walk = client.post("/patients/IND-0215/twin/personal/what-if", headers=pat,
                       json={"items": [{"food": "Steamed white rice", "servings": 2}], "walk_minutes": 30}).json()
    assert rice["summary"]["peak"] > small["summary"]["peak"] > rice["start_glucose"] - 30
    assert walk["summary"]["peak"] <= rice["summary"]["peak"]
