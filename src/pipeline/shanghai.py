"""ShanghaiT2DM: real CGM from 100 people with type 2 diabetes (Zhao et al., Sci Data 2023, CC BY 4.0).

Download: https://doi.org/10.6084/m9.figshare.20444397 -> data/raw/shanghai_t2dm/ (zip). Unpack with
`extract()` (done once; files go to data/raw/shanghai_t2dm/extracted/).

What it has: CGM every 15 minutes for 3-14 days, meal times (as text, no carb counts), medicines,
and a summary sheet (age, sex, BMI, HbA1c, creatinine, eGFR, complications). No heart rate or steps.

load_participant(pid) returns our usual 5-minute series: time, glucose (15-minute CGM linearly
interpolated to 5 minutes, gaps up to 30 minutes filled), measured (1 at a real reading), meal (1 at a
logged meal), carbs_g (0: unknown), steps (0) and heart_rate (NaN).
"""

from __future__ import annotations

import zipfile
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw" / "shanghai_t2dm"
DIR = RAW / "extracted"
T2DM_DIR = DIR / "Shanghai_T2DM"


def extract() -> int:
    """Unpack the figshare zip into DIR (drops the Chinese-named top folder and Office lock files)."""
    zips = sorted(RAW.glob("*.zip"))
    if not zips:
        return 0
    n = 0
    with zipfile.ZipFile(zips[0]) as z:
        for info in z.infolist():
            parts = info.filename.split("/")[1:]
            if not parts or not parts[-1] or parts[-1].startswith("~$") or ".." in parts:
                continue
            p = DIR.joinpath(*parts)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(z.read(info))
            n += 1
    return n


def available() -> bool:
    return T2DM_DIR.exists() and any(T2DM_DIR.glob("*.xls*"))


def participant_ids() -> list[str]:
    """One id per recording, e.g. '2016_0_20201224' (patient 2016, first recording)."""
    return sorted(p.stem for p in T2DM_DIR.glob("*.xls*")) if available() else []


@lru_cache(maxsize=1)
def summary() -> pd.DataFrame:
    s = pd.read_excel(DIR / "Shanghai_T2DM_Summary.xlsx")
    s.columns = [c.strip() for c in s.columns]

    def num(col):  # '/' means not measured
        return pd.to_numeric(s[col], errors="coerce")
    out = pd.DataFrame({
        "pid": s["Patient Number"].astype(str),
        "male": (s["Gender (Female=1, Male=2)"] == 2).astype(int),
        "age": num("Age (years)"), "bmi": num("BMI (kg/m2)"),
        "dm_duration_yrs": num("Duration of diabetes (years)"),
        "hba1c_pct": (num("HbA1c (mmol/mol)") / 10.929 + 2.15).round(1),  # IFCC -> NGSP
        "creatinine_mg_dl": (num("Creatinine (umol/L)") / 88.4).round(2),
        "egfr": num("Estimated Glomerular Filtration Rate  (ml/min/1.73m2)"),
        "nephropathy": s["Diabetic Microvascular Complications"].astype(str).str.contains("nephropathy").astype(int),
        "agents": s["Hypoglycemic Agents"].astype(str).str.strip(),
    })
    return out


def _file(pid: str) -> Path:
    for ext in (".xlsx", ".xls"):
        p = T2DM_DIR / f"{pid}{ext}"
        if p.exists():
            return p
    raise FileNotFoundError(pid)


@lru_cache(maxsize=16)
def load_participant(pid: str) -> pd.DataFrame:
    x = pd.read_excel(_file(pid))
    x = x.rename(columns={x.columns[0]: "time", x.columns[1]: "glucose"})
    x["time"] = pd.to_datetime(x["time"])
    diet = (x["Dietary intake"] if "Dietary intake" in x else pd.Series(None, index=x.index, dtype=object))
    diet = diet.fillna("").astype(str).str.strip()
    x["meal"] = (diet.ne("") & ~diet.str.contains("not available", case=False)).astype(int)
    x = x[["time", "glucose", "meal"]].dropna(subset=["time"]).sort_values("time")
    x["glucose"] = pd.to_numeric(x["glucose"], errors="coerce")
    g = x.set_index("time").resample("5min").agg({"glucose": "mean", "meal": "max"})
    g["measured"] = g["glucose"].notna().astype(int)  # 1 = a real sensor reading, 0 = filled in
    g["glucose"] = g["glucose"].interpolate(limit=6, limit_area="inside")  # 15-min -> 5-min, gaps <= 30 min
    g["meal"] = g["meal"].fillna(0).astype(int)
    g = g.reset_index()
    g["carbs_g"] = 0.0           # not recorded as grams of carbs
    g["steps"] = 0
    g["heart_rate"] = np.nan
    return g  # regular 5-minute grid; rows inside long gaps keep glucose = NaN


def demo_participant() -> str | None:
    """A typical recording for the live demo: 10+ days, mean glucose 150-200 mg/dL, several meals logged."""
    best = None
    for pid in participant_ids():
        try:
            s = load_participant(pid)
        except Exception:  # noqa: BLE001  (skip unreadable files)
            continue
        days = len(s) / 288
        if days >= 10 and 150 <= s["glucose"].mean() <= 200 and s["meal"].sum() >= 10:
            return pid
        if best is None and days >= 7:
            best = pid
    return best
