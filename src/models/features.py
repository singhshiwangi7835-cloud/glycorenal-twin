"""Feature engineering shared by training (scripts/train_models.py) and live prediction.

Keeping one copy means the live twin computes features exactly as the models were trained.

Glucose forecast input: a 5-minute series with columns
  time, glucose (mg/dL), carbs_g (grams eaten at that time, else 0), activity (steps per 5 min,
  or a METs-based equivalent for CGMacros)
"""

from __future__ import annotations

import numpy as np
import pandas as pd

GLUCOSE_LAGS = [5, 10, 15, 20, 30, 45, 60, 90, 120]  # minutes back
GLUCOSE_FEATURES = (
    ["g_now"] + [f"g_lag_{m}" for m in GLUCOSE_LAGS]
    + ["slope_15", "slope_30", "mean_2h", "sd_2h", "min_2h", "max_2h",
       "tod_sin", "tod_cos", "carbs_30m", "carbs_2h", "activity_30m", "activity_2h"]
)
HORIZONS = {"30": 6, "60": 12}  # minutes -> number of 5-min steps ahead


def glucose_frame(series: pd.DataFrame) -> pd.DataFrame:
    """Turn a regular 5-minute series into one feature row per time point.

    Rows without 2 hours of history get NaN lag features (XGBoost handles missing values).
    """
    s = series.sort_values("time").reset_index(drop=True)
    g = s["glucose"].astype(float)
    f = pd.DataFrame({"time": s["time"], "g_now": g})
    for m in GLUCOSE_LAGS:
        f[f"g_lag_{m}"] = g.shift(m // 5)
    f["slope_15"] = (g - g.shift(3)) / 15
    f["slope_30"] = (g - g.shift(6)) / 30
    roll = g.rolling(24, min_periods=6)
    f["mean_2h"], f["sd_2h"], f["min_2h"], f["max_2h"] = roll.mean(), roll.std(), roll.min(), roll.max()
    minutes = pd.to_datetime(s["time"]).dt.hour * 60 + pd.to_datetime(s["time"]).dt.minute
    f["tod_sin"] = np.sin(2 * np.pi * minutes / 1440)
    f["tod_cos"] = np.cos(2 * np.pi * minutes / 1440)
    carbs = s.get("carbs_g", pd.Series(0.0, index=s.index)).fillna(0).astype(float)
    act = s.get("activity", pd.Series(0.0, index=s.index)).fillna(0).astype(float)
    f["carbs_30m"] = carbs.rolling(6, min_periods=1).sum()
    f["carbs_2h"] = carbs.rolling(24, min_periods=1).sum()
    f["activity_30m"] = act.rolling(6, min_periods=1).sum()
    f["activity_2h"] = act.rolling(24, min_periods=1).sum()
    return f


def glucose_training_rows(series: pd.DataFrame) -> pd.DataFrame:
    """Feature rows plus targets y_30 / y_60 (glucose 30 and 60 minutes later)."""
    f = glucose_frame(series)
    for name, steps in HORIZONS.items():
        f[f"y_{name}"] = f["g_now"].shift(-steps)
    return f.dropna(subset=["g_lag_120", "y_30", "y_60"])


# --------------------------------------------------------------------------- 90-minute spike
# "Will glucose go above the spike line within the next 90 minutes?" Uses the glucose features
# above plus the patient's HABITS from previous days at the same time of day (how many carbs they
# usually eat in the coming 90 minutes, how high they usually go), so it can warn before a meal
# is even logged. Horizon and spike line: config/alerts.yaml -> spike_forecast.
SPIKE_EXTRA = ["habit_carbs_next_90m", "habit_peak_next_90m", "habit_spike_rate_next_90m"]
SPIKE_FEATURES = GLUCOSE_FEATURES + SPIKE_EXTRA
HABIT_DAYS = 7


def _regular(series: pd.DataFrame) -> pd.DataFrame:
    """Put readings on a regular 5-minute grid (gaps become NaN) so 'same time yesterday' is a shift."""
    s = series.copy()
    s["time"] = pd.to_datetime(s["time"])
    s = s.set_index("time").sort_index()
    agg = {"glucose": "mean"}
    for c in ("carbs_g", "activity"):
        if c in s:
            agg[c] = "sum"
    g = s[list(agg)].resample("5min").agg(agg)
    return g.reset_index()


def spike_frame(series: pd.DataFrame, horizon_min: int = 90, spike_above: float = 250) -> pd.DataFrame:
    """Feature rows for the spike model, on a regular 5-minute grid."""
    s = _regular(series)
    f = glucose_frame(s)
    steps = horizon_min // 5
    g = s["glucose"].astype(float)
    carbs = s.get("carbs_g", pd.Series(0.0, index=s.index)).fillna(0).astype(float)
    # value over the window [t, t + horizon) computed at each t (looks forward; used only via past days)
    fwd_carbs = carbs[::-1].rolling(steps, min_periods=1).sum()[::-1]
    fwd_peak = g[::-1].rolling(steps, min_periods=steps // 2).max()[::-1]
    day = 288
    past_c = pd.concat([fwd_carbs.shift(day * d) for d in range(1, HABIT_DAYS + 1)], axis=1)
    past_p = pd.concat([fwd_peak.shift(day * d) for d in range(1, HABIT_DAYS + 1)], axis=1)
    f["habit_carbs_next_90m"] = past_c.mean(axis=1)
    f["habit_peak_next_90m"] = past_p.mean(axis=1)
    f["habit_spike_rate_next_90m"] = (past_p >= spike_above).astype(float).where(past_p.notna()).mean(axis=1)
    f["_future_peak"] = g[::-1].shift(1).rolling(steps, min_periods=steps // 2).max()[::-1]  # (t, t+90]
    return f


def habit_features(series: pd.DataFrame, at, horizon_min: int = 90, spike_above: float = 250) -> dict:
    """Habit features for ONE moment `at` straight from timestamps (live use; same meaning as in
    spike_frame): what happened in [at - d days, at - d days + horizon) for the previous 7 days."""
    s = series.copy()
    s["time"] = pd.to_datetime(s["time"])
    at = pd.Timestamp(at)
    carbs = s.get("carbs_g", pd.Series(0.0, index=s.index)).fillna(0)
    c_list, p_list = [], []
    for d in range(1, HABIT_DAYS + 1):
        lo = at - pd.Timedelta(days=d)
        m = (s["time"] >= lo) & (s["time"] < lo + pd.Timedelta(minutes=horizon_min))
        if m.sum() >= horizon_min // 10:  # at least half the readings
            c_list.append(float(carbs[m].sum()))
            p_list.append(float(s.loc[m, "glucose"].max()))
    if not c_list:
        return {"habit_carbs_next_90m": np.nan, "habit_peak_next_90m": np.nan, "habit_spike_rate_next_90m": np.nan}
    return {"habit_carbs_next_90m": float(np.mean(c_list)), "habit_peak_next_90m": float(np.mean(p_list)),
            "habit_spike_rate_next_90m": float(np.mean([p >= spike_above for p in p_list]))}


def spike_training_rows(series: pd.DataFrame, horizon_min: int = 90, spike_above: float = 250) -> pd.DataFrame:
    """Rows where glucose is below the spike line now; y_spike = 1 if it crosses it within the horizon."""
    f = spike_frame(series, horizon_min, spike_above)
    f = f.dropna(subset=["g_now", "g_lag_60", "_future_peak"])
    f = f[f["g_now"] < spike_above].copy()
    f["y_spike"] = (f["_future_peak"] >= spike_above).astype(int)
    return f
