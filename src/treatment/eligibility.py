"""Which treatment options are allowed for this patient (rules in clinical_rules.yaml -> eligibility).

Decision support only: every option carries its reason and source; the doctor decides.
Returns one entry per option in clinical_rules.yaml -> effects, plus safety warnings about the
medicines the patient is already taking.
"""

from __future__ import annotations

from src.clinical.rules import clinical_rules


def _opt(option: str, eligible: bool, reason: str, cautions: list[str] | None = None) -> dict:
    eff = clinical_rules()["effects"][option]
    return {"option": option, "label": eff["label"], "kind": eff["kind"], "eligible": eligible,
            "reason": reason, "cautions": cautions or [], "source": eff["source"],
            "verified": eff.get("verified", False)}


def evaluate(state: dict) -> dict:
    r = clinical_rules()
    el = r["eligibility"]
    k, f = state["kidney"], state["med_flags"]
    egfr, uacr = k.get("egfr"), k.get("uacr")
    pot = (state["labs"].get("potassium") or {}).get("value")
    hba1c = state["glycaemia"]["hba1c"]
    above_target = hba1c is not None and hba1c >= r["targets"]["hba1c_pct_below"]
    albuminuria = uacr is not None and uacr >= el["finerenone"]["uacr_at_least"]
    htn = state["profile"]["hypertension"] or (state["vitals"]["sbp"] or 0) >= 140
    out: list[dict] = []

    if egfr is None:
        return {"options": [], "warnings": ["No creatinine/eGFR on record: order kidney labs first"]}

    # --- kidney-protective drugs ---
    s = el["sglt2i"]
    if f["on_sglt2i"]:
        out.append(_opt("sglt2i", False, "Already on an SGLT2 inhibitor (continue until dialysis/transplant)"))
    elif egfr < s["initiate_egfr_at_least"]:
        out.append(_opt("sglt2i", False, f"eGFR {egfr:.0f} is below {s['initiate_egfr_at_least']}: do not start"))
    else:
        out.append(_opt("sglt2i", True, f"eGFR {egfr:.0f} >= {s['initiate_egfr_at_least']}",
                        ["Genital mycotic infection", "Volume depletion / sick-day rules",
                         "Euglycaemic DKA (rare)"]))

    if f["on_glp1ra"]:
        out.append(_opt("glp1ra", False, "Already on a GLP-1 receptor agonist"))
    else:
        out.append(_opt("glp1ra", True, "No eGFR restriction for most GLP-1 RAs",
                        el["glp1ra"]["cautions"]))

    a = el["acei_arb"]
    if f["on_acei_arb"]:
        out.append(_opt("acei_arb", False, "Already on ACEi or ARB: titrate to max tolerated dose; "
                                           "never combine ACEi with ARB"))
    elif not (albuminuria or htn):
        out.append(_opt("acei_arb", False, "No albuminuria or hypertension"))
    elif pot is not None and pot > a["hold_if_potassium_above"]:
        out.append(_opt("acei_arb", False, f"Potassium {pot} > {a['hold_if_potassium_above']}"))
    else:
        why = "albuminuria (UACR >= 30)" if albuminuria else "hypertension"
        out.append(_opt("acei_arb", True, f"Indicated for {why}",
                        ["Check potassium and creatinine 2-4 weeks after starting"]))

    fn = el["finerenone"]
    if f["on_finerenone"]:
        out.append(_opt("finerenone", False, "Already on finerenone"))
    elif uacr is None or uacr < fn["uacr_at_least"]:
        out.append(_opt("finerenone", False, f"Needs UACR >= {fn['uacr_at_least']} mg/g"))
    elif egfr < fn["egfr_at_least"]:
        out.append(_opt("finerenone", False, f"Needs eGFR >= {fn['egfr_at_least']}"))
    elif pot is None:
        out.append(_opt("finerenone", False, "Needs a recent potassium result"))
    elif pot > fn["potassium_at_most"]:
        out.append(_opt("finerenone", False, f"Potassium {pot} > {fn['potassium_at_most']}"))
    elif fn["requires_max_tolerated_acei_arb"] and not f["on_acei_arb"]:
        out.append(_opt("finerenone", False, "Start ACEi/ARB at max tolerated dose first"))
    else:
        out.append(_opt("finerenone", True, f"UACR {uacr:.0f}, eGFR {egfr:.0f}, K {pot}, on ACEi/ARB",
                        ["Monitor potassium at 4 weeks"]))

    # --- glucose-lowering drugs (only offered when HbA1c is above target) ---
    m = el["metformin"]
    if f["on_metformin"]:
        out.append(_opt("metformin", False, "Already on metformin"))
    elif egfr < m["do_not_start_egfr_below"]:
        out.append(_opt("metformin", False, f"eGFR {egfr:.0f} < {m['do_not_start_egfr_below']}: do not start"))
    elif not above_target:
        out.append(_opt("metformin", False, "HbA1c at target"))
    else:
        out.append(_opt("metformin", True, f"HbA1c {hba1c}% above target, eGFR {egfr:.0f}"))

    for opt, flag, rule_key in [("dpp4i", "on_dpp4i", None), ("sulfonylurea", "on_sulfonylurea", "sulfonylurea"),
                                ("insulin_basal", "on_insulin", "insulin")]:
        if f.get(flag):
            out.append(_opt(opt, False, "Already on this class"))
        elif not above_target:
            out.append(_opt(opt, False, "HbA1c at target"))
        else:
            cautions = []
            if rule_key and egfr < el[rule_key]["hypo_risk_flag_egfr_below"]:
                cautions.append(f"High hypoglycaemia risk at eGFR {egfr:.0f}")
            elif rule_key:
                cautions.append("Hypoglycaemia risk")
            if opt == "dpp4i" and f["on_glp1ra"]:
                out.append(_opt(opt, False, "Do not combine DPP-4 inhibitor with GLP-1 RA"))
                continue
            out.append(_opt(opt, True, f"HbA1c {hba1c}% above target", cautions))

    # --- lifestyle levers (the only options patients see) ---
    life = el["lifestyle"]
    sbp, dbp = state["vitals"]["sbp"], state["vitals"]["dbp"]
    out.append(_opt("bp_control", state["bp"]["on_target"] is False,
                    f"BP {sbp:.0f}/{dbp:.0f}, target < {state['bp']['target']}" if sbp and dbp
                    else "No BP on record"))
    bmi = state["vitals"]["bmi"]
    out.append(_opt("weight_loss_5pct", bmi is not None and bmi >= life["weight_loss_bmi_at_least"],
                    f"BMI {bmi}" + (f" >= {life['weight_loss_bmi_at_least']} (Asian cut-off)"
                                    if bmi and bmi >= life["weight_loss_bmi_at_least"] else "")
                    if bmi else "No BMI on record"))
    steps = state["vitals"]["steps_per_day"]
    out.append(_opt("steps_plus_2000", steps is None or steps < life["steps_below"],
                    f"{steps:,} steps/day" if steps else "Step count unknown"))
    out.append(_opt("stop_smoking", bool(state["profile"]["smoker"]),
                    "Current smoker" if state["profile"]["smoker"] else "Non-smoker"))

    return {"options": out, "warnings": safety_warnings(state)}


