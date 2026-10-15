"""The living twin loop: patient input -> state -> Model 1 -> Model 2 -> alerts -> LLM.

Call `run_twin()` every time a new lab report, CGM upload or prescription change arrives.
"""

from __future__ import annotations

from src.alerts.engine import check as check_alerts
from src.llm import assistant
from src.model1_risk import model as model1
from src.model2_treatment import advisor as model2
from src.patient_state.builder import PatientInput, build_state


def run_twin(p: PatientInput, with_text: bool = True, lang: str = "English") -> dict:
    state = build_state(p)
    prediction = model1.predict(state)
    prediction["drivers"] = model1.explain(state)
    rec = model2.recommend(state)
    alerts = check_alerts(state, prediction)
    lifestyle = model2.patient_safe(rec)

    ctx = {"state": state, "prediction": prediction, "recommendation": rec,
           "alerts": alerts, "lifestyle_options": lifestyle}
    out = {**ctx}
    if with_text:
        out["doctor_summary"] = assistant.doctor_summary(ctx)
        out["patient_message"] = assistant.patient_explain(ctx, lang=lang)
    return out


def patient_view(twin: dict) -> dict:
    """Strip everything a patient must not see (drug options, raw risk model internals)."""
    s = twin["state"]
    return {
        "patient_id": s["patient_id"],
        "labs": s["labs"], "vitals": s["vitals"], "cgm": s["cgm"],
        "derived": {k: s["derived"][k] for k in ("egfr", "kdigo", "kdigo_colour",
                                                  "bp_on_target", "hba1c_on_target")},
        "lifestyle_options": twin["lifestyle_options"],
        "message": twin.get("patient_message"),
    }
