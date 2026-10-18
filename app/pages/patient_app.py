"""Patient app (Hindi / English), phone-style layout (design: glycorenal-twin-ui_3.html).

Tabs: Today, Meals, Medicines, My health, Devices, Ask my twin, Report.
Patients see their own data only, and only lifestyle suggestions (never medicine changes).
All text comes from app/i18n.py; the EN / हिं switch is at the top.
"""

from __future__ import annotations

import re

import streamlit as st

import api_client as api
import ui
from i18n import TEXT, lang, t
from ui import esc, md

user = st.session_state["user"]
pid = user["patient_id"]
PTABS = ["today", "meals", "medicines", "my_health", "devices", "ask", "report"]

# phone-width white column, no sidebar
st.markdown("<style>[data-testid='stSidebar'],[data-testid='stSidebarCollapsedControl']{display:none}"
            ".block-container{max-width:560px;background:#fff;border-left:1px solid var(--line);"
            "border-right:1px solid var(--line);min-height:100vh;flex-shrink:0;padding:18px 20px 40px}"
            "</style>", unsafe_allow_html=True)


def _set_lang() -> None:
    st.session_state["lang"] = "hi" if st.session_state["seg_lang_r"] == "हिं" else "en"


first = (user["full_name"] or "").split(" ")[0]
with st.container(horizontal=True, vertical_alignment="center", gap="small"):
    st.markdown(f"<div class='p-top'>{ui.logo(36)}<div class='hi'>{t('hello')}, {esc(first)}<small>{pid} · "
                f"{t('title')}</small></div></div>", unsafe_allow_html=True, width="stretch")
    st.session_state["seg_lang_r"] = "हिं" if lang() == "hi" else "EN"
    with st.container(key="seg_lang", width="content"):
        st.radio("Language", ["EN", "हिं"], key="seg_lang_r", horizontal=True, label_visibility="collapsed",
                 on_change=_set_lang)
    if st.button(t("signout"), icon=":material/logout:", type="tertiary", key="p_logout"):
        api.logout()
        st.rerun()

with st.container(key="pills_pt"):
    tab = st.radio("Section", PTABS, key="pills_pt_r", horizontal=True, label_visibility="collapsed",
                   format_func=lambda k: t(k))


def _trend_word(arrow: str) -> str:
    return t("rising") if any(a in arrow for a in "↑↗⇈") else t("falling") if any(a in arrow for a in "↓↘⇊")         else t("steady")


def _status(g: float) -> str:
    return t("low_sugar") if g < 70 else (t("high_sugar") if g > 180 else t("good_range"))


def _mark(dose_id: int, status: str) -> None:
    api.post(f"/doses/{dose_id}", json={"status": status})
    st.toast(t("dose_taken") if status == "taken" else t("dose_skipped"))


# ---------------- Today ----------------

def today() -> None:
    @st.fragment(run_every=5)
    def live():
        try:
            _today()
        except Exception as e:  # noqa: BLE001
            st.error(str(e))

    live()


