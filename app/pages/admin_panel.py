"""Admin panel (design: glycorenal-twin-ui_3.html).

Sidebar menu: Demo data, EHR import (connect to a FHIR server, search, import and keep patients synced;
upload FHIR files; Synthea samples), Users, Patients & doctors, Devices.
"""

from __future__ import annotations

import json

import streamlit as st

import api_client as api
import ui
from ui import esc, md

PAGES = {"demo": ":material/settings: Demo data", "ehr": ":material/database: EHR import",
         "users": ":material/group: Users", "assign": ":material/link: Patients & doctors",
         "devices": ":material/devices: Devices"}
TITLES = {"demo": "Demo data", "ehr": "EHR import", "users": "Users", "assign": "Patients & doctors",
          "devices": "Devices"}

page = ui.sidebar_shell("Admin console", "nav_admin", list(PAGES), PAGES, "Admin")
try:
    ov = api.get("/admin/overview")
except api.APIError as e:
    ui.show_error(e)
    st.stop()


def _health() -> None:
    try:
        ok = api.get("/health").get("status") == "ok"
    except api.APIError:
        ok = False
    st.markdown(ui.chip(f"<span class='mono'>API · {esc(api.API_URL.replace('http://', ''))} · "
                        f"{'healthy' if ok else 'unreachable'}</span>", "plain" if ok else "red"),
                unsafe_allow_html=True)


ui.topbar(f"<b>{TITLES[page]}</b>", _health)


# ---------------- Demo data ----------------

def demo() -> None:
    ui.page_head("Demo data", "One click resets everything (including alerts) and sets up Ramesh's story.")
    md("<div class='grid g4' style='margin-bottom:16px'>"
       + ui.stat("Patients", ov["patients"]) + ui.stat("Users", ov["users"])
       + ui.stat("Readings stored", f"{ov['observations']:,}") + ui.stat("Open alerts", ov["open_alerts"]) + "</div>")
    left, right = st.columns(2, gap="medium")
    with left, ui.box("demo"):
        ready = st.session_state.get("demo_ready")
        ui.card_head("Demo mode", ui.chip("✓ Demo ready", "green") if ready else "")
        md("<p class='muted'>Story: EHR import → live sensor → rice lunch → spike warning → missed dose → new labs "
           "(A1 → A2) → ranked treatments → dapagliflozin → risk drops → reports.</p>")
        if st.button("Start demo mode", icon=":material/play_arrow:", type="primary", width="stretch"):
            with st.spinner("Setting up the demo story (about 20-60 seconds) ..."):
                try:
                    r = api.post("/admin/demo-mode")
                    st.session_state["demo_csv"] = r["lab_csv"]
                    st.session_state["demo_ready"] = True
                    st.session_state["demo_log"] = ["Database cleared and re-seeded", "Ramesh imported, labs up to "
                                                    "last quarter", "Live sensor started for IND-0042",
                                                    "Alerts, reminders and AI cache reset", r["next"]]
                    st.toast("Demo ready — log in as dr.mehta and ramesh")
                    st.rerun()
                except api.APIError as e:
                    ui.show_error(e)
        log = st.session_state.get("demo_log")
        md("<div class='code' style='min-height:120px'>" + ("".join(f"<div><span class='k'>✓</span> {esc(x)}</div>"
                                                                    for x in log) if log else
                                                            "<span class='k'>›</span> Idle") + "</div>")
        with st.expander("Reset all data"):
            st.warning("Resetting deletes all data and re-creates the demo patients (about 20-60 seconds).")
            if st.checkbox("I understand") and st.button("Reset demo data", type="primary"):
                with st.spinner("Re-seeding ..."):
                    try:
                        api.post("/admin/reset-demo")
                        st.success("Demo data reset. Ramesh's live sensor has restarted.")
                    except api.APIError as e:
                        ui.show_error(e)
    with right:
        with ui.box("files"):
            ui.card_head("Files for the demo")
            c = st.columns([3, 1.3], vertical_alignment="center")
            c[0].markdown("<b class='mono' style='font-size:13px'>ramesh_labs_today.csv</b><div class='faint' "
                          "style='font-size:12px'>this week's labs, upload in the doctor's EHR tab</div>",
                          unsafe_allow_html=True)
            if st.session_state.get("demo_csv"):
                c[1].download_button("Download", st.session_state["demo_csv"], "ramesh_labs_today.csv", "text/csv",
                                     icon=":material/download:", width="stretch")
            else:
                c[1].caption("after Start demo mode")
        st.write("")
        try:
            srv = api.get("/ehr/server")
        except api.APIError as e:
            srv = {"ok": False, "error": str(e)}
        try:
            llm = api.cached_get("/assistant/status")
        except api.APIError:
            llm = {"configured": False}
        rows = [["<b>FastAPI</b>", "<span class='mono faint'>/health</span>", ui.chip("ok", "green")],
                ["<b>Database</b>", f"<span class='mono faint'>{ov['observations']:,} readings</span>",
                 ui.chip("ok", "green")],
                ["<b>FHIR server</b>", f"<span class='mono faint'>{esc(srv.get('base_url', ''))}</span>",
                 ui.chip("connected" if srv.get("ok") else "offline", "green" if srv.get("ok") else "orange")],
                ["<b>LLM</b>", f"<span class='mono faint'>{esc(', '.join(llm.get('providers') or []) or '—')} → "
                               "templates</span>",
                 ui.chip("ok" if llm.get("configured") else "templates only",
                         "green" if llm.get("configured") else "orange")],
                ["<b>Simulators</b>", f"<span class='mono faint'>{len(ov['simulators'])} running</span>",
                 ui.chip("ok", "green")]]
        md(ui.card("System", ui.table(["Part", "Detail", ""], rows), pad=False))


