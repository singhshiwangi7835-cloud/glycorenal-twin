"""The twin: state + predictions, and re-running it.

GET  /patients/{pid}/twin       state, latest predictions, active alerts
POST /patients/{pid}/twin/run   full re-run now (doctor/admin)
POST /twin/run-all              daily job, on demand (admin)
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlmodel import Session

from api.deps import patient_for
from src.alerts.engine import active_alerts
from src.auth.security import require_roles
from src.db.models import Patient
from src.db.session import get_session
from src.twin.engine import latest_predictions, run_all, run_full
from src.twin.state import build_state

router = APIRouter(tags=["twin"])


def alert_dict(a) -> dict:
    return {"id": a.id, "patient_id": a.patient_id, "type": a.type, "severity": a.severity,
            "message": a.message, "created_at": a.created_at.isoformat(),
            "acknowledged_at": a.acknowledged_at.isoformat() if a.acknowledged_at else None}


@router.get("/patients/{pid}/twin")
def get_twin(p: Patient = Depends(patient_for), session: Session = Depends(get_session)) -> dict:
    state = build_state(session, p.id)
    return {"state": state, "predictions": latest_predictions(session, p.id),
            "alerts": [alert_dict(a) for a in active_alerts(session, p.id)]}


@router.post("/patients/{pid}/twin/run", dependencies=[Depends(require_roles("doctor", "admin"))])
def rerun(p: Patient = Depends(patient_for), session: Session = Depends(get_session)) -> dict:
    return run_full(session, p.id)


@router.post("/twin/run-all", dependencies=[Depends(require_roles("admin"))])
def rerun_all(session: Session = Depends(get_session)) -> dict:
    return {"patients": run_all(session)}
