"""LLM assistant: explains the twin's outputs. It never makes predictions itself.

Provider is picked from env vars:
  ANTHROPIC_API_KEY -> Claude      GEMINI_API_KEY -> Gemini
With no key, a rule-based template is used so the demo always works offline.

Guardrails:
- only de-identified data is sent (patient_id + clinical values, no names/phones)
- answers only from the data given and quotes the values used
- patient mode never suggests starting, stopping or changing medicines
"""

from __future__ import annotations

import json
import os

import httpx

DOCTOR_SYSTEM = (
    "You are a clinical decision-support explainer for a type 2 diabetes + diabetic kidney "
    "disease digital twin. Use ONLY the JSON data provided. Quote the values you use. "
    "Give: 1) a 3-line clinical summary, 2) red flags, 3) the ranked options exactly as "
    "provided by the treatment model, citing KDIGO 2022 / ADA where relevant. "
    "You do not prescribe; the clinician decides. Be concise."
)
PATIENT_SYSTEM = (
    "You explain health readings to a patient with type 2 diabetes in simple words. "
    "Use ONLY the JSON data provided. Reply in {lang}. NEVER suggest starting, stopping or "
    "changing any medicine or dose; say 'talk to your doctor' for anything about medicines. "
    "Give at most 3 short, practical lifestyle steps. Be warm and encouraging."
)


def deidentify(context: dict) -> dict:
    state = context.get("state", {})
    safe_state = {k: state.get(k) for k in
                  ("patient_id", "profile", "labs", "vitals", "meds", "cgm", "derived")}
    return {**{k: v for k, v in context.items() if k != "state"}, "state": safe_state}


def _call_claude(system: str, user: str) -> str:
    r = httpx.post(
        "https://api.anthropic.com/v1/messages",
        headers={"x-api-key": os.environ["ANTHROPIC_API_KEY"],
                 "anthropic-version": "2023-06-01", "content-type": "application/json"},
        json={"model": os.getenv("CLAUDE_MODEL", "claude-sonnet-4-5"), "max_tokens": 700,
              "system": system, "messages": [{"role": "user", "content": user}]},
        timeout=60,
    )
    r.raise_for_status()
    return r.json()["content"][0]["text"]


def _call_gemini(system: str, user: str) -> str:
    model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
    r = httpx.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        params={"key": os.environ["GEMINI_API_KEY"]},
        json={"system_instruction": {"parts": [{"text": system}]},
              "contents": [{"parts": [{"text": user}]}]},
        timeout=60,
    )
    r.raise_for_status()
    return r.json()["candidates"][0]["content"]["parts"][0]["text"]


def _llm(system: str, user: str) -> str | None:
    try:
        if os.getenv("ANTHROPIC_API_KEY"):
            return _call_claude(system, user)
        if os.getenv("GEMINI_API_KEY"):
            return _call_gemini(system, user)
    except Exception as exc:  # fall back to template on any API failure
        print(f"LLM call failed ({exc.__class__.__name__}); using template")
    return None


# ---------- template fallbacks ----------

def _doctor_template(ctx: dict) -> str:
    s, p, r = ctx["state"], ctx["prediction"], ctx["recommendation"]
    d, labs, v = s["derived"], s["labs"], s["vitals"]
    lines = [
        f"**{s['patient_id']}**: {s['profile']['age']:.0f}{s['profile']['sex']}, "
        f"T2DM {s['profile']['dm_duration_yrs']} yrs. HbA1c {labs['hba1c']}%, "
        f"eGFR {d['egfr']}, UACR {labs['uacr']} mg/g (KDIGO {d['kdigo']}, {d['kdigo_risk']}). "
        f"BP {v['sbp']:.0f}/{v['dbp']:.0f}.",
        f"Predicted 3-year DKD {p['outcome_type']} risk: **{p['dkd_risk_3y']:.0%}** "
        f"({p['dkd_risk_band']}). HbA1c forecast at 3 months: {p['hba1c_3m_forecast']}%.",
    ]
    if ctx.get("alerts"):
        lines.append("**Red flags:** " + "; ".join(a["message"] for a in ctx["alerts"][:4]))
    if r["safety_warnings"]:
        lines.append("**Safety:** " + "; ".join(r["safety_warnings"]))
    if r["ranked_options"]:
        lines.append("**Options ranked by predicted risk reduction:**")
        for i, o in enumerate(r["ranked_options"][:4], 1):
            lines.append(f"{i}. {o['label']}: {o['risk_before']:.0%} -> {o['risk_after']:.0%} "
                         f"({o['evidence']})")
    lines.append("_Decision support only. The clinician decides._")
    return "\n\n".join(lines)


