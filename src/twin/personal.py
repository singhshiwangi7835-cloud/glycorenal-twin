"""Personal (progressive) twin: glucose twin + kidney twin + how well the twin knows the patient.

Maturity (0-100%) grows with the patient's own data: days of CGM, meals logged, eGFR results and
UACR results (targets and weights in clinical_rules.yaml -> personal_twin.maturity). A new patient
starts near the population; as maturity rises the twin's numbers become the patient's own.

Every re-tuning is saved (Prediction kind "personal_twin", at most once an hour per patient) so the
doctor can see the twin learning over time: maturity and replay accuracy by date.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlmodel import Session, select

from src.clinical.rules import clinical_rules
from src.db.models import Patient, Prediction
from src.twin import personal_glucose, personal_kidney
from src.twin.state import build_state

VERSION = "personal_twin@1"


def maturity(glucose: dict, kidney: dict, state: dict) -> dict:
    m = clinical_rules()["personal_twin"]["maturity"]
    parts = {
        "cgm": min(glucose.get("days_of_cgm", 0) / m["cgm_days_full"], 1.0),
        "meals": min(glucose.get("meals", 0) / m["meals_full"], 1.0),
        "egfr": min(len(state["history"]["egfr"]) / m["egfr_results_full"], 1.0),
        "uacr": min(len(state["history"]["uacr"]) / m["uacr_results_full"], 1.0),
    }
    score = sum(m["weights"][k] * v for k, v in parts.items()) * 100
    level = "personal" if score >= 75 else ("learning" if score >= 40 else "getting to know the patient")
    tips = []
    if parts["cgm"] < 1:
        tips.append(f"{m['cgm_days_full'] - glucose.get('days_of_cgm', 0):.0f} more days of CGM")
    if parts["meals"] < 1:
        tips.append(f"{m['meals_full'] - glucose.get('meals', 0)} more logged meals")
    if parts["egfr"] < 1:
        tips.append(f"{m['egfr_results_full'] - len(state['history']['egfr'])} more creatinine results")
    if parts["uacr"] < 1:
        tips.append(f"{m['uacr_results_full'] - len(state['history']['uacr'])} more UACR results")
    return {"score": round(score), "level": level, "parts": {k: round(v * 100) for k, v in parts.items()},
            "to_improve": tips}


def build(session: Session, patient_id: str, options: list[str] | None = None, save: bool = True) -> dict:
    if session.get(Patient, patient_id) is None:
        raise LookupError(patient_id)
    now = datetime.now(timezone.utc)
    state = build_state(session, patient_id, now)
    glucose = personal_glucose.build(session, patient_id, now)
    kidney = personal_kidney.build(state, now, options)
    mat = maturity(glucose, kidney, state)
    out = {"patient_id": patient_id, "as_of": now.isoformat(), "maturity": mat, "glucose": glucose,
           "kidney": kidney, "version": VERSION}
    if save and not options:
        _save(session, patient_id, out, now)
    out["history"] = history(session, patient_id)
    out["glucose_learning"] = personal_glucose.learning_curve(session, patient_id, now=now)
    return out


def _save(session: Session, patient_id: str, out: dict, now: datetime) -> None:
    last = session.exec(select(Prediction.created_at).where(
        Prediction.patient_id == patient_id, Prediction.kind == "personal_twin")
        .order_by(Prediction.created_at.desc())).first()
    if last is not None and now - last < timedelta(hours=1):
        return
    g, k = out["glucose"], out["kidney"]
    details = {"maturity": out["maturity"]["score"], "glucose_params": g.get("params"),
               "replay_mae": (g.get("accuracy") or {}).get("mae"), "egfr_slope": k.get("slope"),
               "egfr_slope_80pct": k.get("slope_80pct")}
    session.add(Prediction(patient_id=patient_id, kind="personal_twin", value=out["maturity"]["score"],
                           details=details, model_version=VERSION, created_at=now))
    session.commit()


def history(session: Session, patient_id: str, limit: int = 60) -> list[dict]:
    rows = session.exec(select(Prediction).where(Prediction.patient_id == patient_id,
                                                 Prediction.kind == "personal_twin")
                        .order_by(Prediction.created_at.desc()).limit(limit)).all()
    return [{"time": r.created_at.isoformat(), "maturity": r.value, **{k: r.details.get(k) for k in
             ("replay_mae", "egfr_slope", "egfr_slope_80pct")}} for r in reversed(rows)]


def refit_all(session: Session) -> int:
    """Daily job: re-tune every patient's personal twin."""
    ids = session.exec(select(Patient.id)).all()
    for pid in ids:
        build(session, pid)
    return len(ids)
