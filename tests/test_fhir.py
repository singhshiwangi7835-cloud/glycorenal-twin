"""FHIR R4 import (Synthea samples) and export."""

from fhir.resources.R4B.bundle import Bundle

from tests.conftest import login


def test_import_sample_creates_twin(client):
    h = login(client, "dr.mehta", "doctor123")
    names = client.get("/ehr/samples", headers=h).json()
    assert len(names) >= 3
    r = client.post("/ehr/import/sample", headers=h, json={"name": names[0]}).json()
    assert r["created"] and r["patient_id"].startswith("EHR-")
    assert r["observations_saved"] > 10 and r["medications_added"] >= 1
    assert r["dkd_risk_3y"] is not None and r["invalid_resources"] == 0
    again = client.post("/ehr/import/sample", headers=h, json={"name": names[0]}).json()
    assert not again["created"] and again["patient_id"] == r["patient_id"]
    assert again["observations_saved"] == 0


def test_patients_cannot_import(client):
    h = login(client, "ramesh", "patient123")
    assert client.post("/ehr/import/sample", headers=h, json={"name": "x.json"}).status_code == 403


def test_export_is_valid_fhir(client):
    h = login(client, "dr.mehta", "doctor123")
    b = client.get("/patients/IND-0042/fhir", headers=h).json()
    Bundle.model_validate(b)
    types = {e["resource"]["resourceType"] for e in b["entry"]}
    assert {"Patient", "Condition", "Observation", "MedicationRequest"} <= types
    codes = {e["resource"]["code"]["coding"][0]["code"] for e in b["entry"]
             if e["resource"]["resourceType"] == "Observation"}
    assert {"4548-4", "2160-0", "98979-8", "9318-7"} <= codes


def test_export_then_reimport_round_trip(client):
    h = login(client, "dr.mehta", "doctor123")
    b = client.get("/patients/IND-0215/fhir", headers=h).json()
    b["entry"][0]["resource"]["id"] = "roundtrip-1"
    r = client.post("/ehr/import/bundle", headers=h, json=b).json()
    assert r["created"] and r["observations_saved"] > 20


def test_hospital_link_search_and_resync(client, monkeypatch):
    """A fake FHIR server: import links the patient, a re-sync updates it without duplicates."""
    import json

    import httpx
    from sqlmodel import Session, select

    from src.db.models import Observation
    from src.db.session import engine
    from src.ingestion import fhir_import

    sample = json.loads((fhir_import.SAMPLES / fhir_import.list_samples()[-1]).read_text(encoding="utf-8"))
    pat = next(e["resource"] for e in sample["entry"] if e["resource"]["resourceType"] == "Patient")

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/metadata"):
            return httpx.Response(200, json={"fhirVersion": "4.0.1", "software": {"name": "Test FHIR"}})
        if req.url.path.endswith("/$everything"):
            return httpx.Response(200, json=sample)
        if req.url.path.endswith("/Patient"):
            assert "44054006" in str(req.url)  # type 2 diabetes filter
            return httpx.Response(200, json={"resourceType": "Bundle", "entry": [{"resource": pat}]})
        return httpx.Response(404)

    monkeypatch.setattr(fhir_import, "_client", lambda timeout=30: httpx.Client(transport=httpx.MockTransport(handler)))
    base = "https://fhir.example-hospital.test/R4"
    h = login(client, "admin", "admin123")
    assert client.get("/ehr/server", headers=h, params={"base_url": base}).json()["ok"]
    hits = client.get("/ehr/search", headers=h, params={"base_url": base}).json()
    assert hits[0]["fhir_id"] == pat["id"]
    r = client.post("/ehr/fetch", headers=h, json={"fhir_patient_id": pat["id"], "base_url": base}).json()
    pid = r["patient_id"]
    assert r["linked_to"] == base
    links = client.get("/ehr/links", headers=h).json()["patients"]
    assert any(x["patient_id"] == pid and x["status"] == "linked" for x in links)
    with Session(engine) as s:
        before = len(s.exec(select(Observation).where(Observation.patient_id == pid)).all())
    sync = client.post("/ehr/sync", headers=h).json()
    assert sync["synced"] >= 1 and sync["failed"] == 0
    with Session(engine) as s:
        assert len(s.exec(select(Observation).where(Observation.patient_id == pid)).all()) == before
    assert client.get("/ehr/search", headers=h, params={"base_url": base}).json()[0]["imported_as"] == pid
