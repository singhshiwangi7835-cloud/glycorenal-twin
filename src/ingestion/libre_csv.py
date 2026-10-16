"""FreeStyle Libre (LibreView) CSV export -> CGM glucose observations.

LibreView exports start with one or two title lines, then a header row such as
  Device,Serial Number,Device Timestamp,Record Type,Historic Glucose mg/dL,Scan Glucose mg/dL,...
Record Type 0 = historic reading (every 15 min), 1 = scan. Some exports use mmol/L
("Historic Glucose mmol/L"); we convert x 18.016. Timestamps are local time (settings.timezone)
in either day-first (16-10-2026 08:15) or month-first (10-16-2026 08:15 AM) form; we pick the
reading that gives no impossible dates.
"""

from __future__ import annotations

import io
from zoneinfo import ZoneInfo

import pandas as pd

from config.settings import get_settings
from src.ingestion.translator import ObservationIn


def _header_row(lines: list[str]) -> int:
    for i, line in enumerate(lines[:10]):
        if "Device Timestamp" in line:
            return i
    raise ValueError("Not a LibreView export: no 'Device Timestamp' column in the first lines")


def _parse_times(raw: pd.Series) -> pd.Series:
    day_first = pd.to_datetime(raw, dayfirst=True, errors="coerce")
    month_first = pd.to_datetime(raw, dayfirst=False, errors="coerce")
    return day_first if day_first.notna().sum() >= month_first.notna().sum() else month_first


def parse(content: bytes | str, patient_id: str) -> tuple[list[ObservationIn], dict]:
    text = content.decode("utf-8-sig") if isinstance(content, bytes) else content
    lines = text.splitlines()
    df = pd.read_csv(io.StringIO("\n".join(lines[_header_row(lines):])))
    df.columns = [c.strip() for c in df.columns]
    hist = next((c for c in df.columns if c.startswith("Historic Glucose")), None)
    scan = next((c for c in df.columns if c.startswith("Scan Glucose")), None)
    if hist is None and scan is None:
        raise ValueError("No 'Historic Glucose' or 'Scan Glucose' column found")
    unit = "mmol/L" if "mmol" in (hist or scan) else "mg/dL"

    df["time"] = _parse_times(df["Device Timestamp"])
    values = df[hist] if hist else pd.Series(index=df.index, dtype=float)
    if scan:
        values = values.fillna(df[scan])
    df["value"] = pd.to_numeric(values, errors="coerce")
    ok = df.dropna(subset=["time", "value"])
    tz = ZoneInfo(get_settings().timezone)
    items = [ObservationIn(patient_id=patient_id, variable="glucose", value=float(v), unit=unit,
                           time=t.to_pydatetime().replace(tzinfo=tz), source="libre", device="cgm")
             for t, v in zip(ok["time"], ok["value"])]
    summary = {"rows": len(df), "readings": len(items), "unit": unit,
               "from": ok["time"].min().isoformat() if len(ok) else None,
               "to": ok["time"].max().isoformat() if len(ok) else None}
    return items, summary
