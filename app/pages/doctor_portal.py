"""Doctor portal: patient list sorted by DKD risk, then patient detail tabs
(Overview, Live, Treatments, Medications, Meals, EHR, AI, Report). Decision support only.
"""

from __future__ import annotations

import json
from datetime import datetime

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import api_client as api
import ui

ui.sidebar_user()
st.title("🩺 Doctor portal")


try:
    patients = api.cached_get("/patients")
except api.APIError as e:
    ui.show_error(e)
    st.stop()

# ---------------- patient list ----------------
with st.expander(f"Patients ({len(patients)}), highest predicted 3-year kidney risk first", expanded=True):
    table =["<table style='width:100%;border-collapse:collapse;font-size:14px'>",
             "<tr style='text-align:left;border-bottom:2px solid #e4e7eb'><th>ID</th><th>Name</th><th>Age</th>"
             "<th>KDIGO</th><th>DKD risk (3 yr)</th><th>HbA1c</th><th>eGFR</th><th>UACR</th><th>TIR</th>"
             "<th>Adherence</th><th>Alerts</th></tr>"]
    for p in patients:
        fmt = lambda v, f="{:.0f}", s="": (f.format(v) + s) if v is not None else "–"  # noqa: E731
        table.append(
            f"<tr style='border-bottom:1px solid #eef2f5'><td><b>{p['patient_id']}</b></td><td>{p['display_name']}</td>"
            f"<td>{p['age']}{p['sex']}</td><td>{ui.kdigo_chip(p['kdigo'], p['kdigo_colour'])}</td>"
            f"<td>{ui.risk_chip(p['dkd_risk_3y'], p['risk_band'])}</td><td>{fmt(p['hba1c'], '{:.1f}', '%')}</td>"
            f"<td>{fmt(p['egfr'])}</td><td>{fmt(p['uacr'])}</td><td>{fmt(p['tir_pct'], '{:.0f}', '%')}</td>"
            f"<td>{fmt(p['adherence_7d'], '{:.0f}', '%')}</td>"
            f"<td>{'🔔 ' + str(p['n_alerts']) if p['n_alerts'] else '–'}</td></tr>")
    table.append("</table>")
    st.markdown("".join(table), unsafe_allow_html=True)

ids = [p["patient_id"] for p in patients]
labels = {p["patient_id"]: f"{p['patient_id']} · {p['display_name']}" for p in patients}
default = ids.index(st.session_state.get("pid", "IND-0042")) if st.session_state.get("pid", "IND-0042") in ids else 0
pid = st.selectbox("Open patient", ids, index=default, format_func=lambda i: labels[i])
st.session_state["pid"] = pid

try:
    twin = api.cached_get(f"/patients/{pid}/twin")
except api.APIError as e:
    ui.show_error(e)
    st.stop()
s, preds, alerts = twin["state"], twin["predictions"], twin["alerts"]
k, g, cgm = s["kidney"], s["glycaemia"], s["cgm"]
dkd = preds.get("dkd_3y", {})

tabs = st.tabs(["Overview", "Live", "Treatments", "Medications", "Meals", "EHR", "AI assistant", "Report"])

