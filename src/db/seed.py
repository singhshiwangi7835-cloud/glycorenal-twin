"""Demo data: users and patients for the prototype (CLAUDE.md section 11).

All patients are fictional. Labs, medicines and 14 days of CGM are added in FAST TRACK step 3.
Demo accounts: admin/admin123, dr.mehta/doctor123, and every patient below with patient123.
"""

from __future__ import annotations

from datetime import date

from sqlmodel import Session

from src.auth.security import hash_password
from src.db.models import Patient, User
from src.db.session import drop_all, engine, init_db, is_empty

YEAR = date.today().year

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

DEMO_ACCOUNTS = [("admin", "admin123", "admin"), ("dr.mehta", "doctor123", "doctor")] + [
    (p[1], "patient123", "patient") for p in DEMO_PATIENTS
]


def seed_demo(reset: bool = False) -> None:
    if reset:
        drop_all()
    init_db()
    if not is_empty():
        return
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
