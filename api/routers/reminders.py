"""Medicines (doctor prescribes) and reminders (patient responds).

POST   /patients/{pid}/medications          doctor: prescribe -> daily reminders + twin re-run
PUT    /medications/{med_id}                doctor: change dose / times / end date
DELETE /medications/{med_id}                doctor: stop (end date = today)
GET    /patients/{pid}/reminders            today's doses, due now, next dose, adherence 7/30 d
POST   /doses/{event_id}                    {"status": "taken" | "skipped"} (patient or doctor)
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlmodel import Session

from api.deps import patient_for
from config.settings import get_settings
from src.auth.security import can_see_patient, current_user, require_roles
from src.clinical.drugs import classify
from src.db.models import DoseEvent, Medication, Patient, User
from src.db.session import get_session
from src.reminders import engine as rem
from src.twin.engine import run_full

router = APIRouter(tags=["medicines and reminders"])
doctor = require_roles("doctor", "admin")


def _check_times(v: list[str]) -> list[str]:
    for t in v:
        datetime.strptime(t, "%H:%M")  # raises ValueError if not HH:MM
    return sorted(v)


class MedicationIn(BaseModel):
    drug: str
    dose: str = ""
    times: list[str] = ["08:00"]
    with_food: bool = False
    drug_class: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None

    @field_validator("times")
    @classmethod
    def _hhmm(cls, v: list[str]) -> list[str]:
        return _check_times(v)


class MedicationEdit(BaseModel):
    dose: Optional[str] = None
    times: Optional[list[str]] = None
    with_food: Optional[bool] = None
    end_date: Optional[date] = None


class DoseIn(BaseModel):
    status: str


def _freq(times: list[str]) -> str:
    return {1: "once daily", 2: "twice daily", 3: "three times daily"}.get(len(times), f"{len(times)} times daily")


def _med_dict(m: Medication) -> dict:
    # read attributes explicitly: after a commit the object is expired and model_dump() is empty
    return {"id": m.id, "patient_id": m.patient_id, "drug": m.drug, "drug_class": m.drug_class,
            "dose": m.dose, "frequency": m.frequency, "times": m.times, "with_food": m.with_food,
            "start_date": m.start_date.isoformat() if m.start_date else None,
            "end_date": m.end_date.isoformat() if m.end_date else None, "source": m.source,
            "classes": sorted(classify(m.drug))}


@router.post("/patients/{pid}/medications")
def prescribe(body: MedicationIn, p: Patient = Depends(patient_for), user: User = Depends(doctor),
              session: Session = Depends(get_session)) -> dict:
    classes = classify(body.drug) - {"acei_arb"}
    med = Medication(patient_id=p.id, drug=body.drug.strip(), dose=body.dose, times=body.times,
                     frequency=_freq(body.times), with_food=body.with_food,
                     drug_class=body.drug_class or (sorted(classes)[0] if classes else ""),
                     start_date=body.start_date or datetime.now(ZoneInfo(get_settings().timezone)).date(),
                     end_date=body.end_date, prescribed_by=user.id, source="doctor")
    session.add(med)
    session.commit()
    session.refresh(med)
    rem.ensure_dose_events(session, patient_id=p.id)
    twin = run_full(session, p.id)  # medicine change -> DKD re-run
    return {"medication": _med_dict(med), "dkd_risk_3y": (twin.get("dkd") or {}).get("risk_3y")}


def _own_med(session: Session, med_id: int) -> Medication:
    m = session.get(Medication, med_id)
    if m is None:
        raise HTTPException(404, "medication not found")
    return m


@router.put("/medications/{med_id}", dependencies=[Depends(doctor)])
def edit(med_id: int, body: MedicationEdit, session: Session = Depends(get_session)) -> dict:
    m = _own_med(session, med_id)
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(m, k, v)
    if body.times is not None:
        try:
            m.times = _check_times(body.times)
        except ValueError:
            raise HTTPException(422, "times must look like 08:00")
        m.frequency = _freq(m.times)
    session.add(m)
    session.commit()
    rem.reschedule(session, m)
    run_full(session, m.patient_id)
    return _med_dict(m)


@router.delete("/medications/{med_id}", dependencies=[Depends(doctor)])
def stop(med_id: int, session: Session = Depends(get_session)) -> dict:
    m = _own_med(session, med_id)
    m.end_date = datetime.now(ZoneInfo(get_settings().timezone)).date() - timedelta(days=1)
    session.add(m)
    session.commit()
    rem.reschedule(session, m)
    run_full(session, m.patient_id)
    return _med_dict(m)


@router.get("/patients/{pid}/reminders")
def reminders(p: Patient = Depends(patient_for), session: Session = Depends(get_session)) -> dict:
    rem.ensure_dose_events(session, patient_id=p.id)
    rem.mark_missed(session)
    return {"today": rem.doses(session, p.id), "due_now": rem.due_now(session, p.id),
            "next": rem.next_dose(session, p.id),
            "adherence_7d": rem.adherence(session, p.id, 7), "adherence_30d": rem.adherence(session, p.id, 30)}


@router.post("/doses/{event_id}")
def respond(event_id: int, body: DoseIn, user: User = Depends(current_user),
            session: Session = Depends(get_session)) -> dict:
    e = session.get(DoseEvent, event_id)
    if e is None:
        raise HTTPException(404, "dose not found")
    med = session.get(Medication, e.medication_id)
    if not can_see_patient(user, med.patient_id):
        raise HTTPException(403, "Not your medicine")
    try:
        rem.respond(session, event_id, body.status)
    except ValueError as err:
        raise HTTPException(422, str(err))
    return {"id": event_id, "status": body.status,
            "adherence_7d": rem.adherence(session, med.patient_id, 7)}
