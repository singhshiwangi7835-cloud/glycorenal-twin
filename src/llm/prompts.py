"""Prompts for the six assistant modes and the compact, de-identified twin context.

Modes: doctor_summary, patient_summary, chat_doctor, chat_patient, report_doctor, report_patient.
Language: "en" or "hi" (patient modes). The context holds the patient id (e.g. IND-0042) and
clinical numbers only, never names, phone numbers or raw database rows.
"""

from __future__ import annotations

import json

MODES = ("doctor_summary", "patient_summary", "chat_doctor", "chat_patient", "report_doctor", "report_patient")
PATIENT_MODES = ("patient_summary", "chat_patient", "report_patient")

COMMON = (
    "You are the explainer for GlycoRenal Twin, a digital twin for type 2 diabetes and diabetic kidney "
    "disease. Use ONLY the JSON data and guideline notes given. Quote the numbers you use. Never invent "
    "values, predictions or doses. The twin's models make the predictions; you only explain them."
)

SYSTEM = {
    "doctor_summary": COMMON + (
        " Write for a physician in under 180 words: 1) one-paragraph clinical summary (glycaemia, kidney "
        "status with KDIGO stage, BP, adherence); 2) red flags and stale data; 3) the ranked options exactly "
        "as given, each with its predicted risk change and source. Frame options as suggestions; the "
        "clinician decides."),
    "chat_doctor": COMMON + (
        " Answer the physician's question briefly from the data. Cite guideline notes by title when used. "
        "Frame any treatment idea as a suggestion with its source; the clinician decides."),
    "report_doctor": COMMON + (
        " Write a 120-word clinical summary paragraph for a PDF report: status, trends, predicted 3-year "
        "kidney risk, top ranked options with sources. Neutral clinical tone."),
    "patient_summary": COMMON + (
        " Explain to the patient in simple, warm words (no jargon) in under 120 words: how their sugar and "
        "kidneys are doing compared with targets, and up to 3 practical lifestyle steps from the options "
        "given. NEVER suggest starting, stopping or changing any medicine or dose; for medicines say "
        "'please discuss this with your doctor'."),
    "chat_patient": COMMON + (
        " Answer the patient's question in simple, warm words, under 100 words. NEVER suggest starting, "
        "stopping or changing any medicine or dose; if asked about medicines, say 'please discuss this "
        "with your doctor'."),
    "report_patient": COMMON + (
        " Write 3 short, encouraging lifestyle tips for the patient's one-page report, based on the data. "
        "No medicine advice."),
}

LANGUAGE = {"en": "Reply in English.",
            "hi": "Reply in simple Hindi (Devanagari script). Keep numbers and units as digits, e.g. 8.4%."}


def system_prompt(mode: str, language: str) -> str:
    return f"{SYSTEM[mode]} {LANGUAGE.get(language, LANGUAGE['en'])}"


def build_context(state: dict, predictions: dict, treatments: dict, alerts: list[dict],
                  top_foods: list[dict] | None, patient_view: bool) -> dict:
    k, g, c = state["kidney"], state["glycaemia"], state["cgm"]
    m = c.get("metrics") or {}
    dkd = predictions.get("dkd_3y", {})
    ctx = {
        "patient_id": state["patient_id"],
        "age": state["profile"]["age"], "sex": state["profile"]["sex"],
        "years_with_diabetes": state["profile"]["dm_duration_yrs"],
        "hba1c_pct": g["hba1c"], "hba1c_target_below": g["target"], "hba1c_change_1y": g["hba1c_change_1y"],
        "egfr": k.get("egfr"), "uacr_mg_g": k.get("uacr"), "kdigo_stage": k.get("stage"),
        "kdigo_risk": k.get("risk"), "egfr_change_per_year": k.get("egfr_slope_per_year"),
        "bp": f"{state['vitals']['sbp']:.0f}/{state['vitals']['dbp']:.0f}" if state["vitals"]["sbp"] else None,
        "bp_target": state["bp"]["target"], "bp_on_target": state["bp"]["on_target"],
        "bmi": state["vitals"]["bmi"], "steps_per_day": state["vitals"]["steps_per_day"],
        "cgm_14d": {k2: m.get(k2) for k2 in ("tir_pct", "tbr_pct", "tar_pct", "cv_pct", "gmi_pct")} if m else None,
        "latest_glucose": (c.get("latest") or {}).get("value"),
        "medicine_adherence_7d_pct": state["adherence"]["pct_7d"],
        "medicines": [f"{x['drug']} {x['dose']}".strip() for x in state["medications"]],
        "predicted": {
            "dkd_3y_risk_pct": round(dkd["risk_3y"] * 100) if dkd.get("risk_3y") is not None else None,
            "dkd_outcome": dkd.get("outcome"), "risk_band": dkd.get("band"),
            "main_drivers": [d["label"] for d in dkd.get("drivers", []) if d["contribution"] > 0][:3],
            "hba1c_in_3_months": (predictions.get("hba1c_3m") or {}).get("hba1c_3m"),
        },
        "active_alerts": [a["message"] for a in alerts[:5]],
        "stale_data": state["freshness_flags"],
    }
    opts = treatments.get("options", []) if treatments.get("available") else []
    if patient_view:
        ctx["lifestyle_options"] = [o["summary"] for o in opts if o["kind"] == "lifestyle"][:3]
        ctx["top_spiking_foods"] = [f"{f['food']} (+{f['avg_spike']:.0f} mg/dL)" for f in (top_foods or [])]
        ctx["top_spiking_foods_hi"] = [f["food_hi"] for f in (top_foods or [])]
        ctx.pop("medicines")  # patients see their medicines in the app; the assistant never discusses them
    else:
        ctx["ranked_options"] = [o["summary"] for o in opts[:5]]
        ctx["safety_warnings"] = treatments.get("warnings", [])
    return ctx


def user_prompt(context: dict, snippets: list[dict], question: str | None) -> str:
    notes = "\n".join(f"- [{s['title']}; {s['source']}] {s['text']}" for s in snippets) or "- none"
    q = f"\n\nQuestion: {question}" if question else ""
    return f"Twin data (JSON):\n{json.dumps(context, ensure_ascii=False)}\n\nGuideline notes:\n{notes}{q}"
