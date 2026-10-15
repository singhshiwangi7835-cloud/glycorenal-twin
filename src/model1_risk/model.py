"""Model 1: risk prediction ("upcoming disease").

1. DKD risk in 3 years: onset (healthy kidneys today) or progression (CKD today)
2. HbA1c forecast in 3 months
3. Short-term hypo/hyper risk from CGM (rule-based)

Trained on the synthetic cohort by default; swap in NHANES/UCI data later.
"""

from __future__ import annotations

from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression, LogisticRegression
from sklearn.metrics import mean_absolute_error, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier

from src.pipeline.synthetic import FEATURES, generate_cohort

MODEL_PATH = Path("models/model1.joblib")


def train(df: pd.DataFrame | None = None, save: bool = True) -> dict:
    df = df if df is not None else generate_cohort()
    X, y = df[FEATURES], df["dkd_event_3y"]
    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.2, random_state=0, stratify=y)

    logreg = make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000)).fit(X_tr, y_tr)
    xgb = XGBClassifier(
        n_estimators=300, max_depth=3, learning_rate=0.05, subsample=0.9,
        eval_metric="logloss", random_state=0,
    ).fit(X_tr, y_tr)

    auc_lr = roc_auc_score(y_te, logreg.predict_proba(X_te)[:, 1])
    auc_xgb = roc_auc_score(y_te, xgb.predict_proba(X_te)[:, 1])
    best, best_name = (xgb, "xgboost") if auc_xgb > auc_lr else (logreg, "logistic_regression")

    a1c_X = df[FEATURES]
    a1c = LinearRegression().fit(a1c_X.loc[X_tr.index], df.loc[X_tr.index, "hba1c_3m"])
    mae = mean_absolute_error(df.loc[X_te.index, "hba1c_3m"], a1c.predict(a1c_X.loc[X_te.index]))

    bundle = {
        "dkd_model": best,
        "dkd_model_name": best_name,
        "hba1c_model": a1c,
        "features": FEATURES,
        "metrics": {"auc_logreg": round(auc_lr, 3), "auc_xgboost": round(auc_xgb, 3),
                    "hba1c_mae": round(mae, 3), "n_train": len(X_tr)},
    }
    if save:
        MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(bundle, MODEL_PATH)
    return bundle


_cache: dict | None = None


def load() -> dict:
    global _cache
    if _cache is None:
        _cache = joblib.load(MODEL_PATH) if MODEL_PATH.exists() else train()
    return _cache


def _risk_band(p: float) -> str:
    if p < 0.10:
        return "low"
    if p < 0.25:
        return "moderate"
    if p < 0.45:
        return "high"
    return "very_high"


def glycemic_event_risk(cgm: dict | None) -> dict:
    if not cgm:
        return {"hypo": "unknown", "hyper": "unknown", "reason": "no CGM data"}
    hypo = "high" if cgm["tbr_severe_pct"] >= 1 or cgm["tbr_pct"] >= 4 else (
        "moderate" if cgm["tbr_pct"] >= 1 or cgm["cv_pct"] > 36 else "low")
    hyper = "high" if cgm["tar_severe_pct"] >= 5 or cgm["tar_pct"] >= 50 else (
        "moderate" if cgm["tar_pct"] >= 25 else "low")
    return {"hypo": hypo, "hyper": hyper}


def predict_features(features: dict) -> dict:
    m = load()
    X = pd.DataFrame([features])[m["features"]]
    p = float(m["dkd_model"].predict_proba(X)[0, 1])
    return {
        "dkd_risk_3y": round(p, 3),
        "dkd_risk_band": _risk_band(p),
        "hba1c_3m_forecast": round(float(m["hba1c_model"].predict(X)[0]), 1),
    }


def predict(state: dict) -> dict:
    out = predict_features(state["features"])
    out["outcome_type"] = "progression" if state["derived"]["has_ckd"] else "onset"
    out["glycemic_events"] = glycemic_event_risk(state.get("cgm"))
    out["model"] = load()["dkd_model_name"]
    return out


LABELS = {"hba1c": "HbA1c above 7%", "sbp": "Systolic BP above 125", "log_uacr": "Albuminuria (UACR)",
          "bmi": "BMI above 24", "smoker": "Smoking"}


def explain(state: dict, top: int = 4) -> list[dict]:
    """Simple what-drives-the-risk: change each modifiable factor to target, see the delta."""
    base = predict_features(state["features"])["dkd_risk_3y"]
    targets = {"hba1c": 7.0, "sbp": 125, "log_uacr": float(np.log(20)), "bmi": 24.0, "smoker": 0}
    drivers = []
    for k, v in targets.items():
        f = dict(state["features"])
        if (k == "smoker" and f[k] == 0) or (k != "smoker" and f[k] <= v):
            continue
        f[k] = v
        delta = base - predict_features(f)["dkd_risk_3y"]
        if delta > 0.005:
            drivers.append({"factor": LABELS[k], "contribution": round(delta, 3)})
    return sorted(drivers, key=lambda d: -d["contribution"])[:top]


if __name__ == "__main__":
    b = train()
    print(f"Trained Model 1 ({b['dkd_model_name']}): {b['metrics']}")
