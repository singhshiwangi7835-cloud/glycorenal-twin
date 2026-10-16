"""TwinState: the twin's live snapshot of one patient, built from the database.

Everything downstream (models, treatment advisor, alerts, LLM, PDFs) reads this one dict.
It holds the latest labs with their age, histories, derived kidney status (eGFR by CKD-EPI 2021
from creatinine, KDIGO stage, slopes), 14-day CGM metrics, BP, medicines, adherence, freshness
flags, and the exact feature dicts the models expect.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

from sqlmodel import Session, select

from src.clinical import loinc
from src.clinical.cgm_metrics import cgm_metrics, gmi
from src.clinical.drugs import class_flags, classify
from src.clinical.egfr import egfr_ckd_epi_2021, egfr_slope_per_year
from src.clinical.kdigo import kdigo_stage
from src.clinical.rules import clinical_rules
from src.db.models import DeviceConnection, DoseEvent, Medication, Observation, Patient

LAB_VARS = ["hba1c", "creatinine", "egfr", "uacr", "potassium", "ldl"]
VITAL_VARS = ["sbp", "dbp", "weight", "bmi", "heart_rate", "steps", "sleep"]


class PatientNotFound(LookupError):
    pass


def _utc(t: datetime) -> datetime:
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def _closest(series: list[dict], target: datetime, min_days: int, max_days: int) -> dict | None:
    """Reading closest to `target` whose age vs the latest is between min_days and max_days."""
    if not series:
        return None
    latest = series[-1]["time"]
    pool = [r for r in series if min_days <= (latest - r["time"]).days <= max_days]
    return min(pool, key=lambda r: abs((r["time"] - target).days)) if pool else None


def _arrow(slope_per_min: float) -> str:
    if slope_per_min > 2:
        return "↑↑"
    if slope_per_min > 1:
        return "↑"
    if slope_per_min > -1:
        return "→"
    if slope_per_min > -2:
        return "↓"
    return "↓↓"


def build_state(session: Session, patient_id: str, now: datetime | None = None) -> dict:
    now = _utc(now or datetime.now(timezone.utc))
    p = session.get(Patient, patient_id)
    if p is None:
        raise PatientNotFound(patient_id)
    rules = clinical_rules()
    age = now.year - p.birth_year
    dm_years = now.year - p.dm_diagnosis_year if p.dm_diagnosis_year else None

    # ---------------- observations (non-CGM) ----------------
    code_var = {loinc.code(v): v for v in LAB_VARS + VITAL_VARS + ["glucose"]}
    rows = session.exec(
        select(Observation).where(Observation.patient_id == patient_id,
                                  Observation.loinc_code.in_(list(code_var)),
                                  Observation.effective_time <= now)
        .order_by(Observation.effective_time)
    ).all()
    hist: dict[str, list[dict]] = {v: [] for v in code_var.values()}
    for o in rows:
        var = code_var[o.loinc_code]
        if var == "glucose" or var == "heart_rate":
            continue  # CGM/HR handled below (they are many)
        hist[var].append({"time": _utc(o.effective_time), "value": o.value, "source": o.source})

    # eGFR: always recalculated from creatinine (CKD-EPI 2021) when creatinine exists
    if hist["creatinine"]:
        hist["egfr"] = [{"time": r["time"], "source": r["source"],
                         "value": egfr_ckd_epi_2021(r["value"], max(18, r["time"].year - p.birth_year), p.sex)}
                        for r in hist["creatinine"]]

    def latest(var: str) -> dict | None:
        return hist[var][-1] if hist.get(var) else None

    fr = rules["freshness"]
    max_days = {"hba1c": fr["hba1c_max_days"], "uacr": fr["uacr_max_days"],
                "creatinine": fr["creatinine_max_days"], "egfr": fr["creatinine_max_days"]}
    labs, flags = {}, []
    for var in LAB_VARS:
        r = latest(var)
        if r is None:
            labs[var] = None
            if var in max_days:
                flags.append(f"No {loinc.display(var)} on record")
            continue
        days = (now - r["time"]).days
        stale = var in max_days and days > max_days[var]
        labs[var] = {"value": round(r["value"], 2), "unit": loinc.unit(var), "time": r["time"].isoformat(),
                     "days_old": days, "stale": stale, "source": r["source"]}
        if stale and var != "egfr":
            flags.append(f"{loinc.display(var)} is {days // 30} months old")

    # ---------------- kidney ----------------
    egfr = latest("egfr")["value"] if latest("egfr") else None
    uacr = latest("uacr")["value"] if latest("uacr") else None
    kidney: dict = {"egfr": egfr, "uacr": uacr}
    if egfr is not None and uacr is not None:
        k = kdigo_stage(egfr, uacr)
        kidney.update(g_stage=k["g_stage"], a_stage=k["a_stage"], stage=k["stage"], risk=k["risk"],
                      colour=k["colour"], colour_hex=k["colour_hex"], has_dkd=k["has_ckd"])
        if len(hist["uacr"]) >= 2:
            kidney["a_stage_previous"] = kdigo_stage(egfr, hist["uacr"][-2]["value"])["a_stage"]
    eg = [r for r in hist["egfr"] if (now - r["time"]).days <= 3 * 365]
    kidney["egfr_slope_per_year"] = egfr_slope_per_year(
        [((r["time"] - eg[0]["time"]).days / 365.25, r["value"]) for r in eg]) if len(eg) >= 2 else None
    year_ago = _closest(hist["egfr"], now - timedelta(days=365), 180, 550)
    kidney["egfr_drop_pct_12m"] = (round((year_ago["value"] - egfr) / year_ago["value"] * 100, 1)
                                   if year_ago and egfr is not None else None)

    # ---------------- glycaemia ----------------
    a1c = latest("hba1c")
    a1c_1y = _closest(hist["hba1c"], now - timedelta(days=365), 180, 550)
    glyc = {
        "hba1c": a1c["value"] if a1c else None,
        "hba1c_change_1y": round(a1c["value"] - a1c_1y["value"], 2) if a1c and a1c_1y else None,
        "hba1c_change_3m": (round(hist["hba1c"][-1]["value"] - hist["hba1c"][-2]["value"], 2)
                            if len(hist["hba1c"]) >= 2 else None),
        "on_target": a1c["value"] < rules["targets"]["hba1c_pct_below"] if a1c else None,
        "target": rules["targets"]["hba1c_pct_below"],
    }

    # ---------------- CGM (last 14 days) ----------------
    window = rules["cgm"]["window_days"]
    cgm_rows = session.exec(
        select(Observation).where(Observation.patient_id == patient_id,
                                  Observation.loinc_code == loinc.code("glucose"),
                                  Observation.device == "cgm",
                                  Observation.effective_time > now - timedelta(days=window),
                                  Observation.effective_time <= now)
        .order_by(Observation.effective_time)
    ).all()
    connected = session.exec(
        select(DeviceConnection).where(DeviceConnection.patient_id == patient_id,
                                       DeviceConnection.status == "connected")).first() is not None
    cgm: dict = {"connected": connected or bool(cgm_rows), "metrics": None, "latest": None,
                 "minutes_since_last": None}
    if len(cgm_rows) >= 2:
        cgm["metrics"] = cgm_metrics([o.value for o in cgm_rows], window_days=window)
    if cgm_rows:
        last = cgm_rows[-1]
        t_last = _utc(last.effective_time)
        back = [o for o in cgm_rows[-4:]]
        slope = ((last.value - back[0].value) /
                 max((t_last - _utc(back[0].effective_time)).total_seconds() / 60, 1)) if len(back) > 1 else 0
        cgm["latest"] = {"value": last.value, "time": t_last.isoformat(), "trend_per_min": round(slope, 2),
                         "arrow": _arrow(slope), "source": last.source}
        cgm["minutes_since_last"] = round((now - t_last).total_seconds() / 60)
        if cgm["minutes_since_last"] > rules["freshness"]["cgm_max_minutes"]:
            flags.append(f"No CGM reading for {cgm['minutes_since_last'] // 60} h")

    # ---------------- vitals ----------------
    vitals = {}
    for var in ["sbp", "dbp", "weight", "bmi", "sleep"]:
        r = latest(var)
        vitals[var] = round(r["value"], 1) if r else None
    hr = session.exec(select(Observation).where(Observation.patient_id == patient_id,
                                                Observation.loinc_code == loinc.code("heart_rate"),
                                                Observation.effective_time <= now)
                      .order_by(Observation.effective_time.desc())).first()
    vitals["heart_rate"] = hr.value if hr else None
    week = [r["value"] for r in hist["steps"] if (now - r["time"]).days < 7]
    vitals["steps_per_day"] = round(sum(week) / len(week)) if week else None
    albuminuria = uacr is not None and uacr >= 30
    t = rules["targets"]["bp_with_albuminuria" if albuminuria else "bp_without_albuminuria"]
    bp = {"target": f"{t['systolic_below']}/{t['diastolic_below']}",
          "on_target": (vitals["sbp"] < t["systolic_below"] and vitals["dbp"] < t["diastolic_below"])
          if vitals["sbp"] and vitals["dbp"] else None}

    # ---------------- medicines + adherence ----------------
    today = now.date()
    meds = session.exec(select(Medication).where(Medication.patient_id == patient_id)).all()
    active = [m for m in meds if (m.start_date is None or m.start_date <= today)
              and (m.end_date is None or m.end_date >= today)]
    med_list = [{"id": m.id, "drug": m.drug, "drug_class": m.drug_class, "dose": m.dose,
                 "frequency": m.frequency, "times": m.times, "with_food": m.with_food,
                 "classes": sorted(classify(m.drug) | ({m.drug_class} if m.drug_class else set())),
                 "source": m.source} for m in active]
    names = [m.drug + " " + (m.drug_class or "") for m in active]
    flags_meds = class_flags(names)
    all_classes = set().union(*(set(m["classes"]) for m in med_list)) if med_list else set()
    flags_meds["on_acei"] = int("acei" in all_classes)
    flags_meds["on_arb"] = int("arb" in all_classes)

    def adherence(days: int) -> float | None:
        ids = [m.id for m in meds]
        if not ids:
            return None
        ev = session.exec(select(DoseEvent).where(DoseEvent.medication_id.in_(ids),
                                                  DoseEvent.scheduled_time > now - timedelta(days=days),
                                                  DoseEvent.scheduled_time <= now,
                                                  DoseEvent.status != "pending")).all()
        return round(100 * sum(e.status == "taken" for e in ev) / len(ev), 1) if ev else None

    adh = {"pct_7d": adherence(7), "pct_30d": adherence(30)}

    # ---------------- model features ----------------
    hba1c_v = glyc["hba1c"]
    tir = (cgm["metrics"] or {}).get("tir_pct")
    tir_feat = tir if tir is not None else (
        70 - (hba1c_v - 7) * rules["cohort"]["progression"]["tir_per_hba1c"] if hba1c_v else None)
    adh_frac = adh["pct_30d"] / 100 if adh["pct_30d"] is not None else None
    dkd_features = {
        "age": age, "male": int(p.sex.upper().startswith("M")), "dm_duration_yrs": dm_years,
        "hba1c": hba1c_v, "hba1c_change_1y": glyc["hba1c_change_1y"] or 0.0, "tir_pct": tir_feat,
        "sbp": vitals["sbp"], "bmi": vitals["bmi"], "egfr": egfr,
        "egfr_slope_1y": kidney["egfr_slope_per_year"] or 0.0,
        "log_uacr": math.log(max(uacr, 1)) if uacr is not None else None,
        "smoker": int(p.smoker), "family_history": int(p.family_history_ckd),
        "hypertension": int(p.hypertension or (vitals["sbp"] or 0) >= 140),
        "adherence": adh_frac,
        **{k: flags_meds[k] for k in ["on_sglt2i", "on_glp1ra", "on_acei_arb", "on_finerenone",
                                      "on_insulin", "on_sulfonylurea"]},
    }
    gmi_v = (cgm["metrics"] or {}).get("gmi_pct") or (round(gmi(28.7 * hba1c_v - 46.7), 2) if hba1c_v else None)
    hba1c_features = {
        "hba1c": hba1c_v, "hba1c_change_3m": glyc["hba1c_change_3m"] or 0.0, "gmi_pct": gmi_v,
        "tir_pct": tir_feat, "adherence": adh_frac, "bmi": vitals["bmi"], "egfr": egfr,
        "new_glucose_drug": 0,
        **{k: flags_meds[k] for k in ["on_metformin", "on_sulfonylurea", "on_dpp4i", "on_sglt2i",
                                      "on_glp1ra", "on_insulin"]},
    }

    def series(var: str, n: int = 12) -> list[dict]:
        return [{"time": r["time"].isoformat(), "value": round(r["value"], 2)} for r in hist[var][-n:]]

    return {
        "patient_id": p.id,
        "as_of": now.isoformat(),
        "profile": {"age": age, "sex": p.sex, "dm_duration_yrs": dm_years, "smoker": p.smoker,
                    "family_history_ckd": p.family_history_ckd, "hypertension": p.hypertension},
        "labs": labs,
        "history": {v: series(v) for v in ["hba1c", "egfr", "uacr", "sbp", "dbp", "weight", "potassium"]},
        "kidney": kidney,
        "glycaemia": glyc,
        "cgm": cgm,
        "vitals": vitals,
        "bp": bp,
        "medications": med_list,
        "med_flags": flags_meds,
        "adherence": adh,
        "freshness_flags": flags,
        "features": {"dkd": dkd_features, "hba1c": hba1c_features},
    }
