"""GlycoRenal Twin: Streamlit entry point. Login, then route to the page for the user's role.

Run:  streamlit run app/Home.py      (the API must be running at API_URL, default localhost:8000)
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

import api_client
import ui

st.set_page_config(page_title="GlycoRenal Twin", page_icon=str(Path(__file__).parent / "assets" / "logo.png"),
                   layout="wide")
ui.apply_style()

DEMO_ACCOUNTS = [("dr.mehta", "doctor123", "Doctor"), ("ramesh", "patient123", "Patient · Hindi"),
                 ("sunita", "patient123", "Patient"), ("admin", "admin123", "Admin")]


def _fill(u: str, pw: str) -> None:
    st.session_state["lu"], st.session_state["lp"] = u, pw


def login_page() -> None:
    st.markdown("<style>[data-testid='stSidebar'],[data-testid='stSidebarCollapsedControl']{display:none}"
                ".block-container{padding-top:1.2rem;max-width:1440px}</style>", unsafe_allow_html=True)
    art, form = st.columns([1.1, 1], gap="large")
    with art:
        ui.md(f"<div class='login-hero'>{ui.logo(360, on_dark=True, cls='hero-logo')}"
              "<div class='hero-name'>GlycoRenal Twin</div>"
              "<div class='hero-line'>Digital twin for diabetes and kidney care</div></div>")
    with form:
        _, mid, _ = st.columns([0.08, 1, 0.12])
        with mid:
            ui.md(f"<div class='signin' style='margin-top:8vh'>{ui.logo(45)}"
                  "<div class='eyebrow' style='margin-top:14px'>Sign in</div><h2>Welcome back</h2>"
                  "<p class='muted' style='margin-top:4px'>One login for doctors, patients and admins. "
                  "Each role sees only what it should.</p></div>")
            with st.container(key="loginform"), st.form("login", border=False):
                username = st.text_input("Username", placeholder="e.g. dr.mehta", key="lu")
                password = st.text_input("Password", type="password", placeholder="••••••••", key="lp")
                submitted = st.form_submit_button("Sign in", type="primary", width="stretch")
            if submitted:
                try:
                    api_client.login(username, password)
                    st.rerun()
                except api_client.APIError:
                    st.error("Wrong username or password. Try a demo account below.")
            st.write("")
            with st.container(key="acclist"):
                ui.md("<div class='acc-h'>Demo accounts</div>")
                for u, pw, role in DEMO_ACCOUNTS:
                    with st.container(key=f"row_acc_{u.replace('.', '_')}"):
                        ui.md(f"<div class='acc'><span><span class='mono'>{u}</span> <span class='faint'>/ {pw}"
                              f"</span></span><span class='r'>{role}</span></div>")
                        st.button("Use", key=f"use_{u}", on_click=_fill, args=(u, pw))
            st.caption("Click an account to fill the form. Other demo patients: priya, mohan, arjun, lakshmi, "
                       "imran, kavita, suresh, anita (password patient123).")


user = api_client.current_user()
if user is None:
    pages = [st.Page(login_page, title="Log in", icon="🔐")]
else:
    pages = {
        "doctor": [st.Page("pages/doctor_portal.py", title="Doctor portal", icon="🩺")],
        "patient": [st.Page("pages/patient_app.py", title="My health", icon="💙")],
        "admin": [st.Page("pages/admin_panel.py", title="Admin panel", icon="🛠️")],
    }[user["role"]]

st.navigation(pages, position="hidden").run()
