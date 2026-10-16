"""Admin tools (minimal): overview, link patient to doctor, reset demo data.

GET  /admin/overview                    counts, device connections, running simulators
POST /admin/patients/{pid}/doctor       {"doctor_id": 2}
POST /admin/reset-demo                  wipe and re-seed the demo data (about 20 s)
POST /admin/demo-mode                   reset + set up the demo story (Ramesh without this week's labs,
                                        his live sensor running); see docs/demo_script.md
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, func, select

from pathlib import Path

from config.settings import get_settings
from src.auth.security import require_roles
from src.db.models import Alert, DeviceConnection, Observation, Patient, User
from src.db.session import get_session
from src.ingestion import simulator

LAB_CSV = Path(__file__).resolve().parents[2] / "docs" / "demo" / "ramesh_labs_today.csv"
router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_roles("admin"))])


class DoctorIn(BaseModel):
    doctor_id: int


@router.get("/overview")
def overview(session: Session = Depends(get_session)) -> dict:
    conns = session.exec(select(DeviceConnection)).all()
    return {
        "patients": session.exec(select(func.count(Patient.id))).one(),
        "users": session.exec(select(func.count(User.id))).one(),
        "observations": session.exec(select(func.count(Observation.id))).one(),
        "open_alerts": session.exec(select(func.count(Alert.id)).where(Alert.acknowledged_at.is_(None))).one(),
        "doctors": [{"id": u.id, "username": u.username, "full_name": u.full_name}
                    for u in session.exec(select(User).where(User.role == "doctor")).all()],
        "patient_doctor": [{"patient_id": p.id, "display_name": p.display_name, "doctor_id": p.assigned_doctor_id}
                           for p in session.exec(select(Patient).order_by(Patient.id)).all()],
        "devices": [{"patient_id": c.patient_id, "provider": c.provider, "status": c.status,
                     "last_sync": c.last_sync.isoformat() if c.last_sync else None} for c in conns],
        "simulators": simulator.status(),
    }


@router.post("/patients/{pid}/doctor")
def link_doctor(pid: str, body: DoctorIn, session: Session = Depends(get_session)) -> dict:
    p = session.get(Patient, pid)
    d = session.get(User, body.doctor_id)
    if p is None or d is None or d.role != "doctor":
        raise HTTPException(404, "patient or doctor not found")
    p.assigned_doctor_id = d.id
    session.add(p)
    session.commit()
    return {"patient_id": pid, "doctor_id": d.id}


def _reseed(story: bool) -> None:
    from src.db.seed import seed_demo
    from src.db.session import engine

    for st in simulator.status():
        with Session(engine) as s:
            simulator.stop(s, st["patient_id"])
    seed_demo(reset=True, story=story)
    with Session(engine) as s:
        for pid in [x.strip() for x in get_settings().sim_autostart.split(",") if x.strip()]:
            if s.get(Patient, pid):
                simulator.start(s, pid)


@router.post("/reset-demo")
def reset_demo() -> dict:
    _reseed(story=False)
    return {"status": "demo data reset"}


@router.post("/demo-mode")
def demo_mode() -> dict:
    _reseed(story=True)
    return {"status": "demo story ready",
            "next": "Log in as dr.mehta: Ramesh (IND-0042) has last labs from months ago. Upload "
                    "docs/demo/ramesh_labs_today.csv in his EHR tab to show the risk rise.",
            "lab_csv": LAB_CSV.read_text(encoding="utf-8")}

