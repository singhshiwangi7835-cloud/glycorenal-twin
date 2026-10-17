"""Devices and home readings.

GET  /patients/{pid}/devices                  simulator / Libre / Dexcom status
POST /patients/{pid}/devices/simulator/start  {"source": "synthetic" | "cgmacros:CGMacros-001" | "shanghai[:2015_0_20210203]"}
POST /patients/{pid}/devices/simulator/stop
POST /patients/{pid}/devices/simulator/scenario   {"scenario": "meal_spike" | "hypo"}
POST /patients/{pid}/devices/libre            upload a LibreView CSV export
POST /patients/{pid}/vitals                   BP, weight, fingerstick glucose, sleep, steps
GET  /devices/simulators                      all running simulators (doctor/admin)
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel
from sqlmodel import Session, select

from api.deps import is_clinician, patient_for
from src.auth.security import current_user, require_roles
from src.db.models import DeviceConnection, Patient, User
from src.db.session import get_session
from src.ingestion import dexcom, libre_csv, simulator
from src.ingestion.translator import ObservationIn, save
from src.pipeline import cgmacros

router = APIRouter(tags=["devices"])


class StartIn(BaseModel):
    source: str = "synthetic"


class ScenarioIn(BaseModel):
    scenario: str            # meal_spike | hypo
    carbs_g: float = 90      # for meal_spike


class VitalsIn(BaseModel):
    systolic: Optional[float] = None
    diastolic: Optional[float] = None
    weight_kg: Optional[float] = None
    glucose_mg_dl: Optional[float] = None    # fingerstick
    sleep_hours: Optional[float] = None
    steps: Optional[int] = None
    time: Optional[datetime] = None


@router.get("/patients/{pid}/devices")
def devices(p: Patient = Depends(patient_for), session: Session = Depends(get_session)) -> dict:
    conns = session.exec(select(DeviceConnection).where(DeviceConnection.patient_id == p.id)).all()
    return {"simulator": simulator.status(p.id),
            "connections": [{"provider": c.provider, "status": c.status,
                             "last_sync": c.last_sync.isoformat() if c.last_sync else None} for c in conns],
            "dexcom": dexcom.status(),
            "cgmacros_participants": cgmacros.participant_ids() if cgmacros.available() else []}


@router.post("/patients/{pid}/devices/simulator/start")
def sim_start(body: StartIn, p: Patient = Depends(patient_for), session: Session = Depends(get_session)) -> dict:
    return simulator.start(session, p.id, body.source)


@router.post("/patients/{pid}/devices/simulator/stop")
def sim_stop(p: Patient = Depends(patient_for), session: Session = Depends(get_session)) -> dict:
    return simulator.stop(session, p.id)


@router.post("/patients/{pid}/devices/simulator/scenario")
def sim_scenario(body: ScenarioIn, p: Patient = Depends(patient_for)) -> dict:
    if not simulator.is_running(p.id):
        raise HTTPException(409, "Start the simulator first")
    if body.scenario == "meal_spike":
        simulator.inject_meal_spike(p.id, carbs_g=body.carbs_g)
    elif body.scenario == "hypo":
        simulator.inject_hypo(p.id)
    else:
        raise HTTPException(422, "scenario must be 'meal_spike' or 'hypo'")
    return simulator.status(p.id)


@router.post("/patients/{pid}/devices/libre")
async def libre_upload(file: UploadFile, p: Patient = Depends(patient_for),
                       session: Session = Depends(get_session)) -> dict:
    try:
        items, summary = libre_csv.parse(await file.read(), p.id)
    except ValueError as e:
        raise HTTPException(422, str(e))
    result = save(session, items)
    conn = session.exec(select(DeviceConnection).where(DeviceConnection.patient_id == p.id,
                                                       DeviceConnection.provider == "libre")).first() \
        or DeviceConnection(patient_id=p.id, provider="libre")
    conn.status, conn.last_sync = "uploaded", datetime.now(timezone.utc)
    session.add(conn)
    session.commit()
    return {**summary, **result}


@router.post("/patients/{pid}/vitals")
def vitals(body: VitalsIn, p: Patient = Depends(patient_for), user: User = Depends(current_user),
           session: Session = Depends(get_session)) -> dict:
    t = body.time or datetime.now(timezone.utc)
    src = "manual" if is_clinician(user) else "patient_app"
    pairs = [("sbp", body.systolic, None), ("dbp", body.diastolic, None), ("weight", body.weight_kg, None),
             ("glucose", body.glucose_mg_dl, "fingerstick"), ("sleep", body.sleep_hours, None),
             ("steps", body.steps, None)]
    items = [ObservationIn(patient_id=p.id, variable=v, value=x, time=t, source=src, device=d)
             for v, x, d in pairs if x is not None]
    if (body.systolic is None) != (body.diastolic is None):
        raise HTTPException(422, "Enter both systolic and diastolic BP")
    if not items:
        raise HTTPException(422, "Enter at least one value")
    if body.weight_kg:  # keep BMI in step with weight, using the last BMI to infer height
        from src.twin.state import build_state
        s = build_state(session, p.id)
        if s["vitals"]["bmi"] and s["vitals"]["weight"]:
            h2 = s["vitals"]["weight"] / s["vitals"]["bmi"]
            items.append(ObservationIn(patient_id=p.id, variable="bmi", value=round(body.weight_kg / h2, 1),
                                       time=t, source=src))
    return save(session, items)


@router.get("/devices/simulators", dependencies=[Depends(require_roles("doctor", "admin"))])
def running() -> list[dict]:
    return simulator.status()
