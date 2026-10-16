"""Train all twin models (CLAUDE.md section 7) and write the model card.

Usage:  python scripts/train_models.py            # all models (~5 min on a laptop)
        python scripts/train_models.py glucose    # just one: dkd_current | dkd | hba1c | glucose

Needs: data/processed/nhanes_diabetes.csv (python -m src.pipeline.nhanes_merge)
       data/synthetic/cohort_visits.csv   (python scripts/build_synthetic_cohort.py)
Optional: data/raw/cgmacros/ (glucose model uses CGMacros if present, else synthetic CGM)

Outputs: models/<name>.joblib, models/metrics.json, models/model_card.md (+ copy in docs/),
         docs/models/*.png (ROC, calibration, feature importance, forecast example)
"""

from __future__ import annotations

import json
import shutil
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import joblib  # noqa: E402
import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.calibration import calibration_curve  # noqa: E402
from sklearn.impute import SimpleImputer  # noqa: E402
from sklearn.isotonic import IsotonicRegression  # noqa: E402
from sklearn.linear_model import LogisticRegression  # noqa: E402
from sklearn.metrics import (brier_score_loss, mean_absolute_error, roc_auc_score,  # noqa: E402
                             roc_curve)
from sklearn.model_selection import StratifiedKFold, cross_val_predict  # noqa: E402
from sklearn.pipeline import make_pipeline  # noqa: E402
from sklearn.preprocessing import StandardScaler  # noqa: E402
from xgboost import XGBClassifier, XGBRegressor  # noqa: E402

from src.clinical.egfr import egfr_ckd_epi_2021  # noqa: E402
from src.models.features import GLUCOSE_FEATURES, glucose_training_rows  # noqa: E402
from src.pipeline import cgm_synth, cgmacros, cohort  # noqa: E402

MODELS = ROOT / "models"
PLOTS = ROOT / "docs" / "models"
VERSION = date.today().isoformat()
RNG = np.random.default_rng(7)

NHANES_FEATURES = ["age", "male", "asian", "dm_duration_yrs", "hba1c", "sbp", "dbp", "bmi",
                   "waist", "smoker", "hypertension", "on_insulin", "on_metformin",
                   "on_sulfonylurea", "on_sglt2i", "on_glp1ra", "on_acei_arb", "on_statin"]

LABELS = {
    "age": "Age", "male": "Male sex", "asian": "Asian ethnicity", "dm_duration_yrs": "Years with diabetes",
    "hba1c": "HbA1c", "hba1c_change_1y": "HbA1c change (1 yr)", "tir_pct": "Time in range",
    "sbp": "Systolic BP", "dbp": "Diastolic BP", "bmi": "BMI", "waist": "Waist", "egfr": "eGFR",
    "egfr_slope_1y": "eGFR change (1 yr)", "log_uacr": "UACR (log)", "smoker": "Smoking",
    "family_history": "Family history of CKD", "hypertension": "Hypertension",
    "adherence": "Medicine adherence", "on_sglt2i": "On SGLT2i", "on_glp1ra": "On GLP-1 RA",
    "on_acei_arb": "On ACEi/ARB", "on_finerenone": "On finerenone", "on_insulin": "On insulin",
    "on_sulfonylurea": "On sulfonylurea", "on_metformin": "On metformin", "on_statin": "On statin",
}


# --------------------------------------------------------------------------- helpers

def split_by_patient(ids: pd.Series, fractions=(0.6, 0.2, 0.2)) -> list[np.ndarray]:
    """Train / calibration / test masks that never put one patient in two sets."""
    uniq = np.array(ids.unique(), dtype=object)
    RNG.shuffle(uniq)
    cuts = np.cumsum([int(f * len(uniq)) for f in fractions[:-1]])
    groups = np.split(uniq, cuts)
    return [ids.isin(set(g)).to_numpy() for g in groups]


def xgb_classifier() -> XGBClassifier:
    return XGBClassifier(n_estimators=300, max_depth=3, learning_rate=0.05, subsample=0.9,
                         colsample_bytree=0.9, min_child_weight=5, eval_metric="logloss",
                         random_state=0, n_jobs=4)


