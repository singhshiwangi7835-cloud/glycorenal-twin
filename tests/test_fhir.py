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