# ---------------- EHR import ----------------

def _show(r: dict, label: str) -> str:
    return (f"{label} → {r['patient_id']} {r.get('display_name', '')}: {r['observations_saved']} results, "
            f"{r['medications_added']} medicines"
            + (f", DKD 3-yr risk {r['dkd_risk_3y']:.0%}" if r.get("dkd_risk_3y") is not None else ""))


def _log(key: str, lines: list[str]) -> None:
    if not lines:
        return
    md("<div class='code' style='min-height:60px'>" + ("".join(
        f"<div><span class='k'>{'✗' if x.startswith('✗') else '✓'}</span> {esc(x.lstrip('✗ '))}</div>"
        for x in lines) if lines else "<span class='k'>›</span> —") + "</div>")


def ehr() -> None:
    ui.page_head("EHR import", "Search a hospital FHIR server, import patients, keep them linked and in sync.")
    try:
        status = api.get("/ehr/server", base_url=st.session_state.get("ehr_base") or None)
    except api.APIError as e:
        status = {"ok": False, "base_url": "", "error": str(e)}
    ok = status.get("ok")
    md(f"<div class='card conn'><div class='row'><span class='{'dot-ok' if ok else 'dot-bad'}'></span><div><b>"
       + (f"Connected: {esc(status.get('software') or 'FHIR server')}, FHIR {esc(status.get('fhir_version'))}"
          + (" · with access token" if status.get("auth") else "") if ok
          else f"Cannot reach the server: {esc(status.get('error', ''))}")
       + f"</b><div class='faint mono' style='font-size:12px'>{esc(status.get('base_url', ''))}</div></div></div>"
       + ui.chip("online" if ok else "offline", "green" if ok else "red") + "</div>")
    with st.expander("Change server address"):
        st.text_input("FHIR server address", value=status.get("base_url", ""), key="ehr_base",
                      help="Default comes from FHIR_BASE_URL in .env (public HAPI R4 test server). A hospital server "
                           "needs an access token in FHIR_AUTH_TOKEN.")
    base = status.get("base_url")
    doctors = {d["id"]: d["full_name"] or d["username"] for d in ov["doctors"]}
    st.write("")
    with ui.box("ehrsearch"):
        ui.card_head("Search patients")
        c = st.columns([2.2, 2.2, 2, 1.3], vertical_alignment="bottom")
        name = c[0].text_input("Name (optional)", key="ehr_name")
        assign = c[1].selectbox("Assign imported patients to", [None] + list(doctors),
                                format_func=lambda i: "(no doctor yet)" if i is None else doctors[i], key="ehr_doc")
        t2dm = c[2].checkbox("Only patients with type 2 diabetes", value=True, key="ehr_t2dm")
        if c[3].button("Search", icon=":material/search:", type="primary", disabled=not ok, width="stretch"):
            with st.spinner(f"Searching {base} …"):
                try:
                    st.session_state["ehr_hits"] = api.get("/ehr/search", name=name, diabetes_only=t2dm, base_url=base)
                except api.APIError as e:
                    ui.show_error(e)
        hits = st.session_state.get("ehr_hits")
        if hits is None:
            md("<div class='empty'>Press Search to query the FHIR server.</div>")
        elif not hits:
            md("<div class='empty'>No patients found.</div>")
        else:
            import pandas as pd
            table = pd.DataFrame(hits)
            table.insert(0, "import", False)
            picked = st.data_editor(table, hide_index=True, width="stretch", disabled=list(table.columns[1:]),
                                    column_config={"import": st.column_config.CheckboxColumn("Import"),
                                                   "imported_as": "Already here as"}, key="ehr_pick")
            chosen = picked[picked["import"]]
            c = st.columns([3, 1.4], vertical_alignment="center")
            c[0].markdown(f"<span class='faint' style='font-size:12px'>{len(hits)} result(s) · <span class='mono'>"
                          "GET /Patient/{id}/$everything</span></span>", unsafe_allow_html=True)
            if c[1].button(f"Import and link {len(chosen)} patient(s)", type="primary", disabled=chosen.empty,
                           width="stretch"):
                log = []
                for _, row in chosen.iterrows():
                    with st.spinner(f"Pulling {row['name']} from the hospital server ..."):
                        try:
                            log.append(_show(api.post("/ehr/fetch", json={"fhir_patient_id": row["fhir_id"],
                                                                          "base_url": base, "doctor_id": assign}),
                                             row["name"]))
                        except api.APIError as e:
                            log.append(f"✗ {row['name']}: {e}")
                st.session_state["imp_log"] = log
                st.session_state.pop("ehr_hits", None)
                st.toast(f"Imported and linked {len(chosen)} patient(s)")
                st.rerun()
        _log("imp", st.session_state.get("imp_log", []))
        with st.expander("Import by FHIR patient id"):
            fid = st.text_input("FHIR patient id", key="ehr_fid")
            if st.button("Import and link", disabled=not fid.strip()):
                try:
                    st.session_state["imp_log"] = [_show(api.post("/ehr/fetch", json={
                        "fhir_patient_id": fid.strip(), "base_url": base, "doctor_id": assign}), fid.strip())]
                    st.rerun()
                except api.APIError as e:
                    ui.show_error(e)
    st.write("")
    left, right = st.columns(2, gap="medium")
    links = api.get("/ehr/links")
    with left, ui.box("linked"):
        every = f"every {links['sync_minutes']} min" if links["sync_minutes"] else "only when you press Sync now"
        ui.card_head("Linked patients")
        if links["patients"]:
            keys = list(links["patients"][0].keys())
            md(ui.table([k.replace("_", " ").title() for k in keys],
                        [[esc(p.get(k)) for k in keys] for p in links["patients"]]))
        else:
            md("<div class='empty'>No linked patients yet.</div>")
        c = st.columns([3, 1.3], vertical_alignment="center")
        c[0].caption(f"New results are pulled {every}. Re-importing updates in place.")
        if c[1].button("Sync now", icon=":material/sync:", disabled=not links["patients"], width="stretch"):
            with st.spinner("Pulling new results from the hospital server ..."):
                try:
                    r = api.post("/ehr/sync")
                    st.toast(f"Synced {r['synced']} patient(s), {r['new_observations']} new results"
                             + (f", {r['failed']} failed" if r["failed"] else ""))
                except api.APIError as e:
                    ui.show_error(e)
    with right, ui.box("othersrc"):
        ui.card_head("Other sources")
        files = st.file_uploader("Upload FHIR files (R4 Bundle JSON)", type=["json"], accept_multiple_files=True)
        log = []
        if files and st.button(f"Import {len(files)} file(s)", type="primary"):
            for f in files:
                try:
                    q = f"?doctor_id={assign}" if assign else ""
                    log.append(_show(api.post(f"/ehr/import/bundle{q}", json=json.loads(f.getvalue())), f.name))
                except (api.APIError, ValueError) as e:
                    log.append(f"✗ {f.name}: {e}")
        samples = api.get("/ehr/samples")
        c = st.columns([3, 1.6], vertical_alignment="center")
        c[0].markdown(f"<b>Synthea samples</b><div class='faint' style='font-size:12px'>{len(samples)} bundles in "
                      "<span class='mono'>data/fhir_samples/</span></div>", unsafe_allow_html=True)
        if c[1].button("Import all samples", width="stretch"):
            for name in samples:
                try:
                    q = f"?doctor_id={assign}" if assign else ""
                    log.append(_show(api.post("/ehr/import/sample" + q, json={"name": name}), name))
                except api.APIError as e:
                    log.append(f"✗ {name}: {e}")
        if log:
            st.session_state["syn_log"] = log
        _log("syn", st.session_state.get("syn_log", []))


