"""Patient app (Hindi / English): Today, Medicines, Meals, My health, Devices, Ask my twin, Report.

Patients see their own data only, and only lifestyle suggestions (never medicine changes).
All text comes from app/i18n.py; the language toggle is in the sidebar.
"""

from __future__ import annotations

import math

import pandas as pd
import streamlit as st

import api_client as api
import ui
from i18n import TEXT, lang, t

ui.sidebar_user()
user = st.session_state["user"]
pid = user["patient_id"]

with st.sidebar:
    choice = st.radio(t("language"), ["English", "हिंदी"], index=1 if lang() == "hi" else 0, horizontal=True)
    st.session_state["lang"] = "hi" if choice == "हिंदी" else "en"

first_name = (user["full_name"] or "").split(" ")[0]
st.title(f"💙 {t('title')}")
st.caption(f"{t('hello')} {first_name} · {pid}")


def _status_label(g: float) -> str:
    return t("low_sugar") if g < 70 else (t("high_sugar") if g > 180 else t("good_range"))


tabs = st.tabs([t("today"), t("medicines"), t("meals"), t("my_health"), t("devices"), t("ask"), t("report")])

# ---------------- Today ----------------
with tabs[0]:
    @st.fragment(run_every=5)
    def today():
        try:
            _today()
        except Exception as e:  # noqa: BLE001
            st.error(str(e))

    def _today():
        try:
            tw = api.get(f"/patients/{pid}/twin")
            rem = api.get(f"/patients/{pid}/reminders")
        except api.APIError as e:
            ui.show_error(e)
            return
        s = tw["state"]
        latest = s["cgm"].get("latest")
        fc = tw["predictions"].get("glucose_30m")
        c = st.columns([2, 2, 2])
        with c[0]:
            if latest:
                g = latest["value"]
                colour = ui.KDIGO_HEX["red"] if g < 70 else (ui.KDIGO_HEX["orange"] if g > 180 else ui.KDIGO_HEX["green"])
                st.markdown(f"<div style='font-size:15px;color:#52606d'>{t('sugar_now')}</div>"
                            f"<div style='font-size:64px;font-weight:700;color:{colour};line-height:1'>{g:.0f} "
                            f"<span style='font-size:40px'>{latest['arrow']}</span></div>"
                            f"<div>mg/dL · {_status_label(g)} · {ui.minutes_ago(latest['time'])} {t('minutes_ago')}</div>",
                            unsafe_allow_html=True)
                if fc:
                    st.caption(f"{t('forecast')}: ~{fc['plus_30']} mg/dL")
            else:
                st.info(t("no_cgm"))
        with c[1]:
            tir = (s["cgm"].get("metrics") or {}).get("tir_pct")
            st.plotly_chart(ui.tir_ring(tir, t("in_range")), width="stretch", key="tir")
            st.caption(t("target_tir"))
        with c[2]:
            st.markdown(f"**{t('next_dose')}**")
            due = rem["due_now"]
            nxt = due[0] if due else rem["next"]
            if nxt:
                st.markdown(f"💊 **{nxt['drug']}** {nxt['dose']}  \n🕗 {nxt['local_time']}"
                            + (f" · {t('with_food')}" if nxt["with_food"] else ""))
                if due:
                    b = st.columns(2)
                    if b[0].button(f"✓ {t('taken')}", key=f"take_{nxt['id']}", type="primary"):
                        api.post(f"/doses/{nxt['id']}", json={"status": "taken"})
                        st.rerun(scope="fragment")
                    if b[1].button(t("skip"), key=f"skip_{nxt['id']}"):
                        api.post(f"/doses/{nxt['id']}", json={"status": "skipped"})
                        st.rerun(scope="fragment")
            else:
                st.caption(t("no_dose"))
        # toasts: new alerts and medicines that just became due
        seen = st.session_state.setdefault("seen", set())
        for a in tw["alerts"]:
            key = f"a{a['id']}"
            if key not in seen:
                if st.session_state.get("toasts_ready"):
                    st.toast(f"{ui.SEVERITY_ICON[a['severity']]} {t('new_alert')}: {a['message']}")
                seen.add(key)
        for d in rem["due_now"]:
            key = f"d{d['id']}"
            if key not in seen:
                if st.session_state.get("toasts_ready"):
                    st.toast(f"💊 {t('medicine_due_toast')}: {d['drug']} {d['dose']}")
                seen.add(key)
        st.session_state["toasts_ready"] = True
        rows = api.get(f"/patients/{pid}/observations", variable="glucose", device="cgm", hours=6)
        st.plotly_chart(ui.cgm_chart(rows[-120:], t("sugar_now"), None, height=240), width="stretch", key="pcgm")
        if tw["alerts"]:
            st.markdown(f"**{t('alerts')}**")
            for a in tw["alerts"][:4]:
                st.write(f"{ui.SEVERITY_ICON[a['severity']]} {a['message']}")

    today()

