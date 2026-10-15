"""Patient app (placeholder in FAST TRACK step 1; full tabs arrive in step 5)."""

import streamlit as st

import ui

ui.sidebar_user()

user = st.session_state["user"]
hindi = user.get("language") == "hi"
st.title("💙 मेरा हेल्थ ट्विन" if hindi else "💙 My health twin")
st.success((f"नमस्ते {user['full_name']}!" if hindi else f"Welcome, {user['full_name']}!")
           + f"  (ID {user['patient_id']})")
st.info("Coming next: today's glucose, medicine reminders, meal log, my health, devices, "
        "ask my twin, report.")
ui.footer()