def importance(model, features: list[str]) -> list[dict]:
    gain = model.get_booster().get_score(importance_type="gain")
    total = sum(gain.values()) or 1
    rows = [{"feature": f, "label": LABELS.get(f, f), "share": round(gain.get(f, 0) / total, 3)}
            for f in features]
    return sorted(rows, key=lambda r: -r["share"])


def plot_classifier(name: str, title: str, y, p, imp: list[dict]) -> None:
    PLOTS.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(1, 3, figsize=(15, 4.4))
    fpr, tpr, _ = roc_curve(y, p)
    ax[0].plot(fpr, tpr, color="#0b6e99", lw=2)
    ax[0].plot([0, 1], [0, 1], ls="--", color="#9aa5b1")
    ax[0].set(title=f"ROC (AUROC {roc_auc_score(y, p):.2f})", xlabel="1 - specificity",
              ylabel="Sensitivity")
    frac, mean_p = calibration_curve(y, p, n_bins=10, strategy="quantile")
    ax[1].plot(mean_p, frac, "o-", color="#0b6e99")
    ax[1].plot([0, 1], [0, 1], ls="--", color="#9aa5b1")
    ax[1].set(title="Calibration", xlabel="Predicted risk", ylabel="Observed rate")
    top = imp[:10][::-1]
    ax[2].barh([r["label"] for r in top], [r["share"] for r in top], color="#0b6e99")
    ax[2].set(title="Top features (XGBoost gain)")
    fig.suptitle(title)
    fig.tight_layout()
    fig.savefig(PLOTS / f"{name}.png", dpi=110)
    plt.close(fig)


def save(name: str, bundle: dict) -> None:
    MODELS.mkdir(exist_ok=True)
    bundle.update(name=name, version=VERSION)
    joblib.dump(bundle, MODELS / f"{name}.joblib")


# --------------------------------------------------------------------------- models

def train_dkd_current() -> dict:
    """Has DKD now, from NHANES (real data), using NO kidney labs as inputs."""
    df = pd.read_csv(ROOT / "data" / "processed" / "nhanes_diabetes.csv")
    X, y = df[NHANES_FEATURES], df["has_dkd"]
    cv = StratifiedKFold(5, shuffle=True, random_state=0)
    lr = make_pipeline(SimpleImputer(strategy="median"), StandardScaler(),
                       LogisticRegression(max_iter=2000))
    xgb = xgb_classifier()
    p_lr = cross_val_predict(lr, X, y, cv=cv, method="predict_proba")[:, 1]
    p_xgb = cross_val_predict(xgb, X, y, cv=cv, method="predict_proba")[:, 1]
    auc_lr, auc_xgb = roc_auc_score(y, p_lr), roc_auc_score(y, p_xgb)
    best_name, best, p_best = (("xgboost", xgb, p_xgb) if auc_xgb > auc_lr
                               else ("logistic_regression", lr, p_lr))
    best.fit(X, y)
    xgb.fit(X, y)
    imp = importance(xgb, NHANES_FEATURES)
    asian = df["asian"] == 1
    metrics = {
        "data": "NHANES 2017-Mar 2020, adults with diabetes", "n": int(len(df)),
        "prevalence": round(float(y.mean()), 3),
        "auroc_logistic_cv5": round(auc_lr, 3), "auroc_xgboost_cv5": round(auc_xgb, 3),
        "auroc_best_asian_subgroup": round(roc_auc_score(y[asian], p_best[asian]), 3),
        "n_asian": int(asian.sum()), "brier_best": round(brier_score_loss(y, p_best), 3),
        "chosen": best_name, "top_features": imp[:6],
    }
    plot_classifier("dkd_current", f"dkd_current: has DKD now, NHANES (5-fold CV, {best_name})",
                    y, p_best, imp)
    save("dkd_current", {"model": best, "features": NHANES_FEATURES, "metrics": metrics})
    return metrics


