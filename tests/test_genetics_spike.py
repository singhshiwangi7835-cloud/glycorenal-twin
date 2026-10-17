"""Genetic markers (simulated) and the 90-minute glucose spike early warning."""

from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from src.clinical import genetics
from src.models.features import SPIKE_FEATURES, spike_frame, spike_training_rows
from src.models.t2dm import forecast_spike
from src.treatment.eligibility import evaluate, safety_warnings


def _markers(prs=82, tcf=2, cyp=1, slc=0):
    return genetics.summarize({"ckd_prs_percentile": {"value": prs, "time": None},
                               "tcf7l2_rs7903146": {"value": tcf, "time": None},
                               "cyp2c9_phenotype": {"value": cyp, "time": None},
                               "slc22a1_reduced_alleles": {"value": slc, "time": None}})


def test_genetic_interpretation_and_flags():
    m = {x["marker"]: x for x in _markers()}
    assert m["ckd_prs_percentile"]["flag"] and "82nd percentile" in m["ckd_prs_percentile"]["result"]
    assert m["cyp2c9_phenotype"]["result"] == "intermediate metaboliser" and m["cyp2c9_phenotype"]["flag"]
    assert not m["slc22a1_reduced_alleles"]["flag"]
    assert genetics.summarize({}) == []  # not tested -> nothing shown


def test_kidney_score_changes_odds_not_beyond_bounds():
    assert genetics.dkd_odds_ratio(None) == 1.0
    assert genetics.dkd_odds_ratio(50) == 1.0
    assert genetics.dkd_odds_ratio(90) > 1 > genetics.dkd_odds_ratio(10)
    p = genetics.apply_odds_ratio(0.30, 1.35)
    assert 0.30 < p < 0.40
    assert genetics.apply_odds_ratio(0.30, 1.0) == 0.30


def test_dkd_risk_higher_with_high_kidney_score(state_ramesh):
    from src.models.dkd import predict_dkd
    f = dict(state_ramesh["features"]["dkd"])
    f["ckd_prs_percentile"] = 50
    avg = predict_dkd(f)
    f["ckd_prs_percentile"] = 90
    high = predict_dkd(f)
    assert high["risk_3y"] > avg["risk_3y"]
    assert any(d["feature"] == "ckd_prs_percentile" for d in high["drivers"])


def test_pharmacogenomic_cautions(state_ramesh):
    st = dict(state_ramesh)
    st["genetics"] = _markers(tcf=2, cyp=2, slc=2)
    st["glycaemia"] = {**st["glycaemia"], "hba1c": 9.0}
    st["med_flags"] = {**st["med_flags"], "on_sulfonylurea": 0, "on_metformin": 1}
    opts = {o["option"]: o for o in evaluate(st)["options"]}
    su = " ".join(opts["sulfonylurea"]["cautions"])
    assert "TCF7L2" in su and "CYP2C9" in su
    assert any("OCT1" in w for w in safety_warnings(st))  # already on metformin


def _series(days=8, meal_hour=13, carbs=90, rise=180):
    """Regular 5-min CGM with one big lunch a day."""
    t0 = datetime(2026, 1, 1)
    n = days * 288
    t = [t0 + timedelta(minutes=5 * i) for i in range(n)]
    g = np.full(n, 140.0)
    c = np.zeros(n)
    for d in range(days):
        i = d * 288 + meal_hour * 12
        c[i] = carbs
        k = np.arange(0, 36)
        g[i:i + 36] += rise * (k / 12) * np.exp(1 - k / 12)  # peak ~60 min later
    return pd.DataFrame({"time": t, "glucose": g, "carbs_g": c})


def test_spike_habit_features_use_only_past_days():
    s = _series()
    f = spike_frame(s)
    lunch_minus_30 = 7 * 288 + 13 * 12 - 6  # day 8, 30 min before lunch
    r = f.iloc[lunch_minus_30]
    assert r["habit_carbs_next_90m"] == 90 and r["habit_spike_rate_next_90m"] == 1.0
    assert np.isnan(f.iloc[100]["habit_carbs_next_90m"])  # first day: no history
    rows = spike_training_rows(s)
    assert set(SPIKE_FEATURES) <= set(rows.columns) and rows["y_spike"].sum() > 0
    assert (rows["g_now"] < 250).all()


def test_spike_forecast_warns_before_the_crossing():
    s = _series()
    cut = 7 * 288 + 13 * 12 + 2  # 10 min after today's lunch, glucose still low
    out = forecast_spike(s.iloc[:cut])
    assert out["available"] and out["now"] < 250
    assert out["spike_likely"] and out["probability"] >= 0.5
    assert out["habit"]["peak_next_90m"] >= 250  # yesterday at this time he went above the line


@pytest.fixture(scope="module")
def state_ramesh(client):
    from sqlmodel import Session

    from src.db.session import engine
    from src.twin.state import build_state
    with Session(engine) as s:
        st = build_state(s, "IND-0042")
    assert st["genetics"], "seed should give Ramesh simulated genetic results"
    return st


def test_shanghai_real_cgm_loader():
    from src.pipeline import shanghai
    if not shanghai.available():
        pytest.skip("ShanghaiT2DM not downloaded (data/raw is not in git)")
    pid = shanghai.demo_participant()
    s = shanghai.load_participant(pid)
    real = s[s["measured"] == 1]
    assert len(real) > 200 and s["glucose"].dropna().between(30, 500).all()
    assert (pd.to_datetime(s["time"]).diff().dropna() == pd.Timedelta(minutes=5)).all()  # regular grid
    assert s["meal"].sum() >= 1 and (s["carbs_g"] == 0).all()
    assert shanghai.summary()["hba1c_pct"].between(4, 16).mean() > 0.8
