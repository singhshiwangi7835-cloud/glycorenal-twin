"""Demo data (CLAUDE.md section 11 + FAST TRACK step 3). All patients are fictional.

Creates: admin, dr.mehta, 10 patients (each with a login) and, per patient,
  - 12 months of labs (HbA1c, creatinine -> eGFR, UACR, potassium, LDL)
  - 6 months of weekly BP and monthly weight/BMI
  - 14 days of 5-minute CGM + heart rate, daily steps and sleep (data/synthetic/cgm/, or
    generated on the fly), moved forward by whole days so it ends now and meals stay at meal times
  - current medicines with reminder times, and 30 days of dose history (adherence)
  - 14 days of logged Indian meals (matching the CGM trace) with their 2-hour spikes
then runs the twin once for everyone (risk scores and alerts).

Ramesh (IND-0042) is the demo story: 54 M, T2DM 9 yrs, HbA1c 8.4, eGFR ~63, UACR rising
18 -> 24 -> 85 mg/g, metformin + telmisartan, ~60% adherence.
Accounts: admin/admin123, dr.mehta/doctor123, every patient username / patient123.
"""

from __future__ import annotations

import random
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
from sqlalchemy import insert
from sqlmodel import Session

from config.settings import get_settings
from src.auth.security import hash_password
from src.clinical import loinc
from src.clinical.egfr import egfr_ckd_epi_2021
from src.db.models import DeviceConnection, DoseEvent, Meal, Medication, Observation, Patient, User
from src.db.session import drop_all, engine, init_db, is_empty

YEAR = date.today().year
CGM_DIR = Path(__file__).resolve().parents[2] / "data" / "synthetic" / "cgm"

# (patient_id, username, display name, sex, age, years with T2DM, smoker, family hx CKD, HTN, language)
DEMO_PATIENTS = [
    ("IND-0042", "ramesh", "Ramesh Kumar", "M", 54, 9, False, True, True, "hi"),
    ("IND-0107", "sunita", "Sunita Sharma", "F", 63, 15, False, False, True, "hi"),
    ("IND-0215", "priya", "Priya Nair", "F", 46, 4, False, False, False, "en"),
    ("IND-0333", "mohan", "Mohan Reddy", "M", 68, 20, True, False, True, "en"),
    ("IND-0481", "arjun", "Arjun Patel", "M", 38, 3, False, True, False, "en"),
    ("IND-0512", "lakshmi", "Lakshmi Iyer", "F", 59, 11, False, True, True, "en"),
    ("IND-0618", "imran", "Imran Khan", "M", 49, 6, True, False, True, "hi"),
    ("IND-0724", "kavita", "Kavita Joshi", "F", 52, 7, False, False, False, "hi"),
    ("IND-0839", "suresh", "Suresh Gowda", "M", 61, 14, False, False, True, "en"),
    ("IND-0950", "anita", "Anita Das", "F", 44, 2, False, True, False, "en"),
]

