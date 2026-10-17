"""Live sensor simulator: replays a CGM + heart-rate + steps trace as if it were arriving now.

Source per patient: a CGMacros participant (if downloaded and chosen) or the patient's synthetic
14-day trace (data/synthetic/cgm/<id>.csv, generated if missing). Replay starts at the row whose
time of day matches the local time now, so breakfast spikes come in the morning.

Speed: one 5-minute reading every SIM_SPEED_SECONDS (default 3 s = 100x real time; 300 = real
time). Each reading is stamped with the real clock time; the forecast and meal-spike logic count
readings, so in fast mode "+30 min" is 6 readings (~18 s).

Demo scenarios: inject_meal_spike (e.g. a big rice meal) and inject_hypo (slide to ~52 mg/dL).
Every reading goes through translator.save() -> instant alerts + short-term twin re-run.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from sqlmodel import Session, select

from config.settings import get_settings
from src.clinical import loinc
from src.db.models import DeviceConnection, Observation, Patient
from src.ingestion.translator import ObservationIn, save
from src.pipeline import cgm_synth, cgmacros, shanghai

log = logging.getLogger("glycorenal.simulator")
CGM_DIR = Path(__file__).resolve().parents[2] / "data" / "synthetic" / "cgm"


@dataclass
class Simulation:
    patient_id: str
    source: str
    rows: pd.DataFrame                    # glucose, heart_rate, steps (one row = 5 sensor minutes)
    idx: int = 0
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    readings_sent: int = 0
    scenarios: list[str] = field(default_factory=list)

    def status(self) -> dict:
        return {"patient_id": self.patient_id, "running": True, "source": self.source,
                "readings_sent": self.readings_sent, "started_at": self.started_at.isoformat(),
                "next_glucose": float(self.rows.loc[self.idx % len(self.rows), "glucose"]),
                "scenarios": self.scenarios[-5:]}


_sims: dict[str, Simulation] = {}
_lock = threading.Lock()


def _trace(patient_id: str, source: str) -> tuple[pd.DataFrame, str]:
    if source.startswith("cgmacros") and cgmacros.available():
        pid = source.split(":", 1)[1] if ":" in source else cgmacros.participant_ids()[0]
        t = cgmacros.load_participant(pid).rename(columns={"activity": "steps"})
        t["glucose"] = t["glucose"].interpolate(limit=6)
        t = t.dropna(subset=["glucose"])
        t["heart_rate"] = t["heart_rate"].fillna(t["heart_rate"].median())
        return t.reset_index(drop=True), f"CGMacros {pid}"
    if source.startswith("shanghai") and shanghai.available():
        pid = source.split(":", 1)[1] if ":" in source else shanghai.demo_participant()
        t = shanghai.load_participant(pid).dropna(subset=["glucose"]).reset_index(drop=True)
        return t[["time", "glucose", "heart_rate", "steps"]], f"real CGM: ShanghaiT2DM {pid.split('_')[0]}"
    path = CGM_DIR / f"{patient_id}.csv"
    if path.exists():
        return pd.read_csv(path, parse_dates=["time"]), "synthetic trace"
    t, _ = cgm_synth.generate(days=14, hba1c=8.0, seed=abs(hash(patient_id)) % 1000)
    return t, "synthetic trace (generated)"


def _align_to_now(t: pd.DataFrame) -> int:
    """Index of the first row whose time of day matches the local time now."""
    local = datetime.now(ZoneInfo(get_settings().timezone))
    minutes = local.hour * 60 + local.minute
    tod = pd.to_datetime(t["time"]).dt.hour * 60 + pd.to_datetime(t["time"]).dt.minute
    return int(np.argmin(np.abs(tod.to_numpy() - minutes)))


def _set_connection(session: Session, patient_id: str, status: str) -> None:
    conn = session.exec(select(DeviceConnection).where(DeviceConnection.patient_id == patient_id,
                                                       DeviceConnection.provider == "simulator")).first()
    if conn is None:
        conn = DeviceConnection(patient_id=patient_id, provider="simulator")
    conn.status, conn.last_sync = status, datetime.now(timezone.utc)
    session.add(conn)
    session.commit()


def start(session: Session, patient_id: str, source: str = "synthetic") -> dict:
    if session.get(Patient, patient_id) is None:
        raise LookupError(patient_id)
    rows, label = _trace(patient_id, source)
    start_idx = _align_to_now(rows)
    rows = pd.concat([rows.iloc[start_idx:], rows.iloc[:start_idx]], ignore_index=True)
    sim = Simulation(patient_id=patient_id, source=label,
                     rows=rows[["time", "glucose", "heart_rate", "steps"]].copy())
    with _lock:
        _sims[patient_id] = sim
    _set_connection(session, patient_id, "connected")
    return sim.status()


def stop(session: Session, patient_id: str) -> dict:
    with _lock:
        _sims.pop(patient_id, None)
    _set_connection(session, patient_id, "disconnected")
    return {"patient_id": patient_id, "running": False}


def status(patient_id: str | None = None) -> dict | list[dict]:
    with _lock:
        if patient_id:
            s = _sims.get(patient_id)
            return s.status() if s else {"patient_id": patient_id, "running": False}
        return [s.status() for s in _sims.values()]


def is_running(patient_id: str) -> bool:
    return patient_id in _sims


def inject_meal_spike(patient_id: str, carbs_g: float = 90, gi_factor: float = 1.3) -> bool:
    """Glucose rise starting in 2 readings, peak ~ carbs x GI (x1.1), like a big rice meal."""
    with _lock:
        s = _sims.get(patient_id)
        if not s:
            return False
        rise = min(180.0, carbs_g * gi_factor * 1.1)
        s.rows = cgm_synth.inject_meal_spike(_ahead(s), 2, peak_rise=rise)
        s.idx = 0
        s.scenarios.append(f"meal spike +{rise:.0f} mg/dL")
    return True


def inject_hypo(patient_id: str, nadir: float = 52) -> bool:
    """Glucose slides to `nadir` over ~9 readings (45 sensor minutes), then recovers."""
    with _lock:
        s = _sims.get(patient_id)
        if not s:
            return False
        s.rows = cgm_synth.inject_hypo(_ahead(s), 1, nadir=nadir)
        s.idx = 0
        s.scenarios.append(f"hypo to {nadir:.0f} mg/dL")
    return True


def _ahead(s: Simulation) -> pd.DataFrame:
    """Rows rotated so the next reading is row 0 (scenario helpers work on positions)."""
    i = s.idx % len(s.rows)
    return pd.concat([s.rows.iloc[i:], s.rows.iloc[:i]], ignore_index=True)


def _add_steps(session: Session, patient_id: str, steps: int, now: datetime) -> None:
    """Keep one 'steps today' observation per local day, increasing as the day goes on."""
    tz = ZoneInfo(get_settings().timezone)
    day_end = datetime.combine(now.astimezone(tz).date(), datetime.max.time().replace(microsecond=0),
                               tzinfo=tz).astimezone(timezone.utc) - timedelta(minutes=1)
    obs = session.exec(select(Observation).where(Observation.patient_id == patient_id,
                                                 Observation.loinc_code == loinc.code("steps"),
                                                 Observation.effective_time == day_end)).first()
    if obs is None:
        obs = Observation(patient_id=patient_id, loinc_code=loinc.code("steps"), name=loinc.display("steps"),
                          value=0, unit=loinc.unit("steps"), effective_time=day_end, source="simulator",
                          device="fitbit")
    obs.value += int(steps)
    session.add(obs)
    session.commit()


def tick(session: Session) -> list[dict]:
    """Send the next reading for every running simulation. Returns what was sent."""
    with _lock:
        batch = []
        for s in _sims.values():
            r = s.rows.iloc[s.idx % len(s.rows)]
            s.idx += 1
            s.readings_sent += 1
            hr = float(r["heart_rate"]) if pd.notna(r["heart_rate"]) else None  # real CGM sets have no HR
            batch.append((s.patient_id, float(r["glucose"]), hr, int(r["steps"])))
    now = datetime.now(timezone.utc)
    sent = []
    for pid, g, hr, steps in batch:
        items = [ObservationIn(patient_id=pid, variable="glucose", value=round(g), time=now,
                               source="simulator", device="cgm")]
        if hr is not None:
            items.append(ObservationIn(patient_id=pid, variable="heart_rate", value=round(hr), time=now,
                                       source="simulator", device="fitbit"))
        result = save(session, items, check_duplicates=False)
        if steps:
            _add_steps(session, pid, steps, now)
        sent.append({"patient_id": pid, "glucose": round(g), "new_alerts": result["new_alerts"]})
    return sent


class Runner(threading.Thread):
    """Background thread: tick() every SIM_SPEED_SECONDS while the API runs."""

    def __init__(self, engine, interval: float):
        super().__init__(daemon=True, name="cgm-simulator")
        self.engine, self.interval = engine, interval
        self._halt = threading.Event()

    def run(self) -> None:
        while not self._halt.wait(self.interval):
            if not _sims:
                continue
            try:
                with Session(self.engine) as s:
                    tick(s)
            except Exception:  # noqa: BLE001  (keep the simulator alive; log and continue)
                log.exception("simulator tick failed")

    def stop(self) -> None:
        self._halt.set()