def _today() -> None:
    tw = api.get(f"/patients/{pid}/twin")
    rem = api.get(f"/patients/{pid}/reminders")
    s = tw["state"]
    latest = s["cgm"].get("latest")
    sp = tw["predictions"].get("spike_90m")
    if latest:
        g = latest["value"]
        if g < 70:
            md(f"<div class='safety'><b>⚠ {t('safety_title')} ({g:.0f} mg/dL)</b><ol><li>{t('safety1')}</li>"
               f"<li>{t('safety2')}</li><li>{t('safety3')}</li></ol></div>")
        elif sp and sp.get("spike_likely") and (ui.minutes_ago(sp["created_at"]) or 99) <= 10:
            md(ui.banner("warn", "<b>⚠ " + t("spike_warning").format(line=f"{sp['spike_above']:.0f}",
                                                                    p=f"{sp['probability']:.0%}") + "</b>"))
        recent = api.get(f"/patients/{pid}/observations", variable="glucose", device="cgm", hours=3)
        cls = "low" if g < 70 else ("high" if g > 250 else "")
        live = "<span class='badge-live'>LIVE</span>" if (ui.minutes_ago(latest["time"]) or 99) < 15 else ""
        md(f"<div class='glu-hero {cls}'><div class='row between'><span class='lbl'>{t('sugar_now')}</span>{live}</div>"
           f"<div class='val'>{g:.0f}<span class='arrow'>{latest['arrow']}</span><small>mg/dL</small></div>"
           f"<span class='state'>{_status(g)} · {_trend_word(latest['arrow'])}</span>"
           f"{ui.sparkline([r['value'] for r in recent])}"
           f"<div class='foot'><span>{t('last_3h')}</span><span>70 – 180</span></div></div>")
        fc = tw["predictions"].get("glucose_30m")
        if fc and fc.get("plus_30") is not None:
            st.caption(f"{t('forecast')}: ~{fc['plus_30']} mg/dL")
    else:
        md(f"<div class='p-card'><div class='empty'>{t('no_cgm')}</div></div>")

    due = rem["due_now"]
    nxt = due[0] if due else rem["next"]
    with st.container(key="pcard_due" if due else "pcard_next"):
        md(f"<div class='ph'>{t('next_dose')}</div>")
        if nxt:
            c = st.columns([5, 1.4, 1.6] if due else [1], vertical_alignment="center")
            c[0].markdown(f"<div class='dose'><div class='pill'>💊</div><div class='what'><b>{esc(nxt['drug'])} "
                          f"{esc(nxt['dose'])}</b><span>{nxt['local_time']}"
                          f"{' · ' + t('with_food') if nxt['with_food'] else ''}"
                          f"{' · <b style=color:var(--accent)>' + t('due_now') + '</b>' if due else ''}</span></div></div>",
                          unsafe_allow_html=True)
            if due:
                c[1].button(t("skip"), key=f"skip_{nxt['id']}", on_click=_mark, args=(nxt["id"], "skipped"),
                            width="stretch")
                c[2].button(f"{t('taken')} ✓", key=f"take_{nxt['id']}", type="primary", on_click=_mark,
                            args=(nxt["id"], "taken"), width="stretch")
        else:
            md(f"<div class='row'>{ui.chip('✓', 'green')}{t('all_done')}</div>")

    m = s["cgm"].get("metrics") or {}
    tir = m.get("tir_pct")
    if tir is not None:
        tbr, tar = m.get("tbr_pct") or 0, m.get("tar_pct") or 0
        center = (f"<text x='54' y='60' text-anchor='middle' font-family='Plus Jakarta Sans' font-weight='700' "
                  f"font-size='24' fill='#13212A'>{tir:.0f}%</text>")
        md(f"<div class='p-card'><h4>{t('in_range')}</h4><div class='ring-wrap'>"
           + ui.ring([(tbr, ui.KDIGO_HEX["red"]), (tir, ui.NAVY), (tar, ui.KDIGO_HEX["yellow"])], 108, 13, center)
           + f"<div><p style='font-size:14px'>{t('tir_text').format(v=f'{tir:.0f}')}</p>"
           + ui.legend([("70–180", ui.NAVY), ("&gt;180", ui.KDIGO_HEX["yellow"]), ("&lt;70", ui.KDIGO_HEX["red"])])
           + "</div></div></div>")

    # toasts: new alerts and medicines that just became due
    seen = st.session_state.setdefault("seen", set())
    for a in tw["alerts"]:
        key = f"a{a['id']}"
        if key not in seen:
            if st.session_state.get("toasts_ready"):
                st.toast(f"{ui.SEVERITY_ICON[a['severity']]} {t('new_alert')}: {a['message']}")
            seen.add(key)
    for d in due:
        key = f"d{d['id']}"
        if key not in seen:
            if st.session_state.get("toasts_ready"):
                st.toast(f"💊 {t('medicine_due_toast')}: {d['drug']} {d['dose']}")
            seen.add(key)
    st.session_state["toasts_ready"] = True


# ---------------- Medicines ----------------

