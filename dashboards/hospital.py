"""Hospital dashboard (doctors). Run: streamlit run dashboards/hospital.py"""

from __future__ import annotations

import os

import pandas as pd
import requests
import streamlit as st

API = os.getenv("API_URL", "http://localhost:8000")
BAND_COLOUR = {"low": "🟢", "moderate": "🟡", "high": "🟠", "very_high": "🔴"}
LEVEL_ICON = {"critical": "🚨", "warning": "⚠️", "info": "ℹ️"}

st.set_page_config(page_title="GlycoRenal Twin: Hospital", page_icon="🩺", layout="wide")


@st.cache_data(ttl=30)
def get(path: str):
    r = requests.get(f"{API}{path}", timeout=60)
    r.raise_for_status()
    return r.json()


st.title("🩺 GlycoRenal Twin: Hospital dashboard")
st.caption("T2DM glycaemic control + diabetic kidney disease prevention. "
           "Decision support only; the clinician decides.")

try:
    patients = get("/patients")
except Exception as e:
    st.error(f"Cannot reach the API at {API}. Is it running? ({e})")
    st.stop()

# ---------- patient list ----------
st.subheader("Patients by predicted 3-year DKD risk")
df = pd.DataFrame(patients)
df["risk"] = df.apply(lambda r: f"{BAND_COLOUR[r.risk_band]} {r.dkd_risk_3y:.0%}", axis=1)
st.dataframe(
    df[["patient_id", "age", "sex", "hba1c", "egfr", "kdigo", "risk", "n_alerts"]],
    hide_index=True, use_container_width=True,
)

pid = st.selectbox("Open patient twin", df["patient_id"])
t = get(f"/patients/{pid}/twin")
s, p, rec = t["state"], t["prediction"], t["recommendation"]
d = s["derived"]

# ---------- headline metrics ----------
c = st.columns(6)
c[0].metric("DKD risk (3 yr)", f"{p['dkd_risk_3y']:.0%}", p["outcome_type"])
c[1].metric("HbA1c", f"{s['labs']['hba1c']}%", f"{p['hba1c_3m_forecast'] - s['labs']['hba1c']:+.1f} in 3 mo",
            delta_color="inverse")
c[2].metric("eGFR", d["egfr"],
            f"{d['egfr_slope_per_year']:+} /yr" if d["egfr_slope_per_year"] is not None else None)
c[3].metric("UACR", f"{s['labs']['uacr']} mg/g")
c[4].metric("KDIGO", d["kdigo"], d["kdigo_risk"].replace("_", " "), delta_color="off")
c[5].metric("Time in range", f"{s['cgm']['tir_pct']}%" if s["cgm"] else "n/a")

left, right = st.columns([3, 2])

with left:
    st.subheader("Ranked treatment options")
    if rec["safety_warnings"]:
        for w in rec["safety_warnings"]:
            st.error(w)
    opts = pd.DataFrame(rec["ranked_options"])
    if not opts.empty:
        opts["risk change"] = opts.apply(
            lambda o: f"{o.risk_before:.0%} → {o.risk_after:.0%}", axis=1)
        st.dataframe(opts[["label", "risk change", "absolute_reduction", "kind", "evidence"]],
                     hide_index=True, use_container_width=True)
        st.bar_chart(opts.set_index("option")["absolute_reduction"])
    if rec["combined_plan"]:
        cp = rec["combined_plan"]
        st.success(f"Combined plan ({' + '.join(cp['options'])}): "
                   f"{rec['baseline_risk']:.0%} → {cp['risk_after']:.0%}")
    with st.expander("Not eligible / already in place"):
        for k, v in rec["not_eligible"].items():
            st.write(f"**{k}**: {v}")

    if s.get("cgm_trace_24h"):
        st.subheader("CGM, last 24 hours")
        trace = pd.DataFrame({"glucose (mg/dL)": s["cgm_trace_24h"]})
        trace["hours"] = trace.index * 5 / 60
        st.line_chart(trace.set_index("hours"))

with right:
    st.subheader("Alerts")
    for a in t["alerts"]:
        st.write(f"{LEVEL_ICON[a['level']]} {a['message']}")
    st.subheader("What drives this risk")
    for dr in p["drivers"]:
        st.write(f"- {dr['factor']}: fixing it lowers risk by {dr['contribution']:.1%}")
    st.subheader("Twin summary")
    st.markdown(t["doctor_summary"])

    st.subheader("Ask the twin")
    q = st.text_input("Question", placeholder="Why is the kidney risk high?")
    if q:
        r = requests.post(f"{API}/patients/{pid}/ask",
                          json={"question": q, "mode": "doctor"}, timeout=90)
        st.markdown(r.json()["answer"])

with st.expander("Raw patient state (JSON)"):
    st.json({k: v for k, v in s.items() if k != "cgm_trace_24h"})
