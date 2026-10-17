"""FT5: AI assistant guardrails, fallback, retrieval and permissions (no LLM key needed)."""

from datetime import datetime, timezone

from src.llm import guardrails, rag
from src.llm.client import providers
from tests.conftest import login


def test_no_llm_configured_in_tests():
    assert providers() == [] or all(len(p) == 4 for p in providers())


def test_retrieval_finds_relevant_guideline():
    hits = rag.retrieve("finerenone potassium UACR", k=3)
    assert hits and "finerenone" in hits[0]["title"].lower() + hits[0]["text"].lower()
    assert all(h["source"] for h in hits)


def test_medicine_change_filter_english_and_hindi():
    assert guardrails.violates_patient_rules("You should stop metformin today.")
    assert guardrails.violates_patient_rules("Increase your insulin dose by 2 units.")
    assert guardrails.violates_patient_rules("मेटफॉर्मिन की दवा बंद कर दें।")
    assert not guardrails.violates_patient_rules("Please discuss your metformin dose with your doctor.")
    assert not guardrails.violates_patient_rules("Walk for 15 minutes after dinner.")


def test_doctor_summary_template_has_numbers(client):
    r = client.post("/patients/IND-0042/assistant", headers=login(client, "dr.mehta", "doctor123"),
                    json={"mode": "doctor_summary"}).json()
    assert "IND-0042" in r["text"] and "HbA1c 8.4%" in r["text"] and "KDIGO G2-A2" in r["text"]
    assert "Decision support only" not in r["text"]
    assert "Ramesh" not in r["text"]  # de-identified
    if r["offline"]:
        assert r["provider"] == "template"


def test_patient_summary_in_hindi_has_no_drug_options(client):
    r = client.post("/patients/IND-0215/assistant", headers=login(client, "priya", "patient123"),
                    json={"mode": "patient_summary", "language": "hi"}).json()
    assert "HbA1c" in r["text"] and "डॉक्टर" in r["text"]
    assert "SGLT2" not in r["text"] and "dapagliflozin" not in r["text"].lower()


def test_patient_medicine_question_gets_fixed_reply(client):
    r = client.post("/patients/IND-0950/assistant", headers=login(client, "anita", "patient123"),
                    json={"mode": "chat_patient", "question": "Can I stop my metformin?"}).json()
    assert r["guardrail"] == "medicine question" and "discuss this with your doctor" in r["text"]


def test_low_glucose_gives_fixed_safety_message(client):
    h = login(client, "kavita", "patient123")
    client.post("/patients/IND-0724/observations", headers=h,
                json=[{"variable": "glucose", "value": 52, "device": "cgm",
                       "time": datetime.now(timezone.utc).isoformat()}])
    r = client.post("/patients/IND-0724/assistant", headers=h,
                    json={"mode": "chat_patient", "question": "how am I doing?"}).json()
    assert r["guardrail"] == "hypoglycaemia" and "15 g" in r["text"]


def test_assistant_permissions(client):
    pat = login(client, "ramesh", "patient123")
    assert client.post("/patients/IND-0042/assistant", headers=pat,
                       json={"mode": "doctor_summary"}).status_code == 403
    assert client.post("/patients/IND-0107/assistant", headers=pat,
                       json={"mode": "patient_summary"}).status_code == 403
    assert client.post("/patients/IND-0042/assistant", headers=pat,
                       json={"mode": "chat_patient", "question": " "}).status_code == 422
    assert client.get("/assistant/status", headers=pat).json()["configured"] in (True, False)


def test_admin_overview_and_link_doctor(client):
    adm = login(client, "admin", "admin123")
    ov = client.get("/admin/overview", headers=adm).json()
    assert ov["patients"] >= 10 and ov["doctors"]
    doc_id = ov["doctors"][0]["id"]
    assert client.post("/admin/patients/IND-0042/doctor", headers=adm, json={"doctor_id": doc_id}).status_code == 200
    assert client.get("/admin/overview", headers=login(client, "dr.mehta", "doctor123")).status_code == 403
