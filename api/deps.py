"""Shared API dependencies: patient access checks.

Doctors and admins can open any patient (prototype); a patient can open only their own record.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException
from sqlmodel import Session

from src.auth.security import can_see_patient, current_user
from src.db.models import Patient, User
from src.db.session import get_session


def patient_for(pid: str, user: User = Depends(current_user),
                session: Session = Depends(get_session)) -> Patient:
    """Path dependency for /patients/{pid}/...: 404 if unknown, 403 if not allowed."""
    if not can_see_patient(user, pid):
        raise HTTPException(403, "You can only see your own record")
    p = session.get(Patient, pid)
    if p is None:
        raise HTTPException(404, f"Patient {pid} not found")
    return p


def is_clinician(user: User) -> bool:
    return user.role in ("doctor", "admin")
