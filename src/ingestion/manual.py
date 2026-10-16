"""Manual entry and lab CSV upload -> ObservationIn items (then translator.save()).

Lab CSV format (header row required; unit optional, blank = standard unit):
    date,test,value,unit
    2026-10-01,HbA1c,8.4,%
    2026-10-01,creatinine,1.3,mg/dL
    2026-10-01,UACR,8.5,mg/mmol
`date` may also be the word "today" (handy for demo files).
`test` may be our variable name (hba1c, creatinine, uacr, potassium, ldl, sbp, ...), a common
name (HbA1c, eGFR, UACR, BP systolic), or a LOINC code.
"""

from __future__ import annotations

import io
from datetime import datetime, timedelta, timezone

import pandas as pd

from src.clinical import loinc
from src.ingestion.translator import ObservationIn

SYNONYMS = {
    "hba1c": "hba1c", "a1c": "hba1c", "glycated haemoglobin": "hba1c", "glycated hemoglobin": "hba1c",
    "creatinine": "creatinine", "serum creatinine": "creatinine", "scr": "creatinine",
    "uacr": "uacr", "acr": "uacr", "urine acr": "uacr", "albumin creatinine ratio": "uacr",
    "potassium": "potassium", "k": "potassium", "ldl": "ldl", "ldl cholesterol": "ldl",
    "glucose": "glucose", "fbs": "glucose", "fasting glucose": "glucose", "rbs": "glucose",
    "sbp": "sbp", "systolic": "sbp", "bp systolic": "sbp", "dbp": "dbp", "diastolic": "dbp",
    "bp diastolic": "dbp", "weight": "weight", "bmi": "bmi", "heart rate": "heart_rate",
    "pulse": "heart_rate", "steps": "steps", "sleep": "sleep", "egfr": "egfr",
}


def resolve(test: str) -> str | None:
    t = str(test).strip()
    if t.lower() in SYNONYMS:
        return SYNONYMS[t.lower()]
    if t in loinc.table().index:
        return t
    return loinc.variable_for(t)


def parse_lab_csv(content: bytes | str, patient_id: str, source: str = "manual") -> tuple[list[ObservationIn], list[str]]:
    text = content.decode("utf-8-sig") if isinstance(content, bytes) else content
    df = pd.read_csv(io.StringIO(text))
    df.columns = [c.strip().lower() for c in df.columns]
    missing = {"date", "test", "value"} - set(df.columns)
    if missing:
        raise ValueError(f"CSV needs columns date,test,value[,unit]; missing {sorted(missing)}")
    items, problems = [], []
    for i, r in df.iterrows():
        var = resolve(r["test"])
        if var is None:
            problems.append(f"row {i + 2}: unknown test {r['test']!r}")
            continue
        try:
            raw = str(r["date"]).strip().lower()
            t = (datetime.now(timezone.utc) - timedelta(minutes=1) if raw == "today"
                 else pd.to_datetime(r["date"]).to_pydatetime())
            items.append(ObservationIn(patient_id=patient_id, variable=var, value=float(r["value"]),
                                       unit=str(r.get("unit", "") if pd.notna(r.get("unit", "")) else ""),
                                       time=t if t.tzinfo else t.replace(tzinfo=timezone.utc),
                                       source=source, device="lab"))
        except (ValueError, TypeError) as e:
            problems.append(f"row {i + 2}: {e}")
    return items, problems


def bp_entry(patient_id: str, systolic: float, diastolic: float, time: datetime | None = None,
             source: str = "patient_app") -> list[ObservationIn]:
    t = time or datetime.now(timezone.utc)
    return [ObservationIn(patient_id=patient_id, variable="sbp", value=systolic, time=t, source=source),
            ObservationIn(patient_id=patient_id, variable="dbp", value=diastolic, time=t, source=source)]
