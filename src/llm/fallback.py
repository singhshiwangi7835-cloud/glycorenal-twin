"""Template answers filled from the twin's numbers: used when no LLM is configured, when the LLM
fails or times out, or when a patient-mode answer breaks a guardrail ("offline summary" badge).
"""

from __future__ import annotations

TIPS = {
    "steps_plus_2000": ("Walk 10-15 minutes after each main meal; aim for 2,000 more steps a day.",
                        "हर मुख्य भोजन के बाद 10-15 मिनट टहलें; रोज़ 2,000 कदम ज़्यादा चलें।"),
    "weight_loss_5pct": ("Lose about 5% of your weight slowly: smaller rice/roti portions, half the plate vegetables.",
                         "धीरे-धीरे लगभग 5% वज़न घटाएँ: चावल/रोटी कम, आधी थाली सब्ज़ी।"),
    "bp_control": ("Use less salt (under 1 teaspoon a day, fewer pickles and namkeen) and check BP at home.",
                   "नमक कम करें (दिन में 1 चम्मच से कम, अचार-नमकीन कम) और घर पर BP जाँचें।"),
    "stop_smoking": ("Stopping smoking protects your kidneys and heart; ask your doctor for help.",
                     "धूम्रपान छोड़ने से किडनी और दिल सुरक्षित रहते हैं; डॉक्टर से मदद लें।"),
}


def _n(x, fmt="{:.0f}", none="n/a"):
    return fmt.format(x) if isinstance(x, (int, float)) else none


def doctor(ctx: dict, report: bool = False) -> str:
    p = ctx["predicted"]
    lines = [
        f"**{ctx['patient_id']}**, {ctx['age']}{ctx['sex']}, T2DM {ctx['years_with_diabetes']} yrs. "
        f"HbA1c {ctx['hba1c_pct']}% (change 1 yr {ctx['hba1c_change_1y']}), eGFR {_n(ctx['egfr'])} "
        f"(slope {ctx['egfr_change_per_year']}/yr), UACR {_n(ctx['uacr_mg_g'])} mg/g, KDIGO {ctx['kdigo_stage']} "
        f"({ctx['kdigo_risk']}). BP {ctx['bp']} (target < {ctx['bp_target']}). "
        f"TIR {_n((ctx['cgm_14d'] or {}).get('tir_pct'))}%, adherence {_n(ctx['medicine_adherence_7d_pct'])}% (7 d).",
        f"Predicted 3-year risk of {p['dkd_outcome']}: **{_n(p['dkd_3y_risk_pct'])}%** ({p['risk_band']}); "
        f"main drivers: {', '.join(p['main_drivers']) or 'n/a'}. HbA1c forecast in 3 months: {p['hba1c_in_3_months']}%.",
    ]
    if not report and (ctx["active_alerts"] or ctx["stale_data"]):
        lines.append("**Red flags:** " + "; ".join(ctx["active_alerts"] + ctx["stale_data"]))
    if ctx.get("safety_warnings"):
        lines.append("**Medicine safety:** " + "; ".join(ctx["safety_warnings"]))
    if ctx.get("ranked_options"):
        lines.append("**Options ranked by predicted risk reduction:**\n" +
                     "\n".join(f"{i}. {o}" for i, o in enumerate(ctx["ranked_options"][:4], 1)))
    return "\n\n".join(lines)


def patient(ctx: dict, language: str, options: list[dict], tips_only: bool = False) -> str:
    hi = language == "hi"
    tir = (ctx.get("cgm_14d") or {}).get("tir_pct")
    out = []
    if not tips_only:
        if hi:
            out.append(f"आपका HbA1c {ctx['hba1c_pct']}% है (लक्ष्य {ctx['hba1c_target_below']}% से कम)।")
            if tir is not None:
                out.append(f"पिछले 14 दिनों में आपकी शुगर {tir:.0f}% समय सही दायरे (70-180) में रही (लक्ष्य 70% से ज़्यादा)।")
            out.append(f"किडनी: eGFR {_n(ctx['egfr'])}, UACR {_n(ctx['uacr_mg_g'])}। BP {ctx['bp']} (लक्ष्य {ctx['bp_target']} से कम)।")
        else:
            out.append(f"Your HbA1c is {ctx['hba1c_pct']}% (target: below {ctx['hba1c_target_below']}%).")
            if tir is not None:
                out.append(f"In the last 14 days your sugar was in the healthy range (70-180) {tir:.0f}% "
                           "of the time (target: more than 70%).")
            out.append(f"Kidneys: eGFR {_n(ctx['egfr'])}, UACR {_n(ctx['uacr_mg_g'])}. "
                       f"BP {ctx['bp']} (target: below {ctx['bp_target']}).")
    tips = [TIPS[o["option"]][1 if hi else 0] for o in options if o["option"] in TIPS][:3]
    if ctx.get("top_spiking_foods"):
        food = (ctx.get("top_spiking_foods_hi") or [None])[0] if hi else None
        food = food or ctx["top_spiking_foods"][0].split(" (")[0]
        tips.append(f"{food} आपकी शुगर सबसे ज़्यादा बढ़ाता है: इसकी मात्रा कम करें।" if hi
                    else f"{food} raises your sugar the most: try a smaller portion.")
    if tips:
        out.append(("आप ये कर सकते हैं:" if hi else "What you can do:") + "\n- " + "\n- ".join(tips[:3]))
    out.append("दवाइयों के बारे में अपने डॉक्टर से बात करें।" if hi
               else "For anything about your medicines, please discuss this with your doctor.")
    return "\n\n".join(out)


def chat(ctx: dict, question: str, patient_view: bool, language: str, options: list[dict]) -> str:
    if patient_view:
        return patient(ctx, language, options)
    return doctor(ctx) + "\n\n_(Offline: the AI assistant is not reachable, so this is the standard summary " \
                         "rather than an answer to your exact question.)_"
