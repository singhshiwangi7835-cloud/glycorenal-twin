"""GlycoRenal Twin: Streamlit entry point. Login, then route to the page for the user's role.

Run:  streamlit run app/Home.py      (the API must be running at API_URL, default localhost:8000)
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

import api_client
import ui

st.set_page_config(page_title="GlycoRenal Twin", page_icon=str(Path(__file__).parent / "assets" / "logo.png"),
                   layout="wide")
ui.apply_style()

DEMO_ACCOUNTS = pd.DataFrame([
    ("Doctor", "dr.mehta", "doctor123"),
    ("Patient (Ramesh)", "ramesh", "patient123"),
    ("Patient (Sunita)", "sunita", "patient123"),
    ("Admin", "admin", "admin123"),
], columns=["Role", "Username", "Password"])


def login_page() -> None:
    st.markdown("<style>[data-testid='stSidebar'],[data-testid='stSidebarCollapsedControl']{display:none}"
                ".block-container{padding-top:1.4rem;max-width:1400px}</style>", unsafe_allow_html=True)
    art, form = st.columns([1.1, 1], gap="large")
    with art:
        st.markdown(f"<div class='gr-hero'>{ui.logo(300, on_dark=True)}<div class='name'>GlycoRenal Twin</div>"
                    "<div class='line'>Digital twin for diabetes and kidney care</div></div>", unsafe_allow_html=True)
    with form:
        st.markdown(f"<div class='gr-signin' style='margin-top:9vh'>{ui.logo(46)}"
                    "<div class='gr-eyebrow' style='margin-top:14px'>Sign in</div><h2>Welcome back</h2>"
                    "<p style='color:#46565F;margin-top:-6px'>One login for doctors, patients and admins. "
                    "Each role sees only what it should.</p></div>", unsafe_allow_html=True)
        with st.form("login"):
            username = st.text_input("Username", placeholder="e.g. dr.mehta")
            password = st.text_input("Password", type="password", placeholder="••••••••")
            submitted = st.form_submit_button("Sign in", type="primary", width="stretch")
        if submitted:
            try:
                api_client.login(username, password)
                st.rerun()
            except api_client.APIError as e:
                st.error(str(e))
        with st.expander("Demo accounts", expanded=True):
            st.dataframe(DEMO_ACCOUNTS, hide_index=True, width="stretch")
            st.caption("Other demo patients: priya, mohan, arjun, lakshmi, imran, kavita, "
                       "suresh, anita (password patient123).")


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
