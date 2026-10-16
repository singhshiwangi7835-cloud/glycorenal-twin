"""Personal kidney twin (Track B): this patient's own eGFR and UACR path, learnt progressively.

eGFR over time is modelled as a straight line for this patient: eGFR(t) = now + slope x years.
The slope starts from the population estimate for someone with the same HbA1c, BP, UACR, age,
smoking and kidney medicines (the progression weights in clinical_rules.yaml -> cohort), and is
updated by Bayes' rule with every eGFR result the patient has. With one result the twin follows the
population; with several results over a year or more it follows the patient. The uncertainty band
narrows as results accumulate. UACR is modelled the same way on a log scale.

Treatments change the patient's own slope: the population model says how much the decline rate
changes when HbA1c, BP or weight change, and each kidney drug multiplies the rate by its trial
hazard ratio (same effects as the treatment advisor).
"""

from __future__ import annotations

import math
from copy import deepcopy
from datetime import datetime, timezone

import numpy as np

from src.clinical.rules import clinical_rules
from src.treatment.simulate import apply_effects

KIDNEY_DRUGS = {"sglt2i": "on_sglt2i", "glp1ra": "on_glp1ra", "acei_arb": "on_acei_arb",
                "finerenone": "on_finerenone"}


def _cfg() -> dict:
    return clinical_rules()["personal_twin"]["kidney"]


def population_decline(f: dict) -> float:
    """Expected eGFR decline (mL/min/1.73m2 per year, positive = falling) for these features."""
    rules = clinical_rules()
    w = rules["cohort"]["progression"]
    hb, sbp, lu = f.get("hba1c") or 7, f.get("sbp") or 130, f.get("log_uacr") or math.log(10)
    d = (w["egfr_decline_base"]
         + w["egfr_decline_per_hba1c"] * max(hb - 7, 0)
         + w["egfr_decline_per_sbp"] * max(sbp - 130, 0)
         + w["egfr_decline_per_log_uacr"] * max(lu - math.log(30), 0)
         + w["egfr_decline_per_age"] * max((f.get("age") or 55) - 55, 0)
         + w["egfr_decline_smoker"] * (f.get("smoker") or 0)
         + w["egfr_decline_per_bmi"] * max((f.get("bmi") or 25) - 25, 0)
         + w["egfr_decline_per_dm_year"] * max((f.get("dm_duration_yrs") or 8) - 8, 0))
    eff = rules["effects"]
    for opt, flag in KIDNEY_DRUGS.items():
        if f.get(flag):
            d *= float(eff[opt]["kidney_hr"])
    return d


def population_uacr_drift(f: dict) -> float:
    """Expected yearly change in log(UACR) for these features."""
    w = clinical_rules()["cohort"]["progression"]
    return (w["uacr_log_drift_base"] + w["uacr_log_drift_per_hba1c"] * ((f.get("hba1c") or 7) - 7)
            + w["uacr_log_drift_per_sbp"] * ((f.get("sbp") or 130) - 130)
            + w["uacr_log_drift_smoker"] * (f.get("smoker") or 0))


def _bayes_line(times_yr: np.ndarray, values: np.ndarray, slope_prior: float, slope_sd: float,
                noise_sd: float) -> tuple[np.ndarray, np.ndarray]:
    """Posterior mean and covariance of [level now, slope per year] (conjugate normal)."""
    X = np.column_stack([np.ones_like(times_yr), times_yr])
    mu0 = np.array([values[-1], slope_prior])
    L0 = np.diag([1 / 30.0 ** 2, 1 / slope_sd ** 2])        # vague prior on the level, informative on slope
    prec = X.T @ X / noise_sd ** 2 + L0
    cov = np.linalg.inv(prec)
    mean = cov @ (X.T @ values / noise_sd ** 2 + L0 @ mu0)
    return mean, cov


MAX_YEARS = 15  # beyond this a straight-line projection means nothing: reported as None


def _years_to(level: float, slope: float, threshold: float) -> float | None:
    if level <= threshold:
        return 0.0
    if slope >= -1e-6:
        return None
    years = (threshold - level) / slope
    return round(years, 1) if years <= MAX_YEARS else None