# ---------------- Overview ----------------
with tabs[0]:
    c = st.columns(6)
    c[0].markdown(f"**DKD risk (3 yr)**<br>{ui.risk_chip(dkd.get('risk_3y'), dkd.get('band'))}"
                  f"<br><small>{dkd.get('outcome', '')}</small>", unsafe_allow_html=True)
    h3 = (preds.get("hba1c_3m") or {}).get("hba1c_3m")
    c[1].metric("HbA1c", f"{g['hba1c']}%", f"{h3 - g['hba1c']:+.1f} forecast 3 mo" if h3 and g["hba1c"] else None,
                delta_color="inverse")
    c[2].metric("eGFR", f"{k['egfr']:.0f}" if k.get("egfr") else "–",
                f"{k['egfr_slope_per_year']:+.1f} /yr" if k.get("egfr_slope_per_year") is not None else None)
    c[3].metric("UACR", f"{k['uacr']:.0f} mg/g" if k.get("uacr") is not None else "–",
                f"was {k['a_stage_previous']}" if k.get("a_stage_previous") and k.get("a_stage_previous") != k.get("a_stage") else None,
                delta_color="off")
    v = s["vitals"]
    c[4].metric("BP", f"{v['sbp']:.0f}/{v['dbp']:.0f}" if v["sbp"] else "–", f"target < {s['bp']['target']}",
                delta_color="off")
    c[5].metric("Adherence (7 d)", f"{s['adherence']['pct_7d']:.0f}%" if s["adherence"]["pct_7d"] is not None else "–")

    left, right = st.columns([1, 2])
    with left:
        st.markdown(f"**KDIGO {k.get('stage', '')}** {ui.kdigo_chip(k.get('stage'), k.get('colour'))}",
                    unsafe_allow_html=True)
        st.markdown(ui.kdigo_grid(k.get("g_stage"), k.get("a_stage")), unsafe_allow_html=True)
        def _val(d):
            if d["feature"] == "log_uacr" and isinstance(d["value"], (int, float)):
                return f"{2.718281828 ** d['value']:.0f} mg/g"
            return round(d["value"], 1) if isinstance(d["value"], float) else d["value"]
        drivers = dkd.get("drivers", [])
        up = [d for d in drivers if d["contribution"] > 0]
        down = [d for d in drivers if d["contribution"] <= 0]
        st.markdown("**Raising this patient's risk**")
        for d in up:
            st.write(f"🔺 {d['label']} ({_val(d)})")
        if down:
            st.caption("Lower than the average patient in the model: " +
                       ", ".join(f"{d['label']} ({_val(d)})" for d in down))
        st.caption(dkd.get("model_version", ""))
    with right:
        h = s["history"]
        st.plotly_chart(ui.trend_chart(h["egfr"], "eGFR (CKD-EPI 2021)", "mL/min/1.73m²", 60, "above"),
                        width="stretch", key="egfr")
        st.plotly_chart(ui.trend_chart(h["hba1c"], "HbA1c", "%", g["target"]), width="stretch", key="hba1c")
    if s["freshness_flags"]:
        st.warning("Stale or missing data: " + "; ".join(s["freshness_flags"]))
    m = cgm.get("metrics") or {}
    if m:
        st.caption(f"CGM 14 days: TIR {m['tir_pct']}% · below 70 {m['tbr_pct']}% · below 54 {m['tbr_severe_pct']}% · "
                   f"above 180 {m['tar_pct']}% · CV {m['cv_pct']}% · GMI {m['gmi_pct']}% · "
                   f"data {m['sufficiency_pct']}%")

