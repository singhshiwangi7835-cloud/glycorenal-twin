"""Simulate a treatment option on the twin (CLAUDE.md section 6, treatment advisor flow).

1. Apply the option's average effects (clinical_rules.yaml -> effects) to the model features:
   HbA1c change (and time in range with it), systolic BP change, weight change -> BMI.
2. Re-run the DKD model on the changed features.
3. Multiply the result by the option's kidney hazard ratio (trial evidence).
Drug on/off flags are NOT switched on in step 1, so a drug's kidney benefit is counted once
(through its hazard ratio) rather than twice.
"""

from __future__ import annotations

from copy import deepcopy

from src.clinical.rules import clinical_rules
from src.models.dkd import predict_dkd, risk_band
from src.models.t2dm import forecast_hba1c

GLUCOSE_DRUGS = {"metformin", "dpp4i", "sulfonylurea", "insulin_basal", "sglt2i", "glp1ra"}


def apply_effects(dkd_features: dict, hba1c_features: dict, options: list[str]) -> tuple[dict, dict, float]:
    """Returns (new dkd features, new hba1c features, combined kidney hazard ratio)."""
    eff = clinical_rules()["effects"]
    tir_per = clinical_rules()["cohort"]["progression"]["tir_per_hba1c"]
    d, h = deepcopy(dkd_features), deepcopy(hba1c_features)
    hr = 1.0
    for opt in options:
        e = eff[opt]
        if d.get("hba1c") is not None and e.get("hba1c_change"):
            d["hba1c"] = max(5.5, d["hba1c"] + e["hba1c_change"])
            if d.get("tir_pct") is not None:
                d["tir_pct"] = min(99.0, d["tir_pct"] - e["hba1c_change"] * tir_per)
        if d.get("sbp") is not None:
            d["sbp"] = d["sbp"] + e.get("sbp_change", 0)
            if "sbp_target" in e:
                d["sbp"] = min(d["sbp"], e["sbp_target"])
        if d.get("bmi") is not None and e.get("weight_change_pct"):
            d["bmi"] = d["bmi"] * (1 + e["weight_change_pct"] / 100)
        hr *= float(e.get("kidney_hr", 1.0))
        if opt in GLUCOSE_DRUGS:
            h["new_glucose_drug"] = 1
    h["bmi"], h["tir_pct"] = d.get("bmi"), d.get("tir_pct")
    return d, h, hr


def simulate(state: dict, options: list[str], baseline: dict | None = None) -> dict:
    """Predicted 3-year DKD risk and 3-month HbA1c before and after the given options."""
    base = baseline or predict_dkd(state["features"]["dkd"])
    d, h, hr = apply_effects(state["features"]["dkd"], state["features"]["hba1c"], options)
    rerun = predict_dkd(d)["risk_3y"]
    after = round(min(max(rerun * hr, 0.0), 1.0), 3)
    eff = clinical_rules()["effects"]
    hba1c_now = state["glycaemia"]["hba1c"]
    expected_change = sum(eff[o].get("hba1c_change", 0) for o in options)
    out = {
        "options": options,
        "labels": [eff[o]["label"] for o in options],
        "risk_before": base["risk_3y"],
        "risk_after": after,
        "band_after": risk_band(after),
        "absolute_reduction": round(base["risk_3y"] - after, 3),
        "kidney_hr": round(hr, 3),
        "sources": [eff[o]["source"] for o in options],
        "hba1c_now": hba1c_now,
        "hba1c_after_expected": round(hba1c_now + expected_change, 1) if hba1c_now else None,
        "sbp_after": d.get("sbp"),
    }
    if hba1c_now is not None:
        out["hba1c_3m_model"] = forecast_hba1c(h)["hba1c_3m"]
    return out
