"""Shared UI pieces: sidebar user box, KDIGO colours and chips, charts.

Look: warm off-white background, logo navy as the accent, logo orange for brand highlights,
KDIGO colours used only for risk (design: glycorenal-twin-ui_2.html).
"""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import api_client

ACCENT = "#1C3C5F"
KDIGO_HEX = {"green": "#2F9A5A", "yellow": "#E5B92E", "orange": "#E37C33", "red": "#C6363A"}
BAND_HEX = {"low": "#2F9A5A", "moderate": "#E5B92E", "high": "#E37C33", "very_high": "#C6363A"}
TINT = {"#2F9A5A": ("#E6F4EC", "#1E6B3E"), "#E5B92E": ("#FBF3DA", "#7A5C05"),
        "#E37C33": ("#FCEBDD", "#8F4510"), "#C6363A": ("#F9E3E3", "#8E1F22")}
BAND_LABEL = {"low": "Low", "moderate": "Moderate", "high": "High", "very_high": "Very high"}
SEVERITY_ICON = {"critical": "🚨", "warning": "⚠️", "info": "ℹ️"}
G_ORDER = ["G1", "G2", "G3a", "G3b", "G4", "G5"]
A_ORDER = ["A1", "A2", "A3"]
GRID = {"G1": ["low", "moderate", "high"], "G2": ["low", "moderate", "high"],
        "G3a": ["moderate", "high", "very_high"], "G3b": ["high", "very_high", "very_high"],
        "G4": ["very_high"] * 3, "G5": ["very_high"] * 3}


# --------------------------------------------------------------------------- look and feel
# Design: logo navy (primary) + logo orange (brand highlight); KDIGO colours used for risk only.
NAVY, NAVY_INK, ORANGE = "#1C3C5F", "#132B45", "#EB7230"

LOGO_SVG = """<svg viewBox="0 0 46 30" fill="none" width="{w}" aria-label="GlycoRenal Twin logo">
<circle cx="30.5" cy="15" r="12.3" stroke="{r2}" stroke-width="2.1" opacity=".8"/>
<circle cx="15.5" cy="15" r="12.3" stroke="{r1}" stroke-width="2.1"/>
<path d="M5.5 15.5H11.6L14.6 8.6L18.6 21.4L21.6 14.8H27.6" stroke="#EB7230" stroke-width="2.2"
 stroke-linecap="round" stroke-linejoin="round"/></svg>"""


def logo(width: int = 34, on_dark: bool = False) -> str:
    return LOGO_SVG.format(w=width, r1="#F1F5FA" if on_dark else NAVY, r2="#8FA7C4")


CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500&family=Noto+Sans+Devanagari:wght@400;500;600;700&display=swap');
:root{--bg:#F6F5F1;--paper:#fff;--ink:#13212A;--ink-2:#46565F;--ink-3:#86939A;--line:#E5E3DC;--line-2:#EFEDE7;
 --accent:#1C3C5F;--accent-ink:#132B45;--accent-tint:#E8EEF5;--accent-tint-2:#F3F6FA;--brand:#EB7230;--brand-tint:#FDEEE5;
 --k-green:#2F9A5A;--k-yellow:#E5B92E;--k-orange:#E37C33;--k-red:#C6363A;
 --shadow:0 1px 0 rgba(19,33,42,.04),0 8px 24px -12px rgba(19,33,42,.12)}