def medicines() -> None:
    rem = api.get(f"/patients/{pid}/reminders")
    a7, a30 = rem["adherence_7d"]["pct"], rem["adherence_30d"]["pct"]
    c7 = ui.KDIGO_HEX["red"] if a7 is not None and a7 < 80 else ui.NAVY
    md("<div class='grid g2' style='gap:10px'>"
       f"<div class='p-card'><h4>{t('adherence')} · {t('last_7')}</h4><div class='big-n' style='font-size:38px;"
       f"color:{c7}'>{f'{a7:.0f}%' if a7 is not None else '–'}</div></div>"
       f"<div class='p-card'><h4>{t('last_30')}</h4><div class='big-n' style='font-size:38px'>"
       f"{f'{a30:.0f}%' if a30 is not None else '–'}</div></div></div>")
    with st.container(key="pcard_doses"):
        md(f"<div class='ph'>{t('todays_doses')}</div>")
        if not rem["today"]:
            md(f"<div class='faint'>{t('no_dose')}</div>")
        for d in rem["today"]:
            pending = d["status"] in ("pending", "missed")
            c = st.columns([5, 1.3, 1.4] if pending else [5, 1.6], vertical_alignment="center")
            c[0].markdown(f"<div class='dose'><div class='pill'>💊</div><div class='what'><b>{esc(d['drug'])} "
                          f"{esc(d['dose'])}</b><span>{d['local_time']}"
                          f"{' · ' + t('with_food') if d['with_food'] else ''}</span></div></div>",
                          unsafe_allow_html=True)
            if pending:
                c[1].button(t("skip"), key=f"ms_{d['id']}", on_click=_mark, args=(d["id"], "skipped"), width="stretch")
                c[2].button(t("taken"), key=f"mt_{d['id']}", type="primary", on_click=_mark, args=(d["id"], "taken"),
                            width="stretch")
            else:
                c[1].markdown(ui.chip(t("status_" + d["status"]), {"taken": "green", "missed": "red"}.get(
                    d["status"], "plain")), unsafe_allow_html=True)
    st.caption(t("med_note"))


# ---------------- Meals ----------------

def _add_food(name: str) -> None:
    sel = st.session_state.setdefault("meal_sel", {})
    sel[name] = sel.get(name, 0) + 1
    st.session_state.pop("meal_pred", None)


def _clear_meal() -> None:
    st.session_state["meal_sel"] = {}
    st.session_state.pop("meal_pred", None)


