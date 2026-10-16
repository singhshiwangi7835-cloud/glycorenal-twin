"""Alerts.

GET  /alerts                      doctor/admin: all active alerts; patient: own
GET  /patients/{pid}/alerts       one patient (add ?include_acknowledged=true for history)
POST /alerts/{alert_id}/ack       doctor/admin acknowledges
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from api.deps import is_clinician, patient_for
from api.routers.twin import alert_dict
from src.alerts.engine import active_alerts
from src.auth.security import current_user, require_roles
from src.db.models import Alert, Patient, User
from src.db.session import get_session

router = APIRouter(tags=["alerts"])


@router.get("/alerts")
def all_alerts(user: User = Depends(current_user), session: Session = Depends(get_session)) -> list[dict]:
    pid = None if is_clinician(user) else user.patient_id
    return [alert_dict(a) for a in active_alerts(session, pid)]


@router.get("/patients/{pid}/alerts")
def patient_alerts(include_acknowledged: bool = False, p: Patient = Depends(patient_for),
                   session: Session = Depends(get_session)) -> list[dict]:
    if not include_acknowledged:
        return [alert_dict(a) for a in active_alerts(session, p.id)]
    rows = session.exec(select(Alert).where(Alert.patient_id == p.id)
                        .order_by(Alert.created_at.desc()).limit(200)).all()
    return [alert_dict(a) for a in rows]


@router.post("/alerts/{alert_id}/ack")
def acknowledge(alert_id: int, user: User = Depends(require_roles("doctor", "admin")),
                session: Session = Depends(get_session)) -> dict:
    a = session.get(Alert, alert_id)
    if a is None:
        raise HTTPException(404, "alert not found")
    a.acknowledged_by, a.acknowledged_at = user.id, datetime.now(timezone.utc)
    session.add(a)
    session.commit()
    return alert_dict(a)