# ---------------- Live ----------------
with tabs[1]:
    sim = api.get(f"/patients/{pid}/devices")["simulator"]
    b = st.columns([1, 1, 1, 1, 3])
    if not sim["running"]:
        if b[0].button("▶ Start sensor", key="sim_start"):
            api.post(f"/patients/{pid}/devices/simulator/start", json={})
            st.rerun()
    else:
        if b[0].button("■ Stop sensor", key="sim_stop"):
            api.post(f"/patients/{pid}/devices/simulator/stop")
            st.rerun()
        if b[1].button("🍚 Meal spike", key="sim_meal"):
            api.post(f"/patients/{pid}/devices/simulator/scenario", json={"scenario": "meal_spike"})
        if b[2].button("📉 Hypo", key="sim_hypo"):
            api.post(f"/patients/{pid}/devices/simulator/scenario", json={"scenario": "hypo"})
    b[4].caption(f"Sensor: {'running (' + sim['source'] + ', ' + str(sim['readings_sent']) + ' readings sent)' if sim['running'] else 'off'}"
                 " · one 5-minute reading every few seconds in demo mode")

    @st.fragment(run_every=5)
    def live_panel():
        try:
            _live_panel()
        except Exception as e:  # noqa: BLE001  (show the problem, keep the rest of the page working)
            st.error(f"Live panel error: {e}")

    def _live_panel():
        try:
            rows = api.get(f"/patients/{pid}/observations", variable="glucose", device="cgm", hours=6)
            hr = api.get(f"/patients/{pid}/observations", variable="heart_rate", hours=1)
            tw = api.get(f"/patients/{pid}/twin")
            live_alerts = api.get(f"/patients/{pid}/alerts")
        except api.APIError as e:
            ui.show_error(e)
            return
        st_cgm = tw["state"]["cgm"]
        fc = tw["predictions"].get("glucose_30m")
        latest = st_cgm.get("latest")
        c = st.columns(4)
        if latest:
            c[0].metric("Glucose now", f"{latest['value']:.0f} mg/dL {latest['arrow']}",
                        f"{ui.minutes_ago(latest['time'])} min ago", delta_color="off")
        if fc:
            c[1].metric("Forecast +30 / +60 min", f"{fc['plus_30']} / {fc['plus_60']}",
                        "⚠ hypo risk" if fc.get("hypo_risk_30m") else None, delta_color="inverse")
        if hr:
            c[2].metric("Heart rate", f"{hr[-1]['value']:.0f} /min")
        steps = tw["state"]["vitals"]["steps_per_day"]
        c[3].metric("Steps (7-day avg)", f"{steps:,}" if steps else "–")
        st.plotly_chart(ui.cgm_chart(rows[-150:], "CGM, latest readings (green band = 70-180 mg/dL)", fc),
                        width="stretch", key=f"cgm_{pid}")
        seen = st.session_state.setdefault("seen_alerts", set())
        for a in live_alerts:
            if a["id"] not in seen:
                seen.add(a["id"])
                if a["severity"] in ("critical", "warning") and len(seen) > len(live_alerts) - 3:
                    st.toast(f"{ui.SEVERITY_ICON[a['severity']]} {a['message']}")
        st.markdown("**Alerts**")
        for a in live_alerts[:8]:
            cols = st.columns([6, 1])
            cols[0].write(f"{ui.SEVERITY_ICON[a['severity']]} {a['message']}  \n"
                          f"<small>{a['created_at'][11:16]} UTC</small>", unsafe_allow_html=True)
            if cols[1].button("Ack", key=f"ack_{a['id']}"):
                api.post(f"/alerts/{a['id']}/ack")
                st.rerun(scope="fragment")
        if not live_alerts:
            st.caption("No active alerts.")

    live_panel()

# ---------------- Treatments ----------------
with tabs[2]:
    try:
        tr = api.cached_get(f"/patients/{pid}/treatments")
    except api.APIError as e:
        ui.show_error(e)
        tr = {"available": False, "reason": str(e)}
    if not tr.get("available"):
        st.info(tr.get("reason", "Not available"))
    else:
        bl = tr["baseline"]
        st.markdown(f"Baseline: **{bl['risk_3y']:.0%}** predicted risk of {bl['outcome']} "
                    f"{ui.risk_chip(bl['risk_3y'], bl['band'])} · {bl['model_version']}", unsafe_allow_html=True)
        for w in tr["warnings"]:
            st.error(f"Medicine safety: {w}")
        st.markdown("**Eligible options, ranked by predicted absolute risk reduction**")
        for o in tr["options"]:
            with st.container(border=True):
                cc = st.columns([5, 2])
                cc[0].markdown(f"**{o['label']}**  \n{o['reason']}" +
                               (f"  \n⚠ {'; '.join(o['cautions'])}" if o["cautions"] else "") +
                               f"  \n<small>Source: {o['source']}{' · to verify' if not o['verified'] else ''}</small>",
                               unsafe_allow_html=True)
                cc[1].markdown(f"{o['risk_before']:.0%} → **{o['risk_after']:.0%}**  \n"
                               f"(−{o['absolute_reduction'] * 100:.0f} points)" +
                               (f"  \nHbA1c → {o['hba1c_after_expected']}%" if o.get("hba1c_after_expected") else ""))
        st.markdown("**Apply to simulation** (what-if; nothing is prescribed)")
        chosen = st.multiselect("Options to combine", [o["option"] for o in tr["options"]],
                                default=[o["option"] for o in tr["options"]][:2],
                                format_func=lambda x: next(o["label"] for o in tr["options"] if o["option"] == x))
        if chosen:
            try:
                sim_r = api.post(f"/patients/{pid}/treatments/simulate", json={"options": chosen})
                fig = go.Figure(go.Bar(x=["Now", "With plan"], y=[sim_r["risk_before"] * 100, sim_r["risk_after"] * 100],
                                       marker_color=[ui.BAND_HEX.get(bl["band"]), ui.BAND_HEX.get(sim_r["band_after"])],
                                       text=[f"{sim_r['risk_before']:.0%}", f"{sim_r['risk_after']:.0%}"],
                                       textposition="outside"))
                fig.update_layout(height=280, yaxis_title="3-year risk (%)", yaxis_range=[0, 105],
                                  margin=dict(l=10, r=10, t=10, b=10), plot_bgcolor="#fff")
                cc = st.columns([2, 3])
                cc[0].plotly_chart(fig, width="stretch", key="sim_bar")
                cc[1].markdown(f"**Combined plan:** {', '.join(sim_r['labels'])}  \n"
                               f"Risk {sim_r['risk_before']:.0%} → **{sim_r['risk_after']:.0%}** "
                               f"(kidney HR {sim_r['kidney_hr']})  \n"
                               f"HbA1c {sim_r['hba1c_now']}% → {sim_r['hba1c_after_expected']}% expected"
                               + (f" (model: {sim_r['hba1c_3m_model']}%)" if sim_r.get("hba1c_3m_model") else "") +
                               f"  \nSystolic BP → {sim_r['sbp_after']:.0f}" if sim_r.get("sbp_after") else "")
                st.caption(sim_r["disclaimer"])
            except api.APIError as e:
                ui.show_error(e)
        with st.expander("Not eligible / already in place"):
            for n in tr["not_eligible"]:
                st.write(f"**{n['label']}**: {n['reason']}")

