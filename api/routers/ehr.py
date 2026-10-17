"""Hospital EHR (FHIR R4): import samples or bundles, fetch from a FHIR server, export a twin.

GET  /ehr/samples                 sample bundles in data/fhir_samples/
POST /ehr/import/sample           {"name": "synthea_....json"}
POST /ehr/import/bundle           a FHIR R4 Bundle (JSON body)
POST /ehr/fetch                   {"fhir_patient_id": "...", "base_url": optional}
GET  /patients/{pid}/fhir         the twin as a FHIR R4 Bundle
Import and fetch are for doctors/admins.
"""

from __future__ import annotations

from typing import Optional

import httpx
from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session

from api.deps import patient_for
from config.settings import get_settings
from src.auth.security import require_roles
from src.db.models import Patient, User
from src.db.session import get_session
from src.ingestion import fhir_import

router = APIRouter(tags=["ehr"])
clinician = require_roles("doctor", "admin")


class SampleIn(BaseModel):
    name: str


class FetchIn(BaseModel):
    fhir_patient_id: str
    base_url: Optional[str] = None
    doctor_id: Optional[int] = None   # admin only: assign the imported patient to this doctor


def _doctor_id(user: User, requested: Optional[int] = None) -> Optional[int]:
    return user.id if user.role == "doctor" else requested


@router.get("/ehr/samples", dependencies=[Depends(clinician)])
def samples() -> list[str]:
    return fhir_import.list_samples()


@router.post("/ehr/import/sample")
def import_sample(body: SampleIn, doctor_id: Optional[int] = None, user: User = Depends(clinician),
                  session: Session = Depends(get_session)) -> dict:
    try:
        return fhir_import.import_sample(session, body.name, _doctor_id(user, doctor_id))
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))


@router.post("/ehr/import/bundle")
def import_bundle(bundle: dict = Body(...), doctor_id: Optional[int] = None, user: User = Depends(clinician),
                  session: Session = Depends(get_session)) -> dict:
    if bundle.get("resourceType") != "Bundle":
        raise HTTPException(422, "Body must be a FHIR Bundle")
    try:
        return fhir_import.import_bundle(session, bundle, _doctor_id(user, doctor_id))
    except ValueError as e:
        raise HTTPException(422, str(e))


@router.get("/ehr/server", dependencies=[Depends(clinician)])
def server(base_url: Optional[str] = None) -> dict:
    """Is the hospital FHIR server reachable? (GET {base}/metadata)"""
    return fhir_import.server_status(base_url)


@router.get("/ehr/search", dependencies=[Depends(clinician)])
def search(name: str = "", diabetes_only: bool = True, base_url: Optional[str] = None,
           session: Session = Depends(get_session)) -> list[dict]:
    try:
        return fhir_import.search_patients(session, name, diabetes_only, base_url)
    except httpx.HTTPStatusError as e:
        raise HTTPException(502, f"FHIR server said {e.response.status_code}")
    except httpx.HTTPError as e:
        raise HTTPException(504, f"Could not reach the FHIR server: {e}")


@router.get("/ehr/links", dependencies=[Depends(clinician)])
def links(session: Session = Depends(get_session)) -> dict:
    return {"patients": fhir_import.linked_patients(session), "sync_minutes": get_settings().ehr_sync_minutes}


@router.post("/ehr/sync", dependencies=[Depends(clinician)])
def sync(session: Session = Depends(get_session)) -> dict:
    """Re-pull every linked hospital patient now."""
    return fhir_import.sync_all(session)


@router.post("/ehr/fetch")
def fetch(body: FetchIn, user: User = Depends(clinician), session: Session = Depends(get_session)) -> dict:
    try:
        return fhir_import.fetch_patient(session, body.fhir_patient_id, _doctor_id(user, body.doctor_id),
                                         body.base_url)
    except httpx.HTTPStatusError as e:
        raise HTTPException(502, f"FHIR server said {e.response.status_code} for patient "
                                 f"{body.fhir_patient_id}")
    except httpx.HTTPError as e:
        raise HTTPException(504, f"Could not reach the FHIR server: {e}")
    except ValueError as e:
        raise HTTPException(422, str(e))


@router.get("/patients/{pid}/fhir")
def export(p: Patient = Depends(patient_for), session: Session = Depends(get_session)) -> dict:
    return fhir_import.export_bundle(session, p.id)
