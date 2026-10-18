"""Doctor portal (design: glycorenal-twin-ui_3.html).

Sidebar menu: Patients, Alerts, Live monitor. Patients = list sorted by predicted 3-year kidney risk
(click a row to open the twin). Patient detail tabs: Overview, Personal twin, Live, Treatments,
Medications, Meals, EHR, AI assistant, Report.
"""

from __future__ import annotations

import json
import re
from datetime import datetime

import streamlit as st

import api_client as api
import ui
from ui import esc, md

TABS = {"overview": "Overview", "twin": "Personal twin", "live": "Live", "treatments": "Treatments",
        "meds": "Medications", "meals": "Meals", "ehr": "EHR", "ai": "AI assistant", "report": "Report"}
LAB_NAMES = {"hba1c": "HbA1c", "creatinine": "Serum creatinine", "egfr": "eGFR (CKD-EPI 2021)", "uacr": "UACR",
             "potassium": "Potassium", "ldl": "LDL cholesterol"}
WHAT_IF = {"rice": ("White rice ×2 + dal", [("Steamed white rice", 2), ("Toor dal", 1)]),
           "jowar": ("Jowar roti ×2 + dal", [("Jowar roti", 2), ("Toor dal", 1)]),
           "dosa": ("Masala dosa + chai", [("Masala dosa", 1), ("Tea with milk and sugar", 1)])}


# --------------------------------------------------------------------------- navigation

def _sim_pids() -> list[str]:
    try:
        return [s["patient_id"] for s in api.get("/devices/simulators") if s.get("running")]
    except api.APIError:
        return []


def _nav_changed() -> None:
    choice = st.session_state["nav_doc_r"]
    if choice == "patients":
        st.session_state["pid"] = None
    elif choice == "live":
        live = _sim_pids()
        st.session_state["pid"] = live[0] if live else (st.session_state.get("pid") or "IND-0042")
        st.session_state["tabs_pt_r"] = "live"


def open_patient(pid: str, tab: str = "overview") -> None:
    st.session_state["pid"] = pid
    st.session_state["tabs_pt_r"] = tab
    st.session_state["nav_doc_r"] = "patients"


def back_to_list() -> None:
    st.session_state["pid"] = None


def set_tab(tab: str) -> None:
    st.session_state["tabs_pt_r"] = tab


st.session_state.setdefault("pid", None)
try:
    patients = api.cached_get("/patients")
    all_alerts = api.cached_get("/alerts")
except api.APIError as e:
    ui.show_error(e)
    st.stop()
by_id = {p["patient_id"]: p for p in patients}
n_open = len(all_alerts)
nav = ui.sidebar_shell("Clinician portal", "nav_doc", ["patients", "alerts", "live"],
                       {"patients": ":material/group: Patients",
                        "alerts": f":material/notifications: Alerts  :red-badge[{n_open}]",
                        "live": ":material/monitor_heart: Live monitor"}, "Clinic", on_change=_nav_changed)
me = api.current_user() or {}


def _search_box() -> None:
    st.text_input("Search", placeholder="Search patient or ID", key="search", label_visibility="collapsed",
                  icon=":material/search:", width=260)


# --------------------------------------------------------------------------- patient list

def patient_list() -> None:
    ui.topbar("<b>Patients</b>", _search_box)
    ui.page_head("Your patients", "Sorted by predicted 3-year kidney risk, coloured by the KDIGO heat map. "
                 "Click a row to open the twin.", f"{esc(me.get('full_name', ''))} · Endocrinology")
    live = _sim_pids()
    high = sum(1 for p in patients if p["kdigo_colour"] in ("orange", "red"))
    crit = sum(1 for a in all_alerts if a["severity"] == "critical")
    adh = [p["adherence_7d"] for p in patients if p["adherence_7d"] is not None]
    md("<div class='grid g4' style='margin-bottom:18px'>"
       + ui.stat("Patients", len(patients), desc=f"{len(live)} sensor streaming live" if live else "no live sensor")
       + ui.stat("High / very high KDIGO", high, desc="orange + red cells")
       + ui.stat("Open alerts", n_open, desc=f"{crit} critical", colour=ui.KDIGO_HEX["red"] if n_open else None)
       + ui.stat("Avg adherence · 7 d", f"{sum(adh) / len(adh):.0f}" if adh else "–", "%", "target ≥ 80%")
       + "</div>")
    q = (st.session_state.get("search") or "").strip().lower()
    rows = [p for p in patients if not q or q in p["display_name"].lower() or q in p["patient_id"].lower()]
    with st.container(key="ptable"):
        md("<div class='prow h'><span>Patient</span><span>KDIGO</span><span>Kidney risk</span><span>HbA1c</span>"
           "<span>eGFR</span><span>UACR</span><span>Adherence</span><span>Alerts</span><span>Data</span></div>")
        if not rows:
            md(f"<div class='empty'>No patient matches “{esc(q)}”.</div>")
        for p in rows:
            pid = p["patient_id"]
            risk = (p["dkd_risk_3y"] or 0) * 100
            f = lambda v, fmt="{:.0f}": fmt.format(v) if v is not None else "–"  # noqa: E731
            a = p["adherence_7d"]
            alerts_here = [x for x in all_alerts if x["patient_id"] == pid]
            al = (ui.chip(f"{len(alerts_here)} open", "red" if any(x["severity"] == "critical" for x in alerts_here)
                          else "orange") if alerts_here else "<span class='faint'>—</span>")
            data = (ui.chip("<span class='badge-live' style='font-size:10px'>LIVE</span>", "plain") if pid in live
                    else ui.chip("stale", "orange") if p.get("freshness_flags") else ui.chip("current", "plain"))
            with st.container(key=f"row_p_{pid}"):
                md(f"<div class='prow'><div><div style='font-weight:600'>{pid} · {esc(p['display_name'])}</div>"
                   f"<div class='faint' style='font-size:11.5px'>{p['age']} {p['sex']} · T2DM "
                   f"{p.get('dm_duration_yrs') or '–'} y</div></div>"
                   f"<div>{ui.kdigo_chip(p['kdigo'], p['kdigo_colour'])}</div>"
                   f"<div><div class='row' style='gap:10px'><div style='width:70px'>"
                   f"{ui.progress(risk, ui.band_hex(p['risk_band']))}</div><b class='num'>{risk:.0f}%</b></div>"
                   f"<div class='faint' style='font-size:11px'>{p.get('risk_kind') or 'risk'} · 3 yr</div></div>"
                   f"<div>{f(p['hba1c'], '{:.1f}')}<span class='faint'>%</span></div><div>{f(p['egfr'])}</div>"
                   f"<div>{f(p['uacr'])}</div>"
                   f"<div style='color:{'var(--k-red)' if a is not None and a < 80 else 'inherit'}'>{f(a)}%</div>"
                   f"<div>{al}</div><div>{data}</div></div>")
                st.button("Open", key=f"open_{pid}", on_click=open_patient, args=(pid,))


# --------------------------------------------------------------------------- alerts page

def alerts_page() -> None:
    ui.topbar("<b>Alerts</b>")
    ui.page_head("Alerts", "Thresholds come from <span class='mono'>config/alerts.yaml</span>. The same alert is "
                 "not repeated within 60 minutes.")
    with ui.box("alerts"):
        md("<div class='prow h' style='grid-template-columns:.9fr 1.6fr 4fr 1fr .8fr;min-width:0'>"
           "<span>Severity</span><span>Patient</span><span>Alert</span><span>When</span><span></span></div>")
        if not all_alerts:
            md("<div class='empty'>No open alerts.</div>")
        for a in all_alerts:
            p = by_id.get(a["patient_id"], {})
            c = st.container(key=f"txrow_al_{a['id']}").columns([.9, 1.6, 4, 1, .8], vertical_alignment="center")
            c[0].markdown(ui.chip(a["severity"], {"critical": "red", "warning": "orange"}.get(a["severity"], "accent")),
                          unsafe_allow_html=True)
            c[1].button(p.get("display_name", a["patient_id"]), key=f"al_open_{a['id']}", type="tertiary",
                        on_click=open_patient, args=(a["patient_id"],), help=a["patient_id"])
            c[2].markdown(f"{esc(a['message'])}<div class='faint mono' style='font-size:11px'>{a['type']}</div>",
                          unsafe_allow_html=True)
            c[3].markdown(f"<span class='faint'>{ui.when(a['created_at'])}</span>", unsafe_allow_html=True)
            if c[4].button("Ack", icon=":material/check:", key=f"al_ack_{a['id']}", help="Acknowledge",
                           width="stretch"):
                api.post(f"/alerts/{a['id']}/ack")
                st.toast("Alert acknowledged")
                st.rerun()


# --------------------------------------------------------------------------- patient detail

