"""Twin engine: runs the models on a patient's TwinState and stores the results.

run_short()  after new CGM readings: glucose +30/+60 forecast and predicted-hypo alert (cheap)
run_full()   after a new lab, a medicine change, or the daily job: DKD risk, HbA1c forecast,
             glucose forecast, state alerts. DKD is never re-run on every CGM point.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
from sqlmodel import Session, select

from src.alerts.engine import check_state, raise_alert
from src.clinical import loinc
from src.db.models import Meal, Observation, Patient, Prediction
from src.models.dkd import predict_dkd
from src.models.t2dm import forecast_glucose, forecast_hba1c
from src.twin.state import build_state


def _recent_cgm(session: Session, patient_id: str, now: datetime) -> pd.DataFrame:
    obs = session.exec(select(Observation).where(
        Observation.patient_id == patient_id, Observation.loinc_code == loinc.code("glucose"),
        Observation.device == "cgm", Observation.effective_time > now - timedelta(hours=2, minutes=5),
        Observation.effective_time <= now).order_by(Observation.effective_time)).all()
    df = pd.DataFrame({"time": [o.effective_time for o in obs], "glucose": [o.value for o in obs]})
    df["carbs_g"] = 0.0
    meals = session.exec(select(Meal).where(Meal.patient_id == patient_id,
                                            Meal.time > now - timedelta(hours=2), Meal.time <= now)).all()
    for m in meals:
        if len(df):
            i = (df["time"] - m.time).abs().idxmin()
            df.loc[i, "carbs_g"] += m.total_carbs_g
    return df


def _save(session: Session, pid: str, kind: str, value: float, details: dict, version: str) -> None:
    session.add(Prediction(patient_id=pid, kind=kind, value=value, details=details, model_version=version))


def _raise(session: Session, pid: str, found: list[tuple[str, str, str]]) -> list[str]:
    return [a.message for t, sev, msg in found if (a := raise_alert(session, pid, t, sev, msg))]


def run_short(session: Session, patient_id: str, now: datetime | None = None) -> dict:
    """Light re-run after CGM readings (called every few seconds by the simulator)."""
    now = now or datetime.now(timezone.utc)
    g = forecast_glucose(_recent_cgm(session, patient_id, now))
    if g.get("available"):
        last = session.exec(select(Prediction.created_at).where(
            Prediction.patient_id == patient_id, Prediction.kind == "glucose_30m")
            .order_by(Prediction.created_at.desc())).first()
        if last is None or now - last > timedelta(seconds=60):  # store at most once a minute
            _save(session, patient_id, "glucose_30m", g["plus_30"], g, g["model_version"])
        mini_state = {"cgm": {"latest": {"value": g["now"]}, "connected": False, "minutes_since_last": None},
                      "kidney": {}, "adherence": {"pct_7d": None}}
        found = [a for a in check_state(mini_state, g) if a[0] == "predicted_hypo"]
        g["new_alerts"] = _raise(session, patient_id, found)
    session.commit()
    return g


def run_full(session: Session, patient_id: str, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    state = build_state(session, patient_id, now)
    f = state["features"]["dkd"]
    out: dict = {"patient_id": patient_id, "as_of": state["as_of"]}
    if f.get("egfr") is not None and f.get("log_uacr") is not None:
        d = predict_dkd(f)
        _save(session, patient_id, "dkd_3y", d["risk_3y"], d, d["model_version"])
        out["dkd"] = d
    if state["glycaemia"]["hba1c"] is not None:
        h = forecast_hba1c(state["features"]["hba1c"])
        _save(session, patient_id, "hba1c_3m", h["hba1c_3m"], h, h["model_version"])
        out["hba1c"] = h
    g = forecast_glucose(_recent_cgm(session, patient_id, now))
    if g.get("available"):
        _save(session, patient_id, "glucose_30m", g["plus_30"], g, g["model_version"])
    out["glucose"] = g
    out["new_alerts"] = _raise(session, patient_id, check_state(state, g))
    session.commit()
    return out


def latest_predictions(session: Session, patient_id: str) -> dict:
    """Most recent stored prediction of each kind."""
    out = {}
    for kind in ("dkd_3y", "hba1c_3m", "glucose_30m"):
        p = session.exec(select(Prediction).where(Prediction.patient_id == patient_id,
                                                  Prediction.kind == kind)
                         .order_by(Prediction.created_at.desc())).first()
        if p:
            out[kind] = {**p.details, "value": p.value, "created_at": p.created_at.isoformat()}
    return out


def run_all(session: Session) -> int:
    """Daily job: full re-run for every patient."""
    ids = session.exec(select(Patient.id)).all()
    for pid in ids:
        run_full(session, pid)
    return len(ids)