def safety_warnings(state: dict) -> list[str]:
    """Problems with medicines the patient is ALREADY taking."""
    el = clinical_rules()["eligibility"]
    f, egfr = state["med_flags"], state["kidney"].get("egfr")
    pot = (state["labs"].get("potassium") or {}).get("value")
    w = []
    if egfr is not None:
        if f["on_metformin"] and egfr < el["metformin"]["contraindicated_egfr_below"]:
            w.append(f"Metformin with eGFR {egfr:.0f} (< {el['metformin']['contraindicated_egfr_below']}): "
                     "contraindicated, stop")
        elif f["on_metformin"] and egfr < el["metformin"]["reduce_dose_egfr_below"]:
            w.append(f"Metformin with eGFR {egfr:.0f}: reduce to max "
                     f"{el['metformin']['max_daily_dose_mg_reduced']:,} mg/day")
        if f["on_sulfonylurea"] and egfr < el["sulfonylurea"]["hypo_risk_flag_egfr_below"]:
            w.append(f"Sulfonylurea with eGFR {egfr:.0f}: high hypoglycaemia risk")
        if f["on_insulin"] and egfr < el["insulin"]["hypo_risk_flag_egfr_below"]:
            w.append(f"Insulin with eGFR {egfr:.0f}: hypoglycaemia risk, review dose")
        if f["on_sglt2i"] and egfr < el["sglt2i"]["initiate_egfr_at_least"]:
            w.append(f"SGLT2i with eGFR {egfr:.0f}: may continue for kidney protection, "
                     "little glucose-lowering effect")
    if f.get("on_acei") and f.get("on_arb"):
        w.append("ACE inhibitor AND ARB together: do not combine (hyperkalaemia, AKI)")
    if pot is not None and pot > el["acei_arb"]["hold_if_potassium_above"] and \
            (f["on_acei_arb"] or f["on_finerenone"]):
        w.append(f"Potassium {pot} on ACEi/ARB/finerenone: review")
    return w
