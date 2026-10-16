"""End-to-end API tests on the seeded demo database (roles, twin, treatments, alerts, labs)."""

from datetime import datetime, timezone

from tests.conftest import login


def test_doctor_sees_all_patients_sorted_by_risk(client):
    rows = client.get("/patients", headers=login(client, "dr.mehta", "doctor123")).json()
    assert len(rows) >= 10
    risks = [r["dkd_risk_3y"] or 0 for r in rows]
    assert risks == sorted(risks, reverse=True)
    ramesh = next(r for r in rows if r["patient_id"] == "IND-0042")
    assert ramesh["kdigo"] == "G2-A2" and ramesh["hba1c"] == 8.4


def test_patient_sees_only_own_record(client):
    h = login(client, "ramesh", "patient123")
    assert [r["patient_id"] for r in client.get("/patients", headers=h).json()] == ["IND-0042"]
    assert client.get("/patients/IND-0042/twin", headers=h).status_code == 200
    assert client.get("/patients/IND-0107/twin", headers=h).status_code == 403
    assert client.get("/patients/NOPE/twin", headers=login(client, "dr.mehta", "doctor123")).status_code == 404


def test_twin_state_for_ramesh(client):
    t = client.get("/patients/IND-0042/twin", headers=login(client, "dr.mehta", "doctor123")).json()
    s = t["state"]
    assert 60 <= s["kidney"]["egfr"] <= 66 and s["kidney"]["a_stage"] == "A2"
    assert s["cgm"]["metrics"]["sufficiency_pct"] > 90
    assert s["adherence"]["pct_30d"] < 80
    assert t["predictions"]["dkd_3y"]["kind"] == "progression"
    assert any(a["type"] == "uacr_rising" for a in t["alerts"])


def test_treatments_doctor_vs_patient(client):
    doc = client.get("/patients/IND-0042/treatments", headers=login(client, "dr.mehta", "doctor123")).json()
    assert doc["options"][0]["absolute_reduction"] >= doc["options"][-1]["absolute_reduction"]
    sglt2 = next(o for o in doc["options"] if o["option"] == "sglt2i")
    assert sglt2["risk_after"] < sglt2["risk_before"] and "DAPA-CKD" in sglt2["summary"]
    assert any(n["option"] == "acei_arb" for n in doc["not_eligible"])  # already on telmisartan
    pat = client.get("/patients/IND-0042/treatments", headers=login(client, "ramesh", "patient123")).json()
    assert pat["options"] and all(o["kind"] == "lifestyle" for o in pat["options"])
    assert pat["not_eligible"] == [] and pat["warnings"] == []


def test_simulate_permissions(client):
    doc = login(client, "dr.mehta", "doctor123")
    r = client.post("/patients/IND-0042/treatments/simulate", headers=doc,
                    json={"options": ["sglt2i", "bp_control"]})
    assert r.status_code == 200 and r.json()["risk_after"] < r.json()["risk_before"]
    pat = login(client, "ramesh", "patient123")
    assert client.post("/patients/IND-0042/treatments/simulate", headers=pat,
                       json={"options": ["sglt2i"]}).status_code == 403
    assert client.post("/patients/IND-0042/treatments/simulate", headers=pat,
                       json={"options": ["steps_plus_2000"]}).status_code == 200


def test_low_glucose_reading_raises_one_critical_alert(client):
    h = login(client, "ramesh", "patient123")
    now = datetime.now(timezone.utc).isoformat()
    r = client.post("/patients/IND-0042/observations", headers=h,
                    json=[{"variable": "glucose", "value": 50, "time": now, "device": "fingerstick"}]).json()
    assert r["saved"] == 1 and any("severe hypoglycaemia" in a for a in r["new_alerts"])
    r2 = client.post("/patients/IND-0042/observations", headers=h,
                     json=[{"variable": "glucose", "value": 48, "device": "fingerstick"}]).json()
    assert not any("severe" in a for a in r2["new_alerts"])  # de-duplicated within 60 min
    dup = client.post("/patients/IND-0042/observations", headers=h,
                      json=[{"variable": "glucose", "value": 50, "time": now, "device": "fingerstick"}]).json()
    assert dup["saved"] == 0  # same patient + code + time + source


def test_mmol_glucose_is_converted(client):
    h = login(client, "dr.mehta", "doctor123")
    client.post("/patients/IND-0215/observations", headers=h,
                json=[{"variable": "glucose", "value": 7.0, "unit": "mmol/L", "device": "fingerstick"}])
    rows = client.get("/patients/IND-0215/observations?variable=glucose&hours=1&device=fingerstick",
                      headers=h).json()
    assert abs(rows[-1]["value"] - 126.1) < 0.2 and rows[-1]["unit"] == "mg/dL"


def test_lab_csv_upload_reruns_twin(client):
    h = login(client, "dr.mehta", "doctor123")
    today = datetime.now(timezone.utc).date().isoformat()
    csv = (f"date,test,value,unit\n{today},HbA1c,7.1,%\n{today},creatinine,0.95,mg/dL\n"
           f"{today},UACR,3.0,mg/mmol\n{today},magic,1,\n")
    r = client.post("/patients/IND-0618/labs/upload", headers=h,
                    files={"file": ("labs.csv", csv, "text/csv")}).json()
    assert r["saved"] == 3 and r["reruns"]["IND-0618"] == "full" and r["problems"]
    s = client.get("/patients/IND-0618/twin", headers=h).json()["state"]
    assert s["glycaemia"]["hba1c"] == 7.1 and abs(s["kidney"]["uacr"] - 26.5) < 0.2


def test_acknowledge_alert(client):
    doc = login(client, "dr.mehta", "doctor123")
    alerts = client.get("/alerts", headers=doc).json()
    assert alerts
    assert client.post(f"/alerts/{alerts[0]['id']}/ack",
                       headers=login(client, "ramesh", "patient123")).status_code == 403
    assert client.post(f"/alerts/{alerts[0]['id']}/ack", headers=doc).json()["acknowledged_at"]
