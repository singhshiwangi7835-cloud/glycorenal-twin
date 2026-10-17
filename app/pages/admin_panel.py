"""Admin panel: overview, users, link patient to doctor, hospital EHR (connect to a FHIR server, search,
import and keep patients synced; upload FHIR files; Synthea samples), device status, reset demo data.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

import api_client as api
import ui

ui.sidebar_user()
st.title("🛠️ Admin panel")

try:
    ov = api.get("/admin/overview")
    users = api.get("/auth/users")
except api.APIError as e:
    ui.show_error(e)
    st.stop()

c = st.columns(4)
c[0].metric("Patients", ov["patients"])
c[1].metric("Users", ov["users"])
c[2].metric("Readings stored", f"{ov['observations']:,}")
c[3].metric("Open alerts", ov["open_alerts"])

tabs = st.tabs(["Users", "Patients & doctors", "EHR import", "Devices", "Demo data"])

with tabs[0]:
    st.dataframe(pd.DataFrame(users)[["username", "role", "full_name", "language", "patient_id"]],
                 hide_index=True, width="stretch")
    with st.form("new_user", clear_on_submit=True):
        st.markdown("**Create user**")
        cc = st.columns(3)
        username = cc[0].text_input("Username")
        password = cc[1].text_input("Password", type="password")
        role = cc[2].selectbox("Role", ["doctor", "patient", "admin"])
        cc = st.columns(3)
        full = cc[0].text_input("Full name")
        language = cc[1].selectbox("Language", ["en", "hi"])
        patient_id = cc[2].selectbox("Patient record (patients only)", [""] + [p["patient_id"] for p in ov["patient_doctor"]])
        if st.form_submit_button("Create", type="primary") and username and password:
            try:
                api.post("/auth/users", json={"username": username, "password": password, "role": role,
                                              "full_name": full, "language": language,
                                              "patient_id": patient_id or None})
                st.success(f"Created {username}")
                st.rerun()
            except api.APIError as e:
                ui.show_error(e)

with tabs[1]:
    doctors = {d["id"]: d["full_name"] or d["username"] for d in ov["doctors"]}
    for p in ov["patient_doctor"]:
        cc = st.columns([3, 3, 1])
        cc[0].write(f"**{p['patient_id']}** {p['display_name']}")
        ids = list(doctors)
        current = ids.index(p["doctor_id"]) if p["doctor_id"] in ids else 0
        choice = cc[1].selectbox("Doctor", ids, index=current, format_func=lambda i: doctors[i],
                                 key=f"doc_{p['patient_id']}", label_visibility="collapsed")
        if choice != p["doctor_id"] and cc[2].button("Save", key=f"link_{p['patient_id']}"):
            api.post(f"/admin/patients/{p['patient_id']}/doctor", json={"doctor_id": choice})
            st.rerun()

with tabs[2]:
    doctor_names = {d["id"]: d["full_name"] or d["username"] for d in ov["doctors"]}
    assign = st.selectbox("Assign imported patients to", [None] + list(doctor_names),
                          format_func=lambda i: "(no doctor yet)" if i is None else doctor_names[i], key="ehr_doc")

    def _show(r: dict, label: str) -> None:
        st.write(f"✓ {label} → **{r['patient_id']}** {r.get('display_name', '')}: {r['observations_saved']} results, "
                 f"{r['medications_added']} medicines"
                 + (f", DKD 3-yr risk {r['dkd_risk_3y']:.0%}" if r.get("dkd_risk_3y") is not None else ""))

    # ---- 1. live connection to a hospital FHIR server ----
    st.markdown("#### 1. Hospital EHR (FHIR R4 server)")
    st.caption("Patients imported from the server stay linked: new lab results and prescriptions are pulled "
               "again automatically, so nothing has to be typed twice.")
    try:
        status = api.get("/ehr/server")
    except api.APIError as e:
        status = {"ok": False, "base_url": "", "error": str(e)}
    base = st.text_input("FHIR server address", value=status.get("base_url", ""),
                         help="Default comes from FHIR_BASE_URL in .env (public HAPI R4 test server). A hospital "
                              "server needs an access token in FHIR_AUTH_TOKEN.")
    if base != status.get("base_url"):
        status = api.get("/ehr/server", base_url=base)
    if status.get("ok"):
        st.success(f"Connected: {status.get('software') or 'FHIR server'}, FHIR {status.get('fhir_version')}"
                   + (" · with access token" if status.get("auth") else ""))
    else:
        st.error(f"Cannot reach the server: {status.get('error', '')}")

    cc = st.columns([3, 2, 1])
    name = cc[0].text_input("Search patients by name (empty = any)", key="ehr_name")
    t2dm = cc[1].checkbox("Only patients with type 2 diabetes", value=True, key="ehr_t2dm")
    if cc[2].button("Search", disabled=not status.get("ok")):
        try:
            st.session_state["ehr_hits"] = api.get("/ehr/search", name=name, diabetes_only=t2dm, base_url=base)
        except api.APIError as e:
            ui.show_error(e)
    hits = st.session_state.get("ehr_hits", [])
    if hits:
        table = pd.DataFrame(hits)
        table.insert(0, "import", False)
        picked = st.data_editor(table, hide_index=True, width="stretch", disabled=list(table.columns[1:]),
                                column_config={"import": st.column_config.CheckboxColumn("Import"),
                                               "imported_as": "Already here as"}, key="ehr_pick")
        chosen = picked[picked["import"]]
        if st.button(f"Import and link {len(chosen)} patient(s)", type="primary", disabled=chosen.empty):
            for _, row in chosen.iterrows():
                with st.spinner(f"Pulling {row['name']} from the hospital server ..."):
                    try:
                        _show(api.post("/ehr/fetch", json={"fhir_patient_id": row["fhir_id"], "base_url": base,
                                                           "doctor_id": assign}), row["name"])
                    except api.APIError as e:
                        st.write(f"✗ {row['name']}: {e}")
            st.session_state.pop("ehr_hits", None)
    with st.expander("Import by FHIR patient id"):
        fid = st.text_input("FHIR patient id", key="ehr_fid")
        if st.button("Import and link", disabled=not fid.strip()):
            try:
                _show(api.post("/ehr/fetch", json={"fhir_patient_id": fid.strip(), "base_url": base,
                                                   "doctor_id": assign}), fid.strip())
            except api.APIError as e:
                ui.show_error(e)

    links = api.get("/ehr/links")
    if links["patients"]:
        every = f"every {links['sync_minutes']} min" if links["sync_minutes"] else "only when you press Sync now"
        st.markdown(f"**Linked patients** (re-synced {every})")
        st.dataframe(pd.DataFrame(links["patients"]), hide_index=True, width="stretch")
        if st.button("🔄 Sync now"):
            with st.spinner("Pulling new results from the hospital server ..."):
                try:
                    r = api.post("/ehr/sync")
                    st.success(f"Synced {r['synced']} patient(s), {r['new_observations']} new results"
                               + (f", {r['failed']} failed" if r["failed"] else ""))
                except api.APIError as e:
                    ui.show_error(e)

    # ---- 2. files ----
    st.markdown("#### 2. Upload FHIR files")
    files = st.file_uploader("FHIR R4 Bundles (.json), one or more", type=["json"], accept_multiple_files=True)
    if files and st.button(f"Import {len(files)} file(s)", type="primary"):
        import json
        for f in files:
            try:
                q = f"?doctor_id={assign}" if assign else ""
                _show(api.post(f"/ehr/import/bundle{q}", json=json.loads(f.getvalue())), f.name)
            except (api.APIError, ValueError) as e:
                st.write(f"✗ {f.name}: {e}")

    # ---- 3. samples ----
    st.markdown("#### 3. Sample patients")
    samples = api.get("/ehr/samples")
    st.caption(f"{len(samples)} Synthea FHIR sample bundles in data/fhir_samples/")
    if st.button("Import all Synthea samples"):
        for name in samples:
            try:
                q = f"?doctor_id={assign}" if assign else ""
                r = api.post("/ehr/import/sample" + q, json={"name": name})
                _show(r, name)
            except api.APIError as e:
                st.write(f"✗ {name}: {e}")

with tabs[3]:
    if ov["devices"]:
        st.dataframe(pd.DataFrame(ov["devices"]), hide_index=True, width="stretch")
    st.markdown("**Running simulators**")
    st.dataframe(pd.DataFrame(ov["simulators"]) if ov["simulators"] else pd.DataFrame({"none": []}),
                 hide_index=True, width="stretch")

with tabs[4]:
    st.markdown("**Demo mode**: one click resets everything and sets up the story in docs/demo_script.md "
                "(Ramesh without this week's labs, his live sensor running).")
    if st.button("▶ Start demo mode", type="primary"):
        with st.spinner("Setting up the demo story (about 20-60 seconds) ..."):
            try:
                r = api.post("/admin/demo-mode")
                st.session_state["demo_csv"] = r["lab_csv"]
                st.success("Demo ready. " + r["next"])
            except api.APIError as e:
                ui.show_error(e)
    if st.session_state.get("demo_csv"):
        st.download_button("⬇ ramesh_labs_today.csv (upload in the doctor's EHR tab)", st.session_state["demo_csv"],
                           "ramesh_labs_today.csv", "text/csv")
    st.divider()
    st.warning("Resetting deletes all data and re-creates the demo patients (about 20-60 seconds).")
    if st.checkbox("I understand") and st.button("Reset demo data", type="primary"):
        with st.spinner("Re-seeding ..."):
            try:
                api.post("/admin/reset-demo")
                st.success("Demo data reset. Ramesh's live sensor has restarted.")
            except api.APIError as e:
                ui.show_error(e)

ui.footer()
