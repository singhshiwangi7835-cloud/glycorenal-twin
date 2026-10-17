"""Doctor PDF report (CLAUDE.md section 12).

Contents: header (patient ID, date, doctor), predicted risks with model versions, KDIGO grid,
latest results with dates and freshness flags, eGFR + HbA1c trend charts, CGM AGP-style
summary, ranked treatment options with sources, medicine safety warnings, current medicines,
active alerts, AI clinical summary (report_doctor mode; template when offline).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlmodel import Session, select

from src.alerts.engine import active_alerts
from src.clinical import loinc
from src.db.models import Observation, Patient, User
from src.llm.assistant import ask
from src.reports.common import GREEN, RED, ReportPDF, agp_png, chart_png
from src.treatment.rank import rank
from src.twin.engine import latest_predictions
from src.twin.state import build_state


def build(session: Session, patient_id: str, doctor_name: str | None = None) -> bytes:
    p = session.get(Patient, patient_id)
    s = build_state(session, patient_id)
    preds = latest_predictions(session, patient_id)
    tr = rank(s)
    alerts = active_alerts(session, patient_id)
    if doctor_name is None and p.assigned_doctor_id:
        d = session.get(User, p.assigned_doctor_id)
        doctor_name = d.full_name if d else None
    summary = ask(session, patient_id, "report_doctor")
    k, g, prof = s["kidney"], s["glycaemia"], s["profile"]

    pdf = ReportPDF("Clinical report",
                    f"Patient {p.id}  |  {prof['age']} y {prof['sex']}  |  T2DM {prof['dm_duration_yrs']} years"
                    + (f"  |  Doctor: {doctor_name}" if doctor_name else ""))
    pdf.add_page()

    # ---- predicted risk + KDIGO grid (grid on the right) ----
    y0 = pdf.get_y()
    pdf.h2("Predicted risk")
    dkd = preds.get("dkd_3y")
    if dkd:
        pdf.para(f"3-year risk of {dkd['outcome']}: {dkd['risk_3y']:.0%} ({dkd['band'].replace('_', ' ')}).",
                 size=10, bold=True, w=135)
        up = [d["label"] for d in dkd.get("drivers", []) if d["contribution"] > 0]
        if up:
            pdf.para("Raising the risk: " + ", ".join(up) + ".", w=135)
        pdf.para(f"Model: {dkd['model_version']}", size=7.5, w=135)
    h3 = preds.get("hba1c_3m")
    if h3:
        pdf.para(f"HbA1c forecast in 3 months: {h3['hba1c_3m']}% (80% range {h3['range_80pct'][0]} to "
                 f"{h3['range_80pct'][1]}%).", w=135)
    drop = k.get("egfr_drop_pct_12m")
    pdf.para(f"KDIGO {k.get('stage', 'n/a')} ({(k.get('risk') or 'n/a').replace('_', ' ')} risk). eGFR slope "
             f"{k.get('egfr_slope_per_year')} per year" + (f"; change over 12 months {-drop:+.0f}%." if drop is not None else "."),
             w=135)
    pdf.kdigo_grid(152, y0 + 3, k.get("g_stage"), k.get("a_stage"))
    pdf.set_y(max(pdf.get_y(), y0 + 42))

    # ---- latest results ----
    pdf.h2("Latest results")
    rows, colours = [], []
    for var in ["hba1c", "creatinine", "egfr", "uacr", "potassium", "ldl"]:
        lab = s["labs"].get(var)
        if lab:
            when = datetime.fromisoformat(lab["time"]).strftime("%d %b %Y")
            rows.append([loinc.display(var), f"{lab['value']:g} {lab['unit']}", when, f"{lab['days_old']} days",
                         "STALE" if lab["stale"] else "current"])
            colours.append(RED if lab["stale"] else GREEN)
        else:
            rows.append([loinc.display(var), "not on record", "", "", "MISSING"])
            colours.append(RED)
    v = s["vitals"]
    rows.append(["Blood pressure", f"{v['sbp']:.0f}/{v['dbp']:.0f} mmHg" if v["sbp"] else "n/a",
                 f"target < {s['bp']['target']}", "", "on target" if s["bp"]["on_target"] else "above target"])
    colours.append(GREEN if s["bp"]["on_target"] else RED)
    rows.append(["BMI / weight", f"{v['bmi']} kg/m2, {v['weight']} kg" if v["bmi"] else "n/a", "", "", ""])
    colours.append(None)
    a7, a30 = s["adherence"]["pct_7d"], s["adherence"]["pct_30d"]
    rows.append(["Medicine adherence", f"{a7}% (7 d), {a30}% (30 d)", "", "",
                 "low" if a7 is not None and a7 < 80 else "ok"])
    colours.append(RED if a7 is not None and a7 < 80 else GREEN)
    pdf.table(["Test", "Value", "Date", "Age", "Status"], rows, [46, 54, 34, 22, 26], status_colours=colours)
    gen = s.get("genetics") or []
    if gen:
        pdf.para("Genetic markers (simulated): " + "; ".join(f"{x['label']}: {x['result']}" for x in gen) + ".",
                 size=8.5)

    # ---- trends ----
    pdf.h2("Trends")
    y = pdf.get_y()
    pdf.image_png(chart_png(s["history"]["egfr"], "eGFR (CKD-EPI 2021)", "mL/min/1.73m2", 60), x=14, w=88)
    pdf.set_y(y)
    pdf.image_png(chart_png(s["history"]["hba1c"], "HbA1c", "%", g["target"]), x=106, w=88)

    # ---- CGM ----
    pdf.h2("CGM summary (14 days)")
    m = s["cgm"].get("metrics")
    if m:
        pdf.para(f"Time in range {m['tir_pct']}% (target > 70%); below 70 mg/dL {m['tbr_pct']}% (target < 4%); "
                 f"below 54 {m['tbr_severe_pct']}%; above 180 {m['tar_pct']}%; above 250 {m['tar_severe_pct']}%. "
                 f"Mean {m['mean_glucose']} mg/dL, GMI {m['gmi_pct']}%, CV {m['cv_pct']}%, "
                 f"data sufficiency {m['sufficiency_pct']}%.")
        rows14 = session.exec(select(Observation.effective_time, Observation.value).where(
            Observation.patient_id == patient_id, Observation.loinc_code == loinc.code("glucose"),
            Observation.device == "cgm",
            Observation.effective_time > datetime.now(timezone.utc) - timedelta(days=14))).all()
        pdf.image_png(agp_png([{"time": t.isoformat(), "value": val} for t, val in rows14]), x=14, w=182)
    else:
        pdf.para("No CGM data in the last 14 days.")

    # ---- personal twin ----
    try:
        from src.twin import personal
        pt = personal.build(session, patient_id, save=False)
        pdf.h2(f"Personal twin (knows this patient: {pt['maturity']['score']}%)")
        ex, acc = pt["glucose"].get("explain"), pt["glucose"].get("accuracy")
        if ex:
            pdf.para(f"Glucose twin tuned on {pt['glucose']['days_of_cgm']} days of CGM and {pt['glucose']['meals']} meals: "
                     f"+{ex['per_10g_carbs']} mg/dL per 10 g carbs, peak {ex['peak_minutes']} min after eating, "
                     f"15-min walk lowers by {ex['walk_15_min_lowers_by']} mg/dL; 2 katori rice: +{ex['two_katori_rice_rise']} mg/dL."
                     + (f" Replays the last {acc['days']} days within {acc['mae']} mg/dL on average." if acc else ""))
        kt = pt["kidney"]
        if kt.get("available"):
            yt = kt["projection"]["years_to"]
            fmt = lambda v: "now" if v == 0 else ("not within 15 y" if v is None else f"{v} y")  # noqa: E731
            pdf.para(f"Own eGFR slope {kt['slope']} mL/min/yr (80% range {kt['slope_80pct'][0]} to {kt['slope_80pct'][1]}; "
                     f"population {kt['population_slope']}), from {kt['results_used']} results. "
                     f"eGFR < 60: {fmt(yt['60'])}; < 45: {fmt(yt['45'])}; < 30: {fmt(yt['30'])}.")
    except Exception:  # noqa: BLE001  (report still builds without the personal twin)
        pass

    # ---- treatments ----
    pdf.add_page()
    pdf.h2("Treatment options, ranked by predicted reduction in 3-year kidney risk")
    if tr.get("available"):
        for w in tr["warnings"]:
            pdf.set_text_color(*RED)
            pdf.para(f"Medicine safety: {w}", bold=True)
            pdf.set_text_color(31, 41, 51)
        rows = [[str(i), o["label"], f"{o['risk_before']:.0%} to {o['risk_after']:.0%}",
                 o["source"].split(";")[0][:58] + ("" if o["verified"] else " (verify)")]
                for i, o in enumerate(tr["options"][:8], 1)]
        pdf.table(["#", "Option", "3-yr risk", "Evidence"], rows, [7, 72, 25, 78], size=7.5)
        cp = tr.get("combined_plan")
        if cp:
            pdf.para(f"Combined plan ({', '.join(cp['labels'])}): {cp['risk_before']:.0%} to {cp['risk_after']:.0%}.")
        if tr["not_eligible"]:
            pdf.para("Not eligible or already in place: " + "; ".join(
                f"{n['label']} ({n['reason']})" for n in tr["not_eligible"]), size=7.5)
    else:
        pdf.para(tr.get("reason", "Not available"))

    # ---- medicines, alerts ----
    pdf.h2("Current medicines")
    pdf.para("; ".join(f"{x['drug']} {x['dose']} at {', '.join(x['times'])}" for x in s["medications"]) or "None")
    pdf.h2("Active alerts")
    pdf.para("\n".join(f"[{a.severity}] {a.message}" for a in alerts[:10]) or "None")
    if s["freshness_flags"]:
        pdf.para("Data gaps: " + "; ".join(s["freshness_flags"]))

    # ---- AI clinical summary ----
    pdf.h2("Clinical summary" + (" (offline template)" if summary["offline"] else f" (AI: {summary['provider']})"))
    pdf.para(summary["text"])
    return bytes(pdf.output())