TIPS = {
    "weight_loss": ("Aim to lose about 5% of your weight slowly, with smaller portions of rice/roti "
                    "and more vegetables and dal.",
                    "धीरे-धीरे अपना लगभग 5% वज़न कम करें: चावल/रोटी थोड़ी कम, सब्ज़ी और दाल ज़्यादा।"),
    "activity": ("Walk for 30 minutes most days, ideally 10-15 minutes after meals.",
                 "रोज़ 30 मिनट टहलें, हो सके तो खाने के 10-15 मिनट बाद।"),
    "stop_smoking": ("Stopping smoking protects your kidneys and heart. Ask your doctor for support.",
                     "धूम्रपान छोड़ने से किडनी और दिल सुरक्षित रहते हैं। डॉक्टर से मदद लें।"),
    "bp_control": ("Use less salt (under 1 teaspoon a day) and check your BP at home.",
                   "नमक कम खाएं (दिन में 1 चम्मच से कम) और घर पर BP जांचें।"),
}


def _patient_template(ctx: dict, lang: str) -> str:
    s, p = ctx["state"], ctx["prediction"]
    hi = lang.lower().startswith("hi")
    tir = (s.get("cgm") or {}).get("tir_pct")
    if hi:
        out = [f"आपका HbA1c {s['labs']['hba1c']}% है (लक्ष्य 7% से कम)।"]
        if tir is not None:
            out.append(f"आपका शुगर {tir}% समय सही दायरे (70-180) में रहा (लक्ष्य 70% से ज़्यादा)।")
        out.append(f"किडनी की जांच: eGFR {s['derived']['egfr']}, UACR {s['labs']['uacr']}।")
    else:
        out = [f"Your HbA1c is {s['labs']['hba1c']}% (target: below 7%)."]
        if tir is not None:
            out.append(f"Your sugar was in the healthy range (70-180) {tir}% of the time "
                       "(target: more than 70%).")
        out.append(f"Kidney check: eGFR {s['derived']['egfr']}, UACR {s['labs']['uacr']}.")
    steps = [TIPS[o["option"]][1 if hi else 0] for o in ctx.get("lifestyle_options", [])
             if o["option"] in TIPS][:3]
    if steps:
        out.append(("आप ये कर सकते हैं:" if hi else "What you can do:") + "\n- " + "\n- ".join(steps))
    out.append("दवाइयों के बारे में अपने डॉक्टर से बात करें।" if hi
               else "For anything about your medicines, talk to your doctor.")
    return "\n\n".join(out)


def doctor_summary(ctx: dict, question: str | None = None) -> str:
    ctx = deidentify(ctx)
    user = json.dumps(ctx, default=str) + (f"\n\nDoctor's question: {question}" if question else "")
    return _llm(DOCTOR_SYSTEM, user) or _doctor_template(ctx)


def patient_explain(ctx: dict, lang: str = "English", question: str | None = None) -> str:
    ctx = deidentify(ctx)
    user = json.dumps(ctx, default=str) + (f"\n\nPatient's question: {question}" if question else "")
    text = _llm(PATIENT_SYSTEM.format(lang=lang), user)
    return text or _patient_template(ctx, lang)