# labs: list of (days ago, value); bp: (systolic, diastolic); meds: (drug, class, dose, times, with food)
DEMO_CLINICAL = {
    "IND-0042": dict(hba1c=[(360, 7.6), (180, 7.9), (90, 8.1), (7, 8.4)],
                     creatinine=[(360, 1.22), (180, 1.28), (7, 1.34)],
                     uacr=[(360, 18), (180, 24), (7, 85)], potassium=[(7, 4.6)], ldl=[(7, 118)],
                     bp=(142, 88), weight=80, height=1.69, adherence=0.60,
                     meds=[("Metformin", "metformin", "1000 mg", ["08:00", "20:00"], True),
                           ("Telmisartan", "arb", "40 mg", ["08:00"], False)]),
    "IND-0107": dict(hba1c=[(360, 7.5), (180, 7.6), (7, 7.9)],
                     creatinine=[(360, 1.00), (180, 1.10), (7, 1.15)],
                     uacr=[(360, 150), (180, 170), (7, 180)], potassium=[(7, 4.7)], ldl=[(7, 96)],
                     bp=(138, 82), weight=68, height=1.57, adherence=0.85,
                     meds=[("Metformin", "metformin", "500 mg", ["08:00", "20:00"], True),
                           ("Losartan", "arb", "50 mg", ["08:00"], False),
                           ("Atorvastatin", "statin", "20 mg", ["21:00"], False)]),
    "IND-0215": dict(hba1c=[(360, 7.0), (180, 6.9), (7, 6.8)], creatinine=[(360, 0.72), (7, 0.72)],
                     uacr=[(360, 11), (7, 12)], potassium=[(7, 4.2)], ldl=[(7, 92)],
                     bp=(122, 76), weight=58, height=1.60, adherence=0.95,
                     meds=[("Metformin", "metformin", "500 mg", ["08:00", "20:00"], True)]),
    "IND-0333": dict(hba1c=[(400, 8.2), (200, 8.6)], creatinine=[(360, 1.90), (180, 2.10), (7, 2.30)],
                     uacr=[(760, 420), (400, 650)], potassium=[(7, 5.1)], ldl=[(200, 130)],
                     bp=(156, 92), weight=72, height=1.68, adherence=0.70,
                     meds=[("Metformin", "metformin", "1000 mg", ["08:00", "20:00"], True),
                           ("Glimepiride", "sulfonylurea", "2 mg", ["08:00"], True),
                           ("Ramipril", "acei", "5 mg", ["08:00"], False)]),
    "IND-0481": dict(hba1c=[(360, 8.6), (180, 9.1), (7, 9.6)], creatinine=[(360, 0.88), (7, 0.90)],
                     uacr=[(360, 20), (180, 25), (7, 45)], potassium=[(7, 4.3)], ldl=[(7, 142)],
                     bp=(134, 86), weight=98, height=1.74, adherence=0.50,
                     meds=[("Metformin", "metformin", "1000 mg", ["08:00", "20:00"], True)]),
    "IND-0512": dict(hba1c=[(360, 7.9), (180, 7.7), (7, 7.6)], creatinine=[(360, 0.90), (7, 0.95)],
                     uacr=[(360, 40), (7, 35)], potassium=[(7, 4.5)], ldl=[(7, 88)],
                     bp=(132, 80), weight=66, height=1.55, adherence=0.90,
                     meds=[("Metformin", "metformin", "1000 mg", ["08:00", "20:00"], True),
                           ("Empagliflozin", "sglt2i", "10 mg", ["08:00"], False),
                           ("Telmisartan", "arb", "40 mg", ["08:00"], False)]),
    "IND-0618": dict(hba1c=[(360, 7.8), (180, 8.0), (7, 8.1)], creatinine=[(360, 0.98), (7, 1.00)],
                     uacr=[(360, 15), (7, 19)], potassium=[(7, 4.4)], ldl=[(7, 135)],
                     bp=(146, 92), weight=84, height=1.72, adherence=0.75,
                     meds=[("Metformin", "metformin", "1000 mg", ["08:00", "20:00"], True),
                           ("Amlodipine", "ccb", "5 mg", ["08:00"], False)]),
    "IND-0724": dict(hba1c=[(360, 7.4), (180, 7.3), (7, 7.2)], creatinine=[(360, 0.80), (7, 0.80)],
                     uacr=[(360, 14), (7, 15)], potassium=[(7, 4.1)], ldl=[(7, 104)],
                     bp=(128, 78), weight=64, height=1.58, adherence=0.90,
                     meds=[("Metformin", "metformin", "500 mg", ["08:00", "20:00"], True),
                           ("Sitagliptin", "dpp4i", "100 mg", ["08:00"], False)]),
    "IND-0839": dict(hba1c=[(360, 8.3), (180, 8.1), (7, 8.0)], creatinine=[(360, 1.15), (180, 1.20), (7, 1.25)],
                     uacr=[(360, 90), (7, 110)], potassium=[(7, 4.8)], ldl=[(7, 98)],
                     bp=(140, 86), weight=76, height=1.70, adherence=0.80,
                     meds=[("Metformin", "metformin", "1000 mg", ["08:00", "20:00"], True),
                           ("Gliclazide", "sulfonylurea", "80 mg", ["08:00", "20:00"], True),
                           ("Olmesartan", "arb", "20 mg", ["08:00"], False),
                           ("Insulin glargine", "insulin", "16 units", ["22:00"], False)]),
    "IND-0950": dict(hba1c=[(360, 7.1), (7, 6.9)], creatinine=[(360, 0.70), (7, 0.70)],
                     uacr=[(360, 9), (7, 10)], potassium=[(7, 4.0)], ldl=[(7, 110)],
                     bp=(118, 74), weight=60, height=1.62, adherence=0.95,
                     meds=[("Metformin", "metformin", "500 mg", ["20:00"], True)]),
}

