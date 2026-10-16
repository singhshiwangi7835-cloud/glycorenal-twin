"""Database tables (SQLModel), per CLAUDE.md section 5.

All labs, vitals and wearable readings live in `Observation` (one row per value).
Types are kept portable so the same code runs on SQLite and PostgreSQL.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import JSON, Column, Index
from sqlmodel import Field, SQLModel

ROLES = ("admin", "doctor", "patient")
OBS_SOURCES = ("ehr", "dexcom", "libre", "simulator", "manual", "patient_app")


def utcnow() -> datetime:
    """Current time in UTC (timezone-aware; all stored times are UTC)."""
    return datetime.now(timezone.utc)


class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(index=True, unique=True)
    password_hash: str
    role: str = Field(index=True)                     # admin | doctor | patient
    full_name: str = ""
    language: str = "en"                              # en | hi
    patient_id: Optional[str] = Field(default=None, foreign_key="patient.id")


class Patient(SQLModel, table=True):
    id: str = Field(primary_key=True)                 # de-identified, e.g. IND-0042
    display_name: str
    sex: str                                          # M | F
    birth_year: int
    dm_diagnosis_year: Optional[int] = None
    smoker: bool = False
    family_history_ckd: bool = False
    hypertension: bool = False
    assigned_doctor_id: Optional[int] = Field(default=None, foreign_key="user.id")
    fhir_id: Optional[str] = None
    created_at: datetime = Field(default_factory=utcnow)


class Observation(SQLModel, table=True):
    __table_args__ = (Index("ix_obs_patient_code_time", "patient_id", "loinc_code", "effective_time"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    patient_id: str = Field(foreign_key="patient.id", index=True)
    loinc_code: str = Field(index=True)
    name: str
    value: float
    unit: str
    effective_time: datetime = Field(index=True)
    source: str                                       # see OBS_SOURCES
    device: Optional[str] = None                      # e.g. "cgm", "fingerstick"
    created_at: datetime = Field(default_factory=utcnow)


class Medication(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    patient_id: str = Field(foreign_key="patient.id", index=True)
    drug: str
    drug_class: str = ""
    dose: str = ""
    frequency: str = ""
    times: list[str] = Field(default_factory=list, sa_column=Column(JSON))  # ["08:00","20:00"]
    with_food: bool = False
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    prescribed_by: Optional[int] = Field(default=None, foreign_key="user.id")
    source: str = "doctor"                            # ehr | doctor


class DoseEvent(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    medication_id: int = Field(foreign_key="medication.id", index=True)
    scheduled_time: datetime = Field(index=True)
    status: str = "pending"                           # pending | taken | missed | skipped
    responded_at: Optional[datetime] = None


class Meal(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    patient_id: str = Field(foreign_key="patient.id", index=True)
    time: datetime
    items: list[dict] = Field(default_factory=list, sa_column=Column(JSON))  # [{food, servings}]
    total_carbs_g: float = 0
    glucose_before: Optional[float] = None
    glucose_peak: Optional[float] = None
    spike: Optional[float] = None                     # computed 2 h after the meal


class Alert(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    patient_id: str = Field(foreign_key="patient.id", index=True)
    type: str
    severity: str                                     # info | warning | critical
    message: str
    created_at: datetime = Field(default_factory=utcnow, index=True)
    acknowledged_by: Optional[int] = Field(default=None, foreign_key="user.id")
    acknowledged_at: Optional[datetime] = None


class Prediction(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    patient_id: str = Field(foreign_key="patient.id", index=True)
    kind: str                                         # e.g. dkd_onset_3y, hba1c_3m, glucose_30m
    value: float
    details: dict = Field(default_factory=dict, sa_column=Column(JSON))
    model_version: str = ""
    created_at: datetime = Field(default_factory=utcnow, index=True)


class DeviceConnection(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    patient_id: str = Field(foreign_key="patient.id", index=True)
    provider: str                                     # dexcom | libre | simulator
    status: str = "disconnected"
    tokens: dict = Field(default_factory=dict, sa_column=Column(JSON))  # never commit real tokens
    last_sync: Optional[datetime] = None


class LLMCache(SQLModel, table=True):
    key: str = Field(primary_key=True)                # hash of mode + language + state
    response: str
    created_at: datetime = Field(default_factory=utcnow)
