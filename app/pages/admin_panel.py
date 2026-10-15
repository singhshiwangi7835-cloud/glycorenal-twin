"""Admin panel (minimal in FAST TRACK step 1): list users. More admin tools arrive in step 5/6."""

import pandas as pd
import streamlit as st

import api_client
import ui

ui.sidebar_user()

st.title("🛠️ Admin panel")
try:
    users = api_client.get("/auth/users")
    st.subheader(f"Users ({len(users)})")
    st.dataframe(pd.DataFrame(users)[["username", "role", "full_name", "language", "patient_id"]],
                 hide_index=True, width="stretch")
except api_client.APIError as e:
    st.error(str(e))
st.info("Coming next: create users, link patients to doctors, import EHR patients, "
        "device status, reset demo data.")
ui.footer()