# ---------------- Medicines ----------------
with tabs[1]:
    rem = api.get(f"/patients/{pid}/reminders")
    a7, a30 = rem["adherence_7d"], rem["adherence_30d"]
    c = st.columns(2)
    c[0].metric(f"{t('adherence')} ({t('last_7')})", f"{a7['pct']:.0f}%" if a7["pct"] is not None else "–")
    c[1].metric(f"{t('adherence')} ({t('last_30')})", f"{a30['pct']:.0f}%" if a30["pct"] is not None else "–")
    st.markdown(f"**{t('todays_doses')}**")
    for d in rem["today"]:
        cc = st.columns([3, 2, 1, 1])
        cc[0].markdown(f"💊 **{d['drug']}** {d['dose']}" + (f" · {t('with_food')}" if d["with_food"] else ""))
        cc[1].write(f"🕗 {d['local_time']} · {t('status_' + d['status'])}")
        if d["status"] in ("pending", "missed"):
            if cc[2].button(t("taken"), key=f"mt_{d['id']}"):
                api.post(f"/doses/{d['id']}", json={"status": "taken"})
                st.rerun()
            if cc[3].button(t("skip"), key=f"ms_{d['id']}"):
                api.post(f"/doses/{d['id']}", json={"status": "skipped"})
                st.rerun()
    st.caption(t("med_note"))

# ---------------- Meals ----------------
with tabs[2]:
    foods = api.cached_get("/foods")
    name_of = {f["food"]: (f["food_hi"] if lang() == "hi" else f["food"]) for f in foods}
    info = {f["food"]: f for f in foods}
    with st.container(border=True):
        st.markdown(f"**{t('log_meal')}**")
        picked = st.multiselect(t("pick_foods"), list(name_of), format_func=lambda f: f"{name_of[f]} ({info[f]['serving']})")
        servings = {}
        for f in picked:
            servings[f] = st.number_input(f"{name_of[f]}: {t('servings')}", 0.5, 6.0, 1.0, 0.5, key=f"sv_{f}")
        total = sum(info[f]["carbs_g"] * n for f, n in servings.items())
        if picked:
            st.caption(f"≈ {total:.0f} g {t('carbs')}")
        if st.button(t("save_meal"), type="primary", disabled=not picked):
            try:
                api.post(f"/patients/{pid}/meals", json={"items": [{"food": f, "servings": n} for f, n in servings.items()]})
                st.success(t("meal_saved"))
            except api.APIError as e:
                ui.show_error(e)
    top = api.cached_get(f"/patients/{pid}/meals/top-foods")
    st.markdown(f"**{t('top_foods')}**")
    if top:
        for i, f in enumerate(top, 1):
            st.write(f"{i}. {f['food_hi'] if lang() == 'hi' else f['food']}: +{f['avg_spike']:.0f} mg/dL")
    else:
        st.caption(t("no_meals"))
    meals = api.get(f"/patients/{pid}/meals", days=3)
    st.markdown(f"**{t('recent_meals')}**")
    for m in meals[:8]:
        when = pd.to_datetime(m["time"], format="ISO8601", utc=True).tz_convert("Asia/Kolkata").strftime("%d %b %H:%M")
        foods_txt = ", ".join(name_of.get(i["food"], i["food"]) for i in m["items"])
        rise = f"+{m['spike']:.0f} mg/dL" if m["spike"] is not None else t("waiting")
        st.write(f"🍽 {when} · {foods_txt} · {m['total_carbs_g']:.0f} g · {t('rise')}: **{rise}**")

# ---------------- My health ----------------
with tabs[3]:
    tw = api.get(f"/patients/{pid}/twin")
    s = tw["state"]
    k = s["kidney"]
    st.plotly_chart(ui.trend_chart(s["history"]["hba1c"], t("hba1c_trend"), "%", s["glycaemia"]["target"]),
                    width="stretch", key="ph")
    colour = k.get("colour") or "green"
    st.markdown(f"**{t('kidney')}** {ui.kdigo_chip(k.get('stage'), colour)}", unsafe_allow_html=True)
    st.write(t(f"kidney_{colour}") + f" (eGFR {k['egfr']:.0f}, UACR {k['uacr']:.0f})" if k.get("egfr") else "")
    v = s["vitals"]
    if v["sbp"]:
        st.write(f"**{t('bp')}:** {v['sbp']:.0f}/{v['dbp']:.0f} ({t('target')} < {s['bp']['target']}) "
                 + ("✓" if s["bp"]["on_target"] else "✗"))
    tr = api.cached_get(f"/patients/{pid}/treatments")
    if tr.get("available") and tr["options"]:
        st.markdown(f"**{t('what_helps')}**")
        for o in tr["options"]:
            label = t(f"opt_{o['option']}") if f"opt_{o['option']}" in TEXT else o["label"]
            st.write(f"✅ {label}: {t('kidney_risk')} {o['risk_before']:.0%} → **{o['risk_after']:.0%}**")

