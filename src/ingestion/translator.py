"""Translator: any source -> standard Observation rows, then the living-twin loop.

Every connector (FHIR, simulator, Libre CSV, manual entry, patient app) builds `ObservationIn`
items and calls `save()`, which:
  1. maps the variable / LOINC code (data/reference/loinc_map.csv + loinc_aliases.csv)
  2. converts units to the standard unit (src/clinical/units.py)
  3. skips duplicates (same patient + code + time + source)
  4. adds a CKD-EPI 2021 eGFR row for every new creatinine
  5. runs the living-twin loop: instant alerts on each reading; T2DM short-term re-run if CGM
     arrived; full re-run (DKD) only if a lab arrived
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel
from sqlmodel import Session, select

from src.alerts.engine import check_observation, raise_alert
from src.clinical import loinc
from src.clinical.egfr import egfr_ckd_epi_2021
from src.clinical.units import to_standard
from src.db.models import OBS_SOURCES, Observation, Patient

LAB_VARS = {"hba1c", "creatinine", "egfr", "uacr", "potassium", "ldl"}


class ObservationIn(BaseModel):
    patient_id: str
    variable: Optional[str] = None     # our name, e.g. "hba1c" (or give loinc_code)
    loinc_code: Optional[str] = None
    value: float
    unit: str = ""                     # blank = already in the standard unit
    time: datetime
    source: str = "manual"
    device: Optional[str] = None       # "cgm", "fingerstick", "lab", ...


class SkippedObservation(ValueError):
    pass


def to_row(item: ObservationIn) -> Observation:
    var = item.variable or (loinc.variable_for(item.loinc_code) if item.loinc_code else None)
    if not var or var not in loinc.table().index:
        raise SkippedObservation(f"unknown variable / LOINC code: {item.variable or item.loinc_code}")
    if item.source not in OBS_SOURCES:
        raise SkippedObservation(f"unknown source {item.source!r}")
    std_unit = loinc.unit(var)
    value = to_standard(var, item.value, item.unit, std_unit)
    t = item.time if item.time.tzinfo else item.time.replace(tzinfo=timezone.utc)
    return Observation(patient_id=item.patient_id, loinc_code=loinc.code(var), name=loinc.display(var),
                       value=value, unit=std_unit, effective_time=t.astimezone(timezone.utc),
                       source=item.source, device=item.device)


def _exists(session: Session, o: Observation) -> bool:
    return session.exec(select(Observation.id).where(
        Observation.patient_id == o.patient_id, Observation.loinc_code == o.loinc_code,
        Observation.effective_time == o.effective_time, Observation.source == o.source)).first() is not None


def save(session: Session, items: list[ObservationIn], run_loop: bool = True,
         check_duplicates: bool = True) -> dict:
    """Store readings and update the twin. Returns counts, skipped reasons and new alerts."""
    from src.twin import engine  # local import: engine imports state, which imports db models

    saved, skipped, alerts = [], [], []
    patients: dict[str, Patient] = {}
    for item in items:
        try:
            row = to_row(item)
        except (SkippedObservation, ValueError) as e:
            skipped.append(str(e))
            continue
        p = patients.get(row.patient_id) or session.get(Patient, row.patient_id)
        if p is None:
            skipped.append(f"unknown patient {row.patient_id}")
            continue
        patients[p.id] = p
        if check_duplicates and _exists(session, row):
            skipped.append("duplicate")
            continue
        session.add(row)
        saved.append(row)
        if row.loinc_code == loinc.code("creatinine"):
            age = max(18, row.effective_time.year - p.birth_year)
            eg = Observation(patient_id=p.id, loinc_code=loinc.code("egfr"), name=loinc.display("egfr"),
                             value=egfr_ckd_epi_2021(row.value, age, p.sex), unit=loinc.unit("egfr"),
                             effective_time=row.effective_time, source=row.source, device="calculated")
            if not (check_duplicates and _exists(session, eg)):
                session.add(eg)
        if run_loop:
            for t, sev, msg in check_observation(row):
                if raise_alert(session, row.patient_id, t, sev, msg, at=row.effective_time):
                    alerts.append(msg)
    session.commit()

    reruns = {}
    if run_loop:
        for pid in patients:
            mine = [o for o in saved if o.patient_id == pid]
            vars_ = {loinc.variable_for(o.loinc_code) for o in mine}
            if vars_ & LAB_VARS:
                reruns[pid] = "full"
                alerts += engine.run_full(session, pid)["new_alerts"]
            elif any(o.device == "cgm" for o in mine):
                reruns[pid] = "short"
                alerts += engine.run_short(session, pid).get("new_alerts", [])
    return {"saved": len(saved), "skipped": len(skipped), "skipped_reasons": sorted(set(skipped))[:10],
            "new_alerts": alerts, "reruns": reruns}