html,body,[class*="css"],.stApp,.stMarkdown,button,input,textarea,select{font-family:"Plus Jakarta Sans","Noto Sans Devanagari",system-ui,sans-serif!important}
.stApp{background:var(--bg)}
[data-testid="stDecoration"]{display:none}
[data-testid="stHeader"]{background:transparent}
h1,h2,h3,h4{font-family:"Plus Jakarta Sans","Noto Sans Devanagari",sans-serif!important;color:var(--ink);letter-spacing:-.02em;font-weight:700!important}
h1{font-size:32px!important}
/* sidebar */
[data-testid="stSidebar"]{background:var(--paper);border-right:1px solid var(--line)}
.gr-brand{display:flex;align-items:center;gap:10px;font-weight:700;font-size:15px;color:var(--ink);padding:2px 0 14px}
.gr-brand small{display:block;font-size:11px;color:var(--ink-3);font-weight:500;letter-spacing:.04em}
.gr-me{display:flex;align-items:center;gap:10px;padding:12px 0;border-top:1px solid var(--line-2);margin-top:6px}
.gr-av{width:34px;height:34px;border-radius:50%;background:var(--accent-tint);color:var(--accent-ink);display:grid;place-items:center;font-weight:700;font-size:12px;flex:none}
.gr-me b{display:block;font-size:13px;line-height:1.2}.gr-me small{color:var(--ink-3);font-size:11.5px}
/* cards: bordered containers, metrics, expanders */
[data-testid="stVerticalBlockBorderWrapper"]:has(> div > [data-testid="stVerticalBlock"]){border-radius:10px}
div[data-testid="stVerticalBlockBorderWrapper"][style*="border"],[data-testid="stExpander"] details,[data-testid="stForm"]{background:var(--paper);border:1px solid var(--line)!important;border-radius:10px!important;box-shadow:var(--shadow)}
[data-testid="stMetric"]{background:var(--paper);border:1px solid var(--line);border-radius:10px;padding:14px 16px;box-shadow:var(--shadow)}
[data-testid="stMetricLabel"] p{font-size:11px!important;text-transform:uppercase;letter-spacing:.1em;color:var(--ink-3)!important;font-weight:600!important}
[data-testid="stMetricValue"]{font-weight:700;letter-spacing:-.02em;font-variant-numeric:tabular-nums;color:var(--ink);font-size:26px!important}
[data-testid="stMetricValue"] div{overflow:visible!important;text-overflow:clip!important}
[data-testid="stExpander"] summary{font-weight:600}
/* tabs: underline style */
.stTabs [role="tablist"]{gap:2px;border-bottom:1px solid var(--line)}
.stTabs [data-testid="stTab"]{padding:8px 12px}
.stTabs [data-testid="stTab"] p{font-weight:600;color:var(--ink-3)}
.stTabs [data-testid="stTab"]:hover p{color:var(--ink)}
.stTabs [data-testid="stTab"][aria-selected="true"] p{color:var(--accent-ink)}
.stTabs .react-aria-SelectionIndicator{background:var(--accent)!important}
/* buttons and inputs */
.stButton>button,.stDownloadButton>button,[data-testid="stFormSubmitButton"]>button{border-radius:8px;font-weight:600;border:1px solid var(--line)}
.stButton>button[kind="primary"],[data-testid="stFormSubmitButton"]>button[kind="primaryFormSubmit"],.stDownloadButton>button[kind="primary"]{background:var(--accent);border-color:var(--accent)}
.stButton>button[kind="primary"]:hover,[data-testid="stFormSubmitButton"]>button[kind="primaryFormSubmit"]:hover{background:var(--accent-ink);border-color:var(--accent-ink)}
[data-baseweb="input"],[data-baseweb="select"]>div,[data-baseweb="textarea"]{border-radius:8px!important}
/* alerts as soft banners */
[data-testid="stAlert"]{border-radius:10px}
/* tables and chips */
table.gr-tbl{width:100%;border-collapse:collapse;background:var(--paper);border:1px solid var(--line);border-radius:10px;overflow:hidden;box-shadow:var(--shadow)}
table.gr-tbl th{text-align:left;font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:var(--ink-3);font-weight:600;padding:10px 12px;border-bottom:1px solid var(--line);background:var(--paper)}
table.gr-tbl td{padding:10px 12px;border-bottom:1px solid var(--line-2);vertical-align:middle;font-variant-numeric:tabular-nums;white-space:nowrap}
table.gr-tbl tr:last-child td{border-bottom:none}
table.gr-tbl tr:hover td{background:var(--accent-tint-2)}
.gr-chip{display:inline-flex;align-items:center;padding:2px 9px;border-radius:999px;font-size:11.5px;font-weight:600;white-space:nowrap}
.gr-eyebrow{font-size:11px;text-transform:uppercase;letter-spacing:.1em;color:var(--ink-3);font-weight:600}
.gr-mono{font-family:"JetBrains Mono",ui-monospace,monospace;font-size:.92em}
/* KDIGO heat map */
.gr-kdigo{display:grid;grid-template-columns:44px repeat(3,1fr);gap:3px;font-size:11px;max-width:330px}
.gr-kdigo .h{color:var(--ink-3);font-weight:600;text-align:center;padding:2px 0}
.gr-kdigo .rl{color:var(--ink-2);font-weight:600;display:flex;align-items:center;font-family:"JetBrains Mono",monospace}
.gr-kdigo .c{height:26px;border-radius:4px;opacity:.32;display:grid;place-items:center}
.gr-kdigo .c.here{opacity:1;outline:2px solid var(--ink);outline-offset:2px}
.gr-kdigo .c.here::after{content:"Now";color:#fff;font-weight:700;font-size:10.5px}
/* patient header */
.gr-pt{display:flex;align-items:center;gap:18px;background:var(--paper);border:1px solid var(--line);border-radius:10px;padding:16px 20px;box-shadow:var(--shadow);margin:6px 0 4px}
.gr-pt .big-av{width:52px;height:52px;border-radius:14px;background:var(--accent);color:#fff;display:grid;place-items:center;font-weight:700;font-size:20px;flex:none}
.gr-pt h2{font-size:24px!important;margin:0!important;padding:0!important;line-height:1.15}
.gr-pt .meta{color:var(--ink-2);font-size:12.5px;margin-top:3px}
.gr-pt .right{margin-left:auto;display:flex;gap:8px;flex-wrap:wrap;justify-content:flex-end}
/* patient app */
.gr-hello{display:flex;align-items:center;gap:12px;margin:4px 0 6px}
.gr-hello .hi{font-size:26px;font-weight:700;letter-spacing:-.02em;line-height:1.1}
.gr-hello small{display:block;font-size:12px;color:var(--ink-3);font-weight:500}
.glu-hero{border-radius:18px;background:var(--accent-ink);color:#fff;padding:20px 22px;position:relative;overflow:hidden}
.glu-hero::after{content:"";position:absolute;right:-60px;top:-60px;width:220px;height:220px;border-radius:50%;background:radial-gradient(circle,rgba(235,114,48,.28),transparent 70%)}
.glu-hero.low{background:#8E1F22}.glu-hero.high{background:#8F4510}
.glu-hero .lbl{font-size:12px;color:#AFC3D9;letter-spacing:.04em}
.glu-hero .val{font-size:84px;font-weight:700;line-height:.95;margin-top:6px;display:flex;align-items:flex-end;gap:10px;letter-spacing:-.02em;font-variant-numeric:tabular-nums}
.glu-hero .val small{font-size:14px;color:#AFC3D9;margin-bottom:12px;font-weight:500}
.glu-hero .arrow{font-size:32px;margin-bottom:10px}
.glu-hero .state{display:inline-flex;margin-top:8px;padding:4px 10px;border-radius:999px;background:rgba(255,255,255,.12);font-size:12.5px;font-weight:600}
.glu-hero .foot{display:flex;justify-content:space-between;font-size:11px;color:#AFC3D9;margin-top:4px}
.gr-live{font-size:11px;font-weight:700;letter-spacing:.08em;color:#F4A06F}
/* login */
.gr-hero{background:var(--accent-ink);border-radius:18px;min-height:82vh;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;position:relative;overflow:hidden;color:#E8EEF5}
.gr-hero::before{content:"";position:absolute;inset:0;background:radial-gradient(520px 420px at 50% 46%,rgba(235,114,48,.16),transparent 65%),radial-gradient(900px 600px at 50% 50%,rgba(120,170,230,.12),transparent 70%)}
.gr-hero::after{content:"";position:absolute;inset:0;background-image:linear-gradient(rgba(255,255,255,.04) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,.04) 1px,transparent 1px);background-size:32px 32px;-webkit-mask-image:linear-gradient(180deg,transparent,black 40%,black 70%,transparent)}
.gr-hero>*{position:relative;z-index:1}
.gr-hero svg{width:300px;max-width:60%;height:auto;animation:breathe 3.2s ease-in-out 1s infinite}
.gr-hero svg circle{stroke-dasharray:78;stroke-dashoffset:78;animation:draw 1.3s cubic-bezier(.6,0,.2,1) forwards}
.gr-hero svg circle:first-child{animation-delay:.35s}
.gr-hero svg path{stroke-dasharray:36;stroke-dashoffset:36;animation:draw 1s ease-out 1.1s forwards}
.gr-hero .name{margin-top:30px;font-size:42px;font-weight:800;letter-spacing:-.03em;color:#fff}
.gr-hero .line{margin-top:6px;font-size:16px;color:#9FB3CB}
@keyframes draw{to{stroke-dashoffset:0}}
@keyframes breathe{0%,100%{transform:scale(1)}12%{transform:scale(1.035);filter:drop-shadow(0 0 14px rgba(235,114,48,.45))}24%{transform:scale(1)}}
.gr-signin h2{font-size:32px!important;letter-spacing:-.025em}
</style>
"""


def apply_style() -> None:
    """Inject the design (fonts, colours, cards, chips). Called once per page run from Home.py."""
    st.markdown(CSS, unsafe_allow_html=True)


def initials(name: str) -> str:
    parts = [w for w in (name or "?").replace("Dr.", "").split() if w]
    return "".join(w[0] for w in parts[:2]).upper() or "?"


def sidebar_user() -> None:
    user = api_client.current_user()
    if not user:
        return
    name = user["full_name"] or user["username"]
    portal = {"doctor": "Clinician portal", "admin": "Admin console", "patient": "My health twin"}[user["role"]]
    with st.sidebar:
        st.markdown(f"<div class='gr-brand'>{logo(34)}<div>GlycoRenal Twin<small>{portal}</small></div></div>"
                    f"<div class='gr-me'><div class='gr-av'>{initials(name)}</div><div><b>{name}</b>"
                    f"<small>{user['role'].title()}</small></div></div>", unsafe_allow_html=True)
        if st.button("Log out", width="stretch"):
            api_client.logout()
            st.rerun()


def chip(text: str, hex_: str) -> str:
    bg, fg = TINT.get(hex_, ("#EFEDE7", "#46565F"))
    return f"<span class='gr-chip' style='background:{bg};color:{fg}'>{text}</span>"


def kdigo_chip(stage: str | None, colour: str | None) -> str:
    return chip(stage or "n/a", KDIGO_HEX.get(colour or "", "#86939A"))


def risk_chip(risk: float | None, band: str | None) -> str:
    if risk is None:
        return chip("n/a", "#86939A")
    return chip(f"{risk:.0%} {BAND_LABEL.get(band, '')}", BAND_HEX.get(band, "#86939A"))


def kdigo_grid(g: str | None, a: str | None) -> str:
    """KDIGO heat map (design grid), with the patient's cell marked 'Now'."""
    s = ("<div class='gr-kdigo'><div></div><div class='h'>A1 &lt;30</div><div class='h'>A2 30–300</div>"
         "<div class='h'>A3 &gt;300</div>")
    for gs in G_ORDER:
        s += f"<div class='rl'>{gs}</div>"
        for i, a_s in enumerate(A_ORDER):
            here = " here" if (gs == g and a_s == a) else ""
            s += f"<div class='c{here}' style='background:{BAND_HEX[GRID[gs][i]]}'></div>"
    return s + ("</div><div style='font-size:11.5px;color:#86939A;margin-top:6px'>Rows: eGFR category · "
                "Columns: albuminuria (UACR)</div>")


def minutes_ago(iso: str | None) -> int | None:
    if not iso:
        return None
    t = datetime.fromisoformat(iso)
    if t.tzinfo is None:  # stored as UTC
        t = t.replace(tzinfo=timezone.utc)
    return int((datetime.now(timezone.utc) - t).total_seconds() // 60)


def _layout(fig: go.Figure, title: str, height: int = 280, ytitle: str = "") -> go.Figure:
    fig.update_layout(title=dict(text=title, font=dict(size=13, color="#13212A")), height=height,
                      margin=dict(l=10, r=10, t=40, b=10), plot_bgcolor="#ffffff", paper_bgcolor="#ffffff",
                      yaxis_title=ytitle, showlegend=False,
                      font=dict(family="Plus Jakarta Sans, Noto Sans Devanagari, sans-serif", color="#46565F", size=11))
    fig.update_xaxes(showgrid=True, gridcolor="#EFEDE7", linecolor="#E5E3DC")
    fig.update_yaxes(showgrid=True, gridcolor="#EFEDE7", linecolor="#E5E3DC")
    return fig


def cgm_chart(rows: list[dict], title: str = "CGM glucose", forecast: dict | None = None,
              height: int = 300) -> go.Figure:
    fig = go.Figure()
    fig.add_hrect(y0=70, y1=180, fillcolor="#2e7d32", opacity=0.07, line_width=0)
    if rows:
        df = pd.DataFrame(rows)
        df["time"] = pd.to_datetime(df["time"], format="ISO8601", utc=True).dt.tz_convert("Asia/Kolkata")
        fig.add_trace(go.Scatter(x=df["time"], y=df["value"], mode="lines", line=dict(color=ACCENT, width=2.2),
                                 name="glucose"))
        lows = df[df["value"] < 70]
        if len(lows):
            fig.add_trace(go.Scatter(x=lows["time"], y=lows["value"], mode="markers",
                                     marker=dict(color=KDIGO_HEX["red"], size=7), name="low"))
        if forecast and forecast.get("plus_30") is not None:
            last = df["time"].iloc[-1]
            # each reading stands for 5 minutes; in demo mode readings arrive every few seconds, so draw the
            # forecast 6 and 12 readings ahead (= 30 and 60 min with a real sensor)
            step = df["time"].diff().tail(10).median() if len(df) > 2 else pd.Timedelta(minutes=5)
            step = min(step, pd.Timedelta(minutes=5)) if pd.notna(step) else pd.Timedelta(minutes=5)
            fig.add_trace(go.Scatter(x=[last, last + 6 * step, last + 12 * step],
                                     y=[df["value"].iloc[-1], forecast["plus_30"], forecast.get("plus_60")],
                                     mode="lines+markers", line=dict(color="#9aa5b1", dash="dot"),
                                     name="forecast"))
    fig.add_hline(y=70, line=dict(color=KDIGO_HEX["red"], width=1, dash="dash"))
    fig.add_hline(y=250, line=dict(color=KDIGO_HEX["orange"], width=1, dash="dash"))
    return _layout(fig, title, height, "mg/dL")


def sparkline(values: list[float], w: int = 480, h: int = 60, colour: str = "#fff") -> str:
    """Small inline SVG line (patient glucose card)."""
    v = [x for x in values if x is not None][-36:]
    if len(v) < 2:
        return ""
    lo, hi = min(v + [70]), max(v + [180])
    pts = " ".join(f"{i * w / (len(v) - 1):.1f},{h - (x - lo) / (hi - lo or 1) * h:.1f}" for i, x in enumerate(v))
    y70, y180 = h - (70 - lo) / (hi - lo) * h, h - (180 - lo) / (hi - lo) * h
    return (f"<svg viewBox='0 0 {w} {h}' width='100%' height='{h}' preserveAspectRatio='none' style='margin-top:12px'>"
            f"<rect x='0' y='{y180:.1f}' width='{w}' height='{max(y70 - y180, 0):.1f}' fill='rgba(255,255,255,.08)'/>"
            f"<polyline points='{pts}' fill='none' stroke='{colour}' stroke-width='2.2' stroke-linejoin='round'/></svg>")


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
                           marker=dict(colors=[ACCENT if tir >= 70 else ORANGE, "#EFEDE7"])))
    fig.update_layout(height=200, margin=dict(l=0, r=0, t=0, b=0), showlegend=False,
                      annotations=[dict(text=f"<b>{tir:.0f}%</b><br><span style='font-size:11px'>{label}</span>",
                                        showarrow=False, font=dict(size=22))])
    return fig


def show_error(e: Exception) -> None:
    st.error(str(e))


# ---------------- personal twin charts ----------------

def twin_vs_real_chart(replay: dict, title: str = "Twin vs real (last 3 days, not used for tuning)") -> go.Figure:
    t = pd.to_datetime(pd.Series(replay["time"]), format="ISO8601", utc=True).dt.tz_convert("Asia/Kolkata")
    fig = go.Figure()
    fig.add_hrect(y0=70, y1=180, fillcolor=KDIGO_HEX["green"], opacity=0.07, line_width=0)
    fig.add_trace(go.Scatter(x=t, y=replay["real"], mode="lines", name="real sensor", line=dict(color="#1f2933", width=1.6)))
    fig.add_trace(go.Scatter(x=t, y=replay["twin"], mode="lines", name="twin", line=dict(color=ACCENT, width=2, dash="dot")))
    fig = _layout(fig, title, 300, "mg/dL")
    fig.update_layout(showlegend=True, legend=dict(orientation="h", y=1.12, x=1, xanchor="right"))
    return fig


def what_if_chart(w: dict, label_plan: str = "with this meal", label_without: str = "without it") -> go.Figure:
    t = pd.to_datetime(pd.Series(w["time"]), format="ISO8601", utc=True).dt.tz_convert("Asia/Kolkata")
    fig = go.Figure()
    fig.add_hrect(y0=70, y1=180, fillcolor=KDIGO_HEX["green"], opacity=0.07, line_width=0)
    fig.add_trace(go.Scatter(x=t, y=w["without_meal"], mode="lines", name=label_without,
                             line=dict(color="#9aa5b1", width=1.5, dash="dot")))
    fig.add_trace(go.Scatter(x=t, y=w["with_plan"], mode="lines", name=label_plan, line=dict(color=ACCENT, width=2.4)))
    fig.add_hline(y=180, line=dict(color=KDIGO_HEX["orange"], width=1, dash="dash"))
    fig = _layout(fig, "", 280, "mg/dL")
    fig.update_layout(showlegend=True, legend=dict(orientation="h", y=1.1, x=1, xanchor="right"))
    return fig


def kidney_path_chart(k: dict, measured: list[dict], plan: dict | None = None, plan_label: str = "with plan") -> go.Figure:
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    p = k["projection"]
    xs = [now + timedelta(days=365.25 * y) for y in p["years"]]
    fig = go.Figure()
    for lo, hi, colour in ((90, 160, "#2e7d32"), (60, 90, "#2e7d32"), (45, 60, "#f9a825"), (30, 45, "#ef6c00"),
                           (15, 30, "#c62828"), (0, 15, "#c62828")):
        fig.add_hrect(y0=lo, y1=hi, fillcolor=colour, opacity=0.05, line_width=0)
    fig.add_trace(go.Scatter(x=xs + xs[::-1], y=p["high"] + p["low"][::-1], fill="toself", fillcolor="rgba(28,60,95,0.12)",
                             line=dict(width=0), name="80% range", hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=xs, y=p["mean"], mode="lines", name="twin: current path", line=dict(color=ACCENT, width=2.4)))
    if plan:
        pp = plan["projection"]
        fig.add_trace(go.Scatter(x=xs, y=pp["mean"], mode="lines", name=plan_label,
                                 line=dict(color=KDIGO_HEX["green"], width=2.4, dash="dash")))
    if measured:
        m = pd.DataFrame(measured)
        fig.add_trace(go.Scatter(x=pd.to_datetime(m["time"], format="ISO8601", utc=True), y=m["value"], mode="markers",
                                 name="measured eGFR", marker=dict(color="#1f2933", size=8)))
    for th in (60, 45, 30):
        fig.add_hline(y=th, line=dict(color="#9aa5b1", width=1, dash="dot"), annotation_text=str(th),
                      annotation_position="right")
    fig = _layout(fig, "Personal eGFR path (CKD-EPI 2021)", 320, "mL/min/1.73m²")
    fig.update_layout(showlegend=True, legend=dict(orientation="h", y=1.14, x=1, xanchor="right"))
    return fig