# ---------------- Devices ----------------
with tabs[4]:
    dev = api.cached_get(f"/patients/{pid}/devices")
    with st.container(border=True):
        st.markdown(f"**{t('sensor')}**")
        if dev["simulator"]["running"]:
            st.success(t("sensor_on"))
            if st.button(t("stop_sensor")):
                api.post(f"/patients/{pid}/devices/simulator/stop")
                st.rerun()
        else:
            st.caption(t("sensor_off"))
            if st.button(t("start_sensor"), type="primary"):
                api.post(f"/patients/{pid}/devices/simulator/start", json={})
                st.rerun()
    with st.container(border=True):
        st.markdown(f"**{t('libre')}**")
        f = st.file_uploader("LibreView CSV", type=["csv"], label_visibility="collapsed")
        if f and st.button(t("upload")):
            try:
                r = api.upload(f"/patients/{pid}/devices/libre", f.name, f.getvalue())
                st.success(f"{t('saved')}: {r['saved']} ({r['unit']})")
            except api.APIError as e:
                ui.show_error(e)
    with st.container(border=True):
        st.markdown(f"**{t('dexcom')}**")
        st.button(f"{t('dexcom')} · {t('coming_soon')}", disabled=True)
    with st.form("vitals", clear_on_submit=True):
        st.markdown(f"**{t('enter_readings')}**")
        c = st.columns(3)
        sbp = c[0].number_input(t("systolic"), 0, 260, 0)
        dbp = c[1].number_input(t("diastolic"), 0, 160, 0)
        wt = c[2].number_input(t("weight"), 0.0, 250.0, 0.0, 0.1)
        c = st.columns(3)
        gl = c[0].number_input(t("finger_glucose"), 0, 600, 0)
        sl = c[1].number_input(t("sleep"), 0.0, 16.0, 0.0, 0.5)
        if st.form_submit_button(t("save"), type="primary"):
            body = {"systolic": sbp or None, "diastolic": dbp or None, "weight_kg": wt or None,
                    "glucose_mg_dl": gl or None, "sleep_hours": sl or None}
            try:
                r = api.post(f"/patients/{pid}/vitals", json=body)
                st.success(t("saved"))
                for a in r["new_alerts"]:
                    st.warning(a)
            except api.APIError as e:
                ui.show_error(e)

# ---------------- Ask my twin ----------------
with tabs[5]:
    if st.button(t("summary_btn"), type="primary"):
        with st.spinner(t("thinking")):
            st.session_state["p_sum"] = api.post(f"/patients/{pid}/assistant",
                                                 json={"mode": "patient_summary", "language": lang()})
    res = st.session_state.get("p_sum")
    if res:
        if res["offline"]:
            st.caption(f"🟠 {t('offline')}")
        st.markdown(res["text"])
    chat = st.session_state.setdefault("p_chat", [])
    for role, text in chat:
        with st.chat_message(role):
            st.markdown(text)
    q = st.chat_input(t("your_question"))
    if q:
        chat.append(("user", q))
        try:
            r = api.post(f"/patients/{pid}/assistant", json={"mode": "chat_patient", "language": lang(), "question": q})
            chat.append(("assistant", r["text"]))
        except api.APIError as e:
            chat.append(("assistant", str(e)))
        st.rerun()

# ---------------- Report ----------------
with tabs[6]:
    st.markdown(t("report_intro"))
    if st.button(t("report_btn"), type="primary"):
        with st.spinner(t("thinking")):
            try:
                st.session_state["my_pdf"] = api.get_bytes(f"/patients/{pid}/report/patient.pdf")
            except api.APIError as e:
                ui.show_error(e)
    if st.session_state.get("my_pdf"):
        st.download_button(f"⬇ {t('download')}", st.session_state["my_pdf"], f"{pid}_my_health.pdf",
                           "application/pdf")

st.divider()
st.caption(t("disclaimer"))
ui.footer()