def meals() -> None:
    foods = api.cached_get("/foods")
    info = {f["food"]: f for f in foods}
    name_of = {f["food"]: (f["food_hi"] if lang() == "hi" else f["food"]) for f in foods}
    sel: dict = st.session_state.setdefault("meal_sel", {})
    with st.container(key="pcard_meal"):
        md(f"<div class='ph'>{t('log_meal')}</div>"
           f"<p class='faint' style='font-size:12px;margin:2px 0 0'>{t('tap_food')}</p>")
        q = st.text_input(t("search_food"), placeholder=t("search_food"), key="food_q", label_visibility="collapsed",
                          icon=":material/search:").strip().lower()
        shown = [f for f in foods if not q or q in f["food"].lower() or q in (f["food_hi"] or "")][:12]
        for i in range(0, len(shown), 2):
            c = st.columns(2, gap="small")
            for j, f in enumerate(shown[i:i + 2]):
                n = sel.get(f["food"], 0)
                with c[j], st.container(key=f"row_food_{i + j}"):
                    md(f"<div class='food{' sel' if n else ''}'><span>{esc(name_of[f['food']])}<small>"
                       f"{esc(f['serving'])} · {f['carbs_g']:.0f} g</small></span>{f'<span class=q>×{n}</span>' if n else ''}"
                       "</div>")
                    st.button("+", key=f"addf_{f['food']}", on_click=_add_food, args=(f["food"],))
        total = sum(info[f]["carbs_g"] * n for f, n in sel.items())
        picked = ", ".join(f"{name_of[f]}{f' ×{n}' if n > 1 else ''}" for f, n in sel.items())
        c = st.columns([2.2, .8, 1.6, 1.4], vertical_alignment="center")
        c[0].markdown(f"<span class='faint' style='font-size:12px'>{t('total_carbs')}</span><div class='big-n' "
                      f"style='font-size:28px'>{total:.0f} g</div><div class='faint' style='font-size:12px'>"
                      f"{esc(picked)}</div>", unsafe_allow_html=True)
        if sel:
            c[1].button("✕", key="meal_clear", type="tertiary", on_click=_clear_meal, help=t("clear"))
        if c[2].button(t("see_pred"), disabled=not sel, width="stretch"):
            try:
                st.session_state["meal_pred"] = api.ask(
                    f"/patients/{pid}/twin/personal/what-if",
                    json={"items": [{"food": f, "servings": n} for f, n in sel.items()], "walk_minutes": 0})
            except api.APIError as e:
                ui.show_error(e)
        if c[3].button(t("save_meal"), type="primary", disabled=not sel, width="stretch"):
            try:
                api.post(f"/patients/{pid}/meals", json={"items": [{"food": f, "servings": n} for f, n in sel.items()]})
                st.toast(t("meal_saved"))
                _clear_meal()
                st.rerun()
            except api.APIError as e:
                ui.show_error(e)
        w = st.session_state.get("meal_pred")
        if w:
            if w.get("available"):
                sm = w["summary"]
                pk = sm["peak"]
                col = ui.KDIGO_HEX["red"] if pk > 250 else ui.KDIGO_HEX["orange"] if pk > 180 else ui.KDIGO_HEX["green"]
                md(f"<div class='pred'><div class='row between'><span>{t('pred_peak')}</span><b class='big-n' "
                   f"style='font-size:22px;color:{col}'>{pk:.0f} mg/dL</b></div><div class='row between faint' "
                   f"style='font-size:12px'><span>{t('at')} {sm['peak_time']}</span><span>{sm['minutes_above_180']} "
                   f"{t('minutes_above_180')}</span></div>"
                   + (f"<p style='font-size:12.5px;margin-top:8px'>{t('pred_tip')}</p>" if pk > 180 else "") + "</div>")
            else:
                st.info(w.get("reason"))
    top = api.cached_get(f"/patients/{pid}/meals/top-foods")
    rows = ""
    for i, f in enumerate(top, 1):
        rise = ui.chip("+%.0f mg/dL %s" % (f["avg_spike"], t("avg_rise")), "red" if f["avg_spike"] > 90 else "orange")
        rows += (f"<div class='row between' style='padding:8px 0;border-bottom:1px solid var(--line-2)'><span>"
                 f"<b style='margin-right:8px'>{i}</b>{esc(f['food_hi'] if lang() == 'hi' else f['food'])}</span>"
                 f"{rise}</div>")
    rows = rows or f"<div class='faint'>{t('no_meals')}</div>"
    recent = api.get(f"/patients/{pid}/meals", days=3)
    rec = "".join(f"<div class='row between' style='padding:7px 0;font-size:13px'><span><span class='faint'>"
                  f"{ui.local(m['time'])}</span> · {esc(', '.join(name_of.get(i['food'], i['food']) for i in m['items']))}"
                  f"</span><span class='num' style='white-space:nowrap'>{m['total_carbs_g']:.0f} g · "
                  f"{'+%.0f' % m['spike'] if m['spike'] is not None else '…'}</span></div>" for m in recent[:5])
    md(f"<div class='p-card'><h4>{t('top_foods')}</h4>{rows}</div><div style='height:12px'></div>"
       f"<div class='p-card'><h4>{t('recent_meals')}</h4>{rec or '–'}</div>")


# ---------------- My health ----------------

