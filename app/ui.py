"""Shared UI kit for every screen (design: glycorenal-twin-ui_3.html).

Look: warm off-white background, logo navy as the accent, logo orange for brand highlights,
KDIGO colours used only for risk. Pages build small HTML pieces with the helpers below
(card, stat, chip, table, charts) and pass them to md(). Charts are plain SVG, drawn the
same way as in the design, so they look identical online and offline.
"""

from __future__ import annotations

import html
import math
from datetime import datetime, timezone

import pandas as pd
import streamlit as st

import api_client

# --------------------------------------------------------------------------- colours
NAVY, NAVY_INK, ORANGE = "#1C3C5F", "#132B45", "#EB7230"
ACCENT = NAVY
GREY = "#86939A"
KDIGO_HEX = {"green": "#2F9A5A", "yellow": "#E5B92E", "orange": "#E37C33", "red": "#C6363A"}
BAND_HEX = {"low": "#2F9A5A", "moderate": "#E5B92E", "high": "#E37C33", "very_high": "#C6363A"}
BAND_KIND = {"low": "green", "moderate": "yellow", "high": "orange", "very_high": "red"}
BAND_LABEL = {"low": "Low risk", "moderate": "Moderate", "high": "High", "very_high": "Very high"}
SEVERITY_ICON = {"critical": "🚨", "warning": "⚠️", "info": "ℹ️"}
G_ORDER = ["G1", "G2", "G3a", "G3b", "G4", "G5"]
A_ORDER = ["A1", "A2", "A3"]
GRID = {"G1": ["low", "moderate", "high"], "G2": ["low", "moderate", "high"],
        "G3a": ["moderate", "high", "very_high"], "G3b": ["high", "very_high", "very_high"],
        "G4": ["very_high"] * 3, "G5": ["very_high"] * 3}
LOINC = {"hba1c": "4548-4", "creatinine": "2160-0", "egfr": "98979-8", "uacr": "9318-7", "potassium": "2823-3",
         "ldl": "13457-7", "bp": "8480-6", "bmi": "39156-5"}

LOGO_SVG = ("<svg viewBox='0 0 46 30' fill='none' width='{w}' aria-label='GlycoRenal Twin logo' class='{cls}'>"
            "<circle class='ring r2' cx='30.5' cy='15' r='12.3' stroke='{r2}' stroke-width='2.1' opacity='.8'/>"
            "<circle class='ring r1' cx='15.5' cy='15' r='12.3' stroke='{r1}' stroke-width='2.1'/>"
            "<path class='pulse' d='M5.5 15.5H11.6L14.6 8.6L18.6 21.4L21.6 14.8H27.6' stroke='#EB7230' "
            "stroke-width='2.2' stroke-linecap='round' stroke-linejoin='round'/></svg>")


def logo(width: int = 34, on_dark: bool = False, cls: str = "") -> str:
    return LOGO_SVG.format(w=width, r1="#F1F5FA" if on_dark else NAVY, r2="#8FA7C4", cls=cls)


# --------------------------------------------------------------------------- CSS
CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:ital,wght@0,400;0,500;0,600;0,700;0,800;1,600&family=JetBrains+Mono:wght@400;500&family=Noto+Sans+Devanagari:wght@400;500;600;700&display=swap');
:root{--bg:#F6F5F1;--paper:#fff;--ink:#13212A;--ink-2:#46565F;--ink-3:#86939A;--line:#E5E3DC;--line-2:#EFEDE7;
 --accent:#1C3C5F;--accent-ink:#132B45;--accent-tint:#E8EEF5;--accent-tint-2:#F3F6FA;--brand:#EB7230;--brand-tint:#FDEEE5;
 --k-green:#2F9A5A;--k-yellow:#E5B92E;--k-orange:#E37C33;--k-red:#C6363A;
 --k-green-t:#E6F4EC;--k-yellow-t:#FBF3DA;--k-orange-t:#FCEBDD;--k-red-t:#F9E3E3;
 --mono:"JetBrains Mono",ui-monospace,monospace;--r:10px;
 --shadow:0 1px 0 rgba(19,33,42,.04),0 8px 24px -12px rgba(19,33,42,.12)}
