"""Indian meal log.

GET  /foods                          the food list (indian_foods.csv), with Hindi names
POST /patients/{pid}/meals           {"items": [{"food": "Steamed white rice", "servings": 2}], "time": optional}
GET  /patients/{pid}/meals           recent meals with their 2-hour glucose spike
GET  /patients/{pid}/meals/top-foods "Your top 3 spiking foods"
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session

from api.deps import patient_for
from src.auth.security import current_user
from src.db.models import Patient
from src.db.session import get_session
from src.meals import engine as meals

router = APIRouter(tags=["meals"])


class MealItem(BaseModel):
    food: str
    servings: float = 1


class MealIn(BaseModel):
    items: list[MealItem]
    time: Optional[datetime] = None


@router.get("/foods", dependencies=[Depends(current_user)])
def foods() -> list[dict]:
    return meals.food_list()


@router.post("/patients/{pid}/meals")
def log_meal(body: MealIn, p: Patient = Depends(patient_for), session: Session = Depends(get_session)) -> dict:
    try:
        return meals.log_meal(session, p.id, [i.model_dump() for i in body.items], body.time)
    except ValueError as e:
        raise HTTPException(422, str(e))


@router.get("/patients/{pid}/meals")
def list_meals(days: int = 14, p: Patient = Depends(patient_for), session: Session = Depends(get_session)) -> list[dict]:
    meals.compute_spikes(session, p.id)
    return meals.meals(session, p.id, days)


@router.get("/patients/{pid}/meals/top-foods")
def top_foods(p: Patient = Depends(patient_for), session: Session = Depends(get_session)) -> list[dict]:
    meals.compute_spikes(session, p.id)
    return meals.top_spiking_foods(session, p.id)
