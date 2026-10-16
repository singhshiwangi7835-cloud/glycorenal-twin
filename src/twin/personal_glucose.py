"""Personal glucose twin (Track A): a small physiological model tuned to ONE patient.

Instead of applying a population model, the twin learns how *this* patient's glucose behaves:

    glucose(t) = basal + dawn x (early-morning bump)
                 + carb_sensitivity x sum over meals of [carbs x GI factor x meal curve(t - meal time)]
                 - activity x (recent heart-rate rise above resting, fading over ~1 hour)

The meal curve is a gamma-shaped rise and fall; its time to peak is also learnt (searched between
the limits in clinical_rules.yaml -> personal_twin.glucose). Fitting is ridge regression *towards
population starting values*: with little data the twin stays near the population, with more data
the patient's own numbers take over (this is what makes the twin progressive).

The fit uses the last 14 days of the patient's CGM, logged meals and heart rate. The most recent
3 days are first held out to measure how well the twin reproduces reality ("twin vs real"), then
the final twin is tuned on all days. The twin can then simulate "what if I eat this now / walk
after it" for this patient.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from sqlmodel import Session, select

from config.settings import get_settings
from src.clinical import loinc
from src.clinical.rules import clinical_rules
from src.db.models import Meal, Observation
from src.meals.engine import GI_FACTOR, foods

STEP_MIN = 5
PARAMS = ["basal", "dawn", "carb_sensitivity", "activity"]


def _cfg() -> dict:
    return clinical_rules()["personal_twin"]["glucose"]


# --------------------------------------------------------------------------- data

def _grid(session: Session, patient_id: str, days: int, now: datetime) -> tuple[pd.DataFrame, list[dict]]:
    """5-minute grid with glucose, heart rate; plus the meal list (time, effective carbs)."""
    start = now - timedelta(days=days)

    def series(var: str, device: str) -> pd.Series:
        rows = session.exec(select(Observation.effective_time, Observation.value).where(
            Observation.patient_id == patient_id, Observation.loinc_code == loinc.code(var),
            Observation.device == device, Observation.effective_time > start,
            Observation.effective_time <= now).order_by(Observation.effective_time)).all()
        if not rows:
            return pd.Series(dtype=float)
        s = pd.Series([v for _, v in rows], index=pd.DatetimeIndex([t for t, _ in rows]).tz_convert("UTC"))
        return s.resample(f"{STEP_MIN}min").mean()

    g, hr = series("glucose", "cgm"), series("heart_rate", "fitbit")
    if g.empty:
        return pd.DataFrame(columns=["glucose", "hr"]), []
    idx = pd.date_range(g.index.min(), now.astimezone(timezone.utc).replace(second=0, microsecond=0),
                        freq=f"{STEP_MIN}min", tz="UTC")
    df = pd.DataFrame({"glucose": g.reindex(idx), "hr": hr.reindex(idx) if not hr.empty else np.nan}, index=idx)
    # activity = heart rate above the patient's usual level over the previous 3 hours (walks show as bursts;
    # simply being awake vs asleep does not count as exercise)
    usual = df["hr"].rolling("3h", min_periods=6).median()
    df["exc"] = (df["hr"] - usual).clip(lower=0).fillna(0)
    meals = [{"time": m.time, "carbs": effective_carbs(m.items)} for m in session.exec(
        select(Meal).where(Meal.patient_id == patient_id, Meal.time > start - timedelta(hours=4),
                           Meal.time <= now)).all()]
    return df, meals


def effective_carbs(items: list[dict]) -> float:
    """Carbs weighted by glycaemic index category (low 0.7, medium 1.0, high 1.3)."""
    f = foods()
    total = 0.0
    for i in items:
        if i["food"] in f.index:
            total += float(f.loc[i["food"], "carbs_g"]) * float(i.get("servings", 1)) * \
                GI_FACTOR[f.loc[i["food"], "gi_category"]]
    return total


# --------------------------------------------------------------------------- features

def meal_curve(peak_min: float, n: int | None = None) -> np.ndarray:
    """Gamma-shaped meal response, 1.0 at the peak, over the meal duration."""
    c = _cfg()
    n = n or int(c["meal_duration_minutes"] / STEP_MIN)
    tau = np.arange(n) * STEP_MIN
    a = c["curve_shape"]
    return (tau / peak_min) ** a * np.exp(a * (1 - tau / peak_min))


def _features(df: pd.DataFrame, meals: list[dict], peak_min: float, rest_hr: float = 0.0) -> np.ndarray:
    n = len(df)
    curve = meal_curve(peak_min)
    meal_x = np.zeros(n)
    t0 = df.index[0]
    for m in meals:
        i = int((pd.Timestamp(m["time"]).tz_convert("UTC") - t0).total_seconds() // (STEP_MIN * 60))
        lo, hi = max(i, 0), min(i + len(curve), n)
        if hi > lo:
            meal_x[lo:hi] += m["carbs"] * curve[lo - i: hi - i]
    exc = df["exc"].fillna(0).to_numpy()
    mem = int(_cfg()["activity_memory_minutes"] / STEP_MIN)
    kernel = np.exp(-np.arange(mem * 3) / mem)
    act_x = np.convolve(exc, kernel)[:n]
    local = df.index.tz_convert(get_settings().timezone)
    hours = local.hour + local.minute / 60
    dawn_x = np.exp(-((hours - 6.5) / 1.5) ** 2)
    return np.column_stack([np.ones(n), dawn_x, meal_x, -act_x])


def _ridge(X: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, float]:
    """Ridge regression shrunk towards the population starting values (MAP estimate)."""
    pri = _cfg()["priors"]
    mu0 = np.array([pri[p]["mean"] for p in PARAMS], dtype=float)
    lam = (_cfg()["residual_sd"] / np.array([pri[p]["sd"] for p in PARAMS], dtype=float)) ** 2
    A = X.T @ X + np.diag(lam)
    beta = np.linalg.solve(A, X.T @ y + lam * mu0)
    sse = float(np.sum((y - X @ beta) ** 2) + np.sum(lam * (beta - mu0) ** 2))
    return beta, sse


def _fit(df: pd.DataFrame, meals: list[dict], rest_hr: float) -> dict:
    c = _cfg()
    ok = df["glucose"].notna().to_numpy()
    y = df["glucose"].to_numpy()[ok]
    best = None
    for peak in range(c["meal_peak_minutes"][0], c["meal_peak_minutes"][1] + 1, 5):
        X = _features(df, meals, peak, rest_hr)[ok]
        beta, sse = _ridge(X, y)
        if best is None or sse < best[2]:
            best = (peak, beta, sse)
    peak, beta, _ = best
    return {"peak_minutes": peak, **{p: float(b) for p, b in zip(PARAMS, beta)}}


def _predict(params: dict, df: pd.DataFrame, meals: list[dict], rest_hr: float = 0.0) -> np.ndarray:
    X = _features(df, meals, params["peak_minutes"], rest_hr)
    return X @ np.array([params[p] for p in PARAMS])


# --------------------------------------------------------------------------- public API

def population_params() -> dict:
    pri = _cfg()["priors"]
    lo, hi = _cfg()["meal_peak_minutes"]
    return {"peak_minutes": (lo + hi) // 2 // 5 * 5, **{p: float(pri[p]["mean"]) for p in PARAMS}}


def build(session: Session, patient_id: str, now: datetime | None = None) -> dict:
    """Tune the patient's glucose twin and check it against the most recent days."""
    c = _cfg()
    now = now or datetime.now(timezone.utc)
    df, meals = _grid(session, patient_id, c["window_days"], now)
    days = float(df["glucose"].notna().sum() * STEP_MIN / 1440) if len(df) else 0.0
    if days < c["min_days"] or df["glucose"].notna().sum() < 100:
        return {"available": False, "days_of_cgm": round(days, 1), "meals": len(meals),
                "params": population_params(), "personal": False,
                "reason": f"Needs at least {c['min_days']} days of CGM to tune the twin"}
    hr = df["hr"].dropna()
    rest_hr = float(hr.quantile(0.2)) if len(hr) else 70.0

    # 1. hold out the last days: tune on the rest, then replay the held-out days ("twin vs real")
    cut = df.index[-1] - pd.Timedelta(days=c["replay_days"])
    train, test = df[df.index <= cut], df[df.index > cut]
    replay, accuracy = None, None
    if train["glucose"].notna().sum() * STEP_MIN / 1440 >= c["min_days"] and test["glucose"].notna().sum() > 50:
        p_train = _fit(train, meals, rest_hr)
        pred = _predict(p_train, df, meals, rest_hr)
        # the twin knows yesterday's level: re-anchor the baseline once per day from the previous 24 h
        resid = df["glucose"] - pred
        offset = resid.rolling("24h", min_periods=48).mean().shift(1).reindex(df.index).ffill().fillna(0)
        day_start = pd.Series(df.index.tz_convert(get_settings().timezone).normalize(), index=df.index)
        offset = offset.groupby(day_start).transform("first")
        twin = pd.Series(pred, index=df.index) + offset
        real, sim = df["glucose"][df.index > cut], twin[df.index > cut]
        both = real.notna()
        err = (real[both] - sim[both]).abs()
        accuracy = {
            "mae": round(float(err.mean()), 1),
            "within_20_pct": round(float((err <= 20).mean() * 100), 1),
            "correlation": round(float(np.corrcoef(real[both], sim[both])[0, 1]), 2),
            "days": c["replay_days"],
        }
        replay = {"time": [t.isoformat() for t in real.index], "real": [None if np.isnan(v) else round(v) for v in real],
                  "twin": [round(float(v)) for v in sim]}

    # 2. final twin tuned on everything
    params = _fit(df, meals, rest_hr)
    pri = _cfg()["priors"]
    pull = {p: round(abs(params[p] - pri[p]["mean"]) / max(pri[p]["sd"], 1e-6), 2) for p in PARAMS}
    return {
        "available": True, "personal": True, "days_of_cgm": round(days, 1), "meals": len(meals),
        "rest_hr": round(rest_hr), "params": {k: round(v, 3) for k, v in params.items()},
        "population": population_params(), "shift_from_population_sd": pull,
        "accuracy": accuracy, "replay": replay,
        "explain": explain(params),
        "tuned_at": now.isoformat(),
    }


