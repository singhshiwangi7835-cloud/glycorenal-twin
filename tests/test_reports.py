"""FT6: PDF reports, favourable-option cap, Hindi medicine question."""

from src.llm import guardrails
from tests.conftest import login


def test_doctor_pdf(client):
    r = client.get("/patients/IND-0042/report/doctor.pdf", headers=login(client, "dr.mehta", "doctor123"))
    assert r.status_code == 200 and r.content[:4] == b"%PDF" and len(r.content) > 50_000
    assert r.headers["content-type"] == "application/pdf"


def test_patient_pdf_and_permissions(client):
    pat = login(client, "ramesh", "patient123")
    r = client.get("/patients/IND-0042/report/patient.pdf", headers=pat)
    assert r.status_code == 200 and r.content[:4] == b"%PDF"
    assert client.get("/patients/IND-0042/report/doctor.pdf", headers=pat).status_code == 403
    assert client.get("/patients/IND-0107/report/patient.pdf", headers=pat).status_code == 403


def test_favourable_options_never_raise_risk(client):
    tr = client.get("/patients/IND-0042/treatments", headers=login(client, "dr.mehta", "doctor123")).json()
    for o in tr["options"]:
        assert o["risk_after"] <= o["risk_before"] + 1e-9, o["summary"]


def test_hindi_medicine_question_is_caught():
    assert guardrails.asks_about_medicine("क्या मैं मेटफॉर्मिन बंद कर दूँ?")
    assert guardrails.asks_about_medicine("Can I skip my insulin tonight?")
    assert not guardrails.asks_about_medicine("What should I eat for dinner?")
