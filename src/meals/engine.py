"""Indian meal log and post-meal glucose spikes (CLAUDE.md section 9).

- The patient picks foods from data/reference/indian_foods.csv with servings; carbs are summed.
- Spike = highest CGM in the 2 hours after the meal minus the reading just before it.
  "2 hours" = the next 24 CGM readings (5 minutes each), so it also works with the fast simulator.
- "Your top 3 spiking foods": average spike of the meals each food appeared in, counting a food
  only when it gave at least 20% of that meal's carbs (so dal eaten with rice is not blamed).
If the live simulator is running, logging a meal also adds a matching rise to the simulated
sensor (bigger for more carbs and higher-GI foods), so the twin reacts like a real body would.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
from sqlmodel import Session, select

from src.clinical import loinc
from src.db.models import Meal, Observation

FOODS_CSV = Path(__file__).resolve().parents[2] / "data" / "reference" / "indian_foods.csv"
READINGS_2H = 24
GI_FACTOR = {"low": 0.7, "medium": 1.0, "high": 1.3}


@lru_cache
def foods() -> pd.DataFrame:
    return pd.read_csv(FOODS_CSV).set_index("food")


def food_list() -> list[dict]:
    f = foods().reset_index()
    return f[["food", "food_hi", "serving", "serving_g", "carbs_g", "gi_category", "group"]].to_dict("records")


def _cgm_query(patient_id: str):
    return select(Observation).where(Observation.patient_id == patient_id,
                                     Observation.loinc_code == loinc.code("glucose"),
                                     Observation.device == "cgm")


def log_meal(session: Session, patient_id: str, items: list[dict], when: datetime | None = None) -> dict:
    """items: [{"food": "Steamed white rice", "servings": 2}, ...]"""
    f = foods()
    unknown = [i["food"] for i in items if i["food"] not in f.index]
    if unknown or not items:
        raise ValueError(f"Unknown foods: {unknown}" if unknown else "Pick at least one food")
    when = when or datetime.now(timezone.utc)
    clean = [{"food": i["food"], "servings": float(i.get("servings", 1))} for i in items]
    carbs = sum(float(f.loc[i["food"], "carbs_g"]) * i["servings"] for i in clean)
    gi = (sum(float(f.loc[i["food"], "carbs_g"]) * i["servings"] * GI_FACTOR[f.loc[i["food"], "gi_category"]]
              for i in clean) / carbs) if carbs else 1.0
    before = session.exec(_cgm_query(patient_id).where(Observation.effective_time <= when,
                                                       Observation.effective_time > when - timedelta(minutes=30))
                          .order_by(Observation.effective_time.desc())).first()
    meal = Meal(patient_id=patient_id, time=when, items=clean, total_carbs_g=round(carbs, 1),
                glucose_before=before.value if before else None)
    session.add(meal)
    session.commit()
    session.refresh(meal)

    from src.ingestion import simulator
    spike_added = simulator.inject_meal_spike(patient_id, carbs_g=carbs, gi_factor=gi) \
        if simulator.is_running(patient_id) else False
    return {**meal_dict(meal), "gi_factor": round(gi, 2), "simulated_rise_added": spike_added}


def meal_dict(m: Meal) -> dict:
    return {"id": m.id, "time": m.time.isoformat(), "items": m.items, "total_carbs_g": m.total_carbs_g,
            "glucose_before": m.glucose_before, "glucose_peak": m.glucose_peak, "spike": m.spike}


def compute_spikes(session: Session, patient_id: str | None = None) -> int:
    """Fill in glucose_peak and spike for meals that now have 2 hours of CGM after them."""
    q = select(Meal).where(Meal.spike.is_(None))
    if patient_id:
        q = q.where(Meal.patient_id == patient_id)
    pending = session.exec(q).all()
    by_patient: dict[str, list[Meal]] = {}
    for m in pending:
        by_patient.setdefault(m.patient_id, []).append(m)
    done = 0
    for pid, meal_list in by_patient.items():
        # one query per patient: CGM from just before the earliest pending meal onwards
        start = min(m.time for m in meal_list) - timedelta(hours=1)
        rows = session.exec(select(Observation.effective_time, Observation.value).where(
            Observation.patient_id == pid, Observation.loinc_code == loinc.code("glucose"),
            Observation.device == "cgm", Observation.effective_time > start)
            .order_by(Observation.effective_time)).all()
        if not rows:
            continue
        times = np.array([t.timestamp() for t, _ in rows])
        values = np.array([v for _, v in rows])
        for m in meal_list:
            i = int(np.searchsorted(times, m.time.timestamp(), side="right"))  # first reading after meal
            if i + READINGS_2H > len(values):
                continue  # not 2 hours of CGM yet
            if m.glucose_before is None:
                if i == 0:
                    continue
                m.glucose_before = float(values[i - 1])
            m.glucose_peak = float(values[i:i + READINGS_2H].max())
            m.spike = round(m.glucose_peak - m.glucose_before, 1)
            session.add(m)
            done += 1
    session.commit()
    return done


def meals(session: Session, patient_id: str, days: int = 14) -> list[dict]:
    rows = session.exec(select(Meal).where(Meal.patient_id == patient_id,
                                           Meal.time > datetime.now(timezone.utc) - timedelta(days=days))
                        .order_by(Meal.time.desc())).all()
    return [meal_dict(m) for m in rows]


def top_spiking_foods(session: Session, patient_id: str, n: int = 3, days: int = 30) -> list[dict]:
    rows = session.exec(select(Meal).where(Meal.patient_id == patient_id, Meal.spike.is_not(None),
                                           Meal.time > datetime.now(timezone.utc) - timedelta(days=days))).all()
    f = foods()
    per_food: dict[str, list[float]] = {}
    for m in rows:
        carbs = {i["food"]: float(f.loc[i["food"], "carbs_g"]) * i["servings"] if i["food"] in f.index else 0
                 for i in m.items}
        total = sum(carbs.values()) or 1
        for food, c in carbs.items():
            if c / total >= 0.2:
                per_food.setdefault(food, []).append(m.spike)
    ranked = sorted(({"food": k, "food_hi": f.loc[k, "food_hi"] if k in f.index else k,
                      "avg_spike": round(sum(v) / len(v), 1), "meals": len(v)}
                     for k, v in per_food.items()), key=lambda r: -r["avg_spike"])
    return ranked[:n]