def _uci_sanity(model: XGBClassifier, iso: IsotonicRegression) -> dict:
    """Score UCI CKD adults (Apollo Hospitals, India) and check risk is higher in CKD."""
    path = ROOT / "data" / "raw" / "uci_ckd" / "uci_ckd.csv"
    if not path.exists():
        return {"used": False}
    u = pd.read_csv(path)
    u = u[(u["age"] >= 18) & u["sc"].notna()].copy()
    u["egfr"] = [(egfr_ckd_epi_2021(c, a, "M") + egfr_ckd_epi_2021(c, a, "F")) / 2  # sex unknown
                 for c, a in zip(u["sc"], u["age"])]
    alb_to_uacr = {0: 10, 1: 50, 2: 150, 3: 400, 4: 800, 5: 1500}       # dipstick grade -> mg/g
    u["log_uacr"] = np.log(u["al"].map(alb_to_uacr).fillna(10))
    u["hba1c"] = ((u["bgr"].fillna(140) + 46.7) / 28.7).clip(5, 14)    # ADAG, random glucose: crude
    feats = pd.DataFrame({
        "age": u["age"], "male": 0.5, "dm_duration_yrs": 8, "hba1c": u["hba1c"],
        "hba1c_change_1y": 0, "tir_pct": 70 - (u["hba1c"] - 7) * 12.5,
        "sbp": u["bp"].fillna(80) * 1.6, "bmi": 25, "egfr": u["egfr"], "egfr_slope_1y": 0,
        "log_uacr": u["log_uacr"], "smoker": 0, "family_history": 0,
        "hypertension": (u["htn"] == "yes").astype(int), "adherence": 0.7,
        "on_sglt2i": 0, "on_glp1ra": 0, "on_acei_arb": 0, "on_finerenone": 0, "on_insulin": 0,
        "on_sulfonylurea": 0,
    })[cohort.DKD_FEATURES]
    risk = iso.predict(model.predict_proba(feats)[:, 1])
    y = (u["class"] == "ckd").astype(int)
    twin_ckd = ((u["egfr"] < 60) | (u["al"] >= 1)).astype(int)
    return {"used": True, "n_adults": int(len(u)),
            "auroc_risk_vs_ckd_label": round(roc_auc_score(y, risk), 3),
            "agreement_twin_kdigo_vs_label": round(float((twin_ckd == y).mean()), 3),
            "note": "UCI has no sex, HbA1c or UACR: sex averaged, HbA1c from random glucose, "
                    "UACR from albumin dipstick. Label is CKD now, not progression."}


def train_dkd(kind: str, landmarks: pd.DataFrame) -> dict:
    """dkd_onset (no DKD at landmark) or dkd_progression (DKD at landmark), synthetic cohort."""
    d = landmarks[landmarks["has_dkd"] == (1 if kind == "progression" else 0)].reset_index(drop=True)
    X, y = d[cohort.DKD_FEATURES], d["event"]
    tr, cal, te = split_by_patient(d["patient_id"])
    xgb = xgb_classifier().fit(X[tr], y[tr])
    iso = IsotonicRegression(out_of_bounds="clip", y_min=0.001, y_max=0.999)
    iso.fit(xgb.predict_proba(X[cal])[:, 1], y[cal])
    p = iso.predict(xgb.predict_proba(X[te])[:, 1])
    lr = make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000)).fit(X[tr], y[tr])
    imp = importance(xgb, cohort.DKD_FEATURES)
    metrics = {
        "data": "synthetic Indian T2DM cohort (landmarks at year 1 and 2, 3-year follow-up)",
        "n_train": int(tr.sum()), "n_calibration": int(cal.sum()), "n_test": int(te.sum()),
        "event_rate": round(float(y.mean()), 3),
        "auroc_test": round(roc_auc_score(y[te], p), 3),
        "auroc_logistic_test": round(roc_auc_score(y[te], lr.predict_proba(X[te])[:, 1]), 3),
        "brier_test": round(brier_score_loss(y[te], p), 3), "top_features": imp[:6],
    }
    name = f"dkd_{kind}"
    if kind == "progression":
        metrics["uci_sanity_check"] = _uci_sanity(xgb, iso)
    title = {"onset": "dkd_onset: DKD within 3 years (kidneys healthy now)",
             "progression": "dkd_progression: KDIGO worsening or eGFR -30% within 3 years"}[kind]
    plot_classifier(name, f"{title}, synthetic test set", y[te], p, imp)
    save(name, {"model": xgb, "calibrator": iso, "features": cohort.DKD_FEATURES,
                "metrics": metrics})
    return metrics


