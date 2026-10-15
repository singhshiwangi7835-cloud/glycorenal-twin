"""Synthetic Indian T2DM cohort for prototyping.

This lets the whole twin run end-to-end before the real datasets (NHANES, UCI CKD,
CGMacros) are downloaded. Distributions are rough, illustrative values for Indian
adults with T2DM and MUST be re-calibrated against ICMR-INDIAB and the real data
before any claims are made. Every assumption is in CALIBRATION so it is easy to edit.

Outcomes are generated from a known logistic risk function, so the trained model
should recover sensible directions (higher HbA1c, BP, UACR -> higher DKD risk).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.pipeline.egfr import egfr_ckd_epi_2021
from src.pipeline.kdigo import kdigo_stage

CALIBRATION = {
    "age_mean": 54, "age_sd": 10,
    "male_frac": 0.55,
    "dm_duration_mean": 8, "dm_duration_sd": 5,
    "hba1c_mean": 8.2, "hba1c_sd": 1.5,
    "sbp_mean": 136, "sbp_sd": 16,
    "bmi_mean": 26.5, "bmi_sd": 4.0,
    "hypertension_frac": 0.5,
    "smoker_frac": 0.15,
    "family_history_frac": 0.4,
    # log-normal UACR (mg/g): median ~ 18
    "uacr_log_mean": 2.9, "uacr_log_sd": 1.1,
    "creatinine_mean": 0.95, "creatinine_sd": 0.25,
}

FEATURES = [
    "age", "male", "dm_duration_yrs", "hba1c", "sbp", "bmi",
    "egfr", "log_uacr", "hypertension", "smoker", "family_history",
    "on_sglt2i", "on_acei_arb", "on_glp1ra", "on_finerenone",
]


def _logistic(x: np.ndarray) -> np.ndarray:
    return 1 / (1 + np.exp(-x))


def true_dkd_logit(df: pd.DataFrame) -> np.ndarray:
    """Ground-truth risk function used to simulate 3-year DKD onset/progression."""
    return (
        -3.3
        + 0.45 * (df["hba1c"] - 7)
        + 0.025 * (df["sbp"] - 130)
        + 0.55 * (df["log_uacr"] - np.log(30))
        - 0.03 * (df["egfr"] - 90)
        + 0.04 * (df["dm_duration_yrs"] - 8)
        + 0.02 * (df["age"] - 55)
        + 0.03 * (df["bmi"] - 25)
        + 0.35 * df["smoker"]
        + 0.25 * df["family_history"]
        + 0.20 * df["hypertension"]
        # protective therapies (log hazard ratios, approximate)
        + np.log(0.61) * df["on_sglt2i"]
        + np.log(0.80) * df["on_acei_arb"]
        + np.log(0.76) * df["on_glp1ra"]
        + np.log(0.82) * df["on_finerenone"]
    )


def generate_cohort(n: int = 5000, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    c = CALIBRATION

    age = np.clip(rng.normal(c["age_mean"], c["age_sd"], n), 25, 85).round()
    male = (rng.random(n) < c["male_frac"]).astype(int)
    dm = np.clip(rng.normal(c["dm_duration_mean"], c["dm_duration_sd"], n), 0, 40).round(1)
    hba1c = np.clip(rng.normal(c["hba1c_mean"], c["hba1c_sd"], n), 5.5, 14).round(1)
    sbp = np.clip(rng.normal(c["sbp_mean"], c["sbp_sd"], n), 95, 200).round()
    bmi = np.clip(rng.normal(c["bmi_mean"], c["bmi_sd"], n), 17, 45).round(1)
    htn = ((rng.random(n) < c["hypertension_frac"]) | (sbp >= 140)).astype(int)
    smoker = (rng.random(n) < c["smoker_frac"]).astype(int)
    fam = (rng.random(n) < c["family_history_frac"]).astype(int)

    # UACR rises with HbA1c and BP
    uacr = np.exp(
        rng.normal(c["uacr_log_mean"], c["uacr_log_sd"], n)
        + 0.15 * (hba1c - 8) + 0.01 * (sbp - 135)
    ).clip(2, 3000).round(1)

    creat = np.clip(
        rng.normal(c["creatinine_mean"], c["creatinine_sd"], n) + 0.004 * (age - 55) + 0.08 * male,
        0.4, 6.0,
    ).round(2)
    sex = np.where(male == 1, "M", "F")
    egfr = np.array([egfr_ckd_epi_2021(cr, a, s) for cr, a, s in zip(creat, age, sex)])

    on_acei = ((htn == 1) & (rng.random(n) < 0.6)).astype(int)
    on_sglt2 = (rng.random(n) < 0.18).astype(int)
    on_glp1 = (rng.random(n) < 0.06).astype(int)
    on_fin = ((uacr >= 30) & (rng.random(n) < 0.03)).astype(int)

    df = pd.DataFrame({
        "patient_id": [f"IND-{i:05d}" for i in range(n)],
        "age": age, "sex": sex, "male": male, "dm_duration_yrs": dm,
        "hba1c": hba1c, "sbp": sbp, "dbp": (sbp * 0.62 + rng.normal(0, 6, n)).round(),
        "bmi": bmi, "creatinine": creat, "uacr": uacr, "log_uacr": np.log(uacr),
        "egfr": egfr, "hypertension": htn, "smoker": smoker, "family_history": fam,
        "potassium": rng.normal(4.4, 0.4, n).clip(3.2, 6.2).round(1),
        "on_metformin": (rng.random(n) < 0.8).astype(int),
        "on_sglt2i": on_sglt2, "on_acei_arb": on_acei,
        "on_glp1ra": on_glp1, "on_finerenone": on_fin,
    })

    stages = [kdigo_stage(e, u) for e, u in zip(df["egfr"], df["uacr"])]
    df["kdigo"] = [s["stage"] for s in stages]
    df["has_ckd"] = [int(s["has_ckd"]) for s in stages]

    # 3-year outcome: DKD onset (if no CKD now) or progression (if CKD now)
    p = _logistic(true_dkd_logit(df))
    df["dkd_event_3y"] = (rng.random(n) < p).astype(int)

    # HbA1c in 3 months: regression to mean + therapy effect + noise
    df["hba1c_3m"] = (
        df["hba1c"] - 0.25 * (df["hba1c"] - 7.5)
        - 0.4 * df["on_sglt2i"] - 0.8 * df["on_glp1ra"]
        + rng.normal(0, 0.4, n)
    ).round(1)
    return df


def synthetic_cgm(mean: float = 160, cv: float = 0.32, days: int = 14,
                  seed: int = 0) -> list[float]:
    """Generate a plausible 5-minute CGM trace with meal peaks."""
    rng = np.random.default_rng(seed)
    pts = days * 288
    t = np.arange(pts)
    meals = (
        np.exp(-(((t % 288) - 100) / 18) ** 2)
        + np.exp(-(((t % 288) - 165) / 18) ** 2)
        + 1.2 * np.exp(-(((t % 288) - 245) / 20) ** 2)
    )
    trace = mean * 0.8 + mean * 0.55 * meals
    noise = rng.normal(0, mean * cv * 0.35, pts)
    smooth = np.convolve(noise, np.ones(12) / 12, mode="same") * 2.5
    return np.clip(trace + smooth, 40, 400).round(0).tolist()