# ---------------- Medications ----------------
with tabs[3]:
    rem = api.cached_get(f"/patients/{pid}/reminders")
    a7, a30 = rem["adherence_7d"], rem["adherence_30d"]
    c = st.columns(3)
    c[0].metric("Adherence 7 days", f"{a7['pct']:.0f}%" if a7["pct"] is not None else "–",
                f"{a7['missed']} missed, {a7['skipped']} skipped", delta_color="off")
    c[1].metric("Adherence 30 days", f"{a30['pct']:.0f}%" if a30["pct"] is not None else "–")
    st.markdown("**Current medicines**")
    for med in s["medications"]:
        with st.container(border=True):
            cc = st.columns([3, 2, 2, 1])
            cc[0].markdown(f"**{med['drug']}** {med['dose']}  \n<small>{', '.join(med['classes'])} · {med['source']}</small>",
                           unsafe_allow_html=True)
            new_times = cc[1].text_input("Times", ", ".join(med["times"]), key=f"times_{med['id']}")
            if cc[2].button("Save times", key=f"save_{med['id']}"):
                try:
                    api.put(f"/medications/{med['id']}", json={"times": [x.strip() for x in new_times.split(",") if x.strip()]})
                    st.success("Reminders updated")
                    st.rerun()
                except api.APIError as e:
                    ui.show_error(e)
            if cc[3].button("Stop", key=f"stop_{med['id']}"):
                api.delete(f"/medications/{med['id']}")
                st.rerun()
    with st.form("prescribe", clear_on_submit=True):
        st.markdown("**Prescribe** (creates daily reminders and re-runs the twin)")
        cc = st.columns([3, 2, 3, 1])
        drug = cc[0].text_input("Drug", placeholder="e.g. Dapagliflozin")
        dose = cc[1].text_input("Dose", placeholder="10 mg")
        times = cc[2].multiselect("Times", ["06:00", "07:00", "08:00", "09:00", "13:00", "14:00", "18:00",
                                            "20:00", "21:00", "22:00"], default=["08:00"])
        food = cc[3].checkbox("With food")
        if st.form_submit_button("Prescribe", type="primary") and drug:
            try:
                r = api.post(f"/patients/{pid}/medications", json={"drug": drug, "dose": dose, "times": times,
                                                                     "with_food": food})
                st.success(f"Prescribed. New predicted DKD risk: {r['dkd_risk_3y']:.0%}" if r["dkd_risk_3y"] else "Prescribed.")
                pass  # api_client clears its cache after every change
            except api.APIError as e:
                ui.show_error(e)
    st.markdown("**Today's doses**")
    st.dataframe(pd.DataFrame([{"time": d["local_time"], "medicine": f"{d['drug']} {d['dose']}", "status": d["status"]}
                               for d in rem["today"]]), hide_index=True, width="stretch")

