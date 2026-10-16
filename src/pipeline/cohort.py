"""Synthetic Indian T2DM cohort with quarterly visits (CLAUDE.md section 7).

Why synthetic: there is no open Indian dataset that follows T2DM patients' kidneys over years.
So we simulate one from transparent, editable assumptions (config/clinical_rules.yaml -> cohort):
- baseline values: ICMR-INDIAB-informed distributions
- every quarter: HbA1c drifts with adherence and new drugs; BP wanders; UACR drifts up with
  HbA1c, BP and smoking; eGFR falls faster with high HbA1c, BP, albuminuria, age, smoking,
  and slower on SGLT2i / GLP-1 RA / ACEi-ARB / finerenone (trial hazard ratios)
- what is "measured" at each visit = true value + lab noise
The relative weights of HbA1c, BP, age, smoking, BMI and diabetes duration can be re-scaled to
the odds ratios of a real-data model (NHANES), see `nhanes_calibration()`.

Seeded, so the same YAML always gives the same cohort.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from src.clinical.egfr import egfr_ckd_epi_2021
from src.clinical.rules import clinical_rules

ROOT = Path(__file__).resolve().parents[2]
NHANES_CSV = ROOT / "data" / "processed" / "nhanes_diabetes.csv"

GLUCOSE_DRUGS = ["metformin", "sulfonylurea", "dpp4i", "sglt2i", "glp1ra", "insulin"]
KIDNEY_DRUGS = ["sglt2i", "glp1ra", "acei_arb", "finerenone"]
ALL_DRUGS = GLUCOSE_DRUGS + ["acei_arb", "finerenone"]


def _kidney_hr() -> dict[str, float]:
    eff = clinical_rules()["effects"]
    return {d: float(eff[d]["kidney_hr"]) for d in KIDNEY_DRUGS}


def nhanes_calibration(weights: dict) -> tuple[dict, dict]:
    """Re-scale eGFR-decline weights so their relative sizes follow NHANES odds ratios.

    Fits "has DKD now" ~ standardised risk factors on NHANES adults with diabetes, then sets
    each weight = HbA1c weight x (beta_factor / beta_hba1c) x (sd_hba1c / sd_factor), so a
    1-SD change in each factor has the same relative effect as in the real data.
    Factors with a non-positive NHANES effect keep their YAML value (noted in the report).
    """
    from sklearn.linear_model import LogisticRegression

    if not NHANES_CSV.exists():
        return weights, {"used": False, "reason": "data/processed/nhanes_diabetes.csv not found"}
    df = pd.read_csv(NHANES_CSV)
    cols = {"hba1c": "egfr_decline_per_hba1c", "sbp": "egfr_decline_per_sbp",
            "age": "egfr_decline_per_age", "smoker": "egfr_decline_smoker",
            "bmi": "egfr_decline_per_bmi", "dm_duration_yrs": "egfr_decline_per_dm_year"}
    d = df[list(cols) + ["has_dkd"]].copy()
    d = d.fillna(d.median(numeric_only=True))
    sd = d[list(cols)].std()
    z = (d[list(cols)] - d[list(cols)].mean()) / sd
    lr = LogisticRegression(max_iter=2000).fit(z, d["has_dkd"])
    beta = dict(zip(cols, lr.coef_[0]))

    out = dict(weights)
    report = {"used": True, "n": int(len(d)), "odds_ratio_per_sd": {}, "weights": {}, "kept_yaml": []}
    for factor, key in cols.items():
        report["odds_ratio_per_sd"][factor] = round(math.exp(beta[factor]), 3)
        if factor == "hba1c":
            continue
        if beta[factor] <= 0:
            report["kept_yaml"].append(factor)
            continue
        out[key] = weights["egfr_decline_per_hba1c"] * (beta[factor] / beta["hba1c"]) \
            * (sd["hba1c"] / sd[factor])
    report["weights"] = {k: round(v, 4) for k, v in out.items() if k.startswith("egfr_decline_per")
                         or k == "egfr_decline_smoker"}
    return out, report


def generate(n: int | None = None, seed: int | None = None, calibrate: bool = True
             ) -> tuple[pd.DataFrame, dict]:
    """Returns (visits table: one row per patient per quarter, calibration report)."""
    c = clinical_rules()["cohort"]
    n = n or c["n_patients"]
    rng = np.random.default_rng(seed if seed is not None else c["seed"])
    w = dict(c["progression"])
    report = {"used": False}
    if calibrate:
        w, report = nhanes_calibration(w)
    hr = _kidney_hr()
    noise = c["measurement_noise"]
    n_visits = c["years"] * c["visits_per_year"] + 1
    dt = 1 / c["visits_per_year"]

    # ---- baseline ----
    age = np.clip(rng.normal(c["age"]["mean"], c["age"]["sd"], n), c["age"]["min"], c["age"]["max"])
    male = rng.random(n) < c["male_fraction"]
    dm = np.clip(rng.normal(c["dm_duration_years"]["mean"], c["dm_duration_years"]["sd"], n), 0, 40)
    hba1c_eq = np.clip(rng.normal(c["hba1c_pct"]["mean"], c["hba1c_pct"]["sd"], n), 5.6, 14)
    sbp_base = np.clip(rng.normal(c["sbp_mmHg"]["mean"], c["sbp_mmHg"]["sd"], n), 100, 200)
    bmi = np.clip(rng.normal(c["bmi"]["mean"], c["bmi"]["sd"], n), 17, 45)
    htn = (rng.random(n) < c["hypertension_fraction"]) | (sbp_base >= 140)
    smoker = rng.random(n) < c["smoker_fraction"]
    fam = rng.random(n) < c["family_history_ckd_fraction"]
    adherence = rng.beta(c["adherence"]["beta_a"], c["adherence"]["beta_b"], n)
    log_uacr = (rng.normal(c["uacr_log_mean"], c["uacr_log_sd"], n)
                + 0.15 * (hba1c_eq - 8) + 0.01 * (sbp_base - 135))
    creat = np.clip(rng.normal(c["creatinine_mg_dl"]["mean"], c["creatinine_mg_dl"]["sd"], n)
                    + 0.004 * (age - 55) + 0.08 * male, 0.45, 4.0)
    egfr = np.array([egfr_ckd_epi_2021(cr, a, "M" if m else "F")
                     for cr, a, m in zip(creat, age, male)], dtype=float)
    personal_slope = rng.normal(0, w["egfr_decline_patient_sd"], n)

    bm = c["baseline_meds"]
    on = {d: rng.random(n) < bm[d] for d in GLUCOSE_DRUGS}
    on["acei_arb"] = htn & (rng.random(n) < bm["acei_arb_if_hypertension"])
    on["finerenone"] = (log_uacr >= math.log(30)) & on["acei_arb"] & \
        (rng.random(n) < bm["finerenone_if_albuminuria"])
    # baseline drugs already act on the equilibrium HbA1c / UACR
    hba1c_drop = w["hba1c_drop_per_new_drug"]
    for d in GLUCOSE_DRUGS:
        hba1c_eq = hba1c_eq - 0.5 * hba1c_drop[d] * on[d] * adherence
    for d, f in w["uacr_drug_factor"].items():
        log_uacr = log_uacr + math.log(f) * on[d]
    hba1c = hba1c_eq + w["hba1c_per_low_adherence"] * (1 - adherence)
    sbp = sbp_base - 6 * on["acei_arb"]

    rows = []
    for v in range(n_visits):
        new_drug = np.full(n, "", dtype=object)
        if v > 0:
            # a doctor sometimes adds a drug at this visit (glucose drugs if HbA1c high,
            # kidney drugs if albuminuria / hypertension and eGFR allows)
            add = rng.random(n) < c["quarterly_new_drug_probability"]
            for i in np.where(add)[0]:
                options = [d for d in ALL_DRUGS if not on[d][i]]
                if egfr[i] < 20:
                    options = [d for d in options if d != "sglt2i"]
                if egfr[i] < 30:
                    options = [d for d in options if d != "metformin"]
                if math.exp(log_uacr[i]) < 30:
                    options = [d for d in options if d != "finerenone"]
                if not (htn[i] or log_uacr[i] >= math.log(30)):
                    options = [d for d in options if d != "acei_arb"]
                if hba1c[i] < 7:
                    options = [d for d in options if d not in GLUCOSE_DRUGS or d in KIDNEY_DRUGS]
                if options:
                    d = options[rng.integers(len(options))]
                    on[d][i] = True
                    new_drug[i] = d
                    if d in hba1c_drop:
                        hba1c_eq[i] -= hba1c_drop[d] * adherence[i]
                    if d in w["uacr_drug_factor"]:
                        log_uacr[i] += math.log(w["uacr_drug_factor"][d])
                    if d == "acei_arb":
                        sbp_base[i] -= 8

            # ---- one quarter of disease progression ----
            # adherence wanders a little
            adherence = np.clip(adherence + rng.normal(0, 0.05, n), 0.05, 1)
            target = hba1c_eq + w["hba1c_per_low_adherence"] * (1 - adherence)
            hba1c = hba1c + 0.5 * (target - hba1c) + 0.04 + rng.normal(0, 0.2, n)  # slow upward drift
            hba1c = np.clip(hba1c, 5.0, 15.0)
            sbp = sbp_base + rng.normal(0, 6, n)

            uacr_drift = (w["uacr_log_drift_base"]
                          + w["uacr_log_drift_per_hba1c"] * (hba1c - 7)
                          + w["uacr_log_drift_per_sbp"] * (sbp - 130)
                          + w["uacr_log_drift_smoker"] * smoker)
            log_uacr = np.clip(log_uacr + uacr_drift * dt + rng.normal(0, 0.08, n), 0, 9)

            decline = (w["egfr_decline_base"]
                       + w["egfr_decline_per_hba1c"] * np.maximum(hba1c - 7, 0)
                       + w["egfr_decline_per_sbp"] * np.maximum(sbp - 130, 0)
                       + w["egfr_decline_per_log_uacr"] * np.maximum(log_uacr - math.log(30), 0)
                       + w["egfr_decline_per_age"] * np.maximum(age - 55, 0)
                       + w["egfr_decline_smoker"] * smoker
                       + w["egfr_decline_per_bmi"] * np.maximum(bmi - 25, 0)
                       + w["egfr_decline_per_dm_year"] * np.maximum(dm - 8, 0)
                       + personal_slope)
            drug_mult = np.ones(n)
            for d in KIDNEY_DRUGS:
                drug_mult *= np.where(on[d], hr[d], 1.0)
            egfr = np.clip(egfr - np.maximum(decline, 0) * drug_mult * dt, 5, 150)
            age = age + dt
            dm = dm + dt

        tir = np.clip(70 - (hba1c - 7) * w["tir_per_hba1c"] + rng.normal(0, 6, n), 2, 99)
        rows.append(pd.DataFrame({
            "patient_id": [f"SYN-{i:05d}" for i in range(n)],
            "visit": v, "year": v * dt,
            "age": age.round(1), "male": male.astype(int), "dm_duration_yrs": dm.round(1),
            "smoker": smoker.astype(int), "family_history": fam.astype(int),
            "hypertension": htn.astype(int), "bmi": bmi.round(1),
            "adherence": adherence.round(3),
            # measured values (true value + lab noise)
            "hba1c": (hba1c + rng.normal(0, noise["hba1c"], n)).round(1),
            "sbp": (sbp + rng.normal(0, noise["sbp"], n)).round(0),
            "egfr": np.clip(egfr + rng.normal(0, noise["egfr"], n), 5, 150).round(1),
            "uacr": np.exp(log_uacr + rng.normal(0, noise["log_uacr"], n)).round(1),
            "tir_pct": tir.round(1),
            "gmi_pct": (7 - (tir - 70) / w["tir_per_hba1c"]).round(2),
            "new_drug": new_drug,
            # true (noise-free) values, used only to define outcomes
            "true_egfr": egfr.round(2), "true_log_uacr": log_uacr.round(3),
            **{f"on_{d}": on[d].astype(int) for d in ALL_DRUGS},
        }))
    visits = pd.concat(rows, ignore_index=True)
    visits["log_uacr"] = np.log(visits["uacr"].clip(lower=1))
    return visits, report


# ---------------------------------------------------------------------------
# Training tables built from the visits
# ---------------------------------------------------------------------------

DKD_FEATURES = [
    "age", "male", "dm_duration_yrs", "hba1c", "hba1c_change_1y", "tir_pct", "sbp", "bmi",
    "egfr", "egfr_slope_1y", "log_uacr", "smoker", "family_history", "hypertension", "adherence",
    "on_sglt2i", "on_glp1ra", "on_acei_arb", "on_finerenone", "on_insulin", "on_sulfonylurea",
]

HBA1C_FEATURES = [
    "hba1c", "hba1c_change_3m", "gmi_pct", "tir_pct", "adherence", "bmi", "egfr",
    "new_glucose_drug", "on_metformin", "on_sulfonylurea", "on_dpp4i", "on_sglt2i", "on_glp1ra",
    "on_insulin",
]


def _confirmed(series: pd.Series) -> bool:
    """True if a condition holds on two consecutive visits (avoids one noisy lab)."""
    s = series.to_numpy()
    return bool(np.any(s[:-1] & s[1:])) if len(s) > 1 else False


def dkd_landmarks(visits: pd.DataFrame, landmarks=(4, 8), horizon_visits: int = 12) -> pd.DataFrame:
    """One row per patient per landmark visit, with features at that visit and 3-year outcomes.

    Landmarks are at year 1 and year 2 so each row has one year of history (for slopes) and three
    years of follow-up.
      onset:       no DKD at landmark (eGFR >= 60, UACR < 30); DKD (eGFR < 60 or UACR >= 30)
                   on two consecutive visits within 3 years
      progression: DKD at landmark; KDIGO G or A category worse, or eGFR down >= 30%,
                   on two consecutive visits within 3 years
    """
    from src.clinical.kdigo import albuminuria_category, gfr_category, A_ORDER, G_ORDER

    out = []
    for pid, g in visits.groupby("patient_id", sort=False):
        g = g.set_index("visit")
        for lm in landmarks:
            if lm + horizon_visits not in g.index:
                continue
            now, prev = g.loc[lm], g.loc[lm - 4]
            fut = g.loc[lm + 1: lm + horizon_visits]
            has_dkd = now["egfr"] < 60 or now["uacr"] >= 30
            row = {c: now[c] for c in ["age", "male", "dm_duration_yrs", "hba1c", "tir_pct", "sbp",
                                       "bmi", "egfr", "log_uacr", "smoker", "family_history",
                                       "hypertension", "adherence", "on_sglt2i", "on_glp1ra",
                                       "on_acei_arb", "on_finerenone", "on_insulin",
                                       "on_sulfonylurea"]}
            row.update(patient_id=pid, landmark=lm, has_dkd=int(has_dkd),
                       hba1c_change_1y=now["hba1c"] - prev["hba1c"],
                       egfr_slope_1y=now["egfr"] - prev["egfr"])
            if not has_dkd:
                row["event"] = int(_confirmed((fut["egfr"] < 60) | (fut["uacr"] >= 30)))
            else:
                g0 = G_ORDER.index(gfr_category(now["egfr"]))
                a0 = A_ORDER.index(albuminuria_category(now["uacr"]))
                worse = [(G_ORDER.index(gfr_category(e)) > g0) or
                         (A_ORDER.index(albuminuria_category(u)) > a0) or (e <= 0.7 * now["egfr"])
                         for e, u in zip(fut["egfr"], fut["uacr"])]
                row["event"] = int(_confirmed(pd.Series(worse)))
            out.append(row)
    return pd.DataFrame(out)


def hba1c_pairs(visits: pd.DataFrame) -> pd.DataFrame:
    """One row per patient per quarter: features now -> HbA1c at the next visit (3 months)."""
    v = visits.sort_values(["patient_id", "visit"]).copy()
    grp = v.groupby("patient_id")
    v["hba1c_change_3m"] = grp["hba1c"].diff().fillna(0)
    v["hba1c_next"] = grp["hba1c"].shift(-1)
    # a glucose drug added at the NEXT visit is a "medication change" the doctor is planning now
    v["new_glucose_drug"] = grp["new_drug"].shift(-1).isin(GLUCOSE_DRUGS).astype(int)
    return v.dropna(subset=["hba1c_next"])


def save(visits: pd.DataFrame, report: dict, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    visits.to_csv(out_dir / "cohort_visits.csv", index=False)
    (out_dir / "calibration.json").write_text(json.dumps(report, indent=2))