def patient_detail(pid: str) -> None:
    p = by_id.get(pid, {"patient_id": pid, "display_name": pid})
    ui.topbar(f"<span>/</span><b>{pid} · {esc(p['display_name'])}</b>", _search_box, ("Patients", back_to_list))
    if (st.session_state.get("search") or "").strip():
        st.session_state["pid"] = None
        st.rerun()
    try:
        twin = api.cached_get(f"/patients/{pid}/twin")
    except api.APIError as e:
        ui.show_error(e)
        return
    s, preds, alerts = twin["state"], twin["predictions"], twin["alerts"]
    k, prof = s["kidney"], s["profile"]
    live = pid in _sim_pids()
    md(f"<div class='card pt-head'><div class='big-av'>{esc(p['display_name'][:1])}</div>"
       f"<div style='flex:1;min-width:220px'><h2>{esc(p['display_name'])}</h2><div class='pt-meta'>"
       f"<span class='mono'>{pid}</span><span>{prof.get('age')} y · "
       f"{'Male' if prof.get('sex') == 'M' else 'Female'}</span><span>T2DM {prof.get('dm_duration_yrs')} years</span>"
       f"<span>BMI {s['vitals'].get('bmi') or '–'}</span>"
       f"{'<span>hypertension</span>' if prof.get('hypertension') else ''}</div></div>"
       f"<div class='row wrap' style='justify-content:flex-end'>{ui.kdigo_chip(k.get('stage'), k.get('colour'))}"
       f"{ui.chip(f'{len(alerts)} alerts', 'orange') if alerts else ''}"
       f"{ui.chip('Twin updated ' + ui.when(s.get('as_of')), 'plain')}</div></div>")
    st.session_state.setdefault("tabs_pt_r", "overview")
    with st.container(key="tabs_pt"):
        tab = st.radio("Section", list(TABS), key="tabs_pt_r", horizontal=True, label_visibility="collapsed",
                       format_func=lambda t: TABS[t] + (" :blue[●]" if t == "live" and live else ""))
    {"overview": tab_overview, "twin": tab_twin, "live": tab_live, "treatments": tab_treatments,
     "meds": tab_meds, "meals": tab_meals, "ehr": tab_ehr, "ai": tab_ai, "report": tab_report}[tab](pid, twin)


def _quarter(iso: str) -> str:
    d = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    return f"Q{(d.month - 1) // 3 + 1} {d.year % 100:02d}"


# ---------------- Overview ----------------