# ---------------- Users ----------------

def users() -> None:
    ui.page_head("Users", "Passwords stored hashed (bcrypt). Each login gets a token carrying the role.")
    try:
        us = api.get("/auth/users")
    except api.APIError as e:
        ui.show_error(e)
        return
    left, right = st.columns([1.6, 1], gap="medium")
    with left:
        md(ui.card("", ui.table(["Username", "Name", "Role", "Language", "Patient record"], [
            [f"<span class='mono'>{esc(u['username'])}</span>", esc(u["full_name"]),
             ui.chip(u["role"], "accent" if u["role"] == "doctor" else "plain"),
             "हिंदी" if u.get("language") == "hi" else "English",
             f"<span class='mono faint'>{esc(u.get('patient_id') or '—')}</span>"] for u in us]), pad=False))
    with right, ui.box("newuser"):
        ui.card_head("Create user")
        with st.form("new_user", clear_on_submit=True, border=False):
            username = st.text_input("Username")
            full = st.text_input("Full name")
            c = st.columns(2)
            role = c[0].selectbox("Role", ["patient", "doctor", "admin"])
            language = c[1].selectbox("Language", ["en", "hi"], format_func=lambda x: "हिंदी" if x == "hi" else "English")
            patient_id = st.selectbox("Patient record (patients only)",
                                      [""] + [p["patient_id"] for p in ov["patient_doctor"]])
            password = st.text_input("Temporary password", type="password")
            ok = st.form_submit_button("Create user", type="primary", width="stretch")
        if ok and username and password:
            try:
                api.post("/auth/users", json={"username": username, "password": password, "role": role,
                                              "full_name": full, "language": language, "patient_id": patient_id or None})
                st.toast(f"User created: {username} ({role})")
                st.rerun()
            except api.APIError as e:
                ui.show_error(e)