def train_hba1c(visits: pd.DataFrame) -> dict:
    d = cohort.hba1c_pairs(visits).reset_index(drop=True)
    X, y = d[cohort.HBA1C_FEATURES], d["hba1c_next"]
    tr, _, te = split_by_patient(d["patient_id"], (0.8, 0.0, 0.2))
    m = XGBRegressor(n_estimators=400, max_depth=4, learning_rate=0.05, subsample=0.9,
                     random_state=0, n_jobs=4).fit(X[tr], y[tr])
    pred = m.predict(X[te])
    resid = y[te] - pred
    new = X[te]["new_glucose_drug"] == 1
    imp = importance(m, cohort.HBA1C_FEATURES)
    metrics = {
        "data": "synthetic Indian T2DM cohort, quarterly visit pairs",
        "n_train": int(tr.sum()), "n_test": int(te.sum()),
        "mae_test": round(mean_absolute_error(y[te], pred), 3),
        "mae_no_change_baseline": round(mean_absolute_error(y[te], X[te]["hba1c"]), 3),
        "mae_when_new_drug": round(mean_absolute_error(y[te][new], pred[new.to_numpy()]), 3),
        "mae_when_new_drug_no_change_baseline": round(
            mean_absolute_error(y[te][new], X[te]["hba1c"][new]), 3),
        "n_test_new_drug": int(new.sum()),
        "interval_80pct": [round(float(np.quantile(resid, 0.1)), 2),
                           round(float(np.quantile(resid, 0.9)), 2)],
        "top_features": imp[:6],
    }
    PLOTS.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(1, 2, figsize=(11, 4.4))
    ax[0].scatter(y[te], pred, s=4, alpha=0.3, color="#0b6e99")
    ax[0].plot([5, 14], [5, 14], ls="--", color="#9aa5b1")
    ax[0].set(title=f"HbA1c in 3 months (MAE {metrics['mae_test']}%)", xlabel="Actual %",
              ylabel="Predicted %")
    top = imp[:10][::-1]
    ax[1].barh([r["label"] if r["feature"] in LABELS else r["feature"] for r in top],
               [r["share"] for r in top], color="#0b6e99")
    ax[1].set(title="Top features (XGBoost gain)")
    fig.tight_layout()
    fig.savefig(PLOTS / "hba1c_forecast.png", dpi=110)
    plt.close(fig)
    save("hba1c_forecast", {"model": m, "features": cohort.HBA1C_FEATURES, "metrics": metrics,
                            "residual_q10_q90": metrics["interval_80pct"]})
    return metrics


def _glucose_series() -> tuple[list[tuple[str, pd.DataFrame]], str]:
    if cgmacros.available():
        series = []
        for pid in cgmacros.participant_ids():
            s = cgmacros.load_participant(pid)
            if s["glucose"].notna().sum() > 500:
                series.append((pid, s))
        return series, f"CGMacros v1.0.0 ({len(series)} participants)"
    series = []
    for i in range(40):  # synthetic patients across the HbA1c range
        hba1c = float(np.clip(RNG.normal(8.0, 1.3), 5.8, 12))
        r, _ = cgm_synth.generate(days=14, hba1c=hba1c, cv_target=float(RNG.uniform(0.22, 0.42)),
                                  steps_per_day=int(RNG.uniform(2000, 9000)), seed=1000 + i)
        if i % 3 == 0:  # a third of patients (as if on sulfonylurea / insulin) get some hypos
            for _ in range(int(RNG.integers(3, 7))):
                r = cgm_synth.inject_hypo(r, int(RNG.integers(300, len(r) - 30)),
                                          nadir=float(RNG.uniform(48, 66)))
        r = r.rename(columns={"steps": "activity"})
        series.append((f"SYN-CGM-{i:02d}", r))
    return series, "synthetic CGM (40 simulated patients x 14 days); CGMacros not downloaded yet"


