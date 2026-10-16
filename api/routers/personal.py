"""Personal (progressive) twin: the patient's own glucose and kidney models.

GET  /patients/{pid}/twin/personal                 maturity, glucose twin (+ twin vs real), kidney path
     ?options=sglt2i,bp_control                     kidney path with these options applied
POST /patients/{pid}/twin/personal/what-if          {"items": [{"food": "...", "servings": 2}], "walk_minutes": 15}
Patients may only apply lifestyle options; the meal what-if is open to the patient and the doctor.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session

from api.deps import is_clinician, patient_for
from src.auth.security import current_user
from src.clinical.rules import clinical_rules
from src.db.models import Patient, User
from src.db.session import get_session
from src.twin import personal, personal_glucose

router = APIRouter(tags=["personal twin"])


class MealItem(BaseModel):
    food: str
    servings: float = 1


class WhatIfIn(BaseModel):
    items: list[MealItem] = []
    walk_minutes: int = 0
    walk_after_minutes: int = 30


@router.get("/patients/{pid}/twin/personal")
def get_personal(options: Optional[str] = None, p: Patient = Depends(patient_for),
                 user: User = Depends(current_user), session: Session = Depends(get_session)) -> dict:
    opts = [o.strip() for o in options.split(",") if o.strip()] if options else None
    if opts:
        effects = clinical_rules()["effects"]
        unknown = [o for o in opts if o not in effects]
        if unknown:
            raise HTTPException(422, f"unknown options {unknown}")
        if not is_clinician(user) and any(effects[o]["kind"] != "lifestyle" for o in opts):
            raise HTTPException(403, "Patients can only explore lifestyle options")
    return personal.build(session, p.id, opts)


@router.post("/patients/{pid}/twin/personal/what-if")
def what_if(body: WhatIfIn, p: Patient = Depends(patient_for), session: Session = Depends(get_session)) -> dict:
    try:
        return personal_glucose.what_if(session, p.id, [i.model_dump() for i in body.items],
                                        walk_minutes=body.walk_minutes, walk_after_minutes=body.walk_after_minutes)
    except KeyError as e:
        raise HTTPException(422, f"unknown food {e}")