def tab_overview(pid: str, twin: dict) -> None:
    s, preds = twin["state"], twin["predictions"]
    k, g, cgm, h = s["kidney"], s["glycaemia"], s["cgm"], s["history"]
    dkd = preds.get("dkd_3y") or {}
    risk = (dkd.get("risk_3y") or 0) * 100
    onset = dkd.get("kind") == "onset"
    a1c_now, a1c_f = g.get("hba1c"), (preds.get("hba1c_3m") or {}).get("hba1c_3m")
    fc = preds.get("glucose_30m") or {}
    m = cgm.get("metrics") or {}
    tir = m.get("tir_pct")
    cards = ui.risk_card("Kidney disease onset · 3 yr" if onset else "Kidney disease worsening · 3 yr",
                         f"{risk:.0f}", "%", ui.band_hex(dkd.get("band")),
                         "will DKD develop?" if onset else "will it get worse?",
                         (dkd.get("model_version") or "").split("@")[0], risk)
    if a1c_f is not None:
        cards += ui.risk_card("HbA1c forecast · 3 mo", f"{a1c_f:.1f}", "%",
                              ui.KDIGO_HEX["orange"] if a1c_f >= 7 else ui.KDIGO_HEX["green"],
                              f"now {a1c_now}% · target &lt; {g.get('target', 7)}%", "hba1c_forecast",
                              (a1c_f - 5) / 6 * 100)
    else:
        cards += ui.risk_card("HbA1c forecast · 3 mo", "–", "", ui.GREY, "needs an HbA1c result", "hba1c_forecast", 0)
    if fc.get("plus_30") is not None:
        low = fc.get("hypo_risk_30m")
        cards += ui.risk_card("Glucose · next 30 min", fc["plus_30"], " mg/dL",
                              ui.KDIGO_HEX["red"] if low else ui.glucose_hex(fc["plus_30"]),
                              "low glucose likely" if low else "no low expected", "glucose_forecast",
                              fc["plus_30"] / 3)
    else:
        cards += ui.risk_card("Glucose · next 30 min", "–", "", ui.GREY, "no live sensor", "glucose_forecast", 0)
    cards += ui.risk_card("Time in range · 14 d", f"{tir:.0f}" if tir is not None else "–", "%",
                          ui.GREY if tir is None else ui.KDIGO_HEX["green"] if tir >= 70
                          else ui.KDIGO_HEX["yellow"] if tir >= 50 else ui.KDIGO_HEX["orange"],
                          "target &gt; 70%", "cgm_metrics", tir or 0)
    md(f"<div class='grid g4'>{cards}</div>")
    if s["freshness_flags"]:
        md("<div style='margin-top:14px'>" + ui.banner("warn", "<b>Out-of-date or missing data:</b> "
                                                       + esc("; ".join(s["freshness_flags"]))) + "</div>")

    # KDIGO grid + drivers
    eg = h.get("egfr") or []
    prev_g = None
    if len(eg) > 1:
        t_last = datetime.fromisoformat(eg[-1]["time"])
        year_ago = [x for x in eg if (t_last - datetime.fromisoformat(x["time"])).days >= 300]
        prev_g = ui.g_stage(year_ago[-1]["value"]) if year_ago else None
    colour = k.get("colour") or "plain"
    kd_body = (ui.kdigo_grid(k.get("g_stage"), k.get("a_stage"), prev_g, k.get("a_stage_previous"))
               + f"<p class='faint' style='font-size:12px;margin-top:12px'>eGFR {k.get('egfr') or '–'} → "
               f"<b>{k.get('g_stage') or '–'}</b>, UACR {k.get('uacr') if k.get('uacr') is not None else '–'} mg/g → "
               f"<b>{k.get('a_stage') or '–'}</b>. "
               f"{'Diabetic kidney disease present.' if k.get('has_dkd') else 'On paper: no kidney disease yet.'}</p>")
    drivers = [d for d in dkd.get("drivers", []) if d["contribution"] > 0]
    gor = dkd.get("genetic_odds_ratio") or 1.0
    items = [(d["label"], _driver_value(d) + (f" · odds × {gor}" if "prs" in d["feature"] and gor != 1.0 else ""),
              d["contribution"], "prs" in d["feature"]) for d in drivers]
    items.sort(key=lambda x: -x[2])
    mx = max([x[2] for x in items] or [1])
    drv = "".join(
        f"<div><div class='row between'><span><b>{esc(lbl)}</b> <span class='faint'>· {esc(val)}</span></span>"
        f"<span class='num' style='font-weight:600;color:var(--k-red)'>+{c:.2f}</span></div>"
        f"<div style='margin-top:5px'>{ui.progress(c / mx * 100, ui.ORANGE if gene else ui.KDIGO_HEX['orange'], 6)}"
        f"</div></div>" for lbl, val, c, gene in items) or "<div class='empty'>No factor raises the risk.</div>"
    lower = [d for d in dkd.get("drivers", []) if d["contribution"] <= 0]
    drv += ("<p class='faint' style='font-size:11.5px'>Values are SHAP contributions (log-odds) to the 3-year risk."
            + (" Orange-brand bar = simulated genetic score." if gor != 1.0 else "")
            + (f" Lower than average: {esc(', '.join(d['label'] for d in lower))}." if lower else "") + "</p>")
    md("<div class='grid' style='grid-template-columns:minmax(0,1fr) minmax(0,1.25fr);margin-top:16px'>"
       + ui.card("KDIGO heat-map", kd_body, ui.chip(ui.BAND_LABEL.get(k.get("risk"), k.get("stage") or ""), colour))
       + ui.card("Raising this patient's risk", f"<div class='stack' style='gap:11px'>{drv}</div>",
                 "<span class='faint' style='font-size:12px'>SHAP contributions</span>")
       + "</div>")

    # trends
    if eg:
        vals = [x["value"] for x in eg]
        lo, hi, ticks = ui.nice_range(vals + [60], 8, 15)
        slope = k.get("egfr_slope_per_year")
        eg_chart = ui.line_chart([{"data": vals, "area": True, "dots": True}], lo, hi, y_ticks=ticks,
                                 refs=[(60, "G2 / G3a", ui.KDIGO_HEX["orange"])],
                                 x_labels=[_quarter(x["time"]) for x in eg], uid="eg")
        eg_right = ui.chip(f"{slope:+.1f} mL/min/yr", "orange" if slope < -3 else "plain") if slope is not None else ""
    else:
        eg_chart, eg_right = "<div class='empty'>No eGFR results yet</div>", ""
    a1 = h.get("hba1c") or []
    if a1:
        vals = [x["value"] for x in a1]
        lo, hi, ticks = ui.nice_range(vals + ([a1c_f] if a1c_f else []) + [6, 7], 0.3, 1)
        series = [{"data": vals, "dots": True}]
        if a1c_f is not None:
            series.append({"data": [vals[-1], a1c_f], "offset": len(vals) - 1, "color": ui.GREY, "dash": "5 5",
                           "end": True})
        labels = [ui.local(x["time"], "%b %y") if i in (0, len(a1) - 1) else "" for i, x in enumerate(a1)]
        a1_chart = ui.line_chart(series, lo, hi, y_ticks=ticks, band=(lo, g.get("target", 7)),
                                 refs=[(g.get("target", 7), f"target {g.get('target', 7)}%", ui.KDIGO_HEX["green"])],
                                 x_labels=labels + (["+3 mo"] if a1c_f is not None else []),
                                 n=len(vals) + (1 if a1c_f is not None else 0), uid="a1")
    else:
        a1_chart = "<div class='empty'>No HbA1c results yet</div>"
    md("<div class='grid g2' style='margin-top:16px'>"
       + ui.card("eGFR trend", eg_chart, eg_right)
       + ui.card("HbA1c trend + 3-mo forecast", a1_chart,
                 ui.legend([("measured", ui.NAVY), ("forecast", ui.GREY)]))
       + "</div>")

    # labs, genetics, CGM summary
    labs = []
    for key, name in LAB_NAMES.items():
        lab = s["labs"].get(key)
        if lab:
            labs.append([name, f"<b>{lab['value']:g}</b> <span class='faint'>{esc(lab['unit'])}</span>",
                         f"<span class='faint'>{ui.local(lab['time'], '%Y-%m-%d')}</span>",
                         f"<span class='mono faint'>{ui.LOINC[key]}</span>",
                         ui.chip("out of date", "orange") if lab.get("stale") else ui.chip("current", "plain")])
    v = s["vitals"]
    if v.get("sbp"):
        labs.append(["Blood pressure", f"<b>{v['sbp']:.0f}/{v['dbp']:.0f}</b> <span class='faint'>mmHg</span>",
                     "<span class='faint'>latest</span>", f"<span class='mono faint'>{ui.LOINC['bp']}</span>",
                     ui.chip("at target" if s["bp"]["on_target"] else f"target &lt; {s['bp']['target']}",
                             "green" if s["bp"]["on_target"] else "orange")])
    if v.get("bmi"):
        labs.append(["BMI", f"<b>{v['bmi']}</b> <span class='faint'>kg/m²</span>", "<span class='faint'>latest</span>",
                     f"<span class='mono faint'>{ui.LOINC['bmi']}</span>", ui.chip("current", "plain")])
    lab_card = ui.card("Latest labs", ui.table(["Test", "Value", "Date", "LOINC", ""], labs, "No lab results"),
                       "<span class='faint' style='font-size:12px'>Out-of-date: HbA1c &gt; 6 mo, "
                       "UACR/creatinine &gt; 12 mo</span>", pad=False)
    gen = s.get("genetics") or []
    if gen:
        gtab = ui.table(["Marker", "Result", ""], [
            [f"<span class='mono'>{esc(x['label'])}</span>", esc(x["result"]),
             ui.chip("caution", "orange") if x["flag"] else ui.chip("normal", "green")] for x in gen])
        note = (f"Kidney polygenic score multiplies the odds of the 3-year outcome by {gor} (included above). "
                if gor != 1.0 else "")
        gen_html = (f"<details class='exp'><summary>🧬 Genetic markers (simulated test)</summary>{gtab}"
                    f"<p class='faint' style='font-size:11.5px;padding:10px 14px'>{note}Simulated test for the "
                    "prototype. Effects and sources: <span class='mono'>config/clinical_rules.yaml</span>.</p></details>")
    else:
        gen_html = ("<details class='exp'><summary>🧬 Genetic markers (simulated test)</summary>"
                    "<div class='empty'>No genetic test on file for this patient.</div></details>")
    if m:
        sev, tbr = m.get("tbr_severe_pct") or 0, m.get("tbr_pct") or 0
        tar, tars = m.get("tar_pct") or 0, m.get("tar_severe_pct") or 0
        segs = [(sev, "#8E1F22", ""), (max(tbr - sev, 0), ui.KDIGO_HEX["red"], ""),
                (m.get("tir_pct") or 0, ui.NAVY, f"{m.get('tir_pct', 0):.0f}%"),
                (max(tar - tars, 0), ui.KDIGO_HEX["yellow"], ""), (tars, ui.KDIGO_HEX["orange"], "")]
        bar = ("<div style='display:flex;height:24px;border-radius:6px;overflow:hidden;font-size:11px;font-weight:700;"
               "color:#fff'>" + "".join(f"<div style='width:{w}%;background:{c};display:grid;place-items:center'>"
                                        f"{t}</div>" for w, c, t in segs) + "</div>")
        nums = "".join(f"<div><div class='eyebrow'>{lbl}</div><div class='big-n' style='font-size:20px'>{val}"
                       f"<span class='faint' style='font-size:12px'> {u}</span></div></div>"
                       for lbl, val, u in [("Mean", f"{m.get('mean_glucose', 0):.0f}", "mg/dL"),
                                           ("GMI", m.get("gmi_pct"), "%"), ("CV", m.get("cv_pct"), "%"),
                                           ("TBR &lt;70", tbr, "%")])
        cgm_card = ui.card("CGM · 14-day summary", bar + legend_cgm()
                           + f"<div class='row between wrap' style='margin-top:12px;gap:12px'>{nums}</div>",
                           f"<span class='faint' style='font-size:12px'>sufficiency {m.get('sufficiency_pct')}%</span>")
    else:
        cgm_card = ui.card("CGM · 14-day summary", "<div class='empty'>No CGM data in the last 14 days</div>")
    md("<div class='grid' style='grid-template-columns:minmax(0,1.25fr) minmax(0,1fr);margin-top:16px;"
       f"align-items:start'>{lab_card}<div class='stack'>{gen_html}{cgm_card}</div></div>")

    # last 24 h of glucose
    rows = api.cached_get(f"/patients/{pid}/observations", variable="glucose", device="cgm", hours=24)
    if rows:
        rows = ui.downsample(rows, 288)
        vals = [r["value"] for r in rows]
        chart = ui.line_chart([{"data": vals, "area": True, "width": 1.6}], 40, max(300, max(vals) + 10), w=1000,
                              h=200, y_ticks=[70, 180, 250], band=(70, 180),
                              x_labels=ui.time_labels([r["time"] for r in rows], max(len(rows) // 8, 1)), uid="d24")
    else:
        chart = "<div class='empty'>No sensor readings in the last 24 hours</div>"
    md("<div style='margin-top:16px'>" + ui.card("Glucose · last 24 hours", chart,
                                                 ui.legend([("CGM", ui.NAVY), ("70–180", "#E8EEF5")])) + "</div>")


def legend_cgm() -> str:
    return ("<div class='legend' style='margin-top:8px'>"
            + "".join(f"<span><i style='background:{c}'></i>{t}</span>" for t, c in
                      [("&lt;54", "#8E1F22"), ("54–69", ui.KDIGO_HEX["red"]), ("70–180", ui.NAVY),
                       ("181–250", ui.KDIGO_HEX["yellow"]), ("&gt;250", ui.KDIGO_HEX["orange"])]) + "</div>")


def _driver_value(d: dict) -> str:
    if d["feature"] == "log_uacr" and isinstance(d["value"], (int, float)):
        return f"UACR {2.718281828 ** d['value']:.0f} mg/g"
    if isinstance(d["value"], float):
        return f"{d['value']:.1f}"
    return str(d["value"])


# ---------------- Personal twin ----------------

def tab_twin(pid: str, twin: dict) -> None:
    try:
        pt = api.cached_get(f"/patients/{pid}/twin/personal")
    except api.APIError as e:
        ui.show_error(e)
        return
    mat, gl, kd = pt["maturity"], pt["glucose"], pt["kidney"]
    name = ui.esc((by_id.get(pid) or {}).get("display_name", pid).split(" ")[0])
    if not gl.get("available") and not kd.get("available"):
        md(f"<div class='card'><div class='empty' style='padding:56px'><div class='big-n' style='font-size:22px;"
           f"color:var(--ink)'>The personal twin is still learning {name}</div><p style='margin-top:8px'>"
           f"{esc(gl.get('reason') or 'It needs sensor and meal data.')} Until then it uses population values.</p>"
           f"<div style='max-width:320px;margin:16px auto 0'>{ui.progress(mat['score'])}</div></div></div>")
        return
    ex, popu = gl.get("explain") or {}, gl.get("population") or {}
    tiles = ui.stat(f"How well the twin knows {name}", mat["score"], "%",
                    ui.progress(mat["score"], ui.ORANGE) + f"<div style='margin-top:8px'>{gl.get('days_of_cgm', 0)} days "
                    f"of sensor · {gl.get('meals', 0)} meals · {kd.get('results_used', 0)} eGFR results. Started from "
                    "population values, refitted every night.</div>", cls="know")
    if ex:
        tiles += (ui.stat("Carbs response", f"+{ex['per_10g_carbs']}", "mg/dL per 10 g",
                          f"population: +{popu.get('carb_sensitivity', 0) * 10:.0f}")
                  + ui.stat("Peak after eating", ex["peak_minutes"], "min",
                            f"population: {popu.get('peak_minutes', '–')} min")
                  + ui.stat("15-min walk after meal", f"−{ex['walk_15_min_lowers_by']}", "mg/dL",
                            f"early-morning rise +{ex['morning_rise']} mg/dL"))
    md(f"<div class='grid' style='grid-template-columns:1.1fr 1fr 1fr 1fr'>{tiles}</div>")
    if mat.get("to_improve"):
        st.caption("To improve the twin: " + ", ".join(mat["to_improve"]))

    acc, rp = gl.get("accuracy"), gl.get("replay")
    left = right = ""
    if rp and acc:
        real, tw = ui.downsample(rp["real"], 216), ui.downsample(rp["twin"], 216)
        times = ui.downsample(rp["time"], 216)
        labels = [""] * len(times)
        for i in range(len(times)):
            if i == 0 or ui.local(times[i], "%d") != ui.local(times[i - 1], "%d"):
                labels[i] = ui.local(times[i], "%d %b")
        chart = ui.line_chart([{"data": real, "color": "#9AA4AB", "width": 1.4}, {"data": tw, "width": 1.8}], 60,
                              max(300, max(real) + 10), w=760, h=220, y_ticks=[100, 180, 250], band=(70, 180),
                              x_labels=labels, uid="rp")
        left = ui.card(f"Twin vs real · last {acc['days']} days", chart + "<p class='muted' style='font-size:12.5px;"
                       f"margin-top:6px'>These {acc['days']} days were <b>never used for learning</b>. The twin matches "
                       f"the real sensor within <b>{acc['mae']} mg/dL</b> on average; {acc['within_20_pct']}% of readings "
                       f"within 20 mg/dL (correlation {acc['correlation']}).</p>",
                       ui.legend([("real sensor", "#9AA4AB"), ("twin", ui.NAVY)]))
    lc = pt.get("glucose_learning") or []
    if lc:
        maes = [x["mae"] for x in lc]
        chart = ui.line_chart([{"data": maes, "area": True, "end": True, "dots": True}], 0, max(maes) * 1.3,
                              w=380, h=200, y_ticks=[0, round(max(maes) * .6), round(max(maes) * 1.2)],
                              x_labels=[f"day {x['days_of_data']}" for x in lc], uid="lc")
        drop = round((1 - maes[-1] / maes[0]) * 100) if maes[0] else 0
        right = ui.card("Learning curve", chart + "<p class='muted' style='font-size:12.5px;margin-top:6px'>Average "
                        "error in mg/dL on unseen days when the twin had seen only N earlier days.</p>",
                        ui.chip(f"error ↓ {drop}%", "accent"))
    if left or right:
        md("<div class='grid' style='grid-template-columns:minmax(0,1.6fr) minmax(0,1fr);margin-top:16px'>"
           f"{left}{right}</div>")

    c = st.columns(2, gap="medium")
    with c[0], ui.box("kidney"):
        if kd.get("available"):
            yt = kd["projection"]["years_to"]
            y45 = yt.get("45")
            ui.card_head("Kidney projection", ui.chip(
                "below 45 now" if y45 == 0 else f"reaches 45 in ~{y45} yrs" if y45 else "stays above 45 for 15 yrs",
                "orange" if y45 is not None and y45 < 10 else "plain"))
            try:
                opts = api.cached_get(f"/patients/{pid}/treatments").get("options", [])
            except api.APIError:
                opts = []
            labels_k = {o["option"]: o["label"] for o in opts}
            choice = st.multiselect("Apply options to the path", list(labels_k), key=f"kd_opts_{pid}",
                                    format_func=lambda x: labels_k[x], placeholder="Current plan only")
            plan = None
            if choice:
                plan = api.cached_get(f"/patients/{pid}/twin/personal", options=",".join(choice))["kidney"].get(
                    "with_options")
            pr = kd["projection"]
            pop = [kd["egfr_now"] + kd["population_slope"] * y for y in pr["years"]]
            series = [{"data": pop, "color": "#9AA4AB", "dash": "5 5", "width": 1.5},
                      {"data": pr["low"], "color": "#C9D3DE", "width": 1},
                      {"data": pr["high"], "color": "#C9D3DE", "width": 1},
                      {"data": pr["mean"], "end": True}]
            if plan:
                series.append({"data": plan["projection"]["mean"], "color": ui.KDIGO_HEX["green"], "dash": "6 4",
                               "end": True})
            lo, hi, ticks = ui.nice_range(pr["low"] + pr["high"] + [45, 60], 3, 15)
            md(ui.line_chart(series, lo, hi, w=520, h=210, y_ticks=ticks,
                             refs=[(45, "G3b · 45", ui.KDIGO_HEX["red"]), (60, "G3a · 60", ui.KDIGO_HEX["orange"])],
                             x_labels=["now" if y == 0 else f"+{y:g} yr" if y == int(y) else "" for y in pr["years"]],
                             uid="kp")
               + ui.legend([("own path", ui.NAVY), ("80% range", "#C9D3DE"), ("population", "#9AA4AB")]
                           + ([("with options", ui.KDIGO_HEX["green"])] if plan else []))
               + f"<p class='muted' style='font-size:12.5px;margin-top:8px'>Own eGFR slope <b>{kd['slope']}/yr</b> "
               f"(80% range {kd['slope_80pct'][0]} to {kd['slope_80pct'][1]}); population expected "
               f"<b>{kd['population_slope']}/yr</b>. Learnt from {kd['results_used']} results over {kd['span_years']} "
               "years and updated with each lab result (Bayesian)."
               + (f" With the selected options: <b>{plan['slope']}/yr</b>." if plan else "") + "</p>")
            ua = kd.get("uacr")
            if ua:
                a3 = ua["years_to_A3"]
                st.caption(f"UACR {ua['latest']} mg/g, changing about {ua['change_per_year_pct']:+d}% a year; A3 (> 300) "
                           + ("already." if a3 == 0 else f"in about {a3} years." if a3 else "not within 15 years."))
        else:
            ui.card_head("Kidney projection")
            md(f"<div class='empty'>{esc(kd.get('reason'))}</div>")
    with c[1], ui.box("whatif"):
        ui.card_head("What if…", f"<span class='faint' style='font-size:12px'>{name}'s own meal-response model</span>")
        if not gl.get("available"):
            md(f"<div class='empty'>{esc(gl.get('reason'))}</div>")
            return
        with st.container(key=f"seg_wi_{pid}"):
            meal = st.radio("Meal", list(WHAT_IF), format_func=lambda x: WHAT_IF[x][0], horizontal=True,
                            key=f"wi_meal_{pid}", label_visibility="collapsed")
        walk = st.toggle("+ 15-min walk after", key=f"wi_walk_{pid}")
        try:
            cur = api.ask(f"/patients/{pid}/twin/personal/what-if",
                          json={"items": [{"food": f, "servings": n} for f, n in WHAT_IF[meal][1]],
                                "walk_minutes": 15 if walk else 0})
            ref = api.ask(f"/patients/{pid}/twin/personal/what-if",
                          json={"items": [{"food": f, "servings": n} for f, n in WHAT_IF["rice"][1]],
                                "walk_minutes": 0})
        except api.APIError as e:
            ui.show_error(e)
            return
        if not cur.get("available"):
            md(f"<div class='empty'>{esc(cur.get('reason'))}</div>")
            return
        a, b = cur["with_plan"], ref["with_plan"]
        pk, rpk = cur["summary"]["peak"], ref["summary"]["peak"]
        hi = max(300, max(a + b) + 10)
        step = max(len(a) // 6, 1)
        md(ui.line_chart([{"data": b, "color": "#B4BCC2", "dash": "4 4", "width": 1.4},
                          {"data": a, "area": True, "end": True}], 80, hi, w=520, h=190,
                         y_ticks=[140, 180, 250], refs=[(250, "250", ui.KDIGO_HEX["orange"])],
                         x_labels=[ui.local(t, "%H:%M") if i % step == 0 else "" for i, t in enumerate(cur["time"])],
                         uid="wi")
           + f"<div class='row between' style='margin-top:8px'><span class='muted'>Predicted peak</span>"
           f"<span class='big-n' style='font-size:22px;color:{ui.KDIGO_HEX['red'] if pk > 250 else ui.KDIGO_HEX['orange'] if pk > 180 else ui.KDIGO_HEX['green']}'>"
           f"{pk:.0f} mg/dL</span></div><div class='row between'><span class='muted'>vs. usual rice lunch</span>"
           f"<b class='num'>{pk - rpk:+.0f} mg/dL</b></div><div class='row between'><span class='muted'>Minutes above 180"
           f"</span><b class='num'>{cur['summary']['minutes_above_180']}</b></div>")


# ---------------- Live ----------------

def tab_live(pid: str, twin: dict) -> None:
    sim = api.get(f"/patients/{pid}/devices")["simulator"]
    if not sim["running"]:
        name = esc((by_id.get(pid) or {}).get("display_name", pid))
        md(f"<div class='card'><div class='empty' style='padding:48px 20px 18px'><div class='big-n' style='font-size:22px;"
           f"color:var(--ink)'>No sensor streaming for {name}</div><p style='margin:8px 0 0'>Start the simulated "
           "sensor, or replay a real patient's CGM trace (ShanghaiT2DM) through this twin.</p></div></div>")
        c = st.columns([1, 1, 1, 1])
        if c[1].button("Start sensor", icon=":material/play_arrow:", type="primary", key="sim_start", width="stretch"):
            api.post(f"/patients/{pid}/devices/simulator/start", json={})
            st.rerun()
        if c[2].button("Real patient CGM", icon=":material/play_arrow:", key="sim_real", width="stretch",
                       help="Replays a real T2DM patient's sensor (ShanghaiT2DM, 15-minute CGM, open data)."):
            api.post(f"/patients/{pid}/devices/simulator/start", json={"source": "shanghai"})
            st.rerun()
        return
    with st.container(horizontal=True, vertical_alignment="center", gap="small"):
        st.markdown(f"<span class='badge-live'>LIVE · {esc(sim['source'])} · {sim['readings_sent']} readings · "
                    "one 5-min reading every few seconds</span>", unsafe_allow_html=True, width="stretch")
        if st.button("Stop sensor", icon=":material/pause:", key="sim_stop"):
            api.post(f"/patients/{pid}/devices/simulator/stop")
            st.rerun()
        if st.button("🍚 Meal spike", key="sim_meal"):
            api.post(f"/patients/{pid}/devices/simulator/scenario", json={"scenario": "meal_spike"})
            st.toast("Scenario started: meal spike")
        if st.button("📉 Hypo", key="sim_hypo", type="secondary"):
            api.post(f"/patients/{pid}/devices/simulator/scenario", json={"scenario": "hypo"})
            st.toast("Scenario started: falling glucose")
        if "shanghai" not in sim["source"].lower() and st.button("Real patient CGM", icon=":material/play_arrow:",
                                                                 key="sim_real2"):
            api.post(f"/patients/{pid}/devices/simulator/stop")
            api.post(f"/patients/{pid}/devices/simulator/start", json={"source": "shanghai"})
            st.rerun()

    @st.fragment(run_every=5)
    def live_panel():
        try:
            _live_panel(pid)
        except Exception as e:  # noqa: BLE001  (show the problem, keep the rest of the page working)
            st.error(f"Live panel error: {e}")

    live_panel()


def _live_panel(pid: str) -> None:
    rows = api.get(f"/patients/{pid}/observations", variable="glucose", device="cgm", hours=6)
    hr = api.get(f"/patients/{pid}/observations", variable="heart_rate", hours=3)
    steps = api.get(f"/patients/{pid}/observations", variable="steps", hours=1)
    tw = api.get(f"/patients/{pid}/twin")
    live_alerts = api.get(f"/patients/{pid}/alerts")
    cg = tw["state"]["cgm"]
    fc = tw["predictions"].get("glucose_30m") or {}
    sp = tw["predictions"].get("spike_90m")
    if sp and (ui.minutes_ago(sp["created_at"]) or 99) > 10:
        sp = None  # stale (sensor off)
    latest = cg.get("latest")
    g = latest["value"] if latest else None
    recent = [r["value"] for r in rows[-4:]]
    slope = (recent[-1] - recent[0]) / max(len(recent) - 1, 1) if len(recent) > 1 else 0

    # banner (same rules as the design)
    if g is not None:
        if g >= 70 and fc.get("hypo_risk_30m"):
            md(ui.banner("danger", f"<b>Low glucose likely within 30 minutes</b> — now {g:.0f} mg/dL, forecast "
                         f"{fc.get('plus_30')} mg/dL. " + esc("; ".join(fc.get("hypo_reasons") or []))))
        elif g < 70:
            md(ui.banner("danger", f"<b>Low glucose: {g:.0f} mg/dL.</b> The patient sees the fixed first-aid message "
                         "(15 g fast sugar, recheck in 15 min)."))
        elif sp and sp.get("spike_likely"):
            md(ui.banner("warn", f"<b>Spike early warning</b> — glucose above {sp['spike_above']:.0f} is likely within "
                         f"{sp['horizon_minutes']} minutes (p = {sp['probability']:.2f}). "
                         + esc("Why: " + "; ".join(sp["reasons"]) + "." if sp.get("reasons") else "")))
        elif g > 250:
            md(ui.banner("warn", f"<b>Glucose {g:.0f} mg/dL</b> — above 250."))

    # KPI tiles
    tiles = ""
    if g is not None:
        tiles += ui.stat("Glucose now", f"{g:.0f}", f"mg/dL <span style='font-size:24px'>{latest['arrow']}</span>",
                         f"{'rising' if slope > 2 else 'falling' if slope < -2 else 'steady'} · {slope:+.1f} per reading"
                         f" · {ui.when(latest['time'])}", ui.glucose_hex(g))
    else:
        tiles += ui.stat("Glucose now", "–", desc="waiting for the first reading")
    if fc.get("plus_30") is not None:
        tiles += ui.stat("Forecast +30 / +60", fc["plus_30"], f"/ {fc.get('plus_60')}",
                         "<b style='color:var(--k-red)'>low likely in 30 min</b>" if fc.get("hypo_risk_30m")
                         else (fc.get("model_version") or "").split("@")[0])
    else:
        tiles += ui.stat("Forecast +30 / +60", "–", desc="needs 2 h of readings")
    if sp:
        p = sp["probability"] * 100
        tiles += ui.stat(f"Spike &gt; {sp['spike_above']:.0f} in {sp['horizon_minutes']} min", f"{p:.0f}", "%",
                         "<b style='color:var(--k-red)'>early warning</b>" if sp.get("spike_likely")
                         else "glucose_spike_90m", ui.KDIGO_HEX["red"] if sp.get("spike_likely") else None)
    else:
        tiles += ui.stat("Spike &gt; 250 in 90 min", "–", desc="no recent forecast")
    st_sum = sum(x["value"] for x in steps)
    tiles += ui.stat("Heart rate", f"{hr[-1]['value']:.0f}" if hr else "–", "bpm",
                     f"steps last hour: {st_sum:,.0f}" if steps else "no step data")
    md(f"<div class='grid g4' style='margin-top:10px'>{tiles}</div>")

    # CGM chart + forecast
    if rows:
        d = [r["value"] for r in rows[-36:]]
        n = len(d)
        fcs = [d[-1]] + [None] * 5 + [fc.get("plus_30")] + [None] * 5 + [fc.get("plus_60")] \
            if fc.get("plus_30") is not None else []
        pts = [(i, v, ui.KDIGO_HEX["red"]) for i, v in enumerate(d) if v < 70] + \
              [(i, v, ui.KDIGO_HEX["orange"]) for i, v in enumerate(d) if v > 250]
        xl = ui.time_labels([r["time"] for r in rows[-36:]], 6) + [""] * 12
        if fcs:
            xl[n - 1 + 6], xl[n - 1 + 12] = "+30", "+60"
        series = [{"data": d, "area": True, "end": True, "points": pts}]
        if fcs:
            series.append({"data": fcs, "offset": n - 1, "color": ui.GREY, "dash": "4 5", "width": 1.6})
        cgm_chart = ui.line_chart(series, 40, max(320, max(d) + 10), w=760, h=300, y_ticks=[54, 70, 180, 250, 300],
                                  band=(70, 180), refs=[(70, "70", ui.KDIGO_HEX["red"]),
                                                        (250, "250", ui.KDIGO_HEX["orange"])],
                                  x_labels=xl, n=n + 12, uid="cgm")
    else:
        cgm_chart = "<div class='empty'>Waiting for sensor readings…</div>"
    hr_chart = (ui.line_chart([{"data": [x["value"] for x in hr[-36:]], "color": "#46565F", "width": 1.5}], 50, 110,
                              w=380, h=120, y_ticks=[60, 80, 100],
                              x_labels=ui.time_labels([x["time"] for x in hr[-36:]], 12), uid="hr")
                if hr else "<div class='empty'>No heart-rate data</div>")
    c = st.columns([1.7, 1], gap="medium")
    with c[0]:
        md(ui.card("CGM · latest readings + forecast", cgm_chart,
                   ui.legend([("glucose", ui.NAVY), ("forecast", ui.GREY), ("70–180", "#E8EEF5")])))
    with c[1]:
        with ui.box("livefeed"):
            ui.card_head("Alerts", "<span class='faint' style='font-size:12px'>auto</span>")
            if not live_alerts:
                md("<div class='empty'>No alerts</div>")
            for a in live_alerts[:6]:
                cc = st.columns([5, 1.2], vertical_alignment="center")
                cc[0].markdown(f"<div class='row' style='align-items:flex-start;gap:10px'><span class='sev {a['severity']}'>"
                               f"</span><div><div style='font-size:13px'>{esc(a['message'])}</div><div class='faint' "
                               f"style='font-size:11.5px'>{ui.when(a['created_at'])} · <span class='mono'>{a['type']}"
                               "</span></div></div></div>", unsafe_allow_html=True)
                if cc[1].button("Ack", key=f"ack_{a['id']}", type="tertiary"):
                    api.post(f"/alerts/{a['id']}/ack")
                    st.rerun(scope="fragment")
        md("<div style='height:12px'></div>" + ui.card("Heart rate", hr_chart))
    # toasts for new alerts
    seen = st.session_state.setdefault("seen_alerts", set())
    first = not seen
    for a in live_alerts:
        if a["id"] not in seen:
            seen.add(a["id"])
            if not first and a["severity"] in ("critical", "warning"):
                st.toast(f"{ui.SEVERITY_ICON[a['severity']]} {a['message']}")


# ---------------- Treatments ----------------

def tab_treatments(pid: str, twin: dict) -> None:
    try:
        tr = api.cached_get(f"/patients/{pid}/treatments")
    except api.APIError as e:
        ui.show_error(e)
        return
    if not tr.get("available"):
        md(f"<div class='card'><div class='empty'>{esc(tr.get('reason', 'Not available'))}</div></div>")
        return
    bl = tr["baseline"]
    before = bl["risk_3y"] * 100
    opts = sorted(tr["options"], key=lambda o: o["risk_after"])
    left, right = st.columns([1.5, 1], gap="medium")
    with left:
        with ui.box("tx"):
            ui.card_head("Eligible options · ranked by risk reduction",
                         "<span class='faint' style='font-size:12px'>KDIGO 2022 + ADA rules · switch on to test</span>")
            for i, o in enumerate(opts, 1):
                after = o["risk_after"] * 100
                on = st.session_state.get(f"txon_{pid}_{o['option']}")
                row = st.container(key=f"txrow{'_on' if on else ''}_{i}")
                cc = row.columns([.35, 6, 1], vertical_alignment="center")
                cc[0].markdown(f"<div class='tx'><span class='rank'>{i}</span></div>", unsafe_allow_html=True)
                cc[1].markdown(
                    f"<div class='tx'><h4>{esc(o['label'])} "
                    f"{ui.chip('lifestyle', 'plain') if o.get('kind') != 'drug' else ''}</h4>"
                    f"<div class='delta'><span class='num'>{before:.0f}% → <b style='color:{ui.pct_hex(after)}'>"
                    f"{after:.0f}%</b></span>{ui.chip('−%.0f pts' % (o['absolute_reduction'] * 100), 'accent')}"
                    + (f"<span class='faint'>HbA1c → {o['hba1c_after_expected']}%</span>"
                       if o.get("hba1c_after_expected") else "")
                    + f"</div><div class='src'>HR {o.get('kidney_hr') or '–'} · {esc(o['reason'])} · source: "
                    f"{esc(o['source'])}{' (to verify)' if not o.get('verified') else ''}"
                    + (f" · <b style='color:var(--k-orange)'>caution: {esc('; '.join(o['cautions']))}</b>"
                       if o.get("cautions") else "") + "</div></div>", unsafe_allow_html=True)
                cc[2].toggle("Apply", key=f"txon_{pid}_{o['option']}", label_visibility="collapsed")
        st.write("")
        warn = "".join(ui.feed_item("warning", f"<b>{esc(w)}</b>", right=ui.chip("caution", "orange"))
                       for w in tr["warnings"]) or "<div class='empty'>No medicine safety warnings.</div>"
        ne = "".join(ui.feed_item("info", f"<b>{esc(n['label'])}</b><div class='faint' style='font-size:12px'>"
                                          f"{esc(n['reason'])}</div>") for n in tr["not_eligible"])
        md(ui.card("Cautions", warn, pad=False) + "<div style='height:16px'></div>"
           + f"<details class='exp'><summary>Not eligible / already in place ({len(tr['not_eligible'])})</summary>"
           + (ne or "<div class='empty'>None</div>") + "</details>")
    chosen = [o["option"] for o in opts if st.session_state.get(f"txon_{pid}_{o['option']}")]
    with right:
        after, extra = before, ""
        if chosen:
            try:
                r = api.ask(f"/patients/{pid}/treatments/simulate", json={"options": chosen})
                after = r["risk_after"] * 100
                extra = (f"<div class='row between'><span class='muted'>HbA1c</span><b class='num'>{r['hba1c_now']}% → "
                         f"{r['hba1c_after_expected']}%</b></div>"
                         + (f"<div class='row between'><span class='muted'>Systolic BP</span><b class='num'>→ "
                            f"{r['sbp_after']:.0f}</b></div>" if r.get("sbp_after") else "")
                         + f"<div class='row between'><span class='muted'>Combined kidney HR</span><b class='num'>"
                         f"{r['kidney_hr']}</b></div>")
            except api.APIError as e:
                ui.show_error(e)
        kind = "Onset" if bl.get("kind") == "onset" else "Worsening"
        md(ui.card("Tested on the twin",
                   "<div class='stack compare'>"
                   f"<div><div class='lbl'><span>{kind} risk · current plan</span><b>{before:.0f}%</b></div>"
                   f"<div class='track'><i style='width:{before:.0f}%;background:{ui.band_hex(bl['band'])}'>{before:.0f}%</i>"
                   f"</div></div><div><div class='lbl'><span>With selected options</span><b>{after:.0f}%</b></div>"
                   f"<div class='track'><i style='width:{max(after, 4):.0f}%;background:{ui.pct_hex(after)}'>"
                   f"{after:.0f}%</i></div></div>"
                   "<div class='row between' style='border-top:1px solid var(--line-2);padding-top:12px'>"
                   f"<span class='muted'>Absolute risk reduction</span><span class='big-n' style='font-size:24px;"
                   f"color:var(--accent)'>{before - after:.0f} pts</span></div>{extra}"
                   "<p class='faint' style='font-size:11.5px'>Each option changes the twin (HbA1c, BP, weight), the "
                   "kidney model is re-run and the trial hazard ratio applied. Doctor decides. Patients only see "
                   f"lifestyle options. Model: {esc(bl['model_version'])}.</p></div>",
                   ui.chip(f"{len(chosen)} applied", "accent" if chosen else "plain")))
        st.button("Prescribe from Medications →", on_click=set_tab, args=("meds",), width="stretch")


# ---------------- Medications ----------------

def tab_meds(pid: str, twin: dict) -> None:
    rem = api.cached_get(f"/patients/{pid}/reminders")
    a7, a30 = rem["adherence_7d"], rem["adherence_30d"]
    meds = twin["state"]["medications"]
    left, right = st.columns([1.6, 1], gap="medium")
    with left:
        with ui.box("meds"):
            a7p = a7["pct"]
            ui.card_head("Active medicines", f"<span class='faint' style='font-size:12px'>Adherence 7 d: <b style='color:"
                         f"{'var(--k-red)' if a7p is not None and a7p < 80 else 'inherit'}'>"
                         f"{_pct(a7p)}</b> · 30 d: "
                         f"{_pct(a30['pct'])} · {a7['missed']} missed this week</span>")
            if not meds:
                md("<div class='empty'>No medicines yet</div>")
            for med in meds:
                cc = st.columns([3.6, 1.6, .5, .5], vertical_alignment="center")
                cc[0].markdown(f"<b>{esc(med['drug'])}</b> {esc(med['dose'])}<div class='faint' style='font-size:11.5px'>"
                               f"{esc(', '.join(med['classes']) or med['drug_class'])} · {esc(med['frequency'])}"
                               f"{' · with food' if med['with_food'] else ''} · "
                               f"{'from EHR' if med['source'] == 'ehr' else 'by doctor'}</div>", unsafe_allow_html=True)
                cc[1].markdown(f"<span class='mono'>{', '.join(med['times'])}</span>", unsafe_allow_html=True)
                with cc[2].popover("", icon=":material/schedule:", type="tertiary", help="Edit reminder times"):
                    new_times = st.text_input("Reminder times", ", ".join(med["times"]), key=f"times_{med['id']}")
                    if st.button("Save times", key=f"save_{med['id']}", type="primary"):
                        try:
                            api.put(f"/medications/{med['id']}",
                                    json={"times": [x.strip() for x in new_times.split(",") if x.strip()]})
                            st.toast("Reminders updated")
                            st.rerun()
                        except api.APIError as e:
                            ui.show_error(e)
                if cc[3].button("", icon=":material/close:", key=f"stop_{med['id']}", type="tertiary",
                                help=f"Stop {med['drug']}"):
                    api.delete(f"/medications/{med['id']}")
                    st.toast(f"{med['drug']} stopped — reminders cancelled")
                    st.rerun()
        st.write("")
        doses = "".join(ui.feed_item({"missed": "critical", "taken": "info"}.get(d["status"], "warning"),
                                     f"<b>{esc(d['drug'])} {esc(d['dose'])}</b> <span class='faint mono'>"
                                     f"{d['local_time']}</span>",
                                     right=ui.chip(d["status"], {"taken": "green", "missed": "red"}.get(d["status"],
                                                                                                      "plain")))
                        for d in rem["today"]) or "<div class='empty'>No doses today</div>"
        md(ui.card("Today's doses", doses, "<span class='faint' style='font-size:12px'>not marked within 2 h → "
                   "missed</span>", pad=False))
    with right, ui.box("prescribe"):
        ui.card_head("Prescribe", "<span class='faint' style='font-size:12px'>creates reminders</span>")
        with st.form("prescribe", clear_on_submit=True, border=False):
            drug = st.text_input("Drug", placeholder="e.g. Dapagliflozin")
            dose = st.text_input("Dose", placeholder="10 mg")
            times = st.text_input("Times (comma separated)", "08:00")
            food = st.checkbox("Take with food")
            ok = st.form_submit_button("Prescribe", type="primary", width="stretch")
        st.caption("The reminder appears in the patient app immediately and the twin re-runs.")
        if ok and drug:
            try:
                r = api.post(f"/patients/{pid}/medications",
                             json={"drug": drug, "dose": dose, "with_food": food,
                                   "times": [x.strip() for x in times.split(",") if x.strip()] or ["08:00"]})
                st.toast(f"Prescribed {drug}" + (f" · twin re-run: DKD risk {r['dkd_risk_3y']:.0%}"
                                                 if r.get("dkd_risk_3y") is not None else ""))
                st.rerun()
            except api.APIError as e:
                ui.show_error(e)


def _pct(v) -> str:
    return f"{v:.0f}%" if v is not None else "–"


# ---------------- Meals ----------------

def tab_meals(pid: str, twin: dict) -> None:
    meals = api.cached_get(f"/patients/{pid}/meals")
    top = api.cached_get(f"/patients/{pid}/meals/top-foods")
    rows = []
    for m in meals[:20]:
        sp = m["spike"]
        rows.append([f"<span class='faint'>{ui.local(m['time'])}</span>",
                     "<span style='white-space:normal;display:inline-block;min-width:220px'>" + esc(", ".join(
                         i["food"] + (" ×%g" % i["servings"] if i["servings"] != 1 else "") for i in m["items"]))
                     + "</span>",
                     f"{m['total_carbs_g']:.0f} g", f"{m['glucose_before']:.0f}" if m["glucose_before"] else "–",
                     f"{m['glucose_peak']:.0f}" if m["glucose_peak"] else "–",
                     ui.chip("in 2 h", "plain") if sp is None else
                     ui.chip(f"+{sp:.0f}", "red" if sp > 90 else "orange" if sp > 60 else "yellow")])
    tops = "".join(f"<div><div class='row between' style='font-size:13px;margin-bottom:5px'><span><b>{i}.</b> "
                   f"{esc(f['food'])}</span><span class='num'>+{f['avg_spike']:.0f} mg/dL avg · {f['meals']}×</span></div>"
                   f"{ui.progress(f['avg_spike'] / 1.6, ui.KDIGO_HEX['red'] if f['avg_spike'] > 90 else ui.KDIGO_HEX['orange'])}"
                   "</div>" for i, f in enumerate(top, 1)) or "<div class='empty'>No meals with sensor readings yet</div>"
    md("<div class='grid' style='grid-template-columns:minmax(0,1.6fr) minmax(0,1fr);align-items:start'>"
       + ui.card("Logged meals · glucose rise in 2 h",
                 ui.table(["When", "Foods", "Carbs", "Before", "Peak", "Spike"], rows, "No meals logged"),
                 "<span class='faint' style='font-size:12px'>peak (0–2 h) minus before</span>", pad=False)
       + ui.card("Top 3 spiking foods", f"<div class='stack' style='gap:12px'>{tops}</div>") + "</div>")


# ---------------- EHR ----------------

def _hl(js: str) -> str:
    s = esc(js)
    s = re.sub(r"(&quot;[^&]*?&quot;)(:)", r"<span class='k'>\1</span>\2", s)
    return re.sub(r": (&quot;.*?&quot;)", r": <span class='s'>\1</span>", s)


def tab_ehr(pid: str, twin: dict) -> None:
    left, right = st.columns(2, gap="medium")
    with left:
        with ui.box("labcsv"):
            ui.card_head("Lab CSV", "<span class='faint' style='font-size:12px'>date, test, value, unit</span>")
            lab = st.file_uploader("Lab CSV", type=["csv"], key="labcsv", label_visibility="collapsed")
            if st.button("Upload labs", type="primary", disabled=lab is None):
                try:
                    r = api.upload(f"/patients/{pid}/labs/upload", lab.name, lab.getvalue())
                    log = [f"Parsed {lab.name}", f"{r['saved']} results saved"]
                    if r.get("problems"):
                        log.append(f"Problems: {r['problems']}")
                    log.append("Twin re-run: state → kidney model → HbA1c forecast → alert rules")
                    st.session_state[f"lablog_{pid}"] = log
                except api.APIError as e:
                    st.session_state[f"lablog_{pid}"] = [f"Error: {e}"]
            log = st.session_state.get(f"lablog_{pid}")
            md("<div class='code' style='min-height:80px'>" + (
                "".join(f"<div><span class='k'>✓</span> {esc(x)}</div>" for x in log) if log
                else "<span class='k'>›</span> Waiting for upload…") + "</div>")
            if log:
                st.button("See Overview →", on_click=set_tab, args=("overview",), type="primary")
        st.write("")
        with ui.box("saveres"):
            ui.card_head("Save result", "<span class='faint' style='font-size:12px'>one value, typed by the doctor</span>")
            with st.form("manual_lab", clear_on_submit=True, border=False):
                cc = st.columns(3)
                test = cc[0].selectbox("Test", ["potassium", "creatinine", "uacr", "hba1c", "ldl", "sbp", "dbp",
                                                "weight"])
                val = cc[1].number_input("Value", min_value=0.0, step=0.1)
                day = cc[2].date_input("Date", datetime.now().date())
                unit = st.text_input("Unit (blank = standard)")
                ok = st.form_submit_button("Save result", type="primary")
            if ok:
                try:
                    r = api.post(f"/patients/{pid}/observations",
                                 json=[{"variable": test, "value": val, "unit": unit,
                                        "time": f"{day.isoformat()}T09:00:00+05:30", "device": "lab"}])
                    st.toast(f"Saved. Twin re-run: {r['reruns']}")
                    for a in r.get("new_alerts") or []:
                        st.warning(a if isinstance(a, str) else a.get("message", str(a)))
                except api.APIError as e:
                    ui.show_error(e)
        st.write("")
        with ui.box("ehrimport"):
            ui.card_head("Import from hospital EHR", "<span class='faint' style='font-size:12px'>FHIR R4</span>")
            try:
                samples = api.cached_get("/ehr/samples")
            except api.APIError:
                samples = []
            cc = st.columns([2, 1], vertical_alignment="bottom")
            name = cc[0].selectbox("Synthea sample bundle", samples)
            if cc[1].button("Import sample", disabled=not samples, width="stretch"):
                with st.spinner("Importing and running the twin..."):
                    try:
                        r = api.post("/ehr/import/sample", json={"name": name})
                        st.success(f"{'Created' if r['created'] else 'Updated'} {r['patient_id']} ({r['display_name']}): "
                                   f"{r['observations_saved']} observations, {r['medications_added']} medicines")
                    except api.APIError as e:
                        ui.show_error(e)
            cc = st.columns([2, 1], vertical_alignment="bottom")
            fid = cc[0].text_input("FHIR patient id (HAPI R4 test server)", placeholder="e.g. 56196")
            if cc[1].button("Fetch", disabled=not fid, width="stretch"):
                with st.spinner("Fetching Patient/$everything ..."):
                    try:
                        r = api.post("/ehr/fetch", json={"fhir_patient_id": fid.strip()})
                        st.success(f"Imported {r['patient_id']} ({r['display_name']}): {r['observations_saved']} "
                                   "observations")
                    except api.APIError as e:
                        ui.show_error(e)
            up = st.file_uploader("Or upload a FHIR Bundle (.json)", type=["json"])
            if up and st.button("Import uploaded bundle"):
                try:
                    r = api.post("/ehr/import/bundle", json=json.loads(up.getvalue()))
                    st.success(f"Imported {r['patient_id']}")
                except (api.APIError, ValueError) as e:
                    ui.show_error(e)
    with right, ui.box("fhirexp"):
        ui.card_head("FHIR export", "<span class='faint mono' style='font-size:12px'>GET /patients/{id}/fhir</span>")
        key = f"fhir_export_{pid}"
        if not st.session_state.get(key):
            md("<div class='empty'>The twin can be sent back to the hospital system in the same standard "
               "(FHIR R4 Bundle).</div>")
            if st.button("Prepare FHIR bundle", type="primary"):
                st.session_state[key] = json.dumps(api.get(f"/patients/{pid}/fhir"), indent=2)
                st.rerun()
        else:
            st.download_button("Download", st.session_state[key], f"{pid}_fhir_bundle.json", "application/fhir+json",
                               icon=":material/download:", type="primary")
            lines = st.session_state[key].split("\n")
            md("<div class='code' style='max-height:560px'>" + _hl("\n".join(lines[:60])).replace("\n", "<br>")
               + ("<br>  …" if len(lines) > 60 else "") + "</div>")


# ---------------- AI assistant ----------------

def _md_to_html(text: str) -> str:
    """Tiny markdown → HTML for chat bubbles (bold, code, line breaks, bullets)."""
    s = esc(text)
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"(?m)^\s*[-*•] ", "• ", s)
    return s.replace("\n", "<br>")


def _ask_doc(pid: str, q: str) -> None:
    chat = st.session_state.setdefault(f"chat_{pid}", [])
    chat.append(("user", q))
    try:
        r = api.post(f"/patients/{pid}/assistant", json={"mode": "chat_doctor", "question": q})
        src = "offline summary" if r["offline"] else f"{r['provider']}" + (" · cached" if r.get("cached") else "")
        chat.append(("assistant", r["text"], src))
    except api.APIError as e:
        chat.append(("assistant", f"Error: {e}", ""))


def _quick(pid: str) -> None:
    q = st.session_state.get(f"quick_{pid}")
    if q:
        _ask_doc(pid, q)
    st.session_state[f"quick_{pid}"] = None


def tab_ai(pid: str, twin: dict) -> None:
    status = api.cached_get("/assistant/status")
    left, right = st.columns(2, gap="medium")
    with left, ui.box("aisum"):
        ui.card_head("Clinical summary")
        if not status["configured"]:
            st.info(status["message"])
        if st.button("Generate clinical summary", icon=":material/auto_awesome:", type="primary"):
            with st.spinner("Sending the de-identified twin + top 3 guideline notes …"):
                st.session_state[f"ai_sum_{pid}"] = api.post(f"/patients/{pid}/assistant",
                                                             json={"mode": "doctor_summary"})
        res = st.session_state.get(f"ai_sum_{pid}")
        if res:
            with st.container(key="aiout"):
                st.markdown(res["text"])
            notes = "".join(f"<div style='padding:3px 0'><span class='src-chip'>{esc(x['title'])}</span> "
                            f"<span class='faint' style='font-size:12px'>{esc(x['source'])}</span></div>"
                            for x in res.get("sources") or [])
            badge = ui.chip("offline summary", "orange") if res["offline"] else ui.chip(
                esc(res["provider"]) + (" · cached 30 min" if res.get("cached") else ""), "accent")
            md((f"<div class='eyebrow' style='margin:10px 0 6px'>Guideline notes used</div>{notes}" if notes else "")
               + f"<p class='faint' style='font-size:11.5px;margin-top:10px'>{badge} De-identified data only.</p>")
        else:
            md("<div class='empty'>The assistant explains the twin — it never makes predictions itself.</div>")
    with right, ui.box("aichat"):
        ui.card_head("Ask about this patient", ui.chip("chat_doctor", "plain"))
        chat = st.session_state.get(f"chat_{pid}", [])
        msgs = "".join(f"<div class='msg me'>{esc(m[1])}</div>" if m[0] == "user" else
                       f"<div class='msg bot'>{_md_to_html(m[1])}{f'<small>{esc(m[2])}</small>' if m[2] else ''}</div>"
                       for m in chat)
        md("<div class='chat'>" + (msgs or "<div class='empty' style='padding:30px 10px'>Ask about this patient’s "
                                   "twin. Answers quote the values used.</div>") + "</div>")
        st.pills("Suggestions", ["Why is the kidney risk high?", "Is finerenone appropriate?", "Why SGLT2i first?",
                                 "Is the metformin dose OK?"], key=f"quick_{pid}", label_visibility="collapsed",
                 on_change=_quick, args=(pid,))
        with st.form(f"chatf_{pid}", clear_on_submit=True, border=False):
            cc = st.columns([5, 1], vertical_alignment="bottom")
            q = cc[0].text_input("Question", placeholder="Ask a question…", label_visibility="collapsed")
            sent = cc[1].form_submit_button("Send", type="primary", width="stretch")
        if sent and q.strip():
            with st.spinner("Thinking…"):
                _ask_doc(pid, q.strip())
            st.rerun()


# ---------------- Report ----------------

def tab_report(pid: str, twin: dict) -> None:
    s, preds = twin["state"], twin["predictions"]
    k, dkd = s["kidney"], preds.get("dkd_3y") or {}
    risk = (dkd.get("risk_3y") or 0) * 100
    labs = "".join(f"<tr><td>{LAB_NAMES[key]}</td><td>{lab['value']:g} {esc(lab['unit'])}</td>"
                   f"<td>{ui.local(lab['time'], '%Y-%m-%d')}</td></tr>"
                   for key in LAB_NAMES if (lab := s["labs"].get(key)))
    try:
        opts = sorted(api.cached_get(f"/patients/{pid}/treatments").get("options", []), key=lambda o: o["risk_after"])
    except api.APIError:
        opts = []
    ranked = "<br>".join(f"{i}. {esc(o['label'].split(' (')[0])} {o['risk_before']:.0%} → {o['risk_after']:.0%}"
                         for i, o in enumerate(opts[:3], 1)) or "—"
    preview = (f"<div class='pdf'><div class='hdr'><div><h5>GlycoRenal Twin · Clinical report</h5><div class='faint'>"
               f"{pid} · {datetime.now():%d %b %Y} · {esc(me.get('full_name', ''))}</div></div>{ui.logo(30)}</div>"
               f"<b>Risk</b><div>3-yr kidney {'onset' if dkd.get('kind') == 'onset' else 'worsening'}: "
               f"<b style='color:{ui.band_hex(dkd.get('band'))}'>{risk:.0f}%</b> · KDIGO {k.get('stage') or '–'}</div>"
               f"<b style='display:block;margin-top:6px'>Labs</b><table><tr><th>Test</th><th>Value</th><th>Date</th></tr>"
               f"{labs}</table><b>Genetics</b><div>{'simulated markers on file' if s.get('genetics') else '—'}</div>"
               f"<b style='display:block;margin-top:6px'>Ranked options</b><div>{ranked}</div>"
               "<b style='display:block;margin-top:6px'>AI summary</b><div class='ln'></div><div class='ln'></div>"
               "<div class='ln' style='width:70%'></div></div>")
    left, right = st.columns([1, 1.1], gap="large", vertical_alignment="center")
    with left:
        md(preview)
    with right:
        md("<p class='muted'>Doctor: risk, KDIGO grid, labs with dates and out-of-date flags, genetics, trends, "
           "14-day glucose profile, ranked options with sources and the AI summary. Patient: one page, English and "
           "Hindi side by side.</p><div style='height:12px'></div>")
        with ui.box("reports"):
            ui.card_head("PDF reports")
            if st.session_state.get(f"pdf_doc_{pid}"):
                st.download_button("Download clinical report", st.session_state[f"pdf_doc_{pid}"],
                                   f"{pid}_clinical_report.pdf", "application/pdf", type="primary",
                                   icon=":material/download:", width="stretch")
            elif st.button("Prepare clinical report (doctor)", type="primary", width="stretch"):
                with st.spinner("Building the clinical report ..."):
                    try:
                        st.session_state[f"pdf_doc_{pid}"] = api.get_bytes(f"/patients/{pid}/report/doctor.pdf")
                        st.toast("Report ready: clinical report (doctor)")
                        st.rerun()
                    except api.APIError as e:
                        ui.show_error(e)
            if st.session_state.get(f"pdf_pat_{pid}"):
                st.download_button("Download patient report (EN + हिंदी)", st.session_state[f"pdf_pat_{pid}"],
                                   f"{pid}_patient_report.pdf", "application/pdf", icon=":material/download:",
                                   width="stretch")
            elif st.button("Prepare patient report (English + हिंदी)", width="stretch"):
                with st.spinner("Building the patient report ..."):
                    try:
                        st.session_state[f"pdf_pat_{pid}"] = api.get_bytes(f"/patients/{pid}/report/patient.pdf")
                        st.toast("Report ready: patient report (English + हिंदी)")
                        st.rerun()
                    except api.APIError as e:
                        ui.show_error(e)


# --------------------------------------------------------------------------- route

if nav == "alerts":
    alerts_page()
elif st.session_state.get("pid") and st.session_state["pid"] in by_id:
    patient_detail(st.session_state["pid"])
else:
    patient_list()