def build(state: dict, now: datetime | None = None, options: list[str] | None = None) -> dict:
    """The patient's eGFR / UACR trajectory (optionally with treatment options applied)."""
    c = _cfg()
    now = now or datetime.now(timezone.utc)
    hist = state["history"]
    f = state["features"]["dkd"]
    eg = [(datetime.fromisoformat(r["time"]), r["value"]) for r in hist["egfr"]]
    if not eg:
        return {"available": False, "reason": "No creatinine / eGFR results yet"}
    t = np.array([(ti - now).total_seconds() / (365.25 * 86400) for ti, _ in eg])  # years, <= 0
    v = np.array([val for _, val in eg], dtype=float)

    pop = population_decline(f)
    mean, cov = _bayes_line(t, v, -pop, c["egfr_slope_prior_sd"], c["egfr_noise_sd"])
    level, slope = float(mean[0]), float(mean[1])
    slope_sd = float(math.sqrt(cov[1, 1]))
    # how much the patient's own results moved the slope away from the population estimate
    weight_own = float(1 - (slope_sd / c["egfr_slope_prior_sd"]) ** 2)

    result = {"available": True, "egfr_now": round(level, 1), "egfr_latest": round(float(v[-1]), 1),
              "slope": round(slope, 2),
              "slope_80pct": [round(slope - 1.28 * slope_sd, 2), round(slope + 1.28 * slope_sd, 2)],
              "population_slope": round(-pop, 2), "results_used": len(eg),
              "span_years": round(float(-t.min()), 1), "own_data_weight": round(max(weight_own, 0.0), 2)}

    def project(sl: float, sl_cov: np.ndarray) -> dict:
        years = np.linspace(0, c["projection_years"], c["projection_years"] * 4 + 1)
        mu = level + sl * years
        sd = np.sqrt(sl_cov[0, 0] + 2 * years * sl_cov[0, 1] + years ** 2 * sl_cov[1, 1])
        return {"years": years.round(2).tolist(), "mean": mu.round(1).tolist(),
                "low": (mu - 1.28 * sd).round(1).tolist(), "high": (mu + 1.28 * sd).round(1).tolist(),
                "years_to": {str(th): _years_to(level, sl, th) for th in c["thresholds_egfr"]}}

    result["projection"] = project(slope, cov)

    # how the estimate sharpened as each result arrived (progressive learning)
    result["learning"] = []
    for k in range(1, len(eg) + 1):
        m_k, c_k = _bayes_line(t[:k], v[:k], -pop, c["egfr_slope_prior_sd"], c["egfr_noise_sd"])
        sd_k = float(math.sqrt(c_k[1, 1]))
        result["learning"].append({"results": k, "date": eg[k - 1][0].date().isoformat(),
                                   "slope": round(float(m_k[1]), 2),
                                   "slope_80pct": [round(float(m_k[1]) - 1.28 * sd_k, 2),
                                                   round(float(m_k[1]) + 1.28 * sd_k, 2)]})

    # ---- UACR ----
    ua = [(datetime.fromisoformat(r["time"]), r["value"]) for r in hist["uacr"]]
    if ua:
        tu = np.array([(ti - now).total_seconds() / (365.25 * 86400) for ti, _ in ua])
        vu = np.log(np.clip([val for _, val in ua], 1, None))
        mu_u, cov_u = _bayes_line(tu, vu, population_uacr_drift(f), c["uacr_drift_prior_sd"], c["uacr_log_noise_sd"])
        drift = float(mu_u[1])            # the patient's own yearly change (learnt from all results)
        lvl_u = float(vu[-1])             # start from the latest real result, not the smoothed line

        def years_to_uacr(thr: float) -> float | None:
            if lvl_u >= math.log(thr):
                return 0.0
            if drift <= 1e-6:
                return None
            years = (math.log(thr) - lvl_u) / drift
            return round(years, 1) if years <= MAX_YEARS else None

        result["uacr"] = {"latest": round(math.exp(lvl_u)), "twin_estimate_now": round(math.exp(float(mu_u[0]))),
                          "change_per_year_pct": round((math.exp(drift) - 1) * 100), "results_used": len(ua),
                          "years_to_A2": years_to_uacr(30), "years_to_A3": years_to_uacr(300)}

    # ---- treatment what-if on the patient's own slope ----
    if options:
        d_new, _, hr = apply_effects(f, state["features"]["hba1c"], options)
        f_new = deepcopy(d_new)
        # drug flags are left off: the trial hazard ratio below carries each drug's kidney benefit
        base_rate = max(population_decline({**f, **{fl: 0 for fl in KIDNEY_DRUGS.values()}}), 1e-6)
        new_rate = population_decline({**f_new, **{fl: 0 for fl in KIDNEY_DRUGS.values()}})
        factor = (new_rate / base_rate) * hr
        new_slope = slope * factor if slope < 0 else slope
        cov_new = cov.copy()
        cov_new[1, 1] *= factor ** 2
        cov_new[0, 1] *= factor
        cov_new[1, 0] *= factor
        result["with_options"] = {"options": options, "slope": round(new_slope, 2),
                                  "rate_factor": round(factor, 3), "projection": project(new_slope, cov_new)}
    return result
