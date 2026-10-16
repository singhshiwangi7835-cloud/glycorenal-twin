"""PDF reports.

GET /patients/{pid}/report/doctor.pdf    clinical report (doctor/admin)
GET /patients/{pid}/report/patient.pdf   one-page English + Hindi report (the patient or a doctor)
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlmodel import Session

from api.deps import is_clinician, patient_for
from src.auth.security import current_user
from src.db.models import Patient, User
from src.db.session import get_session
from src.reports import pdf_doctor, pdf_patient
from src.reports.common import local_now

router = APIRouter(tags=["reports"])


def _pdf(content: bytes, name: str) -> Response:
    return Response(content, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.get("/patients/{pid}/report/doctor.pdf")
def doctor_report(p: Patient = Depends(patient_for), user: User = Depends(current_user),
                  session: Session = Depends(get_session)) -> Response:
    if not is_clinician(user):
        raise HTTPException(403, "The clinical report is for doctors")
    name = user.full_name if user.role == "doctor" else None
    return _pdf(pdf_doctor.build(session, p.id, name), f"{p.id}_clinical_{local_now():%Y%m%d}.pdf")


@router.get("/patients/{pid}/report/patient.pdf")
def patient_report(p: Patient = Depends(patient_for), session: Session = Depends(get_session)) -> Response:
    return _pdf(pdf_patient.build(session, p.id), f"{p.id}_my_health_{local_now():%Y%m%d}.pdf")