# ---------------- Patients & doctors ----------------

def _assign(pid: str) -> None:
    doc = st.session_state[f"doc_{pid}"]
    try:
        api.post(f"/admin/patients/{pid}/doctor", json={"doctor_id": doc})
        st.toast(f"Doctor assigned: {pid}")
    except api.APIError as e:
        st.toast(f"Could not assign: {e}")


def assign() -> None:
    ui.page_head("Patients & doctors", "Each patient is linked to one doctor; doctors only see their own patients.")
    doctors = {d["id"]: d["full_name"] or d["username"] for d in ov["doctors"]}
    ids = list(doctors)
    with ui.box("assign"):
        md("<div class='prow h' style='grid-template-columns:2fr 2fr;min-width:0'><span>Patient</span>"
           "<span>Assigned doctor</span></div>")
        for p in ov["patient_doctor"]:
            c = st.columns(2, vertical_alignment="center")
            c[0].markdown(f"<b>{esc(p['display_name'])}</b> <span class='faint mono'>{p['patient_id']}</span>",
                          unsafe_allow_html=True)
            current = ids.index(p["doctor_id"]) if p["doctor_id"] in ids else None
            c[1].selectbox("Doctor", ids, index=current, format_func=lambda i: doctors[i], key=f"doc_{p['patient_id']}",
                           label_visibility="collapsed", placeholder="(no doctor yet)", on_change=_assign,
                           args=(p["patient_id"],))


# ---------------- Devices ----------------

def devices() -> None:
    ui.page_head("Devices", "Live sensor, Libre CSV and Dexcom (coming soon). Tokens are never stored in plain text.")
    names = {p["patient_id"]: p["display_name"] for p in ov["patient_doctor"]}
    sims = {s["patient_id"]: s for s in ov["simulators"]}
    with ui.box("devs"):
        md("<div class='prow h' style='grid-template-columns:2fr 1.4fr 1.4fr 1fr;min-width:0'><span>Patient</span>"
           "<span>Provider</span><span>Status</span><span></span></div>")
        seen = set()
        for d in ov["devices"] + [{"patient_id": pid, "provider": "simulator", "status": "connected"} for pid in sims]:
            key = (d["patient_id"], d["provider"])
            if key in seen:
                continue
            seen.add(key)
            pid = d["patient_id"]
            on = d["provider"] == "simulator" and pid in sims
            c = st.columns([2, 1.4, 1.4, 1], vertical_alignment="center")
            c[0].markdown(f"<b>{esc(names.get(pid, pid))}</b> <span class='faint mono' style='font-size:11px'>{pid}"
                          "</span>", unsafe_allow_html=True)
            c[1].markdown(esc(d["provider"].replace("_", " ")), unsafe_allow_html=True)
            idle = "idle" if d["provider"] == "simulator" else d.get("status", "idle")
            c[2].markdown("<span class='badge-live'>STREAMING</span>" if on else ui.chip(esc(idle), "plain"),
                          unsafe_allow_html=True)
            if d["provider"] == "simulator":
                if c[3].button("Stop" if on else "Start", key=f"dev_{pid}", width="stretch"):
                    if on:
                        api.post(f"/patients/{pid}/devices/simulator/stop")
                    else:
                        api.post(f"/patients/{pid}/devices/simulator/start", json={})
                    st.rerun()
        c = st.columns([2, 1.4, 1.4, 1], vertical_alignment="center")
        c[0].markdown("<b>—</b>", unsafe_allow_html=True)
        c[1].markdown("dexcom")
        c[2].markdown(ui.chip("coming soon", "plain"), unsafe_allow_html=True)


{"demo": demo, "ehr": ehr, "users": users, "assign": assign, "devices": devices}[page]()
