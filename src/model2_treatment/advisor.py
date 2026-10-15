"""Model 2: treatment advisor (clinical decision support, NOT automatic prescribing).

Loop: eligibility rules -> simulate each eligible option on the twin
      -> re-run Model 1 -> rank by predicted DKD risk reduction.

EFFECTS below are approximate, illustrative values summarised from trial literature
(DAPA-CKD, CREDENCE, FLOW, FIDELIO/FIGARO, RENAAL/IDNT, Look AHEAD). They must be
checked and finalised in the clinical rules sheet before the demo.
"""

from __future__ import annotations

import math
from copy import deepcopy

from src.model1_risk.model import predict_features

# feature changes applied to the twin when an option is simulated
EFFECTS = {
    "sglt2i": {
        "label": "Add SGLT2 inhibitor (e.g. dapagliflozin 10 mg)",
        "kind": "drug", "evidence": "DAPA-CKD, CREDENCE, EMPA-KIDNEY",
        "hba1c": -0.5, "sbp": -4, "uacr_factor": 0.70, "flag": "on_sglt2i",
    },
    "glp1ra": {
        "label": "Add GLP-1 receptor agonist (e.g. semaglutide)",
        "kind": "drug", "evidence": "FLOW, SUSTAIN-6, LEADER",
        "hba1c": -0.8, "sbp": -3, "bmi": -1.5, "uacr_factor": 0.80, "flag": "on_glp1ra",
    },
    "acei_arb": {
        "label": "Start / maximise ACEi or ARB (e.g. telmisartan)",
        "kind": "drug", "evidence": "RENAAL, IDNT",
        "sbp": -8, "uacr_factor": 0.65, "flag": "on_acei_arb",
    },
    "finerenone": {
        "label": "Add finerenone 10-20 mg",
        "kind": "drug", "evidence": "FIDELIO-DKD, FIGARO-DKD",
        "sbp": -2, "uacr_factor": 0.68, "flag": "on_finerenone",
    },
    "bp_control": {
        "label": "Intensify BP control to < 130/80",
        "kind": "lifestyle_or_drug", "evidence": "KDIGO 2022, ADA Standards of Care",
        "sbp_target": 125,
    },
    "weight_loss": {
        "label": "Structured 5% weight loss (diet + exercise)",
        "kind": "lifestyle", "evidence": "Look AHEAD, DiRECT",
        "bmi_factor": 0.95, "hba1c": -0.3, "sbp": -3,
    },
    "activity": {
        "label": "Increase activity to >= 7,000 steps/day",
        "kind": "lifestyle", "evidence": "ADA Standards of Care",
        "hba1c": -0.3, "sbp": -2,
    },
    "stop_smoking": {
        "label": "Stop smoking",
        "kind": "lifestyle", "evidence": "KDIGO 2022",
        "smoker": 0,
    },
}