def my_health() -> None:
    tw = api.cached_get(f"/patients/{pid}/twin")
    s = tw["state"]
    k, g, v = s["kidney"], s["glycaemia"], s["vitals"]
    rows = []
    if g.get("hba1c") is not None:
        rows.append((t("hba1c_label"), f"{g['hba1c']}%", f"&lt; {g['target']}%", g["hba1c"] < g["target"]))
    if k.get("egfr") is not None:
        rows.append((t("kidney_filter"), f"{k['egfr']:.0f}", "≥ 90", k["egfr"] >= 90))
    if k.get("uacr") is not None:
        rows.append((t("urine_protein"), f"{k['uacr']:.0f} mg/g", "&lt; 30", k["uacr"] < 30))
    if v.get("sbp"):
        rows.append((t("bp"), f"{v['sbp']:.0f}/{v['dbp']:.0f}", f"&lt; {s['bp']['target']}", s["bp"]["on_target"]))
    goals = "".join(f"<div class='plain-stat'><div><div style='font-size:14px'>{a}</div><div class='faint' "
                    f"style='font-size:12px'>{t('goal')}: {c}</div></div><div class='row'><b class='big-n' "
                    f"style='font-size:22px'>{b}</b><span class='{'ok' if ok else 'no'}'>{'✓' if ok else '✗'}</span>"
                    "</div></div>" for a, b, c, ok in rows)
    colour = k.get("colour") or "green"
    html_ = (f"<div class='p-card'><h4>{t('numbers_vs_goals')}</h4>{goals}</div>"
             f"<div class='p-card' style='background:var(--accent-tint-2);border-color:transparent;margin-top:12px'>"
             f"<p style='font-size:14px'>{t('kidney_' + colour)}</p></div>")
    try:
        ptw = api.cached_get(f"/patients/{pid}/twin/personal")
        sc = ptw["maturity"]["score"]
        days = round((ptw.get("glucose") or {}).get("days_of_cgm") or 0)
        learnt = ""
        ex = (ptw.get("glucose") or {}).get("explain")
        if ex:
            learnt = ("<div style='margin-top:10px;font-size:13px'>• " + t("per_10g").format(x=ex["per_10g_carbs"])
                      + "<br>• " + t("peaks_after").format(x=ex["peak_minutes"])
                      + (("<br>• " + t("walk_lowers").format(x=ex["walk_15_min_lowers_by"]))
                         if ex["walk_15_min_lowers_by"] > 0 else "") + "</div>")
        html_ += (f"<div class='p-card' style='margin-top:12px'><h4>{t('twin_knows_you')}</h4><div class='row' "
                  f"style='gap:14px'><div class='big-n' style='font-size:34px;color:var(--brand)'>{sc}%</div>"
                  f"<div style='flex:1'>{ui.progress(sc, ui.ORANGE)}<p class='faint' style='font-size:12.5px;"
                  f"margin-top:6px'>{t('knows_text').format(v=days)}</p></div></div>{learnt}</div>")
    except api.APIError:
        pass
    a1 = s["history"].get("hba1c") or []
    if a1:
        vals = [x["value"] for x in a1]
        lo, hi, ticks = ui.nice_range(vals + [6, g.get("target", 7)], 0.3, 1)
        chart = ui.line_chart([{"data": vals, "dots": True, "area": True}], lo, hi, w=480, h=170, y_ticks=ticks,
                              band=(lo, g.get("target", 7)),
                              x_labels=[ui.local(x["time"], "%b %y") if i in (0, len(a1) - 1) else ""
                                        for i, x in enumerate(a1)], uid="pa")
        html_ += f"<div class='p-card' style='margin-top:12px'><h4>{t('hba1c_trend')}</h4>{chart}</div>"
    levers = []
    try:
        tr = api.cached_get(f"/patients/{pid}/treatments")
        if tr.get("available"):
            for o in tr["options"]:
                label = t(f"opt_{o['option']}") if f"opt_{o['option']}" in TEXT else o["label"]
                levers.append((label, f"{t('kidney_risk')} {o['risk_before']:.0%} → {o['risk_after']:.0%}"))
    except api.APIError:
        pass
    levers.append((t("lev_meds"), t("helps")))
    html_ += (f"<div class='p-card' style='margin-top:12px'><h4>{t('what_helps')}</h4>"
              + "".join(f"<div class='row' style='padding:8px 0;border-bottom:1px solid var(--line-2)'>"
                        f"{ui.chip('↓', 'accent')}<div><div style='font-size:14px'>{esc(a)}</div><div class='faint' "
                        f"style='font-size:11.5px'>{esc(b)}</div></div></div>" for a, b in levers) + "</div>")
    md(html_)