def train_glucose() -> dict:
    series, source = _glucose_series()
    rows = []
    for pid, s in series:
        f = glucose_training_rows(s)
        f["pid"] = pid
        rows.append(f)
    d = pd.concat(rows, ignore_index=True)
    tr, _, te = split_by_patient(d["pid"], (0.8, 0.0, 0.2))
    models, metrics = {}, {"data": source, "n_train_rows": int(tr.sum()), "n_test_rows": int(te.sum())}
    for h in ("30", "60"):
        y = d[f"y_{h}"]
        m = XGBRegressor(n_estimators=300, max_depth=5, learning_rate=0.08, subsample=0.9,
                         random_state=0, n_jobs=4).fit(d.loc[tr, GLUCOSE_FEATURES], y[tr])
        pred = m.predict(d.loc[te, GLUCOSE_FEATURES])
        actual, now = y[te].to_numpy(), d.loc[te, "g_now"].to_numpy()
        hypo_true, hypo_pred = actual < 70, pred < 80   # warn a little early (80) for safety
        metrics[f"plus_{h}min"] = {
            "mae": round(mean_absolute_error(actual, pred), 1),
            "rmse": round(float(np.sqrt(np.mean((actual - pred) ** 2))), 1),
            "mae_persistence_baseline": round(mean_absolute_error(actual, now), 1),
            "hypo_events_in_test": int(hypo_true.sum()),
            "hypo_sensitivity": round(float(hypo_pred[hypo_true].mean()), 3) if hypo_true.any() else None,
            "hypo_warnings_correct": round(float(hypo_true[hypo_pred].mean()), 3) if hypo_pred.any() else None,
        }
        models[h] = m
    # example plot: one test patient, one day
    pid = d.loc[te, "pid"].iloc[0]
    ex = d[d["pid"] == pid].iloc[:288]
    fig, ax = plt.subplots(figsize=(12, 4))
    ax.plot(ex["time"], ex["g_now"], color="#1f2933", lw=1.5, label="CGM")
    ax.plot(pd.to_datetime(ex["time"]) + pd.Timedelta(minutes=30),
            models["30"].predict(ex[GLUCOSE_FEATURES]), color="#0b6e99", lw=1.2,
            label="forecast made 30 min earlier")
    ax.axhspan(70, 180, color="#2e7d32", alpha=0.07)
    ax.set(title=f"Glucose forecast example ({pid})", ylabel="mg/dL")
    ax.legend()
    fig.tight_layout()
    PLOTS.mkdir(parents=True, exist_ok=True)
    fig.savefig(PLOTS / "glucose_forecast.png", dpi=110)
    plt.close(fig)
    save("glucose_forecast", {"models": models, "features": GLUCOSE_FEATURES, "metrics": metrics})
    return metrics


# --------------------------------------------------------------------------- model card

