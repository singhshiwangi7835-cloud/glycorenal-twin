"""Alert engine (CLAUDE.md section 9). Thresholds live in config/alerts.yaml.

Two kinds of checks:
  check_observation()  instant, on every new reading (low/high glucose, potassium, BP)
  check_state()        on the twin state + predictions (predicted hypo, UACR category rise,
                       eGFR drop > 25% in 12 months, adherence < 80%, stale CGM)
`raise_alert()` stores an Alert unless the same type was raised for the same patient within
`dedupe_minutes` (default 60), so a run of low readings gives one alert, not twelve.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlmodel import Session, select

from src.clinical import loinc
from src.clinical.rules import alert_rules
from src.db.models import Alert, Observation

SEVERITY_ORDER = {"critical": 0, "warning": 1, "info": 2}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def raise_alert(session: Session, patient_id: str, type_: str, severity: str, message: str,
                at: datetime | None = None) -> Alert | None:
    """Create an alert unless the same type fired for this patient within the de-dup window."""
    at = at or _now()
    window = timedelta(minutes=alert_rules()["dedupe_minutes"])
    recent = session.exec(
        select(Alert).where(Alert.patient_id == patient_id, Alert.type == type_,
                            Alert.created_at > at - window, Alert.created_at <= at + window)
    ).first()
    if recent:
        return None
    alert = Alert(patient_id=patient_id, type=type_, severity=severity, message=message,
                  created_at=at)
    session.add(alert)
    return alert


def check_observation(obs: Observation) -> list[tuple[str, str, str]]:
    """Instant checks on one new reading. Returns (type, severity, message) tuples."""
    r = alert_rules()
    var = loinc.variable_for(obs.loinc_code)
    v = obs.value
    out = []
    if var == "glucose":
        g = r["glucose"]
        if v < g["low_critical_below"]:
            out.append(("glucose_very_low", "critical",
                        f"Glucose {v:.0f} mg/dL (below {g['low_critical_below']}): severe hypoglycaemia"))
        elif v < g["low_warning_below"]:
            out.append(("glucose_low", "warning",
                        f"Glucose {v:.0f} mg/dL (below {g['low_warning_below']}): hypoglycaemia"))
        elif v > g["high_warning_above"]:
            out.append(("glucose_high", "warning",
                        f"Glucose {v:.0f} mg/dL (above {g['high_warning_above']})"))
    elif var == "potassium" and v > r["kidney"]["potassium_critical_above"]:
        out.append(("potassium_high", "critical",
                    f"Potassium {v:.1f} mmol/L (above {r['kidney']['potassium_critical_above']}): "
                    "review ACEi/ARB, finerenone"))
    elif var == "sbp" and v > r["blood_pressure"]["systolic_warning_above"]:
        out.append(("bp_high", "warning", f"Systolic BP {v:.0f} mmHg (above "
                                          f"{r['blood_pressure']['systolic_warning_above']})"))
    elif var == "dbp" and v > r["blood_pressure"]["diastolic_warning_above"]:
        out.append(("bp_high", "warning", f"Diastolic BP {v:.0f} mmHg (above "
                                          f"{r['blood_pressure']['diastolic_warning_above']})"))
    return out


def check_state(state: dict, glucose_forecast: dict | None = None) -> list[tuple[str, str, str]]:
    """Checks that need history or predictions."""
    r = alert_rules()
    out = []
    if glucose_forecast and glucose_forecast.get("available") and glucose_forecast["hypo_risk_30m"]:
        if state["cgm"]["latest"] and state["cgm"]["latest"]["value"] >= r["glucose"]["low_warning_below"]:
            out.append(("predicted_hypo", "warning",
                        f"Low glucose likely within {r['glucose']['predicted_hypo_minutes']} min "
                        f"(now {glucose_forecast['now']:.0f}, forecast {glucose_forecast['plus_30']}, "
                        f"trend {glucose_forecast['trend_30']} mg/dL)"))

    k = state["kidney"]
    if r["kidney"]["uacr_category_rise"] and k.get("a_stage_previous") and \
            k["a_stage"] > k["a_stage_previous"]:
        out.append(("uacr_rising", "warning",
                    f"Albuminuria rose from {k['a_stage_previous']} to {k['a_stage']} "
                    f"(UACR {k['uacr']:.0f} mg/g)"))
    drop = k.get("egfr_drop_pct_12m")
    if drop is not None and drop > r["kidney"]["egfr_drop_pct_in_12_months"]:
        out.append(("egfr_falling", "warning",
                    f"eGFR fell {drop:.0f}% in 12 months (to {k['egfr']:.0f})"))

    adh = state["adherence"]["pct_7d"]
    if adh is not None and adh < r["adherence"]["warning_below_pct"]:
        out.append(("low_adherence", "warning", f"Medicine adherence {adh:.0f}% in the last 7 days"))

    if state["cgm"]["connected"] and state["cgm"]["minutes_since_last"] is not None and \
            state["cgm"]["minutes_since_last"] > r["stale_data"]["cgm_minutes"]:
        out.append(("sensor_disconnected", "warning",
                    f"No CGM reading for {state['cgm']['minutes_since_last'] / 60:.1f} hours: "
                    "sensor disconnected?"))
    return out


def active_alerts(session: Session, patient_id: str | None = None, hours: int = 72) -> list[Alert]:
    q = select(Alert).where(Alert.acknowledged_at.is_(None),
                            Alert.created_at > _now() - timedelta(hours=hours))
    if patient_id:
        q = q.where(Alert.patient_id == patient_id)
    alerts = session.exec(q).all()
    return sorted(alerts, key=lambda a: (SEVERITY_ORDER[a.severity], -a.created_at.timestamp()))
