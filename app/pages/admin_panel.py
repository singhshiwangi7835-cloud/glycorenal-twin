"""Admin panel (minimal): overview, users, link patient to doctor, import EHR samples,
device status, reset demo data.
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
    samples = api.get("/ehr/samples")
    st.write(f"{len(samples)} Synthea FHIR sample bundles in data/fhir_samples/")
    if st.button("Import all Synthea samples", type="primary"):
        for name in samples:
            try:
                r = api.post("/ehr/import/sample", json={"name": name})
                st.write(f"✓ {name} → {r['patient_id']} ({r['observations_saved']} observations)")
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
