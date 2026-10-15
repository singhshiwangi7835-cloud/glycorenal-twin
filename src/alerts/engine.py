"""Alert engine: hypo/hyper from CGM, rising UACR, falling eGFR, stale data."""

from __future__ import annotations


def _alert(level: str, code: str, message: str) -> dict:
    return {"level": level, "code": code, "message": message}


def check(state: dict, prediction: dict | None = None) -> list[dict]:
    alerts = []
    cgm = state.get("cgm")
    d = state["derived"]
    labs = state["labs"]

    if cgm:
        if cgm["min"] < 54:
            alerts.append(_alert("critical", "HYPO_SEVERE",
                                 f"Glucose fell to {cgm['min']:.0f} mg/dL (< 54)"))
        elif cgm["tbr_pct"] >= 4:
            alerts.append(_alert("warning", "HYPO_TIME",
                                 f"Time below range {cgm['tbr_pct']}% (target < 4%)"))
        if cgm["max"] > 300:
            alerts.append(_alert("warning", "HYPER_SEVERE",
                                 f"Glucose reached {cgm['max']:.0f} mg/dL (> 300)"))
        if cgm["tir_pct"] < 50:
            alerts.append(_alert("warning", "LOW_TIR",
                                 f"Time in range {cgm['tir_pct']}% (target > 70%)"))

    if labs["uacr"] > 300:
        alerts.append(_alert("warning", "UACR_A3", f"UACR {labs['uacr']} mg/g: severely increased"))
    elif labs["uacr"] >= 30:
        alerts.append(_alert("info", "UACR_A2", f"UACR {labs['uacr']} mg/g: moderately increased"))

    slope = d.get("egfr_slope_per_year")
    if slope is not None and slope <= -5:
        alerts.append(_alert("warning", "EGFR_FAST_DECLINE",
                             f"eGFR falling {abs(slope)} mL/min/yr (rapid decline >= 5)"))
    if d["egfr"] < 30:
        alerts.append(_alert("critical", "EGFR_LOW", f"eGFR {d['egfr']}: refer to nephrology"))

    k = labs.get("potassium")
    if k is not None and k > 5.5:
        alerts.append(_alert("critical", "HYPERKALAEMIA", f"Potassium {k} mmol/L"))

    for flag in d.get("freshness_flags", []):
        alerts.append(_alert("info", "STALE_DATA", flag))

    if prediction and prediction["dkd_risk_band"] in ("high", "very_high"):
        alerts.append(_alert("warning", "HIGH_DKD_RISK",
                             f"Predicted 3-year DKD risk {prediction['dkd_risk_3y']:.0%}"))
    order = {"critical": 0, "warning": 1, "info": 2}
    return sorted(alerts, key=lambda a: order[a["level"]])
