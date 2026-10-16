"""Treatment advisor: ranked options and what-if simulation.

GET  /patients/{pid}/treatments            doctor/admin: all eligible options; patient: lifestyle only
POST /patients/{pid}/treatments/simulate   {"options": ["sglt2i", "bp_control"]} -> before/after
Decision support only; the clinician decides. Patients can only simulate lifestyle options.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session

from api.deps import is_clinician, patient_for
from src.auth.security import current_user
from src.clinical.rules import clinical_rules
from src.db.models import Patient, User
from src.db.session import get_session
from src.treatment.rank import DISCLAIMER, rank
from src.treatment.simulate import simulate
from src.twin.state import build_state

router = APIRouter(tags=["treatments"])


class SimulateIn(BaseModel):
    options: list[str]


@router.get("/patients/{pid}/treatments")
def treatments(p: Patient = Depends(patient_for), user: User = Depends(current_user),
               session: Session = Depends(get_session)) -> dict:
    return rank(build_state(session, p.id), patient_view=not is_clinician(user))


@router.post("/patients/{pid}/treatments/simulate")
def simulate_options(body: SimulateIn, p: Patient = Depends(patient_for),
                     user: User = Depends(current_user), session: Session = Depends(get_session)) -> dict:
    effects = clinical_rules()["effects"]
    unknown = [o for o in body.options if o not in effects]
    if unknown or not body.options:
        raise HTTPException(422, f"unknown options {unknown}; choose from {sorted(effects)}")
    if not is_clinician(user) and any(effects[o]["kind"] != "lifestyle" for o in body.options):
        raise HTTPException(403, "Patients can only explore lifestyle options. "
                                 "Please discuss medicines with your doctor.")
    state = build_state(session, p.id)
    if state["features"]["dkd"].get("egfr") is None or state["features"]["dkd"].get("log_uacr") is None:
        raise HTTPException(409, "Needs eGFR (creatinine) and UACR to estimate kidney risk")
    return {**simulate(state, body.options), "disclaimer": DISCLAIMER}
