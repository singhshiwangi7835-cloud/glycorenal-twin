"""Synthetic 5-minute wearable traces: CGM glucose, heart rate, steps, plus the meals behind them.

Used (a) for demo patients so the live simulator works even without CGMacros, and
(b) as fallback training data for the glucose forecast model.

Glucose model (simple, physiology-shaped, not a validated simulator):
  baseline that drifts slowly + dawn rise + meal responses (gamma-shaped curve, height
  proportional to carbs, larger when control is poor) - a dip after walking + sensor noise.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
FOODS_CSV = ROOT / "data" / "reference" / "indian_foods.csv"

# typical Indian meal plates: (slot hour, list of (food, servings))
MEAL_TEMPLATES = {
    "breakfast": [[("Idli", 3), ("Sambar", 1)], [("Poha", 1), ("Tea with milk and sugar", 1)],
                  [("Aloo paratha", 2), ("Curd (dahi)", 1)], [("Upma", 1), ("Tea with milk and sugar", 1)],
                  [("Moong dal chilla", 2), ("Curd (dahi)", 1)], [("Plain dosa", 2), ("Sambar", 1)]],
    "lunch": [[("Steamed white rice", 2), ("Toor dal", 1), ("Mixed vegetable sabzi", 1)],
              [("Chapati (whole wheat)", 3), ("Rajma curry", 1), ("Raita", 1)],
              [("Vegetable biryani", 1), ("Raita", 1)],
              [("Steamed white rice", 1), ("Sambar", 1), ("Bhindi sabzi", 1)],
              [("Jowar roti", 2), ("Chole", 1), ("Mixed vegetable sabzi", 1)]],
    "snack": [[("Tea with milk and sugar", 1), ("Samosa", 1)], [("Banana", 1)],
              [("Roasted chana", 1)], [("Tea with milk and sugar", 1), ("Onion pakora", 1)],
              [("Guava", 1)]],
    "dinner": [[("Chapati (whole wheat)", 3), ("Paneer curry", 1), ("Toor dal", 1)],
               [("Steamed white rice", 2), ("Chicken curry", 1)],
               [("Khichdi", 1), ("Curd (dahi)", 1)],
               [("Chapati (whole wheat)", 2), ("Aloo sabzi", 1), ("Toor dal", 1)],
               [("Curd rice", 1), ("Mixed vegetable sabzi", 1)]],
}
MEAL_HOURS = {"breakfast": 8.5, "lunch": 13.5, "snack": 17.0, "dinner": 20.75}
GI_FACTOR = {"low": 0.7, "medium": 1.0, "high": 1.3}


def _foods() -> pd.DataFrame:
    return pd.read_csv(FOODS_CSV).set_index("food")


def mean_glucose_for_hba1c(hba1c: float) -> float:
    """Inverse of the ADAG relation: mean glucose (mg/dL) = 28.7 x HbA1c - 46.7."""
    return 28.7 * hba1c - 46.7


def generate(days: int = 14, hba1c: float = 8.0, cv_target: float = 0.30, steps_per_day: int = 5000,
             seed: int = 0, start: datetime | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Returns (readings every 5 min: time, glucose, heart_rate, steps, carbs_g; meals table)."""
    rng = np.random.default_rng(seed)
    foods = _foods()
    start = start or datetime(2026, 1, 1)
    n = days * 288
    t_min = np.arange(n) * 5
    hours = (t_min / 60) % 24

    mean_g = mean_glucose_for_hba1c(hba1c)
    control = np.clip((hba1c - 6) / 4, 0.1, 1.5)       # poorer control -> bigger spikes
    base = mean_g * 0.82 + np.cumsum(rng.normal(0, 0.6, n))
    base = base - np.convolve(base - base.mean(), np.ones(288) / 288, mode="same")  # keep stationary
    glucose = base + 15 * control * np.exp(-((hours - 6.5) / 1.5) ** 2)               # dawn rise

    carbs = np.zeros(n)
    meals = []
    for d in range(days):
        for slot, hour in MEAL_HOURS.items():
            if slot == "snack" and rng.random() < 0.4:
                continue
            plate = MEAL_TEMPLATES[slot][rng.integers(len(MEAL_TEMPLATES[slot]))]
            when = d * 1440 + int((hour + rng.normal(0, 0.4)) * 60)
            idx = min(when // 5, n - 1)
            total, gi = 0.0, 0.0
            for food, servings in plate:
                c = float(foods.loc[food, "carbs_g"]) * servings
                total += c
                gi += c * GI_FACTOR[foods.loc[food, "gi_category"]]
            gi = gi / total if total else 1
            carbs[idx] += total
            # gamma-like meal curve, peak ~45-60 min, lasting ~3 h
            k = np.arange(0, 48)  # 4 h
            curve = (k / 10) ** 2 * np.exp(-k / 5)
            curve = curve / curve.max()
            rise = total * gi * (0.9 + 0.8 * control) * rng.uniform(0.8, 1.2)
            end = min(idx + len(k), n)
            glucose[idx:end] += rise * curve[: end - idx]
            meals.append({"time": start + timedelta(minutes=int(idx * 5)), "slot": slot,
                          "items": [{"food": f, "servings": s} for f, s in plate],
                          "total_carbs_g": round(total, 1)})

    # steps: walking bouts, more in the morning and evening
    steps = np.zeros(n)
    daily_walk_slots = max(int(steps_per_day / 500), 1)
    for d in range(days):
        for _ in range(daily_walk_slots):
            hour = rng.choice([7, 7.5, 10, 12, 14.5, 18, 19, 21.5])
            idx = d * 288 + int((hour + rng.normal(0, 0.3)) * 12)
            span = rng.integers(2, 5)
            steps[idx: idx + span] += rng.integers(120, 220, size=len(steps[idx: idx + span]))
    walking = np.convolve(steps, np.ones(12) / 12, mode="full")[:n]
    glucose = glucose - 0.02 * walking

    # scale variability toward the target CV, then add sensor noise
    g = glucose - glucose.mean()
    cur_cv = g.std() / mean_g
    glucose = mean_g + g * min(cv_target / max(cur_cv, 1e-6), 1.6)
    glucose = glucose + rng.normal(0, 4, n)
    glucose = np.clip(glucose, 40, 400).round(0)

    sleeping = (hours < 6) | (hours >= 23)
    hr = np.where(sleeping, 62, 76) + 0.04 * steps + rng.normal(0, 3, n)

    readings = pd.DataFrame({
        "time": [start + timedelta(minutes=int(m)) for m in t_min],
        "glucose": glucose, "heart_rate": hr.round(0), "steps": steps.astype(int),
        "carbs_g": carbs.round(1),
    })
    return readings, pd.DataFrame(meals)


def inject_hypo(readings: pd.DataFrame, at_index: int, nadir: float = 52) -> pd.DataFrame:
    """Demo scenario: glucose slides to `nadir` over ~45 min, then recovers over ~45 min."""
    r = readings.copy()
    g0 = r.loc[at_index, "glucose"]
    shape = np.concatenate([np.linspace(0, 1, 9), np.linspace(1, 0, 9)])
    for k, s in enumerate(shape):
        i = at_index + k
        if i < len(r):
            r.loc[i, "glucose"] = round(g0 - (g0 - nadir) * s)
    return r


def inject_meal_spike(readings: pd.DataFrame, at_index: int, peak_rise: float = 110) -> pd.DataFrame:
    """Demo scenario: a big rice meal, glucose rises ~peak_rise mg/dL in an hour."""
    r = readings.copy()
    k = np.arange(0, 36)
    curve = (k / 10) ** 2 * np.exp(-k / 5)
    curve = curve / curve.max()
    for j, c in enumerate(curve):
        i = at_index + j
        if i < len(r):
            r.loc[i, "glucose"] = min(400, round(r.loc[i, "glucose"] + peak_rise * c))
    r.loc[at_index, "carbs_g"] += 90
    return r
