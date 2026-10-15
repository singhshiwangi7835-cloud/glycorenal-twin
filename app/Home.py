"""GlycoRenal Twin: Streamlit entry point. Login, then route to the page for the user's role.

Run:  streamlit run app/Home.py      (the API must be running at API_URL, default localhost:8000)
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

import api_client
import ui

st.set_page_config(page_title="GlycoRenal Twin", page_icon="🩺", layout="wide")

DEMO_ACCOUNTS = pd.DataFrame([
    ("Doctor", "dr.mehta", "doctor123"),
    ("Patient (Ramesh)", "ramesh", "patient123"),
    ("Patient (Sunita)", "sunita", "patient123"),
    ("Admin", "admin", "admin123"),
], columns=["Role", "Username", "Password"])


def login_page() -> None:
    left, mid, right = st.columns([1, 1.4, 1])
    with mid:
        st.title("🩺 GlycoRenal Twin")
        st.caption("Digital twin for type 2 diabetes and diabetic kidney disease")
        with st.form("login"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Log in", type="primary", width="stretch")
        if submitted:
            try:
                api_client.login(username, password)
                st.rerun()
            except api_client.APIError as e:
                st.error(str(e))
        with st.expander("Demo accounts"):
            st.dataframe(DEMO_ACCOUNTS, hide_index=True, width="stretch")
            st.caption("Other demo patients: priya, mohan, arjun, lakshmi, imran, kavita, "
                       "suresh, anita (password patient123).")
        ui.footer()


user = api_client.current_user()
if user is None:
    pages = [st.Page(login_page, title="Log in", icon="🔐")]
else:
    pages = {
        "doctor": [st.Page("pages/doctor_portal.py", title="Doctor portal", icon="🩺")],
        "patient": [st.Page("pages/patient_app.py", title="My health", icon="💙")],
        "admin": [st.Page("pages/admin_panel.py", title="Admin panel", icon="🛠️")],
    }[user["role"]]

st.navigation(pages).run()