DEMO_ACCOUNTS = [("admin", "admin123", "admin"), ("dr.mehta", "doctor123", "doctor")] + [
    (p[1], "patient123", "patient") for p in DEMO_PATIENTS
]


def _obs(pid: str, var: str, value: float, t: datetime, source: str, device: str | None = None) -> dict:
    return {"patient_id": pid, "loinc_code": loinc.code(var), "name": loinc.display(var),
            "value": float(value), "unit": loinc.unit(var), "effective_time": t, "source": source,
            "device": device, "created_at": t}


def _trace(pid: str, i: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(5-minute readings, meals) for a demo patient; times are local wall-clock (naive)."""
    path = CGM_DIR / f"{pid}.csv"
    if path.exists():
        meals_path = CGM_DIR / f"{pid}_meals.json"
        meals = pd.read_json(meals_path) if meals_path.exists() else pd.DataFrame(columns=["time", "items", "total_carbs_g"])
        if len(meals):
            meals["time"] = pd.to_datetime(meals["time"])
        return pd.read_csv(path, parse_dates=["time"]), meals
    from src.pipeline.cgm_synth import generate
    hba1c = DEMO_CLINICAL[pid]["hba1c"][-1][1]
    return generate(days=14, hba1c=hba1c, seed=100 + i)


def _to_now(times: pd.Series, offset_days: int, tz: ZoneInfo) -> pd.Series:
    """Move local wall-clock times forward by whole days (keeps meals at meal times) -> UTC."""
    return (times + pd.Timedelta(days=offset_days)).dt.tz_localize(tz).dt.tz_convert("UTC")


def _patient_rows(pid: str, i: int, sex: str, birth_year: int, now: datetime, rng: random.Random,
                  tz: ZoneInfo) -> tuple[list[dict], list[dict]]:
    c = DEMO_CLINICAL[pid]
    rows = []
    for var in ("hba1c", "creatinine", "uacr", "potassium", "ldl"):
        for days, v in c[var]:
            t = now - timedelta(days=days, hours=3)
            rows.append(_obs(pid, var, v, t, "ehr", "lab"))
            if var == "creatinine":
                rows.append(_obs(pid, "egfr", egfr_ckd_epi_2021(v, max(18, t.year - birth_year), sex),
                                 t, "ehr", "calculated"))
    sbp, dbp = c["bp"]
    for w in range(26):  # weekly BP for 6 months, slowly drifting up to today's value
        t = now - timedelta(days=7 * w + 1, hours=rng.randint(0, 4))
        rows.append(_obs(pid, "sbp", round(sbp - 0.15 * w + rng.gauss(0, 5)), t, "patient_app"))
        rows.append(_obs(pid, "dbp", round(dbp - 0.08 * w + rng.gauss(0, 3)), t, "patient_app"))
    for m in range(6):
        t = now - timedelta(days=30 * m + 2)
        wt = c["weight"] + 0.2 * m + rng.gauss(0, 0.3)
        rows.append(_obs(pid, "weight", round(wt, 1), t, "patient_app"))
        rows.append(_obs(pid, "bmi", round(wt / c["height"] ** 2, 1), t, "patient_app"))

    trace, meals = _trace(pid, i)
    offset = (now.astimezone(tz).date() - trace["time"].iloc[-1].date()).days
    trace["time"] = _to_now(trace["time"], offset, tz)
    trace = trace[trace["time"] <= now]  # the trace ends at "now"; the simulator continues it
    for t, g, hr in zip(trace["time"], trace["glucose"], trace["heart_rate"]):
        t = t.to_pydatetime()
        rows.append(_obs(pid, "glucose", g, t, "simulator", "cgm"))
        rows.append(_obs(pid, "heart_rate", hr, t, "simulator", "fitbit"))
    daily = trace.set_index("time")["steps"].resample("1D").sum()
    for t, steps in daily.items():
        rows.append(_obs(pid, "steps", int(steps), t.to_pydatetime() + timedelta(hours=23), "simulator", "fitbit"))
        rows.append(_obs(pid, "sleep", round(rng.uniform(5.5, 7.5), 1), t.to_pydatetime() + timedelta(hours=1),
                         "simulator", "fitbit"))
    meal_rows = []
    if len(meals):
        meals["time"] = _to_now(meals["time"], offset, tz)
        meal_rows = [{"patient_id": pid, "time": t.to_pydatetime(), "items": items,
                      "total_carbs_g": carbs}
                     for t, items, carbs in zip(meals["time"], meals["items"], meals["total_carbs_g"])
                     if t <= now]
    return rows, meal_rows


def _doses(med: Medication, adherence: float, now: datetime, tz: ZoneInfo, rng: random.Random) -> list[dict]:
    out = []
    today = now.astimezone(tz).date()
    for d in range(30, -1, -1):
        day = today - timedelta(days=d)
        for hhmm in med.times:
            h, m = map(int, hhmm.split(":"))
            t = datetime.combine(day, time(h, m), tzinfo=tz).astimezone(timezone.utc)
            if t > now:
                continue  # future doses are created by the reminder engine (step 4)
            r = rng.random()
            status = "taken" if r < adherence else ("skipped" if r < adherence + 0.05 else "missed")
            if now - t < timedelta(hours=2):
                status = "pending"
            out.append({"medication_id": med.id, "scheduled_time": t, "status": status,
                        "responded_at": t + timedelta(minutes=rng.randint(2, 40)) if status in ("taken", "skipped") else None})
    return out


def seed_demo(reset: bool = False, run_twin: bool = True) -> None:
    if reset:
        drop_all()
    init_db()
    if not is_empty():
        return
    now = datetime.now(timezone.utc)
    tz = ZoneInfo(get_settings().timezone)
    rng = random.Random(42)
    with Session(engine) as s:
        admin = User(username="admin", password_hash=hash_password("admin123"), role="admin",
                     full_name="Demo Admin")
        doctor = User(username="dr.mehta", password_hash=hash_password("doctor123"),
                      role="doctor", full_name="Dr. Anjali Mehta")
        s.add_all([admin, doctor])
        s.commit()
        s.refresh(doctor)

        patient_hash = hash_password("patient123")  # same demo password, hash once
        for pid, username, name, sex, age, dm_yrs, smoker, fam, htn, lang in DEMO_PATIENTS:
            s.add(Patient(id=pid, display_name=name, sex=sex, birth_year=YEAR - age,
                          dm_diagnosis_year=YEAR - dm_yrs, smoker=smoker,
                          family_history_ckd=fam, hypertension=htn,
                          assigned_doctor_id=doctor.id))
        s.commit()
        for pid, username, name, *_, lang in DEMO_PATIENTS:
            s.add(User(username=username, password_hash=patient_hash, role="patient",
                       full_name=name, language=lang, patient_id=pid))
        s.commit()

        for i, (pid, _, _, sex, age, *_rest) in enumerate(DEMO_PATIENTS):
            obs_rows, meal_rows = _patient_rows(pid, i, sex, YEAR - age, now, rng, tz)
            s.execute(insert(Observation), obs_rows)
            if meal_rows:
                s.execute(insert(Meal), meal_rows)
            s.add(DeviceConnection(patient_id=pid, provider="simulator", status="connected", last_sync=now))
            c = DEMO_CLINICAL[pid]
            for drug, cls, dose, times, food in c["meds"]:
                med = Medication(patient_id=pid, drug=drug, drug_class=cls, dose=dose,
                                 frequency="twice daily" if len(times) == 2 else "once daily",
                                 times=times, with_food=food,
                                 start_date=(now - timedelta(days=400)).date(), prescribed_by=doctor.id,
                                 source="doctor")
                s.add(med)
                s.flush()
                s.execute(insert(DoseEvent), _doses(med, c["adherence"], now, tz, rng))
        s.commit()

        from src.meals.engine import compute_spikes
        from src.reminders.engine import ensure_dose_events
        compute_spikes(s)
        ensure_dose_events(s)
        if run_twin:
            from src.twin.engine import run_all
            run_all(s)
