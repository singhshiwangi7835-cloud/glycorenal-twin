"""Doctor portal (placeholder in FAST TRACK step 1; full tabs arrive in step 5)."""

import streamlit as st

import ui

ui.sidebar_user()

st.title("🩺 Doctor portal")
user = st.session_state["user"]
st.success(f"Logged in as {user['full_name']} (doctor).")
st.info("Coming next: patient list sorted by DKD risk, patient detail tabs "
        "(Overview, Live, Treatments, Medications, Meals, EHR, AI, Report).")
ui.footer()
