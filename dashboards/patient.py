"""Patient app (Hindi / English). Run: streamlit run dashboards/patient.py"""

from __future__ import annotations

import os

import pandas as pd
import requests
import streamlit as st

API = os.getenv("API_URL", "http://localhost:8000")
st.set_page_config(page_title="GlycoRenal Twin: My health", page_icon="💙", layout="centered")

lang = st.sidebar.radio("Language / भाषा", ["English", "Hindi"])
HI = lang == "Hindi"
T = (lambda en, hi: hi if HI else en)

try:
    ids = [p["patient_id"] for p in requests.get(f"{API}/patients", timeout=60).json()]
except Exception as e:
    st.error(f"Cannot reach the API at {API} ({e})")
    st.stop()

pid = st.sidebar.selectbox(T("Patient ID", "मरीज़ ID"), ids)
v = requests.get(f"{API}/patients/{pid}/patient-view", params={"lang": lang}, timeout=90).json()

st.title(T("💙 My health twin", "💙 मेरा हेल्थ ट्विन"))

c = st.columns(3)
c[0].metric("HbA1c", f"{v['labs']['hba1c']}%", T("target < 7%", "लक्ष्य 7% से कम"), delta_color="off")
if v["cgm"]:
    c[1].metric(T("Time in range", "सही दायरे में समय"), f"{v['cgm']['tir_pct']}%",
                T("target > 70%", "लक्ष्य 70% से ज़्यादा"), delta_color="off")
c[2].metric("BP", f"{v['vitals']['sbp']:.0f}/{v['vitals']['dbp']:.0f}",
            T("target < 130/80", "लक्ष्य 130/80 से कम"), delta_color="off")

colour = {"green": "🟢", "yellow": "🟡", "orange": "🟠", "red": "🔴"}[v["derived"]["kdigo_colour"]]
st.info(T(f"Kidney health: {colour}  (eGFR {v['derived']['egfr']}, UACR {v['labs']['uacr']})",
          f"किडनी की सेहत: {colour}  (eGFR {v['derived']['egfr']}, UACR {v['labs']['uacr']})"))

st.subheader(T("Your twin says", "आपका ट्विन कहता है"))
st.markdown(v["message"])

st.subheader(T("Ask your twin", "अपने ट्विन से पूछें"))
q = st.text_input(T("Your question", "आपका सवाल"))
if q:
    r = requests.post(f"{API}/patients/{pid}/ask",
                      json={"question": q, "mode": "patient", "lang": lang}, timeout=90)
    st.markdown(r.json()["answer"])

st.caption(T("This app does not replace your doctor. Never change your medicines without "
             "talking to your doctor.",
             "यह ऐप डॉक्टर की जगह नहीं लेता। डॉक्टर से बात किए बिना दवाइयां न बदलें।"))
