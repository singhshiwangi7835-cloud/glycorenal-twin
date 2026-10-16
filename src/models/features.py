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