def write_model_card(m: dict) -> None:
    def pct(x):
        return f"{x:.0%}" if isinstance(x, (int, float)) else "n/a"

    cur, on, pr = m.get("dkd_current", {}), m.get("dkd_onset", {}), m.get("dkd_progression", {})
    a1c, glu = m.get("hba1c_forecast", {}), m.get("glucose_forecast", {})
    uci = pr.get("uci_sanity_check", {})

    def feats(x):
        return ", ".join(f"{f['label']} ({f['share']:.0%})" for f in x.get("top_features", [])[:5])

    g30, g60 = glu.get("plus_30min", {}), glu.get("plus_60min", {})
    card = f"""# GlycoRenal Twin: model card

Version {VERSION}. Generated by `scripts/train_models.py`; numbers below are from that run.
Prototype for the Digital Twin Challenge 2026. **Decision support only; not for clinical use.**

## Summary

| Model | Predicts | Trained on | Result |
|---|---|---|---|
| `dkd_current` | Has DKD now (eGFR < 60 or UACR >= 30) from non-kidney data | **Real data:** NHANES 2017-Mar 2020, {cur.get('n')} adults with diabetes | AUROC {cur.get('auroc_logistic_cv5')} (logistic) / {cur.get('auroc_xgboost_cv5')} (XGBoost), 5-fold CV; Asian subgroup (n={cur.get('n_asian')}) {cur.get('auroc_best_asian_subgroup')} |
| `dkd_onset` | DKD within 3 years, kidneys healthy now | Synthetic Indian cohort | AUROC {on.get('auroc_test')} (test), Brier {on.get('brier_test')}, event rate {pct(on.get('event_rate'))} |
| `dkd_progression` | KDIGO stage worse or eGFR down 30% within 3 years | Synthetic cohort; UCI CKD (India) sanity check | AUROC {pr.get('auroc_test')} (test), Brier {pr.get('brier_test')}; UCI risk-vs-CKD AUROC {uci.get('auroc_risk_vs_ckd_label', 'n/a')} |
| `hba1c_forecast` | HbA1c in 3 months | Synthetic cohort | MAE {a1c.get('mae_test')}% vs {a1c.get('mae_no_change_baseline')}% for "no change"; when a drug is added {a1c.get('mae_when_new_drug')}% vs {a1c.get('mae_when_new_drug_no_change_baseline')}%; 80% of errors within {a1c.get('interval_80pct')} |
| `glucose_forecast` | CGM glucose +30 / +60 min | {glu.get('data')} | MAE {g30.get('mae')} / {g60.get('mae')} mg/dL vs {g30.get('mae_persistence_baseline')} / {g60.get('mae_persistence_baseline')} for "stays the same" |

Plots (ROC, calibration, top features, forecast example): `docs/models/`.

## Details

**dkd_current (real-data evidence).** Inputs exclude creatinine, eGFR and UACR, so the model
shows how well routine risk factors flag existing kidney disease. Top features: {feats(cur)}.
Prevalence {pct(cur.get('prevalence'))}. Caveats: single lab measurement (not confirmed over 3
months); survey weights not applied; "on ACEi/ARB" partly reflects treatment *because of* DKD;
US population (only {cur.get('n_asian')} non-Hispanic Asian adults, none identified as Indian).

**dkd_onset / dkd_progression.** XGBoost + isotonic calibration on a separate calibration set,
split by patient (60/20/20). Glycaemic features (HbA1c, HbA1c change, time in range) feed the
kidney model, linking Track A to Track B. Top onset features: {feats(on)}. Top progression
features: {feats(pr)}. Logistic regression comparison: onset {on.get('auroc_logistic_test')},
progression {pr.get('auroc_logistic_test')}.
**The cohort is simulated** from the assumptions in `config/clinical_rules.yaml -> cohort`; the
eGFR-decline weights for HbA1c, BP, age, smoking, BMI and diabetes duration were re-scaled to
NHANES odds ratios (`data/synthetic/calibration.json`). High AUROC here means the model learned
the simulator's rules, **not** that it predicts real Indian patients' kidneys. Drug effects in the
simulator use trial hazard ratios (DAPA-CKD, FLOW, FIDELIO-DKD, RENAAL), all `verified: false`.

**UCI CKD sanity check** ({uci.get('n_adults', 'n/a')} adults, Apollo Hospitals): {uci.get('note', '')}
Risk scores separate CKD from non-CKD with AUROC {uci.get('auroc_risk_vs_ckd_label', 'n/a')};
the twin's eGFR/KDIGO rule agrees with the hospital label in
{pct(uci.get('agreement_twin_kdigo_vs_label'))} of patients. In UCI every diabetic patient has CKD,
so this checks direction and plumbing, not diabetic progression.

**hba1c_forecast.** XGBoost on current HbA1c, recent change, GMI, time in range, adherence,
BMI, eGFR, current drug classes and "new glucose drug started". Top features: {feats(a1c)}.
Synthetic, so it reproduces the simulator's adherence and drug-effect assumptions.

**glucose_forecast.** XGBoost on the last 2 hours of CGM (lags, slopes, mean/SD), time of day,
carbs eaten and activity. Split by person. Hypo warning = forecast < 80 mg/dL:
+30 min sensitivity {g30.get('hypo_sensitivity')}, warnings correct {g30.get('hypo_warnings_correct')}
({g30.get('hypo_events_in_test')} hypo readings in test). Data: {glu.get('data')}.
The model alone can miss a steady fall it never saw in training (it may expect a rebound), so the
live twin adds a **rule-based safety net** (`src/models/t2dm.py`): a hypo warning also fires when
glucose is already < 70 or the last-15-minute trend reaches < 80 within 30 minutes.

## Limitations (say this to judges)

1. Only `dkd_current` is trained and validated on real patients; it is cross-sectional and US-based.
2. Onset, progression and HbA1c models are trained on a **simulated** Indian cohort; they are a
   working pipeline ready to be retrained on real longitudinal data (e.g. hospital EHR via FHIR,
   ICMR registries), not validated predictors.
3. Glucose forecasts are weakest for sudden lows; hypo warnings rely on the rule-based
   safety net, and the synthetic CGM is not a substitute for real sensor data (CGMacros).
4. Treatment simulation multiplies risk by trial hazard ratios; real effects vary by patient.
5. Not a medical device; no CDSCO approval; outputs must be reviewed by a clinician.

## Next steps

Retrain onset/progression on real Indian longitudinal EHR data; external validation; recalibrate
to Indian incidence (ICMR-INDIAB follow-up); add AI-READI for CGM + labs; fairness checks by sex
and age.
"""
    (MODELS / "model_card.md").write_text(card, encoding="utf-8")
    (ROOT / "docs").mkdir(exist_ok=True)
    shutil.copy(MODELS / "model_card.md", ROOT / "docs" / "model_card.md")