# ---------------- Devices ----------------

def _tile(label: str, val: str, unit: str, src: str, tag: str, live: bool, extra: str = "") -> str:
    tg = f"<span class='badge-live' style='font-size:10px'>{tag}</span>" if live else tag
    return (f"<div class='rd'><div class='row between'><span class='rd-l'>{label}</span><span class='rd-tag'>{tg}"
            f"</span></div><div class='rd-v'>{val}<small>{unit}</small></div>{extra}<div class='rd-s'>{src}</div></div>")


@st.fragment(run_every=5)
def readings(running: bool) -> None:
    tw = api.get(f"/patients/{pid}/twin")
    s, v = tw["state"], tw["state"]["vitals"]
    latest = s["cgm"].get("latest")
    glu = api.get(f"/patients/{pid}/observations", variable="glucose", device="cgm", hours=3)
    hr = api.get(f"/patients/{pid}/observations", variable="heart_rate", hours=3)
    tag = t("live_tag") if running else t("paused")
    tiles = ""
    if latest:
        g = latest["value"]
        tiles += _tile(t("glucose"), f"<span style='color:{ui.glucose_hex(g)}'>{g:.0f}</span> "
                       f"<span style='font-size:20px;font-weight:600'>{latest['arrow']}</span>", "mg/dL",
                       f"{t('dev_cgm')} · {esc(latest.get('source') or '')}", tag, running,
                       ui.spark2([r["value"] for r in glu[-36:]], ui.NAVY))
    if hr:
        tiles += _tile(t("heart_rate"), f"{hr[-1]['value']:.0f}", "bpm", t("dev_watch"), tag, running,
                       ui.spark2([r["value"] for r in hr[-36:]], ui.KDIGO_HEX["red"]))
    if v.get("steps_per_day"):
        tiles += _tile(t("steps"), f"{v['steps_per_day']:,}", "", t("dev_watch"), t("synced"), False,
                       f"<div style='margin:8px 0 4px'>{ui.progress(v['steps_per_day'] / 70)}</div>"
                       f"<div class='faint' style='font-size:11px'>{t('goal_steps')}</div>")
    if v.get("sbp"):
        ok = s["bp"]["on_target"]
        tiles += _tile(t("bp"), f"{v['sbp']:.0f}/{v['dbp']:.0f}", "mmHg", t("dev_cuff"), t("synced"), False,
                       f"<div style='margin-top:6px'>{ui.chip((t('in_target') if ok else t('above_target')) + ' · &lt; ' + s['bp']['target'], 'green' if ok else 'orange')}</div>")
    if v.get("weight"):
        tiles += _tile(t("weight_l"), f"{v['weight']:.1f}", "kg", t("dev_scale"), t("synced"), False,
                       f"<div class='faint' style='font-size:12px;margin-top:6px'>BMI {v.get('bmi') or '–'}</div>")
    if v.get("sleep"):
        tiles += _tile(t("sleep_l"), f"{v['sleep']:.1f}", "h", t("dev_watch"), t("synced"), False)
    md(f"<div class='rd-grid'>{tiles}</div>" if tiles else f"<div class='faint'>{t('no_cgm')}</div>")