# ---------------- Meals ----------------
with tabs[4]:
    meals = api.cached_get(f"/patients/{pid}/meals")
    top = api.cached_get(f"/patients/{pid}/meals/top-foods")
    if top:
        st.markdown("**Top spiking foods (avg 2-hour rise)**  " +
                    " · ".join(f"{t['food']} **+{t['avg_spike']:.0f}** ({t['meals']} meals)" for t in top))
    if meals:
        df = pd.DataFrame([{"time": pd.to_datetime(m["time"], format="ISO8601", utc=True).tz_convert("Asia/Kolkata").strftime("%d %b %H:%M"),
                            "foods": ", ".join(f"{i['food']} x{i['servings']:g}" for i in m["items"]),
                            "carbs (g)": m["total_carbs_g"], "before": m["glucose_before"],
                            "peak (2 h)": m["glucose_peak"], "rise": m["spike"]} for m in meals])
        st.dataframe(df.style.background_gradient(subset=["rise"], cmap="OrRd", vmin=0, vmax=200),
                     hide_index=True, width="stretch")
    else:
        st.caption("No meals logged.")

# ---------------- EHR ----------------
with tabs[5]:
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Import from hospital EHR (FHIR R4)**")
        try:
            samples = api.cached_get("/ehr/samples")
        except api.APIError:
            samples = []
        name = st.selectbox("Synthea sample bundle", samples)
        if st.button("Import sample", disabled=not samples):
            with st.spinner("Importing and running the twin..."):
                try:
                    r = api.post("/ehr/import/sample", json={"name": name})
                    st.success(f"{'Created' if r['created'] else 'Updated'} {r['patient_id']} ({r['display_name']}): "
                               f"{r['observations_saved']} observations, {r['medications_added']} medicines, "
                               f"DKD risk {r['dkd_risk_3y']:.0%}" if r["dkd_risk_3y"] is not None else "imported")
                    pass  # api_client clears its cache after every change
                except api.APIError as e:
                    ui.show_error(e)
        fid = st.text_input("Fetch by patient id from the FHIR server (HAPI R4 test server)", placeholder="e.g. 56196")
        if st.button("Fetch from FHIR server", disabled=not fid):
            with st.spinner("Fetching Patient/$everything ..."):
                try:
                    r = api.post("/ehr/fetch", json={"fhir_patient_id": fid.strip()})
                    st.success(f"Imported {r['patient_id']} ({r['display_name']}): {r['observations_saved']} observations")
                    pass  # api_client clears its cache after every change
                except api.APIError as e:
                    ui.show_error(e)
        up = st.file_uploader("Or upload a FHIR Bundle (.json)", type=["json"])
        if up and st.button("Import uploaded bundle"):
            try:
                r = api.post("/ehr/import/bundle", json=json.loads(up.getvalue()))
                st.success(f"Imported {r['patient_id']}")
                pass  # api_client clears its cache after every change
            except (api.APIError, ValueError) as e:
                ui.show_error(e)
    with c2:
        st.markdown("**Export this twin as FHIR R4**")
        if st.button("Prepare FHIR bundle"):
            st.session_state["fhir_export"] = json.dumps(api.get(f"/patients/{pid}/fhir"), indent=1)
        if st.session_state.get("fhir_export"):
            st.download_button("Download FHIR bundle", st.session_state["fhir_export"], f"{pid}_fhir.json",
                               "application/fhir+json")
        st.markdown("**Add lab results**")
        lab = st.file_uploader("Lab CSV (date,test,value,unit)", type=["csv"], key="labcsv")
        if lab and st.button("Upload labs"):
            try:
                r = api.upload(f"/patients/{pid}/labs/upload", lab.name, lab.getvalue())
                st.success(f"Saved {r['saved']} results" + (f"; problems: {r['problems']}" if r["problems"] else ""))
                pass  # api_client clears its cache after every change
            except api.APIError as e:
                ui.show_error(e)
        with st.form("manual_lab", clear_on_submit=True):
            cc = st.columns([2, 1, 1, 1])
            test = cc[0].selectbox("Test", ["hba1c", "creatinine", "uacr", "potassium", "ldl", "sbp", "dbp", "weight"])
            val = cc[1].number_input("Value", min_value=0.0, step=0.1)
            unit = cc[2].text_input("Unit (blank = standard)")
            day = cc[3].date_input("Date", datetime.now().date())
            if st.form_submit_button("Save result"):
                try:
                    r = api.post(f"/patients/{pid}/observations",
                                 json=[{"variable": test, "value": val, "unit": unit,
                                        "time": f"{day.isoformat()}T09:00:00+05:30", "device": "lab"}])
                    st.success(f"Saved. Twin re-run: {r['reruns']}" + (f". Alerts: {r['new_alerts']}" if r["new_alerts"] else ""))
                    pass  # api_client clears its cache after every change
                except api.APIError as e:
                    ui.show_error(e)