# --------------------------------------------------------------------------- main

def main(which: list[str]) -> None:
    which = which or ["dkd_current", "dkd", "hba1c", "glucose"]
    metrics_path = MODELS / "metrics.json"
    metrics = json.loads(metrics_path.read_text()) if metrics_path.exists() else {}
    t0 = time.time()
    visits = None
    if {"dkd", "hba1c"} & set(which):
        visits = pd.read_csv(ROOT / "data" / "synthetic" / "cohort_visits.csv")
    if "dkd_current" in which:
        print("Training dkd_current (NHANES) ...", flush=True)
        metrics["dkd_current"] = train_dkd_current()
    if "dkd" in which:
        print("Building 3-year landmarks ...", flush=True)
        lm = cohort.dkd_landmarks(visits)
        for kind in ("onset", "progression"):
            print(f"Training dkd_{kind} ...", flush=True)
            metrics[f"dkd_{kind}"] = train_dkd(kind, lm)
    if "hba1c" in which:
        print("Training hba1c_forecast ...", flush=True)
        metrics["hba1c_forecast"] = train_hba1c(visits)
    if "glucose" in which:
        print("Training glucose_forecast ...", flush=True)
        metrics["glucose_forecast"] = train_glucose()
    MODELS.mkdir(exist_ok=True)
    metrics_path.write_text(json.dumps(metrics, indent=2, default=float))
    write_model_card(metrics)
    print(f"Done in {time.time() - t0:.0f} s. See models/model_card.md and docs/models/")
    for k, v in metrics.items():
        short = {kk: vv for kk, vv in v.items() if kk not in ("top_features", "uci_sanity_check")}
        print(f"  {k}: {short}")
        if "uci_sanity_check" in v:
            print(f"    uci: {v['uci_sanity_check']}")


if __name__ == "__main__":
    main(sys.argv[1:])