def eligibility(state: dict) -> tuple[dict[str, str], list[str]]:
    """Returns ({option: 'eligible' | reason not eligible}, safety_warnings)."""
    f = state["features"]
    labs = state["labs"]
    d = state["derived"]
    egfr, uacr = d["egfr"], labs["uacr"]
    k = labs.get("potassium")
    meds = state["med_flags"]
    steps = (state.get("lifestyle") or {}).get("steps_per_day")
    out, warnings = {}, []

    def set_(opt, ok, reason):
        out[opt] = "eligible" if ok else reason

    set_("sglt2i", not meds["on_sglt2i"] and egfr >= 20,
         "already on SGLT2i" if meds["on_sglt2i"] else "eGFR < 20")
    set_("glp1ra", not meds["on_glp1ra"], "already on GLP-1 RA")
    acei_needed = uacr >= 30 or f["hypertension"]
    set_("acei_arb",
         not meds["on_acei_arb"] and acei_needed and (k is None or k < 5.0),
         "already on ACEi/ARB" if meds["on_acei_arb"] else
         ("no albuminuria or hypertension" if not acei_needed else "potassium >= 5.0"))
    fin_ok = (not meds["on_finerenone"] and uacr >= 30 and egfr >= 25
              and k is not None and k <= 5.0 and meds["on_acei_arb"])
    fin_reason = ("already on finerenone" if meds["on_finerenone"] else
                  "needs UACR >= 30" if uacr < 30 else
                  "needs eGFR >= 25" if egfr < 25 else
                  "needs potassium result <= 5.0" if k is None or k > 5.0 else
                  "needs max-tolerated ACEi/ARB first")
    set_("finerenone", fin_ok, fin_reason)
    set_("bp_control", f["sbp"] >= 130, "BP already < 130")
    set_("weight_loss", f["bmi"] >= 25, "BMI < 25")
    set_("activity", steps is None or steps < 7000, "already active")
    set_("stop_smoking", bool(f["smoker"]), "non-smoker")

    # safety warnings on current meds
    if meds["on_metformin"] and egfr < 30:
        warnings.append("Metformin with eGFR < 30: contraindicated, review urgently")
    elif meds["on_metformin"] and egfr < 45:
        warnings.append("Metformin with eGFR 30-44: reduce dose (max 1,000 mg/day)")
    if meds["on_sulfonylurea"] and egfr < 45:
        warnings.append("Sulfonylurea with reduced eGFR: higher hypoglycaemia risk")
    if k is not None and k > 5.5:
        warnings.append("Potassium > 5.5: review ACEi/ARB/finerenone")
    return out, warnings


def apply_option(features: dict, option: str) -> dict:
    e = EFFECTS[option]
    f = deepcopy(features)
    if "flag" in e:
        f[e["flag"]] = 1
    f["hba1c"] = max(5.5, f["hba1c"] + e.get("hba1c", 0))
    f["sbp"] = f["sbp"] + e.get("sbp", 0)
    if "sbp_target" in e:
        f["sbp"] = min(f["sbp"], e["sbp_target"])
    f["bmi"] = f["bmi"] * e.get("bmi_factor", 1) + e.get("bmi", 0)
    if "uacr_factor" in e:
        f["log_uacr"] = f["log_uacr"] + math.log(e["uacr_factor"])
    if "smoker" in e:
        f["smoker"] = e["smoker"]
    return f


def recommend(state: dict) -> dict:
    base = predict_features(state["features"])
    elig, warnings = eligibility(state)
    options = []
    for opt, status in elig.items():
        if status != "eligible":
            continue
        new = predict_features(apply_option(state["features"], opt))
        options.append({
            "option": opt,
            "label": EFFECTS[opt]["label"],
            "kind": EFFECTS[opt]["kind"],
            "evidence": EFFECTS[opt]["evidence"],
            "risk_before": base["dkd_risk_3y"],
            "risk_after": new["dkd_risk_3y"],
            "absolute_reduction": round(base["dkd_risk_3y"] - new["dkd_risk_3y"], 3),
            "hba1c_3m_after": new["hba1c_3m_forecast"],
        })
    options.sort(key=lambda o: -o["absolute_reduction"])

    # combined plan: top 3 options stacked
    combo = None
    if len(options) >= 2:
        f = state["features"]
        for o in options[:3]:
            f = apply_option(f, o["option"])
        combo = {
            "options": [o["option"] for o in options[:3]],
            "risk_after": predict_features(f)["dkd_risk_3y"],
        }

    return {
        "baseline_risk": base["dkd_risk_3y"],
        "ranked_options": options,
        "combined_plan": combo,
        "not_eligible": {k: v for k, v in elig.items() if v != "eligible"},
        "safety_warnings": warnings,
        "disclaimer": "Decision support only. The treating clinician decides.",
    }


def patient_safe(rec: dict) -> list[dict]:
    """Patients only see lifestyle options, never drug changes."""
    return [o for o in rec["ranked_options"] if o["kind"] == "lifestyle"]
