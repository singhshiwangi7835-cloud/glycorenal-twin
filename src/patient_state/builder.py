"""Patient state: the twin's live, time-stamped snapshot of one patient.

Every model reads this one structure. `build_state()` takes raw inputs
(profile, labs, vitals, meds, CGM) and adds the derived features.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

import numpy as np
from pydantic import BaseModel, Field

from src.pipeline.cgm import cgm_metrics
from src.pipeline.egfr import egfr_ckd_epi_2021, egfr_slope_per_year
from src.pipeline.kdigo import kdigo_stage

DRUG_CLASSES = {
    "metformin": ["metformin"],
    "sglt2i": ["dapagliflozin", "empagliflozin", "canagliflozin", "remogliflozin", "sglt2"],
    "glp1ra": ["semaglutide", "liraglutide", "dulaglutide", "glp-1", "glp1"],
    "acei_arb": ["telmisartan", "losartan", "olmesartan", "ramipril", "enalapril",
                 "lisinopril", "valsartan", "irbesartan"],
    "finerenone": ["finerenone"],
    "insulin": ["insulin", "glargine", "degludec", "aspart", "lispro"],
    "sulfonylurea": ["glimepiride", "gliclazide", "glipizide", "glibenclamide"],
    "statin": ["atorvastatin", "rosuvastatin", "simvastatin"],
}


class Profile(BaseModel):
    age: float
    sex: str = Field(description="M or F")
    dm_duration_yrs: float = 0
    smoker: bool = False
    family_history: bool = False
    hypertension: bool = False


class Labs(BaseModel):
    hba1c: float
    creatinine: float
    uacr: float
    fasting_glucose: Optional[float] = None
    potassium: Optional[float] = None
    ldl: Optional[float] = None
    uacr_date: Optional[date] = None
    hba1c_date: Optional[date] = None
    egfr_history: list[tuple[float, float]] = Field(
        default_factory=list, description="(years_from_first, egfr) pairs"
    )


class Vitals(BaseModel):
    sbp: float
    dbp: float
    bmi: float
    weight_kg: Optional[float] = None
    waist_cm: Optional[float] = None


class PatientInput(BaseModel):
    patient_id: str
    profile: Profile
    labs: Labs
    vitals: Vitals
    meds: list[str] = Field(default_factory=list)
    cgm_glucose: list[float] = Field(default_factory=list)
    steps_per_day: Optional[float] = None
    sleep_hours: Optional[float] = None


def med_flags(meds: list[str]) -> dict[str, int]:
    text = " ".join(meds).lower()
    return {f"on_{cls}": int(any(k in text for k in kws)) for cls, kws in DRUG_CLASSES.items()}


def _freshness(labs: Labs, today: date) -> list[str]:
    flags = []
    if labs.uacr_date and (today - labs.uacr_date).days > 365:
        flags.append("UACR older than 12 months")
    if labs.hba1c_date and (today - labs.hba1c_date).days > 120:
        flags.append("HbA1c older than 4 months")
    return flags


def build_state(p: PatientInput, today: Optional[date] = None) -> dict:
    today = today or date.today()
    egfr = egfr_ckd_epi_2021(p.labs.creatinine, p.profile.age, p.profile.sex)
    kd = kdigo_stage(egfr, p.labs.uacr)
    meds = med_flags(p.meds)
    cgm = cgm_metrics(p.cgm_glucose) if len(p.cgm_glucose) >= 2 else None

    derived = {
        "egfr": egfr,
        "kdigo": kd["stage"],
        "kdigo_risk": kd["risk"],
        "kdigo_colour": kd["colour"],
        "has_ckd": kd["has_ckd"],
        "egfr_slope_per_year": egfr_slope_per_year(p.labs.egfr_history),
        "bp_on_target": p.vitals.sbp < 130 and p.vitals.dbp < 80,
        "hba1c_on_target": p.labs.hba1c < 7.0,
        "freshness_flags": _freshness(p.labs, today),
    }

    features = {
        "age": p.profile.age,
        "male": int(p.profile.sex.upper().startswith("M")),
        "dm_duration_yrs": p.profile.dm_duration_yrs,
        "hba1c": p.labs.hba1c,
        "sbp": p.vitals.sbp,
        "bmi": p.vitals.bmi,
        "egfr": egfr,
        "log_uacr": float(np.log(max(p.labs.uacr, 1))),
        "hypertension": int(p.profile.hypertension or p.vitals.sbp >= 140),
        "smoker": int(p.profile.smoker),
        "family_history": int(p.profile.family_history),
        "on_sglt2i": meds["on_sglt2i"],
        "on_acei_arb": meds["on_acei_arb"],
        "on_glp1ra": meds["on_glp1ra"],
        "on_finerenone": meds["on_finerenone"],
    }

    return {
        "patient_id": p.patient_id,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "profile": p.profile.model_dump(),
        "labs": p.labs.model_dump(mode="json"),
        "vitals": p.vitals.model_dump(),
        "meds": p.meds,
        "med_flags": meds,
        "cgm": cgm,
        "cgm_trace_24h": p.cgm_glucose[-288:],  # last 24 h at 5-min intervals
        "lifestyle": {"steps_per_day": p.steps_per_day, "sleep_hours": p.sleep_hours},
        "derived": derived,
        "features": features,
    }