# ---------------- AI assistant ----------------
with tabs[6]:
    status = api.cached_get("/assistant/status")
    if not status["configured"]:
        st.info(status["message"])
    if st.button("Generate clinical summary", type="primary"):
        with st.spinner("Asking the AI (can take up to a minute; otherwise the offline summary is shown) ..."):
            st.session_state[f"ai_sum_{pid}"] = api.post(f"/patients/{pid}/assistant", json={"mode": "doctor_summary"})
    res = st.session_state.get(f"ai_sum_{pid}")
    if res:
        badge = "🟠 offline summary" if res["offline"] else f"🟢 {res['provider']}" + (" · cached" if res["cached"] else "")
        st.caption(badge)
        st.markdown(res["text"])
        if res["sources"]:
            st.caption("Guideline notes used: " + "; ".join(f"{x['title']} ({x['source']})" for x in res["sources"]))
    st.markdown("**Ask the twin**")
    chat = st.session_state.setdefault(f"chat_{pid}", [])
    for role, text in chat:
        with st.chat_message(role):
            st.markdown(text)
    q = st.chat_input("e.g. Why is the kidney risk high? Is finerenone an option?", key=f"q_{pid}")
    if q:
        chat.append(("user", q))
        try:
            r = api.post(f"/patients/{pid}/assistant", json={"mode": "chat_doctor", "question": q})
            chat.append(("assistant", r["text"] + ("\n\n`offline summary`" if r["offline"] else "")))
        except api.APIError as e:
            chat.append(("assistant", f"Error: {e}"))
        st.rerun()

# ---------------- Report ----------------
with tabs[7]:
    st.markdown("**PDF reports** for the clinic file and for the patient (English + Hindi, one page).")
    cc = st.columns(2)
    if cc[0].button("Prepare clinical report (doctor)", type="primary"):
        with st.spinner("Building the clinical report ..."):
            try:
                st.session_state[f"pdf_doc_{pid}"] = api.get_bytes(f"/patients/{pid}/report/doctor.pdf")
            except api.APIError as e:
                ui.show_error(e)
    if st.session_state.get(f"pdf_doc_{pid}"):
        cc[0].download_button("⬇ Download clinical report", st.session_state[f"pdf_doc_{pid}"],
                              f"{pid}_clinical_report.pdf", "application/pdf")
    if cc[1].button("Prepare patient report (English + हिंदी)"):
        with st.spinner("Building the patient report ..."):
            try:
                st.session_state[f"pdf_pat_{pid}"] = api.get_bytes(f"/patients/{pid}/report/patient.pdf")
            except api.APIError as e:
                ui.show_error(e)
    if st.session_state.get(f"pdf_pat_{pid}"):
        cc[1].download_button("⬇ Download patient report", st.session_state[f"pdf_pat_{pid}"],
                              f"{pid}_patient_report.pdf", "application/pdf")
    st.caption("Contents: labs with dates and stale-data flags, KDIGO grid, eGFR and HbA1c trends, 14-day glucose "
               "profile, risk scores with model versions, ranked options with sources, alerts, AI summary.")

ui.footer()
