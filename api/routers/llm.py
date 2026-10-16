"""AI assistant (explains the twin; never predicts).

GET  /assistant/status                      which LLM is configured
POST /patients/{pid}/assistant              {"mode": "...", "language": "en"|"hi", "question": "..."}
Patients may only use patient modes (patient_summary, chat_patient, report_patient).
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session

from api.deps import is_clinician, patient_for
from src.auth.security import current_user
from src.db.models import Patient, User
from src.db.session import get_session
from src.llm import assistant
from src.llm.prompts import MODES, PATIENT_MODES

router = APIRouter(tags=["assistant"])


class AskIn(BaseModel):
    mode: str
    language: str = "en"
    question: Optional[str] = None


@router.get("/assistant/status", dependencies=[Depends(current_user)])
def status() -> dict:
    return assistant.status()


@router.post("/patients/{pid}/assistant")
def ask(body: AskIn, p: Patient = Depends(patient_for), user: User = Depends(current_user),
        session: Session = Depends(get_session)) -> dict:
    if body.mode not in MODES:
        raise HTTPException(422, f"mode must be one of {MODES}")
    if not is_clinician(user) and body.mode not in PATIENT_MODES:
        raise HTTPException(403, "Patients can use: " + ", ".join(PATIENT_MODES))
    if body.mode.startswith("chat") and not (body.question or "").strip():
        raise HTTPException(422, "Type a question")
    return assistant.ask(session, p.id, body.mode, body.language, body.question)
