"""Rank eligible options by predicted absolute reduction in 3-year DKD risk.

Doctor view: all eligible options, e.g. "Add SGLT2i: DKD 3-yr risk 34% → 22% (source: DAPA-CKD)".
Patient view: lifestyle options only (never medicines).
"""

from __future__ import annotations

from src.models.dkd import predict_dkd
from src.treatment.eligibility import evaluate
from src.treatment.simulate import simulate

DISCLAIMER = "Decision support only. Suggestions with sources; the treating clinician decides."


def _short_source(source: str) -> str:
    return source.split(",")[0].split(";")[0].strip()


def rank(state: dict, patient_view: bool = False) -> dict:
    ev = evaluate(state)
    if state["features"]["dkd"].get("egfr") is None or state["features"]["dkd"].get("log_uacr") is None:
        return {"available": False, "reason": "Needs eGFR (creatinine) and UACR to estimate kidney risk",
                "warnings": ev["warnings"], "options": [], "not_eligible": []}
    base = predict_dkd(state["features"]["dkd"])
    ranked, not_eligible = [], []
    for o in ev["options"]:
        if patient_view and o["kind"] != "lifestyle":
            continue
        if not o["eligible"]:
            not_eligible.append({k: o[k] for k in ("option", "label", "reason")})
            continue
        sim = simulate(state, [o["option"]], baseline=base)
        o.update({k: sim[k] for k in ("risk_before", "risk_after", "absolute_reduction", "kidney_hr",
                                      "hba1c_after_expected", "sbp_after")})
        o["summary"] = (f"{o['label']}: DKD 3-yr risk {sim['risk_before']:.0%} → {sim['risk_after']:.0%}"
                        + (f"; HbA1c {sim['hba1c_now']}% → {sim['hba1c_after_expected']}%"
                           if sim["hba1c_after_expected"] not in (None, sim["hba1c_now"]) else "")
                        + f" (source: {_short_source(o['source'])})")
        ranked.append(o)
    ranked.sort(key=lambda o: -o["absolute_reduction"])

    combo = None
    drugs = [o["option"] for o in ranked if o["kind"] == "drug"][:2]
    life = [o["option"] for o in ranked if o["kind"] == "lifestyle"][:2]
    plan = (life if patient_view else drugs + life)[:3]
    if len(plan) >= 2:
        combo = simulate(state, plan, baseline=base)

    return {
        "available": True,
        "baseline": {"risk_3y": base["risk_3y"], "band": base["band"], "kind": base["kind"],
                     "outcome": base["outcome"], "model_version": base["model_version"]},
        "options": ranked,
        "combined_plan": combo,
        "not_eligible": [] if patient_view else not_eligible,
        "warnings": [] if patient_view else ev["warnings"],
        "disclaimer": DISCLAIMER,
    }
