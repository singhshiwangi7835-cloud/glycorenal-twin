"""Five synthetic demo patients covering the main story lines. No real patient data."""

from __future__ import annotations

from datetime import date, timedelta

from src.patient_state.builder import PatientInput
from src.pipeline.synthetic import synthetic_cgm

_today = date.today()


def _p(pid, profile, labs, vitals, meds, cgm_mean, cgm_cv, steps, seed):
    return PatientInput(
        patient_id=pid, profile=profile, labs=labs, vitals=vitals, meds=meds,
        cgm_glucose=synthetic_cgm(cgm_mean, cgm_cv, days=14, seed=seed),
        steps_per_day=steps, sleep_hours=6.5,
    )


DEMO = [
    # 1. Classic "predict before it happens": healthy kidneys, poor control
    _p("IND-0042",
       {"age": 54, "sex": "M", "dm_duration_yrs": 9, "hypertension": True, "family_history": True},
       {"hba1c": 8.4, "creatinine": 1.05, "uacr": 22, "potassium": 4.5,
        "uacr_date": _today - timedelta(days=60), "hba1c_date": _today - timedelta(days=20),
        "egfr_history": [(0, 92), (1, 88), (2, 84)]},
       {"sbp": 142, "dbp": 88, "bmi": 28.1},
       ["metformin 1000mg BD", "telmisartan 40mg OD"], 175, 0.34, 3500, 1),
    # 2. Established DKD G3a-A2, eligible for SGLT2i + finerenone
    _p("IND-0107",
       {"age": 63, "sex": "F", "dm_duration_yrs": 15, "hypertension": True},
       {"hba1c": 7.9, "creatinine": 1.15, "uacr": 180, "potassium": 4.7,
        "uacr_date": _today - timedelta(days=30), "hba1c_date": _today - timedelta(days=30),
        "egfr_history": [(0, 62), (1, 57), (2, 51)]},
       {"sbp": 138, "dbp": 82, "bmi": 27.4},
       ["metformin 500mg BD", "losartan 50mg OD", "atorvastatin 20mg"], 165, 0.30, 4500, 2),
    # 3. Well controlled, low risk
    _p("IND-0215",
       {"age": 46, "sex": "F", "dm_duration_yrs": 4},
       {"hba1c": 6.8, "creatinine": 0.75, "uacr": 12, "potassium": 4.2,
        "uacr_date": _today - timedelta(days=90), "hba1c_date": _today - timedelta(days=40)},
       {"sbp": 122, "dbp": 76, "bmi": 23.8},
       ["metformin 500mg BD"], 130, 0.24, 8200, 3),
    # 4. Advanced CKD, metformin safety flag, hypo risk on sulfonylurea
    _p("IND-0333",
       {"age": 68, "sex": "M", "dm_duration_yrs": 20, "hypertension": True, "smoker": True},
       {"hba1c": 8.9, "creatinine": 2.3, "uacr": 650, "potassium": 5.1,
        "uacr_date": _today - timedelta(days=400), "hba1c_date": _today - timedelta(days=150),
        "egfr_history": [(0, 41), (1, 35), (2, 29)]},
       {"sbp": 156, "dbp": 92, "bmi": 26.0},
       ["metformin 1000mg BD", "glimepiride 2mg OD", "ramipril 5mg OD"], 150, 0.45, 2500, 4),
    # 5. Young, obese, rising albuminuria
    _p("IND-0481",
       {"age": 38, "sex": "M", "dm_duration_yrs": 3, "family_history": True},
       {"hba1c": 9.6, "creatinine": 0.9, "uacr": 45, "potassium": 4.3,
        "uacr_date": _today - timedelta(days=15), "hba1c_date": _today - timedelta(days=15)},
       {"sbp": 134, "dbp": 86, "bmi": 32.5},
       ["metformin 1000mg BD"], 205, 0.33, 3000, 5),
]

DEMO_BY_ID = {p.patient_id: p for p in DEMO}