def devices() -> None:
    dev = api.get(f"/patients/{pid}/devices")
    running = dev["simulator"]["running"]
    with st.container(key="pcard_dev"):
        c = st.columns([4, 1.2], vertical_alignment="center")
        c[0].markdown(f"<div class='ph'>{t('live_readings')}</div>"
                      f"<div class='faint' style='font-size:12px;margin-top:2px'>{t('auto_note')}</div>",
                      unsafe_allow_html=True)
        if running:
            if c[1].button(t("stop"), key="dev_stop", width="stretch"):
                api.post(f"/patients/{pid}/devices/simulator/stop")
                st.rerun()
        elif c[1].button(t("start"), key="dev_start", type="primary", width="stretch"):
            api.post(f"/patients/{pid}/devices/simulator/start", json={})
            st.rerun()

        readings(running)
    with st.container(key="pcard_libre"):
        md(f"<b>{t('libre')}</b><div class='faint' style='font-size:12px'>LibreView export · mg/dL or mmol/L</div>")
        f = st.file_uploader("LibreView CSV", type=["csv"], label_visibility="collapsed")
        if f and st.button(t("upload"), type="primary"):
            try:
                r = api.upload(f"/patients/{pid}/devices/libre", f.name, f.getvalue())
                st.success(f"{t('saved')}: {r['saved']} ({r['unit']})")
            except api.APIError as e:
                ui.show_error(e)
    with st.container(key="pcard_dexcom", horizontal=True, vertical_alignment="center"):
        st.markdown(f"<b>{t('dexcom')}</b><div class='faint' style='font-size:12px'>OAuth</div>",
                    unsafe_allow_html=True, width="stretch")
        st.button(t("coming_soon"), disabled=True, key="dexcom_btn")
    with st.expander(t("enter_readings")):
        with st.form("vitals", clear_on_submit=True, border=False):
            c = st.columns(2)
            sbp = c[0].number_input(t("systolic"), 0, 260, 0)
            dbp = c[1].number_input(t("diastolic"), 0, 160, 0)
            c = st.columns(3)
            wt = c[0].number_input(t("weight"), 0.0, 250.0, 0.0, 0.1)
            gl = c[1].number_input(t("finger_glucose"), 0, 600, 0)
            sl = c[2].number_input(t("sleep"), 0.0, 16.0, 0.0, 0.5)
            if st.form_submit_button(t("save"), type="primary"):
                body = {"systolic": sbp or None, "diastolic": dbp or None, "weight_kg": wt or None,
                        "glucose_mg_dl": gl or None, "sleep_hours": sl or None}
                try:
                    r = api.post(f"/patients/{pid}/vitals", json=body)
                    st.toast(t("saved"))
                    for a in r["new_alerts"]:
                        st.warning(a)
                except api.APIError as e:
                    ui.show_error(e)


# ---------------- Ask my twin ----------------

def _bubble(text: str) -> str:
    s = esc(text)
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    return s.replace("\n", "<br>")


def _ask(q: str) -> None:
    chat = st.session_state.setdefault("p_chat", [])
    chat.append(("user", q))
    try:
        r = api.post(f"/patients/{pid}/assistant", json={"mode": "chat_patient", "language": lang(), "question": q})
        chat.append(("assistant", r["text"], t("offline") if r["offline"] else ""))
    except api.APIError as e:
        chat.append(("assistant", str(e), ""))


def _quick() -> None:
    q = st.session_state.get("p_quick")
    if q:
        _ask(q)
    st.session_state["p_quick"] = None


def ask() -> None:
    if st.button(t("summary_btn"), icon=":material/auto_awesome:", type="primary", width="stretch"):
        with st.spinner(t("thinking")):
            st.session_state["p_sum"] = api.post(f"/patients/{pid}/assistant",
                                                 json={"mode": "patient_summary", "language": lang()})
    res = st.session_state.get("p_sum")
    if res:
        with st.container(key="pcard_sum"):
            if res["offline"]:
                md(ui.chip(t("offline"), "orange"))
            st.markdown(res["text"])
    with st.container(key="pcard_chat"):
        chat = st.session_state.get("p_chat", [])
        msgs = "".join(f"<div class='msg me'>{esc(m[1])}</div>" if m[0] == "user" else
                       f"<div class='msg bot'>{_bubble(m[1])}{f'<small>{esc(m[2])}</small>' if m[2] else ''}</div>"
                       for m in chat)
        md("<div class='chat' style='min-height:240px;padding:4px 0'>"
           + (msgs or f"<div class='empty' style='padding:30px 10px'>{t('ask_empty')}</div>") + "</div>")
        st.pills("Suggestions", [t("q1"), t("q2"), t("q3")], key="p_quick", label_visibility="collapsed",
                 on_change=_quick)
        with st.form("p_chatf", clear_on_submit=True, border=False):
            c = st.columns([4, 1], vertical_alignment="bottom")
            q = c[0].text_input(t("your_question"), placeholder=t("your_question"), label_visibility="collapsed")
            sent = c[1].form_submit_button(t("send"), type="primary", width="stretch")
        if sent and q.strip():
            with st.spinner(t("thinking")):
                _ask(q.strip())
            st.rerun()


