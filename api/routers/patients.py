"""Patients, observations, lab upload and medicines.

GET  /patients                          doctor/admin: all (sorted by DKD risk); patient: own
GET  /patients/{pid}                    profile
GET  /patients/{pid}/observations       readings, filter by variable and time window
POST /patients/{pid}/observations       manual entry (doctor) or patient-app entry (patient)
POST /patients/{pid}/labs/upload        lab CSV: date,test,value[,unit]
GET  /patients/{pid}/medications        current medicines
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel
from sqlmodel import Session, select

from api.deps import is_clinician, patient_for
from src.alerts.engine import active_alerts
from src.auth.security import current_user
from src.clinical import loinc
from src.db.models import Observation, Patient, User
from src.db.session import get_session
from src.ingestion.manual import parse_lab_csv
from src.ingestion.translator import ObservationIn, save
from src.twin.engine import latest_predictions
from src.twin.state import build_state

router = APIRouter(tags=["patients"])


class ReadingIn(BaseModel):
    variable: str                     # hba1c, creatinine, uacr, potassium, glucose, sbp, dbp, weight, ...
    value: float
    unit: str = ""
    time: Optional[datetime] = None   # default: now
    device: Optional[str] = None      # e.g. "fingerstick"


def _summary(session: Session, p: Patient) -> dict:
    s = build_state(session, p.id)
    pred = latest_predictions(session, p.id).get("dkd_3y", {})
    k = s["kidney"]
    return {
        "patient_id": p.id, "display_name": p.display_name, "age": s["profile"]["age"], "sex": p.sex,
        "dm_duration_yrs": s["profile"]["dm_duration_yrs"],
        "hba1c": s["glycaemia"]["hba1c"], "egfr": k.get("egfr"), "uacr": k.get("uacr"),
        "kdigo": k.get("stage"), "kdigo_colour": k.get("colour"), "kdigo_risk": k.get("risk"),
        "dkd_risk_3y": pred.get("risk_3y"), "risk_band": pred.get("band"), "risk_kind": pred.get("kind"),
        "tir_pct": (s["cgm"]["metrics"] or {}).get("tir_pct"),
        "adherence_7d": s["adherence"]["pct_7d"],
        "n_alerts": len(active_alerts(session, p.id)),
        "freshness_flags": s["freshness_flags"],
    }


@router.get("/patients")
def list_patients(user: User = Depends(current_user), session: Session = Depends(get_session)) -> list[dict]:
    q = select(Patient) if is_clinician(user) else select(Patient).where(Patient.id == user.patient_id)
    rows = [_summary(session, p) for p in session.exec(q).all()]
    return sorted(rows, key=lambda r: -(r["dkd_risk_3y"] or 0))


@router.get("/patients/{pid}")
def get_patient(p: Patient = Depends(patient_for)) -> dict:
    return p.model_dump()


@router.get("/patients/{pid}/observations")
def observations(variable: Optional[str] = None, hours: int = 24 * 14, device: Optional[str] = None,
                 p: Patient = Depends(patient_for), session: Session = Depends(get_session)) -> list[dict]:
    q = select(Observation).where(Observation.patient_id == p.id,
                                  Observation.effective_time > datetime.now(timezone.utc) - timedelta(hours=hours))
    if variable:
        if variable not in loinc.table().index:
            raise HTTPException(422, f"unknown variable {variable!r}")
        q = q.where(Observation.loinc_code == loinc.code(variable))
    if device:
        q = q.where(Observation.device == device)
    rows = session.exec(q.order_by(Observation.effective_time)).all()
    return [{"time": o.effective_time.isoformat(), "variable": loinc.variable_for(o.loinc_code),
             "value": o.value, "unit": o.unit, "source": o.source, "device": o.device} for o in rows]


@router.post("/patients/{pid}/observations")
def add_observations(readings: list[ReadingIn], p: Patient = Depends(patient_for),
                     user: User = Depends(current_user), session: Session = Depends(get_session)) -> dict:
    source = "manual" if is_clinician(user) else "patient_app"
    now = datetime.now(timezone.utc)
    items = [ObservationIn(patient_id=p.id, variable=r.variable, value=r.value, unit=r.unit,
                           time=r.time or now, source=source, device=r.device) for r in readings]
    return save(session, items)


@router.post("/patients/{pid}/labs/upload")
async def upload_labs(file: UploadFile, p: Patient = Depends(patient_for),
                      user: User = Depends(current_user), session: Session = Depends(get_session)) -> dict:
    try:
        items, problems = parse_lab_csv(await file.read(), p.id,
                                        source="manual" if is_clinician(user) else "patient_app")
    except ValueError as e:
        raise HTTPException(422, str(e))
    result = save(session, items)
    result["problems"] = problems
    return result


@router.get("/patients/{pid}/medications")
def medications(p: Patient = Depends(patient_for), session: Session = Depends(get_session)) -> list[dict]:
    return build_state(session, p.id)["medications"]