def explain(params: dict) -> dict:
    """Plain-language facts about this patient's glucose behaviour."""
    walk = walk_effect(params)
    rice = float(foods().loc["Steamed white rice", "carbs_g"]) * 2 * GI_FACTOR["high"]
    return {
        "between_meals": round(params["basal"]),
        "per_10g_carbs": round(params["carb_sensitivity"] * 10, 1),
        "peak_minutes": int(params["peak_minutes"]),
        "two_katori_rice_rise": round(params["carb_sensitivity"] * rice),
        "walk_15_min_lowers_by": round(walk),
        "morning_rise": round(params["dawn"]),
    }


def walk_effect(params: dict, minutes: int = 15) -> float:
    """Largest glucose fall from a brisk walk of `minutes` (mg/dL)."""
    c = _cfg()
    mem = int(c["activity_memory_minutes"] / STEP_MIN)
    exc = np.zeros(mem * 4)
    exc[: max(minutes // STEP_MIN, 1)] = c["walk_heart_rate_rise"]
    effect = np.convolve(exc, np.exp(-np.arange(mem * 3) / mem))[: len(exc)]
    return float(params["activity"] * effect.max())


def what_if(session: Session, patient_id: str, items: list[dict], walk_minutes: int = 0,
            walk_after_minutes: int = 30, hours: float = 4.0, now: datetime | None = None) -> dict:
    """Simulate this patient's glucose for the next hours if they eat `items` now
    (and optionally walk `walk_minutes`, starting `walk_after_minutes` after the meal)."""
    now = now or datetime.now(timezone.utc)
    twin = build(session, patient_id, now)
    params = twin["params"]
    df, meals = _grid(session, patient_id, 1, now)
    if df["glucose"].notna().sum() == 0:
        return {"available": False, "reason": "No recent CGM reading to start from"}
    n_future = int(hours * 60 / STEP_MIN)
    future_idx = pd.date_range(df.index[-1] + pd.Timedelta(minutes=STEP_MIN), periods=n_future,
                               freq=f"{STEP_MIN}min", tz="UTC")
    rest_hr = twin.get("rest_hr", 70)
    full = pd.concat([df, pd.DataFrame({"glucose": np.nan, "hr": rest_hr, "exc": 0.0}, index=future_idx)])
    eaten = effective_carbs(items)
    planned = meals + ([{"time": now, "carbs": eaten}] if eaten else [])
    walk = full.copy()
    if walk_minutes:
        w0 = now + timedelta(minutes=walk_after_minutes)
        mask = (walk.index >= w0) & (walk.index < w0 + timedelta(minutes=walk_minutes))
        walk.loc[mask, "exc"] = _cfg()["walk_heart_rate_rise"]

    def run(frame: pd.DataFrame, meal_list: list[dict]) -> pd.Series:
        pred = pd.Series(_predict(params, frame, meal_list, rest_hr), index=frame.index)
        last = df["glucose"].dropna()
        anchor = float(last.iloc[-1]) - float(pred.loc[last.index[-1]])  # start from the real reading
        return (pred + anchor).loc[future_idx].clip(40, 400)

    base, with_meal = run(full, meals), run(walk, planned)
    tz = ZoneInfo(get_settings().timezone)

    def summary(s: pd.Series) -> dict:
        peak_t = s.idxmax()
        return {"peak": round(float(s.max())), "peak_time": peak_t.astimezone(tz).strftime("%H:%M"),
                "minutes_above_180": int((s > 180).sum() * STEP_MIN), "lowest": round(float(s.min()))}

    return {
        "available": True, "personal": twin["personal"], "effective_carbs": round(eaten, 1),
        "start_glucose": round(float(df["glucose"].dropna().iloc[-1])),
        "time": [t.isoformat() for t in future_idx],
        "without_meal": [round(float(v)) for v in base], "with_plan": [round(float(v)) for v in with_meal],
        "summary": summary(with_meal), "summary_without": summary(base),
        "walk_minutes": walk_minutes, "params": params,
    }


def learning_curve(session: Session, patient_id: str, steps: tuple[int, ...] = (1, 2, 4, 6, 8, 10),
                   now: datetime | None = None) -> list[dict]:
    """How well the twin reproduces the last `replay_days` when it was tuned on only N earlier days.

    Shows the twin becoming more accurate as it learns the patient (the "progressive" twin).
    """
    c = _cfg()
    now = now or datetime.now(timezone.utc)
    df, meals = _grid(session, patient_id, c["window_days"], now)
    if df["glucose"].notna().sum() < 200:
        return []
    cut = df.index[-1] - pd.Timedelta(days=c["replay_days"])
    test_mask = df.index > cut
    out = []
    for n_days in steps:
        train = df[(df.index <= cut) & (df.index > cut - pd.Timedelta(days=n_days))]
        if train["glucose"].notna().sum() < 100:
            continue
        p = _fit(train, meals, 0.0)
        frame = df[df.index > cut - pd.Timedelta(days=n_days)]
        pred = pd.Series(_predict(p, frame, meals), index=frame.index)
        # anchor each held-out day to the previous day's level (as in build())
        real = frame["glucose"]
        resid = (real - pred).rolling("24h", min_periods=48).mean().shift(1).ffill().fillna(0)
        day = pd.Series(frame.index.tz_convert(get_settings().timezone).normalize(), index=frame.index)
        twin = pred + resid.groupby(day).transform("first")
        sel = test_mask[-len(frame):] & real.notna().to_numpy()
        err = (real[sel] - twin[sel]).abs()
        out.append({"days_of_data": n_days, "mae": round(float(err.mean()), 1),
                    "carb_sensitivity": round(p["carb_sensitivity"], 2), "peak_minutes": int(p["peak_minutes"])})
    return out