# ---------------- Report ----------------

def report() -> None:
    tw = api.cached_get(f"/patients/{pid}/twin")
    s = tw["state"]
    k, g, v = s["kidney"], s["glycaemia"], s["vitals"]
    tir = (s["cgm"].get("metrics") or {}).get("tir_pct")
    en = {key: TEXT[key][0] for key in TEXT}
    hi = {key: TEXT[key][1] for key in TEXT}

    def row(key, val, ok):
        return (f"<tr><td>{en[key]}<br><span style='color:#86939A'>{hi[key]}</span></td><td><b>{val}</b></td>"
                f"<td style='color:{'var(--k-green)' if ok else 'var(--k-red)'};font-weight:700'>{'✓' if ok else '✗'}"
                "</td></tr>")
    rows = ""
    if g.get("hba1c") is not None:
        rows += row("hba1c_label", f"{g['hba1c']}%", g["hba1c"] < g["target"])
    if k.get("egfr") is not None:
        rows += row("kidney_filter", f"{k['egfr']:.0f}", k["egfr"] >= 90)
    if v.get("sbp"):
        rows += row("bp", f"{v['sbp']:.0f}/{v['dbp']:.0f}", s["bp"]["on_target"])
    if tir is not None:
        rows += row("in_range", f"{tir:.0f}%", tir > 70)
    meds = "<br>".join(f"{esc(m['drug'])} {esc(m['dose'])} — {', '.join(m['times'])}" for m in s["medications"]) or "—"
    md(f"<div><h3 class='big-n' style='font-size:22px;margin:4px 0 0'>{t('report_title')}</h3><p class='muted'>"
       f"{t('report_text')}</p></div><div style='height:12px'></div>"
       f"<div class='pdf' style='max-width:100%'><div class='hdr'><div><h5>My twin report · मेरी ट्विन रिपोर्ट</h5>"
       f"<div class='faint'>{pid}</div></div>{ui.logo(30)}</div><table>{rows}</table>"
       f"<b>{en['medicines']} · {hi['medicines']}</b><div>{meds}</div>"
       f"<b style='display:block;margin-top:6px'>{en['what_helps']} · {hi['what_helps']}</b><div>"
       f"1. {en['lev_steps']} · {hi['lev_steps']}<br>2. {en['lev_bp']} · {hi['lev_bp']}<br>3. {en['lev_meds']} · "
       f"{hi['lev_meds']}</div><b style='display:block;margin-top:6px'>{en['call_doctor']} · {hi['call_doctor']}</b>"
       f"<div>• {en['call1']} · {hi['call1']}<br>• {en['call2']} · {hi['call2']}<br>• {en['call3']} · "
       f"{hi['call3']}</div></div><div style='height:12px'></div>")
    if st.session_state.get("my_pdf"):
        st.download_button(t("download"), st.session_state["my_pdf"], f"{pid}_my_health.pdf", "application/pdf",
                           type="primary", icon=":material/download:", width="stretch")
    elif st.button(t("report_btn"), type="primary", width="stretch"):
        with st.spinner(t("thinking")):
            try:
                st.session_state["my_pdf"] = api.get_bytes(f"/patients/{pid}/report/patient.pdf")
                st.rerun()
            except api.APIError as e:
                ui.show_error(e)


try:
    {"today": today, "meals": meals, "medicines": medicines, "my_health": my_health, "devices": devices,
     "ask": ask, "report": report}[tab]()
except api.APIError as e:
    ui.show_error(e)
