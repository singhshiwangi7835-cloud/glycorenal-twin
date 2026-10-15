"""FastAPI backend for GlycoRenal Twin.

Run locally:  uvicorn api.main:app --reload     Docs: http://localhost:8000/docs
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from src.demo_patients import DEMO, DEMO_BY_ID
from src.llm import assistant
from src.model1_risk import model as model1
from src.patient_state.builder import PatientInput
from src.twin import patient_view, run_twin

app = FastAPI(
    title="GlycoRenal Twin API",
    description="Digital twin for T2DM glycaemic control and DKD prevention. "
                "Decision support only; not for autonomous prescribing.",
    version="0.1.0",
)

# in-memory store; replace with a database / FHIR server later
PATIENTS: dict[str, PatientInput] = dict(DEMO_BY_ID)


class AskRequest(BaseModel):
    question: str
    mode: str = "doctor"  # doctor | patient
    lang: str = "English"


@app.on_event("startup")
def _warm() -> None:
    model1.load()


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "model": model1.load()["dkd_model_name"],
            "metrics": model1.load()["metrics"]}


@app.get("/patients")
def list_patients() -> list[dict]:
    rows = []
    for p in PATIENTS.values():
        t = run_twin(p, with_text=False)
        rows.append({
            "patient_id": p.patient_id,
            "age": p.profile.age, "sex": p.profile.sex,
            "hba1c": p.labs.hba1c, "egfr": t["state"]["derived"]["egfr"],
            "kdigo": t["state"]["derived"]["kdigo"],
            "kdigo_colour": t["state"]["derived"]["kdigo_colour"],
            "dkd_risk_3y": t["prediction"]["dkd_risk_3y"],
            "risk_band": t["prediction"]["dkd_risk_band"],
            "n_alerts": len([a for a in t["alerts"] if a["level"] != "info"]),
        })
    return sorted(rows, key=lambda r: -r["dkd_risk_3y"])


def _get(pid: str) -> PatientInput:
    if pid not in PATIENTS:
        raise HTTPException(404, f"patient {pid} not found")
    return PATIENTS[pid]


@app.get("/patients/{pid}/twin")
def twin(pid: str, lang: str = "English") -> dict:
    return run_twin(_get(pid), lang=lang)


@app.get("/patients/{pid}/patient-view")
def patient_app_view(pid: str, lang: str = "English") -> dict:
    return patient_view(run_twin(_get(pid), lang=lang))


@app.post("/patients")
def upsert_patient(p: PatientInput) -> dict:
    """Add or update a patient (new labs, CGM upload, prescription change) and re-run the twin."""
    PATIENTS[p.patient_id] = p
    return run_twin(p)


@app.post("/patients/{pid}/ask")
def ask(pid: str, req: AskRequest) -> dict:
    t = run_twin(_get(pid), with_text=False)
    if req.mode == "patient":
        t = {**t, "recommendation": {"ranked_options": t["lifestyle_options"],
                                      "safety_warnings": []}}
        answer = assistant.patient_explain(t, lang=req.lang, question=req.question)
    else:
        answer = assistant.doctor_summary(t, question=req.question)
    return {"answer": answer}


@app.post("/twin/evaluate")
def evaluate(p: PatientInput) -> dict:
    """Run the twin on a patient without storing them."""
    return run_twin(p)
