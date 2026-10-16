"""Shared UI pieces: disclaimer footer, sidebar user box, KDIGO colours and chips, charts.

Look: white background, one accent colour (#0b6e99), KDIGO colours used only for risk.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import api_client

DISCLAIMER = "Prototype – decision support only, not for clinical use"
ACCENT = "#0b6e99"
KDIGO_HEX = {"green": "#2e7d32", "yellow": "#f9a825", "orange": "#ef6c00", "red": "#c62828"}
BAND_HEX = {"low": "#2e7d32", "moderate": "#f9a825", "high": "#ef6c00", "very_high": "#c62828"}
BAND_LABEL = {"low": "Low", "moderate": "Moderate", "high": "High", "very_high": "Very high"}
SEVERITY_ICON = {"critical": "🚨", "warning": "⚠️", "info": "ℹ️"}
G_ORDER = ["G1", "G2", "G3a", "G3b", "G4", "G5"]
A_ORDER = ["A1", "A2", "A3"]
GRID = {"G1": ["low", "moderate", "high"], "G2": ["low", "moderate", "high"],
        "G3a": ["moderate", "high", "very_high"], "G3b": ["high", "very_high", "very_high"],
        "G4": ["very_high"] * 3, "G5": ["very_high"] * 3}


def footer() -> None:
    st.divider()
    st.caption(f"⚕️ {DISCLAIMER}")


def sidebar_user() -> None:
    user = api_client.current_user()
    if not user:
        return
    with st.sidebar:
        st.markdown(f"**{user['full_name'] or user['username']}**  \n{user['role'].title()}")
        if st.button("Log out", width="stretch"):
            api_client.logout()
            st.rerun()
        st.caption(DISCLAIMER)


def chip(text: str, hex_: str) -> str:
    fg = "#1f2933" if hex_ == KDIGO_HEX["yellow"] else "#ffffff"
    return (f"<span style='background:{hex_};color:{fg};padding:2px 10px;border-radius:12px;"
            f"font-weight:600;white-space:nowrap'>{text}</span>")


def kdigo_chip(stage: str | None, colour: str | None) -> str:
    return chip(stage or "n/a", KDIGO_HEX.get(colour or "", "#607d8b"))


def risk_chip(risk: float | None, band: str | None) -> str:
    if risk is None:
        return chip("n/a", "#607d8b")
    return chip(f"{risk:.0%} {BAND_LABEL.get(band, '')}", BAND_HEX.get(band, "#607d8b"))


def kdigo_grid(g: str | None, a: str | None) -> str:
    """KDIGO heat map as an HTML table, with the patient's cell outlined."""
    head = "".join(f"<th style='padding:4px 10px'>{x}</th>" for x in A_ORDER)
    rows = []
    for gs in G_ORDER:
        cells = []
        for i, a_s in enumerate(A_ORDER):
            hex_ = BAND_HEX[GRID[gs][i]]
            mark = "border:3px solid #1f2933;font-weight:700" if (gs == g and a_s == a) else "border:1px solid #fff"
            cells.append(f"<td style='background:{hex_};{mark};width:46px;height:22px;text-align:center;"
                         f"color:#fff'>{'●' if (gs == g and a_s == a) else ''}</td>")
        rows.append(f"<tr><th style='padding:2px 8px;text-align:right'>{gs}</th>{''.join(cells)}</tr>")
    return (f"<table style='border-collapse:collapse;font-size:13px'><tr><th></th>{head}</tr>"
            f"{''.join(rows)}</table><div style='font-size:12px;color:#52606d'>Rows: eGFR category · "
            "Columns: albuminuria (UACR)</div>")


def minutes_ago(iso: str | None) -> int | None:
    if not iso:
        return None
    t = datetime.fromisoformat(iso)
    return int((datetime.now(timezone.utc) - t).total_seconds() // 60)


def _layout(fig: go.Figure, title: str, height: int = 280, ytitle: str = "") -> go.Figure:
    fig.update_layout(title=dict(text=title, font=dict(size=14)), height=height, margin=dict(l=10, r=10, t=40, b=10),
                      plot_bgcolor="#ffffff", paper_bgcolor="#ffffff", yaxis_title=ytitle, showlegend=False)
    fig.update_xaxes(showgrid=True, gridcolor="#eef2f5")
    fig.update_yaxes(showgrid=True, gridcolor="#eef2f5")
    return fig


def cgm_chart(rows: list[dict], title: str = "CGM glucose", forecast: dict | None = None,
              height: int = 300) -> go.Figure:
    fig = go.Figure()
    fig.add_hrect(y0=70, y1=180, fillcolor="#2e7d32", opacity=0.07, line_width=0)
    if rows:
        df = pd.DataFrame(rows)
        df["time"] = pd.to_datetime(df["time"], format="ISO8601", utc=True).dt.tz_convert("Asia/Kolkata")
        fig.add_trace(go.Scatter(x=df["time"], y=df["value"], mode="lines", line=dict(color=ACCENT, width=2),
                                 name="glucose"))
        lows = df[df["value"] < 70]
        if len(lows):
            fig.add_trace(go.Scatter(x=lows["time"], y=lows["value"], mode="markers",
                                     marker=dict(color=KDIGO_HEX["red"], size=7), name="low"))
        if forecast and forecast.get("plus_30") is not None:
            last = df["time"].iloc[-1]
            fig.add_trace(go.Scatter(x=[last, last + pd.Timedelta(minutes=30), last + pd.Timedelta(minutes=60)],
                                     y=[df["value"].iloc[-1], forecast["plus_30"], forecast.get("plus_60")],
                                     mode="lines+markers", line=dict(color="#9aa5b1", dash="dot"),
                                     name="forecast"))
    fig.add_hline(y=70, line=dict(color=KDIGO_HEX["red"], width=1, dash="dash"))
    fig.add_hline(y=250, line=dict(color=KDIGO_HEX["orange"], width=1, dash="dash"))
    return _layout(fig, title, height, "mg/dL")


def trend_chart(points: list[dict], title: str, unit: str, target: float | None = None,
                target_kind: str = "below", height: int = 240) -> go.Figure:
    fig = go.Figure()
    if points:
        df = pd.DataFrame(points)
        df["time"] = pd.to_datetime(df["time"], format="ISO8601", utc=True).dt.tz_convert("Asia/Kolkata")
        fig.add_trace(go.Scatter(x=df["time"], y=df["value"], mode="lines+markers",
                                 line=dict(color=ACCENT, width=2), marker=dict(size=7)))
    if target is not None:
        fig.add_hline(y=target, line=dict(color=KDIGO_HEX["green"], dash="dash", width=1),
                      annotation_text=f"target {'<' if target_kind == 'below' else '≥'} {target}",
                      annotation_position="top left")
    return _layout(fig, title, height, unit)


def tir_ring(tir: float | None, label: str) -> go.Figure:
    tir = tir or 0
    fig = go.Figure(go.Pie(values=[tir, 100 - tir], hole=0.72, sort=False, textinfo="none",
                           marker=dict(colors=[KDIGO_HEX["green"] if tir >= 70 else KDIGO_HEX["orange"], "#e4e7eb"])))
    fig.update_layout(height=200, margin=dict(l=0, r=0, t=0, b=0), showlegend=False,
                      annotations=[dict(text=f"<b>{tir:.0f}%</b><br><span style='font-size:11px'>{label}</span>",
                                        showarrow=False, font=dict(size=22))])
    return fig


def show_error(e: Exception) -> None:
    st.error(str(e))