html,body,.stApp,.stApp :is(p,div,label,input,textarea,select,button,li,td,th,h1,h2,h3,h4,h5,small,b,a,summary),.stApp span:not([data-testid="stIconMaterial"]):not([role="img"]){font-family:"Plus Jakarta Sans","Noto Sans Devanagari",system-ui,sans-serif!important}
.stApp :is(.mono,.mono *,.code,.code *,code,.src-chip,.kdigo .rl):not(#_){font-family:"JetBrains Mono",ui-monospace,monospace!important}
.stApp{background:var(--bg);color:var(--ink)}
[data-testid="stDecoration"]{display:none}
[data-testid="stHeaderActionElements"]{display:none!important}
.stApp [data-stale="true"]{opacity:1!important;transition:none!important}
[data-testid="stHeader"]{background:transparent;height:2.4rem}
.block-container{padding:1.2rem 2rem 2.5rem;max-width:1440px}
h1,h2,h3,h4{font-family:"Plus Jakarta Sans","Noto Sans Devanagari",sans-serif!important;color:var(--ink);letter-spacing:-.02em}
.stMarkdown p{margin-bottom:0}
[data-testid="stMarkdownContainer"]:has(> div.gr){margin-bottom:0}
div.gr{font-size:14px;line-height:1.5}
.card,[class*="st-key-box"],[class*="st-key-box"] [data-testid="stMarkdownContainer"] p{font-size:14px}
[data-testid="stElementContainer"]:has(> .stMarkdown style){display:none}
.mono{font-family:var(--mono);font-size:.92em;letter-spacing:-.01em}
.muted{color:var(--ink-2)}.faint{color:var(--ink-3)}.num{font-variant-numeric:tabular-nums}
.eyebrow{font-size:11px;text-transform:uppercase;letter-spacing:.1em;color:var(--ink-3);font-weight:600}
.big-n{font-weight:700;letter-spacing:-.02em;line-height:1.1;font-variant-numeric:tabular-nums}
/* cards */
.card{background:var(--paper);border:1px solid var(--line);border-radius:var(--r);box-shadow:var(--shadow);overflow:hidden}
.card-h{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:13px 18px;border-bottom:1px solid var(--line-2)}
.card-h h3{font-size:13px!important;font-weight:600!important;letter-spacing:.02em;margin:0!important;padding:0!important;line-height:1.4!important}
.card-b{padding:16px 18px}
.grid{display:grid;gap:16px}.g2{grid-template-columns:repeat(2,minmax(0,1fr))}.g3{grid-template-columns:repeat(3,minmax(0,1fr))}.g4{grid-template-columns:repeat(4,minmax(0,1fr))}
.grid>*{min-width:0}
.row{display:flex;align-items:center;gap:10px}.between{justify-content:space-between}.wrap{flex-wrap:wrap}
.stack{display:flex;flex-direction:column;gap:14px}
.stat{padding:16px 18px}
.stat .v{font-size:30px;font-weight:700;letter-spacing:-.02em;line-height:1.05;margin-top:6px;font-variant-numeric:tabular-nums}
.stat .v small{font-size:13px;color:var(--ink-3);margin-left:4px;font-weight:500;letter-spacing:0}
.stat .d{font-size:12px;color:var(--ink-2);margin-top:4px}
.risk{padding:18px}
.risk .v{font-size:40px;font-weight:700;letter-spacing:-.02em;line-height:1;margin-top:8px;font-variant-numeric:tabular-nums}
.risk .v small{font-size:14px;color:var(--ink-3);font-weight:500}
.risk .bar{height:6px;border-radius:999px;background:var(--line-2);margin-top:12px;overflow:hidden}
.risk .bar i{display:block;height:100%;border-radius:999px}
.risk .meta{font-size:11.5px;color:var(--ink-3);margin-top:10px;display:flex;justify-content:space-between;gap:8px}
.page-h{margin:2px 0 20px}
.page-h h1{font-size:32px!important;font-weight:700!important;letter-spacing:-.025em;line-height:1.05;padding:4px 0 0!important;margin:0!important}
.page-h p{color:var(--ink-2);margin-top:6px}
/* chips */
.chip{display:inline-flex;align-items:center;gap:6px;padding:2px 9px;border-radius:999px;font-size:11.5px;font-weight:600;border:1px solid var(--line);background:var(--paper);white-space:nowrap;line-height:1.6}
.chip .dot{width:7px;height:7px;border-radius:50%}
.chip.accent{background:var(--accent-tint);border-color:transparent;color:var(--accent-ink)}
.chip.green{background:var(--k-green-t);border-color:transparent;color:#1E6B3E}
.chip.yellow{background:var(--k-yellow-t);border-color:transparent;color:#7A5C05}
.chip.orange{background:var(--k-orange-t);border-color:transparent;color:#8F4510}
.chip.red{background:var(--k-red-t);border-color:transparent;color:#8E1F22}
.chip.plain{background:var(--line-2);border-color:transparent;color:var(--ink-2)}
.chip.brand{background:var(--brand-tint);border-color:transparent;color:#8A3A12}
.badge-live{display:inline-flex;align-items:center;gap:6px;font-size:11px;font-weight:700;letter-spacing:.08em;color:var(--accent)}
.badge-live::before{content:"";width:7px;height:7px;border-radius:50%;background:currentColor;animation:pulse 1.6s infinite}
@keyframes pulse{0%{box-shadow:0 0 0 0 rgba(28,60,95,.5)}70%{box-shadow:0 0 0 7px rgba(28,60,95,0)}100%{box-shadow:0 0 0 0 rgba(28,60,95,0)}}
/* tables */
.tbl{width:100%;border-collapse:collapse;font-size:13.5px}
.tbl th{text-align:left;font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:var(--ink-3);font-weight:600;padding:10px 14px;border-bottom:1px solid var(--line);background:var(--paper)}
.tbl td{white-space:nowrap;padding:11px 14px;border-bottom:1px solid var(--line-2);vertical-align:middle;font-variant-numeric:tabular-nums}
.tbl tr:last-child td{border-bottom:none}
.tscroll{overflow-x:auto}
.progress{height:8px;background:var(--line-2);border-radius:999px;overflow:hidden}
.progress i{display:block;height:100%;background:var(--accent);border-radius:999px}
/* clickable rows: an invisible Streamlit button covers the HTML row */
[class*="st-key-row_"]{position:relative;gap:0!important}
[class*="st-key-row_"]>[data-testid="stElementContainer"]:has(.stButton){position:absolute!important;inset:0;z-index:3;margin:0;width:100%!important;height:100%}
[class*="st-key-row_"] .stButton,[class*="st-key-row_"] .stButton>div{width:100%!important;height:100%}
[class*="st-key-row_"] .stButton button{width:100%;height:100%;opacity:0;cursor:pointer}
[class*="st-key-row_"]:hover .prow{background:var(--accent-tint-2)}
.st-key-ptable,.st-key-acclist{background:var(--paper);border:1px solid var(--line);border-radius:var(--r);box-shadow:var(--shadow);gap:0!important;overflow-x:auto}
.prow{display:grid;grid-template-columns:2.3fr 1fr 1.5fr .7fr .6fr .6fr .9fr .9fr .8fr;align-items:center;gap:8px;padding:11px 16px;border-bottom:1px solid var(--line-2);min-width:860px;font-size:13.5px;font-variant-numeric:tabular-nums}
.prow.h{font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:var(--ink-3);font-weight:600;padding:10px 16px;border-bottom:1px solid var(--line)}
/* KDIGO */
.kdigo{display:grid;grid-template-columns:52px repeat(3,1fr);gap:3px;font-size:11px}
.kdigo .h{color:var(--ink-3);font-weight:600;text-align:center;padding:4px 0}
.kdigo .rl{color:var(--ink-2);font-weight:600;display:flex;align-items:center;font-family:var(--mono)}
.kdigo .c{height:30px;border-radius:4px;display:grid;place-items:center;opacity:.32}
.kdigo .c.here{opacity:1;outline:2px solid var(--ink);outline-offset:2px}
.kdigo .c.here::after{content:"Now";color:#fff;font-weight:700;font-size:10.5px;letter-spacing:.05em}
.kdigo .c.prev{opacity:.75}.kdigo .c.prev::after{content:"1 yr";color:#fff;font-weight:600;font-size:10px}
/* charts */
svg.chart{width:100%;height:auto;display:block}
svg.chart text{font-family:"Plus Jakarta Sans",sans-serif;font-size:10px;fill:#86939A}
.legend{display:flex;gap:14px;font-size:11.5px;color:var(--ink-2);flex-wrap:wrap}
.legend i{display:inline-block;width:10px;height:3px;border-radius:2px;margin-right:6px;vertical-align:middle}
/* feeds, banners, treatments */
.feed-item{display:flex;gap:12px;padding:12px 18px;border-bottom:1px solid var(--line-2);align-items:flex-start}
.feed-item:last-child{border-bottom:none}
.feed-item .t{font-size:11.5px;color:var(--ink-3)}
.sev{width:8px;height:8px;border-radius:50%;margin-top:6px;flex:none}
.sev.info{background:var(--accent)}.sev.warning{background:var(--k-orange)}.sev.critical{background:var(--k-red)}
.banner{border-radius:10px;padding:12px 16px;margin-bottom:4px;font-size:13.5px;line-height:1.5}
.banner.warn{background:var(--k-orange-t);border:1px solid #F0C9A8;color:#6E3510}
.banner.danger{background:var(--k-red-t);border:1px solid #EDBDBF;color:#5E1214}
.banner.info{background:var(--accent-tint-2);border:1px solid var(--accent-tint);color:var(--accent-ink)}
[class*="st-key-txrow"]{border-bottom:1px solid var(--line-2);padding:12px 0}
[class*="st-key-txrow_on"]{background:var(--accent-tint-2)}
.tx h4{font-size:14px!important;font-weight:600!important;margin:0!important;padding:0!important}
.tx .delta{display:flex;align-items:center;gap:8px;margin-top:6px;font-size:12.5px;flex-wrap:wrap}
.tx .src{font-size:11.5px;color:var(--ink-3);margin-top:3px}
.tx .rank{font-size:20px;font-weight:700;color:var(--ink-3)}
.compare .lbl{display:flex;justify-content:space-between;font-size:12px;color:var(--ink-2);margin-bottom:5px}
.compare .track{height:26px;background:var(--line-2);border-radius:6px;overflow:hidden}
.compare .track i{display:flex;align-items:center;justify-content:flex-end;padding-right:8px;height:100%;color:#fff;font-weight:700;font-size:12px;border-radius:6px;font-style:normal}
details.exp{background:var(--paper);border:1px solid var(--line);border-radius:var(--r);box-shadow:var(--shadow);overflow:hidden}
details.exp>summary{list-style:none;cursor:pointer;padding:13px 18px;font-weight:600;font-size:13px;display:flex;justify-content:space-between;align-items:center}
details.exp>summary::-webkit-details-marker{display:none}
details.exp>summary::after{content:"+";color:var(--ink-3);font-size:18px;font-weight:400}
details.exp[open]>summary{border-bottom:1px solid var(--line-2)}
details.exp[open]>summary::after{content:"–"}
.know{border-color:#F6C9AE;background:linear-gradient(180deg,var(--brand-tint),#fff 70%)}
/* AI */
.ai-out{font-size:14px;line-height:1.65}.ai-out p{margin-bottom:10px!important}
.ai-out code,.msg code{font-family:var(--mono);font-size:12.5px;background:var(--accent-tint);color:var(--accent-ink);padding:1px 5px;border-radius:4px}
.src-chip{font-size:11px;font-family:var(--mono);color:var(--ink-2);background:var(--line-2);padding:2px 7px;border-radius:4px}
.chat{display:flex;flex-direction:column;gap:10px;max-height:420px;overflow-y:auto;padding:16px 18px}
.msg{max-width:82%;padding:10px 13px;border-radius:12px;font-size:13.5px;line-height:1.55}
.msg.me{align-self:flex-end;background:var(--accent);color:#fff;border-bottom-right-radius:4px}
.msg.bot{align-self:flex-start;background:var(--line-2);border-bottom-left-radius:4px}
.msg.bot small{display:block;margin-top:6px;font-size:10.5px;color:var(--ink-3)}
.empty{padding:28px;text-align:center;color:var(--ink-3)}
/* report preview, code */
.pdf{background:#fff;border:1px solid var(--line);box-shadow:0 20px 40px -24px rgba(0,0,0,.35);aspect-ratio:1/1.414;padding:28px 30px;font-size:10px;line-height:1.5;max-width:440px;margin:0 auto;overflow:hidden}
.pdf h5{font-weight:700;font-size:15px;letter-spacing:-.01em;margin:0}
.pdf .ln{height:6px;background:var(--line-2);border-radius:3px;margin:5px 0}
.pdf table{width:100%;border-collapse:collapse;margin:8px 0}
.pdf td,.pdf th{border-bottom:1px solid var(--line-2);padding:3px 2px;text-align:left}
.pdf .hdr{display:flex;justify-content:space-between;gap:10px;border-bottom:2px solid var(--accent);padding-bottom:8px;margin-bottom:10px}
div.code{font-family:var(--mono);font-size:11.5px;background:#0F1B22;color:#BFE3DE;padding:14px 16px;border-radius:8px;overflow:auto;max-height:420px;line-height:1.55;white-space:pre-wrap;word-break:break-word;margin:0}
div.code .k{color:#7FD1C7}div.code .s{color:#F2C979}
.conn{display:flex;align-items:center;justify-content:space-between;padding:16px 18px}
.dot-ok{width:10px;height:10px;border-radius:50%;background:var(--k-green);box-shadow:0 0 0 4px var(--k-green-t);margin-right:4px;flex:none}
.dot-bad{width:10px;height:10px;border-radius:50%;background:var(--k-red);box-shadow:0 0 0 4px var(--k-red-t);margin-right:4px;flex:none}

/* ---------- Streamlit widgets restyled ---------- */
.stButton>button,.stDownloadButton>button,[data-testid="stFormSubmitButton"]>button{border-radius:8px;font-weight:600;border:1px solid var(--line);background:var(--paper);color:var(--ink);min-height:38px}
.stButton>button:hover,.stDownloadButton>button:hover{border-color:var(--ink-3);color:var(--ink)}
.stButton>button[kind="primary"],[data-testid="stFormSubmitButton"]>button[kind="primaryFormSubmit"],.stDownloadButton>button[kind="primary"]{background:var(--accent);border-color:var(--accent);color:#fff}
.stButton>button[kind="primary"]:hover,[data-testid="stFormSubmitButton"]>button[kind="primaryFormSubmit"]:hover,.stDownloadButton>button[kind="primary"]:hover{background:var(--accent-ink);border-color:var(--accent-ink);color:#fff}
.stButton>button[kind="tertiary"]{border:none;background:transparent;color:var(--ink-2);min-height:30px}
[data-testid="stTextInputRootElement"],[data-testid="stNumberInputContainer"],[data-baseweb="select"]>div,[data-testid="stTextAreaRootElement"],[data-testid="stDateInputField"]{border-radius:8px!important;border:1px solid var(--line)!important;background:var(--paper)!important}
[data-testid="stTextInputRootElement"]:focus-within,[data-testid="stNumberInputContainer"]:focus-within,[data-testid="stTextAreaRootElement"]:focus-within{border-color:var(--accent)!important;box-shadow:0 0 0 3px var(--accent-tint)}
[data-testid="stTextInputRootElement"] *,[data-testid="stNumberInputContainer"] *,[data-testid="stTextAreaRootElement"] *{background:transparent!important}
[data-testid="stNumberInputContainer"] button{background:var(--line-2)!important}
[data-testid="stWidgetLabel"] p{font-size:12px!important;font-weight:600!important;color:var(--ink-2)!important}
[data-testid="stForm"]{background:var(--paper);border:1px solid var(--line)!important;border-radius:var(--r)!important;box-shadow:var(--shadow);padding:16px 18px}
div[data-testid="stVerticalBlockBorderWrapper"]:has(> div > [data-testid="stVerticalBlock"]){border-radius:var(--r)}
[data-testid="stVerticalBlock"]:has(> [data-testid="stElementContainer"] .card-h.top){gap:0}
[class*="st-key-box"]{background:var(--paper);border:1px solid var(--line);border-radius:var(--r);box-shadow:var(--shadow);padding:0 0 14px;gap:10px!important}
[class*="st-key-box"]>[data-testid="stElementContainer"]:not(:first-child),[class*="st-key-box"]>[data-testid="stHorizontalBlock"],[class*="st-key-box"]>[data-testid="stLayoutWrapper"]{padding:0 18px}
[class*="st-key-box"] [data-testid="stForm"],[class*="st-key-pcard"] [data-testid="stForm"],[data-testid="stExpander"] [data-testid="stForm"]{border:none!important;box-shadow:none;padding:0}
[data-testid="stExpander"] details{background:var(--paper);border:1px solid var(--line)!important;border-radius:var(--r)!important;box-shadow:var(--shadow)}
[data-testid="stExpander"] summary{font-weight:600}
[data-testid="stAlert"]{border-radius:10px}
[data-testid="stToast"]{background:var(--ink)!important;color:#fff!important;border-radius:10px!important}
[data-testid="stToast"] *{color:#fff!important}

/* radio used as navigation: sidebar menu (nav), underline tabs (tabs), pills (pills), segmented (seg) */
[class*="st-key-nav"] [role="radiogroup"] [data-testid="stRadioOption"]>div>div:not([data-testid]),[class*="st-key-tabs"] [role="radiogroup"] [data-testid="stRadioOption"]>div>div:not([data-testid]),[class*="st-key-pills"] [role="radiogroup"] [data-testid="stRadioOption"]>div>div:not([data-testid]),[class*="st-key-seg"] [role="radiogroup"] [data-testid="stRadioOption"]>div>div:not([data-testid]){display:none}
[class*="st-key-nav"] [role="radiogroup"]>div,[class*="st-key-nav"] [data-testid="stRadio"],[class*="st-key-nav"] [data-testid="stRadio"]>div,[class*="st-key-nav"] [data-testid="stRadioOption"]>div{width:100%}
[class*="st-key-nav"] [role="radiogroup"]{flex-direction:column;gap:2px;width:100%}
[class*="st-key-nav"] [role="radiogroup"] label{display:flex;width:100%;margin:0;padding:9px 10px;border-radius:8px;cursor:pointer}
[class*="st-key-nav"] [role="radiogroup"] label p{font-weight:500;color:var(--ink-2);font-size:14px}
[class*="st-key-nav"] [role="radiogroup"] label:hover{background:var(--line-2)}
[class*="st-key-nav"] [role="radiogroup"] label[data-selected="true"]{background:var(--accent-tint)}
[class*="st-key-nav"] [role="radiogroup"] label[data-selected="true"] p{color:var(--accent-ink);font-weight:600}
[class*="st-key-tabs"],[class*="st-key-pills"]{overflow-x:auto;overflow-y:hidden;max-width:100%;scrollbar-width:none}
[class*="st-key-tabs"] *,[class*="st-key-pills"] *{scrollbar-width:none}
[class*="st-key-tabs"]::-webkit-scrollbar,[class*="st-key-tabs"] *::-webkit-scrollbar,[class*="st-key-pills"]::-webkit-scrollbar,[class*="st-key-pills"] *::-webkit-scrollbar{display:none}
[class*="st-key-tabs"] [data-testid="stRadio"],[class*="st-key-tabs"] [data-testid="stRadio"]>div{width:100%;max-width:100%;min-width:0}
[class*="st-key-tabs"] [role="radiogroup"]{max-width:100%;gap:2px;border-bottom:1px solid var(--line);flex-wrap:wrap;width:100%}
[class*="st-key-tabs"] [role="radiogroup"] label{margin:0 0 -1px;padding:9px 14px;border-bottom:2px solid transparent;cursor:pointer;white-space:nowrap}
[class*="st-key-tabs"] [role="radiogroup"] label p{font-weight:600;color:var(--ink-3)}
[class*="st-key-tabs"] [role="radiogroup"] label:hover p{color:var(--ink)}
[class*="st-key-tabs"] [role="radiogroup"] label[data-selected="true"]{border-bottom-color:var(--accent)}
[class*="st-key-tabs"] [role="radiogroup"] label[data-selected="true"] p{color:var(--accent-ink)}
[class*="st-key-pills"] [data-testid="stRadio"],[class*="st-key-pills"] [data-testid="stRadio"]>div{width:100%;max-width:100%;min-width:0}
[class*="st-key-pills"] [role="radiogroup"]{max-width:100%;gap:6px;flex-wrap:nowrap;overflow-x:auto;width:100%;padding-bottom:4px;scrollbar-width:none}
[class*="st-key-pills"] [role="radiogroup"] label{margin:0;padding:6px 13px;border-radius:999px;background:var(--line-2);cursor:pointer;white-space:nowrap}
[class*="st-key-pills"] [role="radiogroup"] label p{font-size:13px;font-weight:600;color:var(--ink-2)}
[class*="st-key-pills"] [role="radiogroup"] label[data-selected="true"]{background:var(--ink)}
[class*="st-key-pills"] [role="radiogroup"] label[data-selected="true"] p{color:#fff}
[class*="st-key-seg"] [role="radiogroup"]{display:inline-flex;background:var(--line-2);border-radius:8px;padding:3px;gap:0;flex-wrap:wrap}
[class*="st-key-seg"] [role="radiogroup"] label{margin:0;padding:5px 11px;border-radius:6px;cursor:pointer}
[class*="st-key-seg"] [role="radiogroup"] label p{font-size:12px;font-weight:600;color:var(--ink-2)}
[class*="st-key-seg"] [role="radiogroup"] label[data-selected="true"]{background:var(--paper);box-shadow:0 1px 2px rgba(0,0,0,.08)}
[class*="st-key-seg"] [role="radiogroup"] label[data-selected="true"] p{color:var(--ink)}

/* sidebar shell (doctor + admin) */
[data-testid="stSidebar"]{background:var(--paper);border-right:1px solid var(--line)}
[data-testid="stSidebarUserContent"]{padding-top:.4rem}
.side-brand{display:flex;align-items:center;gap:10px;font-weight:600;font-size:14.5px;color:var(--ink);padding:0 8px 14px}
.side-brand small{display:block;font-size:10.5px;color:var(--ink-3);font-weight:500;letter-spacing:.04em}
.nav-sec{font-size:10.5px;text-transform:uppercase;letter-spacing:.12em;color:var(--ink-3);padding:10px 10px 4px;font-weight:600}
.me{display:flex;align-items:center;gap:10px;padding:12px 8px 6px;border-top:1px solid var(--line-2);margin-top:22px}
.avatar{width:32px;height:32px;border-radius:50%;background:var(--accent-tint);color:var(--accent-ink);display:grid;place-items:center;font-weight:700;font-size:12px;flex:none}
.me .who{font-size:13px;font-weight:600;line-height:1.2}.me .who small{display:block;font-weight:500;color:var(--ink-3);font-size:11.5px}
.st-key-topbar{border-bottom:1px solid var(--line);padding-bottom:10px;margin-bottom:8px}
.crumbs{display:flex;align-items:center;gap:8px;font-size:13px;color:var(--ink-3);min-height:38px}
.crumbs b{color:var(--ink);font-weight:600}
/* patient header */
.pt-head{display:flex;align-items:center;gap:20px;padding:20px 22px;flex-wrap:wrap}
.pt-head .big-av{width:56px;height:56px;border-radius:14px;background:var(--accent);color:#fff;display:grid;place-items:center;font-weight:700;font-size:24px;flex:none}
.pt-head h2{font-size:26px!important;font-weight:700!important;line-height:1.1;letter-spacing:-.02em;margin:0!important;padding:0!important}
.pt-meta{display:flex;flex-wrap:wrap;gap:6px 14px;color:var(--ink-2);font-size:12.5px;margin-top:4px}
.pt-meta span+span::before{content:"·";margin-right:14px;color:var(--ink-3)}

/* ---------- patient app ---------- */
.p-top{display:flex;align-items:center;gap:10px}
.p-top .hi{font-size:26px;font-weight:700;line-height:1.1;letter-spacing:-.02em}
.p-top .hi small{display:block;font-size:12px;color:var(--ink-3);font-weight:500;letter-spacing:0}
.glu-hero{border-radius:18px;background:var(--accent-ink);color:#fff;padding:22px;position:relative;overflow:hidden}
.glu-hero::after{content:"";position:absolute;right:-60px;top:-60px;width:220px;height:220px;border-radius:50%;background:radial-gradient(circle,rgba(235,114,48,.28),transparent 70%)}
.glu-hero .lbl{font-size:12px;color:#AFC3D9;letter-spacing:.04em}
.glu-hero .val{font-size:92px;font-weight:700;line-height:.95;margin-top:6px;display:flex;align-items:flex-end;gap:10px;letter-spacing:-.02em;font-variant-numeric:tabular-nums}
.glu-hero .val small{font-size:14px;color:#AFC3D9;margin-bottom:14px;font-weight:500;letter-spacing:0}
.glu-hero .arrow{font-size:34px;margin-bottom:10px}
.glu-hero .state{display:inline-flex;margin-top:6px;padding:4px 10px;border-radius:999px;background:rgba(255,255,255,.12);font-size:12.5px;font-weight:600}
.glu-hero .foot{display:flex;justify-content:space-between;font-size:11px;color:#AFC3D9}
.glu-hero.low{background:#8E1F22}.glu-hero.high{background:#8F4510}
.glu-hero .badge-live{color:#F4A06F}
.p-card{border:1px solid var(--line);border-radius:14px;padding:16px;background:var(--paper)}
.ph{font-size:13px;font-weight:600;color:var(--ink-2)}
.p-card h4{font-size:13px!important;font-weight:600!important;color:var(--ink-2);margin:0 0 10px!important;padding:0!important;letter-spacing:0}
[class*="st-key-pcard"]{border:1px solid var(--line);border-radius:14px;padding:16px;background:var(--paper);gap:10px!important}
[class*="st-key-pcard"].st-key-pcard_due{border-color:var(--accent);background:var(--accent-tint-2)}
.dose{display:flex;align-items:center;gap:12px}
.dose .pill{width:42px;height:42px;border-radius:12px;background:var(--accent-tint);display:grid;place-items:center;color:var(--accent);flex:none;font-size:20px}
.dose .what{flex:1}.dose .what b{display:block;font-size:14px}.dose .what span{font-size:12px;color:var(--ink-3)}
.safety{border-radius:14px;padding:16px;background:var(--k-red-t);border:1px solid #EDBDBF;color:#5E1214}
.safety b{display:block;font-size:15px;margin-bottom:4px}.safety ol{margin:8px 0 0 18px}
.ring-wrap{display:flex;align-items:center;gap:18px}
.plain-stat{display:flex;align-items:center;justify-content:space-between;padding:12px 0;border-bottom:1px solid var(--line-2)}
.plain-stat:last-child{border-bottom:none}
.plain-stat .ok{color:var(--k-green);font-weight:700}.plain-stat .no{color:var(--k-red);font-weight:700}
.pred{margin-top:4px;padding:12px 14px;border-radius:12px;background:var(--accent-tint-2);border:1px solid var(--accent-tint)}
.rd-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}
.rd{border:1px solid var(--line);border-radius:12px;padding:12px 13px;background:var(--paper);display:flex;flex-direction:column}
.rd-l{font-size:12.5px;font-weight:600;color:var(--ink-2)}
.rd-tag{font-size:10.5px;color:var(--ink-3);font-weight:600}
.rd-v{font-size:28px;font-weight:800;letter-spacing:-.025em;line-height:1.1;margin:6px 0 4px;font-variant-numeric:tabular-nums}
.rd-v small{font-size:12px;font-weight:500;color:var(--ink-3);margin-left:4px;letter-spacing:0}
.rd-s{font-size:11px;color:var(--ink-3);margin-top:auto;padding-top:8px}
/* food tiles (patient meal log) */
[class*="st-key-row_food"] .food{display:flex;justify-content:space-between;align-items:center;border:1px solid var(--line);border-radius:10px;padding:9px 11px;font-size:13px;background:var(--paper);min-height:54px}
[class*="st-key-row_food"] .food small{color:var(--ink-3);font-size:11px;display:block}
[class*="st-key-row_food"] .food.sel{border-color:var(--accent);background:var(--accent-tint-2)}
[class*="st-key-row_food"] .food .q{font-family:var(--mono);font-size:12px;color:var(--accent);font-weight:600}
[class*="st-key-row_food"]:hover .food{border-color:var(--ink-3)}
/* login */
.login-hero{background:var(--accent-ink);border-radius:18px;min-height:86vh;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;position:relative;overflow:hidden;color:#E8EEF5}
.login-hero::before{content:"";position:absolute;inset:0;background:radial-gradient(520px 420px at 50% 46%,rgba(235,114,48,.16),transparent 65%),radial-gradient(900px 600px at 50% 50%,rgba(120,170,230,.12),transparent 70%)}
.login-hero::after{content:"";position:absolute;inset:0;background-image:linear-gradient(rgba(255,255,255,.04) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,.04) 1px,transparent 1px);background-size:32px 32px;-webkit-mask-image:linear-gradient(180deg,transparent,black 40%,black 70%,transparent);mask-image:linear-gradient(180deg,transparent,black 40%,black 70%,transparent)}
.login-hero>*{position:relative;z-index:1}
.hero-logo{width:360px;max-width:62%;height:auto;overflow:visible;animation:breathe 3.2s ease-in-out 2.4s infinite}
.hero-logo .ring{stroke-dasharray:78;stroke-dashoffset:78;animation:draw 1.3s cubic-bezier(.6,0,.2,1) forwards}
.hero-logo .r1{transform-origin:15.5px 15px;transform:rotate(-90deg)}
.hero-logo .r2{transform-origin:30.5px 15px;transform:rotate(-90deg);animation-delay:.35s}
.hero-logo .pulse{stroke-dasharray:36;stroke-dashoffset:36;animation:draw 1s ease-out 1.1s forwards}
.hero-name{margin-top:34px;font-size:46px;font-weight:800;letter-spacing:-.03em;color:#fff;opacity:0;animation:fadeUp .7s ease 1.6s forwards}
.hero-line{margin-top:8px;font-size:16px;color:#9FB3CB;opacity:0;animation:fadeUp .7s ease 1.9s forwards}
@keyframes draw{to{stroke-dashoffset:0}}
@keyframes fadeUp{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}
@keyframes breathe{0%,100%{transform:scale(1)}12%{transform:scale(1.035);filter:drop-shadow(0 0 14px rgba(235,114,48,.45))}24%{transform:scale(1)}}
@media (prefers-reduced-motion:reduce){.hero-logo,.hero-logo *{animation:none!important;stroke-dashoffset:0!important}.hero-name,.hero-line{opacity:1;animation:none}}
.signin h2{font-size:32px!important;font-weight:700!important;letter-spacing:-.025em;padding:2px 0 0!important;margin:0!important}
.st-key-loginform [data-testid="stForm"]{border:none!important;box-shadow:none;padding:0;background:transparent}
.st-key-acclist{max-width:100%;overflow:hidden!important}
.acc{display:flex;align-items:center;justify-content:space-between;padding:10px 14px;border-bottom:1px solid var(--line-2);font-size:13px}
.acc .r{font-size:11px;color:var(--ink-3);text-transform:uppercase;letter-spacing:.08em}
.acc-h{padding:12px 14px;font-weight:600;font-size:13px;border-bottom:1px solid var(--line-2)}
[class*="st-key-row_acc"]:last-child .acc{border-bottom:none}
[class*="st-key-row_acc"]:hover .acc{background:var(--accent-tint-2)}
@media (max-width:1100px){.g4{grid-template-columns:repeat(2,minmax(0,1fr))}.g3{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media (max-width:760px){.g2,.g3,.g4{grid-template-columns:1fr}.block-container{padding:1rem 1rem 2rem}.login-hero{min-height:340px}.hero-name{font-size:32px}}
</style>
"""


def apply_style() -> None:
    """Inject the design (fonts, colours, components). Called once per page run from Home.py."""
    st.markdown(CSS, unsafe_allow_html=True)


def md(html_: str) -> None:
    """Show an HTML piece. Wrapped in a div with no blank lines so Markdown leaves it alone."""
    st.markdown("<div class='gr'>" + html_.replace("\n", " ") + "</div>", unsafe_allow_html=True)


def esc(x) -> str:
    return html.escape("" if x is None else str(x))


def initials(name: str) -> str:
    parts = [w for w in (name or "?").replace("Dr.", "").split() if w]
    return "".join(w[0] for w in parts[:2]).upper() or "?"


# --------------------------------------------------------------------------- small pieces

def chip(text: str, kind: str = "plain", dot: bool = False) -> str:
    """kind: green / yellow / orange / red / accent / plain / brand, or a KDIGO hex colour."""
    kind = {v: k for k, v in KDIGO_HEX.items()}.get(kind, kind)
    d = f"<span class='dot' style='background:var(--k-{kind})'></span>" if dot and kind in KDIGO_HEX else ""
    return f"<span class='chip {kind}'>{d}{text}</span>"


def kdigo_chip(stage: str | None, colour: str | None) -> str:
    if not stage:
        return chip("n/a", "plain")
    return chip(stage.replace("-", " · "), colour or "plain", dot=True)


def risk_chip(risk: float | None, band: str | None) -> str:
    if risk is None:
        return chip("n/a", "plain")
    return chip(f"{risk:.0%} {BAND_LABEL.get(band, '')}", BAND_KIND.get(band, "plain"))


def band_hex(band: str | None) -> str:
    return BAND_HEX.get(band or "", GREY)


def pct_hex(p: float) -> str:
    """Colour for a risk in percent (design riskColor)."""
    return KDIGO_HEX["green"] if p < 15 else KDIGO_HEX["yellow"] if p < 30 else KDIGO_HEX["orange"] if p < 50 \
        else KDIGO_HEX["red"]


def glucose_hex(g: float) -> str:
    return KDIGO_HEX["red"] if g < 70 else KDIGO_HEX["orange"] if g > 250 else KDIGO_HEX["yellow"] if g > 180 \
        else NAVY


def page_head(title: str, sub: str = "", eyebrow: str = "") -> None:
    md(f"<div class='page-h'>{f'<div class=eyebrow>{eyebrow}</div>' if eyebrow else ''}<h1>{title}</h1>"
       f"{f'<p>{sub}</p>' if sub else ''}</div>")


def card(title: str, body: str, right: str = "", pad: bool = True, cls: str = "", style: str = "") -> str:
    head = f"<div class='card-h'><h3>{title}</h3>{right}</div>" if title else ""
    return f"<div class='card {cls}' style='{style}'>{head}{f'<div class=card-b>{body}</div>' if pad else body}</div>"


def card_head(title: str, right: str = "") -> None:
    """Header strip for a box() container (Streamlit widgets inside a card)."""
    md(f"<div class='card-h top'><h3>{title}</h3>{right}</div>")


def box(key: str):
    """A card-looking Streamlit container; put card_head() first, then widgets."""
    return st.container(key=f"box_{key}")


def stat(label: str, value, unit: str = "", desc: str = "", colour: str | None = None, cls: str = "") -> str:
    c = f" style='color:{colour}'" if colour else ""
    return (f"<div class='card stat {cls}'><div class='eyebrow'>{label}</div><div class='v'{c}>{value}"
            f"{f'<small>{unit}</small>' if unit else ''}</div>{f'<div class=d>{desc}</div>' if desc else ''}</div>")


def risk_card(title: str, value, unit: str, colour: str, meta: str, model: str, pct: float) -> str:
    pct = max(0, min(100, pct))
    return (f"<div class='card risk'><div class='eyebrow'>{title}</div><div class='v' style='color:{colour}'>{value}"
            f"<small>{unit}</small></div><div class='bar'><i style='width:{pct:.0f}%;background:{colour}'></i></div>"
            f"<div class='meta'><span>{meta}</span><span class='mono'>{esc(model)}</span></div></div>")


def progress(pct: float, colour: str = NAVY, height: int = 8) -> str:
    return (f"<div class='progress' style='height:{height}px'><i style='width:{max(0, min(100, pct)):.0f}%;"
            f"background:{colour}'></i></div>")


def table(headers: list[str], rows: list[list[str]], empty: str = "Nothing yet") -> str:
    if not rows:
        return f"<div class='empty'>{empty}</div>"
    h = "".join(f"<th>{x}</th>" for x in headers)
    b = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f"<div class='tscroll'><table class='tbl'><thead><tr>{h}</tr></thead><tbody>{b}</tbody></table></div>"


def feed_item(sev: str, text: str, sub: str = "", right: str = "") -> str:
    return (f"<div class='feed-item'><span class='sev {sev}'></span><div style='flex:1'><div style='font-size:13px'>"
            f"{text}</div>{f'<div class=t>{sub}</div>' if sub else ''}</div>{right}</div>")


def banner(kind: str, text: str) -> str:
    return f"<div class='banner {kind}'>{text}</div>"


def legend(items: list[tuple[str, str]]) -> str:
    return "<div class='legend'>" + "".join(f"<span><i style='background:{c}'></i>{t}</span>" for t, c in items) + "</div>"


def kdigo_grid(g: str | None, a: str | None, prev_g: str | None = None, prev_a: str | None = None) -> str:
    """KDIGO heat map with the patient's cell marked 'Now' (and 1 year ago, if different)."""
    s = ("<div class='kdigo'><div></div><div class='h'>A1 &lt;30</div><div class='h'>A2 30–300</div>"
         "<div class='h'>A3 &gt;300</div>")
    for gs in G_ORDER:
        s += f"<div class='rl'>{gs}</div>"
        for i, a_s in enumerate(A_ORDER):
            here = gs == g and a_s == a
            prev = not here and gs == prev_g and a_s == prev_a
            s += (f"<div class='c{' here' if here else ''}{' prev' if prev else ''}' "
                  f"style='background:{BAND_HEX[GRID[gs][i]]}'></div>")
    return s + "</div>"


def g_stage(egfr: float | None) -> str | None:
    if egfr is None:
        return None
    return "G1" if egfr >= 90 else "G2" if egfr >= 60 else "G3a" if egfr >= 45 else "G3b" if egfr >= 30 \
        else "G4" if egfr >= 15 else "G5"


def minutes_ago(iso: str | None) -> int | None:
    if not iso:
        return None
    t = datetime.fromisoformat(str(iso).replace(" ", "T"))
    if t.tzinfo is None:  # stored as UTC
        t = t.replace(tzinfo=timezone.utc)
    return int((datetime.now(timezone.utc) - t).total_seconds() // 60)


def local(iso: str | None, fmt: str = "%d %b %H:%M") -> str:
    if not iso:
        return "–"
    return pd.to_datetime(iso, format="ISO8601", utc=True).tz_convert("Asia/Kolkata").strftime(fmt)


def when(iso: str | None) -> str:
    m = minutes_ago(iso)
    if m is None:
        return "–"
    if m < 1:
        return "just now"
    if m < 60:
        return f"{m} min ago"
    if m < 24 * 60:
        return f"{m // 60} h ago"
    return local(iso, "%d %b")


# --------------------------------------------------------------------------- SVG charts (ported from the design)

def line_chart(series: list[dict], y_min: float, y_max: float, w: int = 640, h: int = 220,
               y_ticks: list[float] = (), refs: list[tuple[float, str, str]] = (), band: tuple | None = None,
               x_labels: list[str] = (), n: int | None = None, uid: str = "c") -> str:
    """Line chart like the design's lineChart().

    series items: data (list, None allowed), color, width, dash, area, dots, end, offset, points [(i, v, colour)].
    refs: (value, label, colour) dashed reference lines.
    """
    pl, pr, pt, pb = 38, 14, 12, 24
    n = n or max((len(s["data"]) + s.get("offset", 0) for s in series), default=1)
    X = lambda i: pl + (0 if n <= 1 else i / (n - 1)) * (w - pl - pr)  # noqa: E731
    Y = lambda v: pt + (1 - (v - y_min) / ((y_max - y_min) or 1)) * (h - pt - pb)  # noqa: E731
    s = (f"<svg class='chart' viewBox='0 0 {w} {h}' preserveAspectRatio='xMidYMid meet'><defs>"
         f"<linearGradient id='ga{uid}' x1='0' y1='0' x2='0' y2='1'><stop offset='0' stop-color='#1C3C5F' "
         f"stop-opacity='.18'/><stop offset='1' stop-color='#1C3C5F' stop-opacity='0'/></linearGradient></defs>")
    if band:
        s += (f"<rect x='{pl}' y='{Y(band[1]):.1f}' width='{w - pl - pr}' height='{Y(band[0]) - Y(band[1]):.1f}' "
              f"fill='#E8EEF5' opacity='.75'/>")
    for t in y_ticks:
        s += (f"<line x1='{pl}' x2='{w - pr}' y1='{Y(t):.1f}' y2='{Y(t):.1f}' stroke='#EFEDE7'/>"
              f"<text x='{pl - 8}' y='{Y(t) + 3:.1f}' text-anchor='end'>{t:g}</text>")
    for v, label, c in refs:
        s += (f"<line x1='{pl}' x2='{w - pr}' y1='{Y(v):.1f}' y2='{Y(v):.1f}' stroke='{c}' stroke-dasharray='4 4'/>"
              f"<text x='{w - pr}' y='{Y(v) - 4:.1f}' text-anchor='end' style='fill:{c}'>{esc(label)}</text>")
    for i, label in enumerate(x_labels):
        if label:
            s += f"<text x='{X(i):.1f}' y='{h - 6}' text-anchor='middle'>{esc(label)}</text>"
    for se in series:
        off, col = se.get("offset", 0), se.get("color", NAVY)
        pts = [(X(i + off), Y(min(max(v, y_min), y_max))) for i, v in enumerate(se["data"]) if v is not None]
        if not pts:
            continue
        d = " ".join(("L" if i else "M") + f"{x:.1f} {y:.1f}" for i, (x, y) in enumerate(pts))
        if se.get("area"):
            s += f"<path d='{d} L{pts[-1][0]:.1f} {h - pb} L{pts[0][0]:.1f} {h - pb} Z' fill='url(#ga{uid})'/>"
        dash = f" stroke-dasharray='{se['dash']}'" if se.get("dash") else ""
        s += (f"<path d='{d}' fill='none' stroke='{col}' stroke-width='{se.get('width', 2)}' "
              f"stroke-linejoin='round' stroke-linecap='round'{dash}/>")
        if se.get("dots"):
            s += "".join(f"<circle cx='{x:.1f}' cy='{y:.1f}' r='3' fill='#fff' stroke='{col}' stroke-width='1.5'/>"
                         for x, y in pts)
        if se.get("end"):
            x, y = pts[-1]
            s += (f"<circle cx='{x:.1f}' cy='{y:.1f}' r='5' fill='{col}'/>"
                  f"<circle cx='{x:.1f}' cy='{y:.1f}' r='10' fill='{col}' opacity='.15'/>")
        for i, v, c in se.get("points", []):
            s += f"<circle cx='{X(i + off):.1f}' cy='{Y(v):.1f}' r='4' fill='{c}'/>"
    return s + "</svg>"


def nice_range(values: list[float], pad: float = 5, step: float = 10) -> tuple[float, float, list[float]]:
    v = [x for x in values if x is not None] or [0, 1]
    lo = math.floor((min(v) - pad) / step) * step
    hi = math.ceil((max(v) + pad) / step) * step
    ticks = [lo + i * step for i in range(int((hi - lo) / step) + 1)]
    while len(ticks) > 6:
        ticks = ticks[::2]
    return lo, hi, ticks


def time_labels(times: list[str], every: int, fmt: str = "%H:%M", last: str = "now") -> list[str]:
    out = []
    for i, t in enumerate(times):
        if i == len(times) - 1 and last:
            out.append(last)
        elif i % every == 0:
            out.append(local(t, fmt))
        else:
            out.append("")
    return out


def sparkline(values: list[float], w: int = 480, h: int = 64, colour: str = "#fff") -> str:
    v = [x for x in values if x is not None][-36:]
    if len(v) < 2:
        return ""
    lo, hi = min(v + [60]), max(v + [220])
    X = lambda i: i / (len(v) - 1) * w  # noqa: E731
    Y = lambda x: h - 4 - (x - lo) / (hi - lo) * (h - 8)  # noqa: E731
    d = " ".join(("L" if i else "M") + f"{X(i):.1f} {Y(x):.1f}" for i, x in enumerate(v))
    return (f"<svg viewBox='0 0 {w} {h}' width='100%' height='{h}' preserveAspectRatio='none' style='margin-top:14px'>"
            f"<rect x='0' y='{Y(180):.1f}' width='{w}' height='{Y(70) - Y(180):.1f}' fill='{colour}' opacity='.08'/>"
            f"<path d='{d}' fill='none' stroke='{colour}' stroke-width='2' vector-effect='non-scaling-stroke'/></svg>")


def spark2(values: list[float], colour: str, w: int = 160, h: int = 34) -> str:
    v = [x for x in values if x is not None]
    if len(v) < 2:
        return ""
    lo, hi = min(v), max(v)
    r = (hi - lo) or 1
    d = " ".join(("L" if i else "M") + f"{i / (len(v) - 1) * w:.1f} {h - 3 - (x - lo) / r * (h - 6):.1f}"
                 for i, x in enumerate(v))
    return (f"<svg viewBox='0 0 {w} {h}' width='100%' height='{h}' preserveAspectRatio='none'><path d='{d}' "
            f"fill='none' stroke='{colour}' stroke-width='1.8' vector-effect='non-scaling-stroke' "
            f"stroke-linejoin='round'/></svg>")


def ring(segs: list[tuple[float, str]], size: int = 108, stroke: int = 13, center: str = "") -> str:
    r = (size - stroke) / 2
    C = 2 * math.pi * r
    off = 0.0
    s = (f"<svg width='{size}' height='{size}' viewBox='0 0 {size} {size}'><g transform='rotate(-90 {size / 2} "
         f"{size / 2})'><circle cx='{size / 2}' cy='{size / 2}' r='{r}' fill='none' stroke='#EFEDE7' "
         f"stroke-width='{stroke}'/>")
    for v, c in segs:
        L = C * max(v, 0) / 100
        s += (f"<circle cx='{size / 2}' cy='{size / 2}' r='{r}' fill='none' stroke='{c}' stroke-width='{stroke}' "
              f"stroke-dasharray='{L:.1f} {C - L:.1f}' stroke-dashoffset='{-off:.1f}'/>")
        off += L
    return s + f"</g>{center}</svg>"


def downsample(values: list, n: int) -> list:
    if len(values) <= n:
        return list(values)
    step = len(values) / n
    return [values[int(i * step)] for i in range(n)]


# --------------------------------------------------------------------------- shell (doctor + admin)

def sidebar_shell(portal: str, nav_key: str, options: list[str], labels: dict[str, str], section: str,
                  on_change=None) -> str:
    """Sidebar: brand, menu (a radio styled as the design's nav), signed-in user and sign out.
    Returns the chosen menu item."""
    user = api_client.current_user() or {}
    name = user.get("full_name") or user.get("username", "")
    title = {"doctor": "Endocrinology", "admin": "Administrator"}.get(user.get("role"), user.get("role", ""))
    with st.sidebar:
        md(f"<div class='side-brand'>{logo(34)}<div>GlycoRenal Twin<small>{portal}</small></div></div>"
           f"<div class='nav-sec'>{section}</div>")
        with st.container(key=nav_key):
            choice = st.radio("Menu", options, format_func=lambda o: labels[o], key=nav_key + "_r",
                              label_visibility="collapsed", on_change=on_change)
        md(f"<div class='me'><div class='avatar'>{initials(name)}</div><div class='who'>{esc(name)}"
           f"<small>{esc(title)}</small></div></div>")
        if st.button("Log out", icon=":material/logout:", type="tertiary", key="logout"):
            api_client.logout()
            st.rerun()
    return choice


def topbar(crumbs: str, right=None, back=None) -> None:
    """Breadcrumbs on the left (optional back button), right(): a widget such as search on the right."""
    with st.container(key="topbar", horizontal=True, vertical_alignment="center", gap="small"):
        if back:
            st.button(back[0], icon=":material/arrow_back:", type="tertiary", on_click=back[1], key="crumb_back")
        st.markdown(f"<div class='crumbs'>{crumbs}</div>", unsafe_allow_html=True, width="stretch")
        if right:
            right()


def show_error(e: Exception) -> None:
    st.error(str(e))
