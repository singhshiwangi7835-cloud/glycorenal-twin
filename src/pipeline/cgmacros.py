"""CGMacros (PhysioNet) reader: one 5-minute series per participant.

Source: https://physionet.org/content/cgmacros/1.0.0/ (open access, ODC-BY).
Each participant folder CGMacros-0XX holds CGMacros-0XX.csv with minute-level rows:
  Timestamp, Libre GL, Dexcom GL, HR, Calories (Activity), Mets (x10), Meal Type, Carbs,
  Amount Consumed (%), ...  and bio.csv has A1c PDL (Lab) (%) per participant.

We use Dexcom GL (every 5 min; Libre GL as fallback), carbs eaten (Carbs x Amount Consumed),
heart rate, and an activity value built from METs: (METs - 1.5) x 50 per minute, summed per
5 minutes, so brisk walking (~3.5 METs) counts like ~100 steps a minute.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
CGM_DIR = ROOT / "data" / "raw" / "cgmacros"


def available() -> bool:
    return any(CGM_DIR.glob("**/CGMacros-0*.csv"))


def extract_csvs(zip_path: Path, dest: Path = CGM_DIR) -> int:
    """Pull only the CSV files out of the CGMacros zip (skips the ~600 MB of meal photos).

    Handles both the data zip (CGMacros_dateshifted365.zip) and PhysioNet's project zip that
    wraps it. Returns the number of CSV files written.
    """
    dest.mkdir(parents=True, exist_ok=True)
    n = 0
    with zipfile.ZipFile(zip_path) as z:
        inner = [i for i in z.namelist() if i.endswith("CGMacros_dateshifted365.zip")]
        if inner:  # project zip: open the inner data zip in memory-light streaming fashion
            with z.open(inner[0]) as f:
                tmp = dest / "_inner.zip"
                tmp.write_bytes(f.read())
            n = extract_csvs(tmp, dest)
            tmp.unlink()
            return n
        for name in z.namelist():
            if name.lower().endswith(".csv"):
                target = dest / Path(name).name if Path(name).name.lower() == "bio.csv" \
                    else dest / Path(*Path(name).parts[-2:])
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(z.read(name))
                n += 1
    return n


def bio() -> pd.DataFrame:
    path = next(CGM_DIR.glob("**/bio.csv"), None)
    if path is None:
        return pd.DataFrame()
    b = pd.read_csv(path)
    b.columns = [c.strip() for c in b.columns]
    return b


def participant_ids() -> list[str]:
    return sorted({p.stem for p in CGM_DIR.glob("**/CGMacros-0*.csv")})


def load_participant(pid: str) -> pd.DataFrame:
    """5-minute series: time, glucose, heart_rate, activity, carbs_g (gaps left as NaN glucose)."""
    path = next(CGM_DIR.glob(f"**/{pid}.csv"))
    raw = pd.read_csv(path)
    raw.columns = [c.strip() for c in raw.columns]
    raw["time"] = pd.to_datetime(raw["Timestamp"], errors="coerce")
    raw = raw.dropna(subset=["time"]).set_index("time").sort_index()

    gl = raw.get("Dexcom GL")
    if gl is None or gl.notna().sum() < 100:
        gl = raw.get("Libre GL")
    eaten = raw.get("Amount Consumed", pd.Series(100, index=raw.index)).fillna(100) / 100
    carbs = raw.get("Carbs", pd.Series(0, index=raw.index)).fillna(0) * eaten
    mets = raw.get("Mets", pd.Series(np.nan, index=raw.index)) / 10
    activity = ((mets - 1.5).clip(lower=0) * 50).fillna(0)

    out = pd.DataFrame({
        "glucose": pd.to_numeric(gl, errors="coerce").resample("5min").mean(),
        "heart_rate": pd.to_numeric(raw.get("HR"), errors="coerce").resample("5min").mean(),
        "activity": activity.resample("5min").sum(),
        "carbs_g": carbs.resample("5min").sum(),
    })
    return out.reset_index()


def hba1c_by_participant() -> dict[str, float]:
    b = bio()
    if b.empty:
        return {}
    col = next((c for c in b.columns if c.lower().startswith("a1c")), None)
    sid = next((c for c in b.columns if c.lower() in ("subject", "participant", "id")), b.columns[0])
    return {f"CGMacros-{int(s):03d}": float(a) for s, a in zip(b[sid], b[col]) if pd.notna(a)} if col else {}
