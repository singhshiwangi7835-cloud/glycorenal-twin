"""FT4: reminders and adherence, meal spikes, simulator, Libre upload, vitals."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlmodel import Session

from src.db.models import Meal, Observation
from src.db.session import engine
from src.ingestion import simulator
from src.meals.engine import compute_spikes, top_spiking_foods
from src.reminders.engine import adherence, mark_missed
from tests.conftest import login

ROOT = Path(__file__).resolve().parents[1]


# ---------------- reminders and adherence ----------------

def test_seeded_adherence_is_poor_for_ramesh(client):
    r = client.get("/patients/IND-0042/reminders", headers=login(client, "ramesh", "patient123")).json()
    assert r["adherence_30d"]["pct"] < 80
    assert r["today"] and all(d["drug"] in ("Metformin", "Telmisartan") for d in r["today"])
    assert r["next"] is not None


def test_taking_a_dose_counts_toward_adherence(client):
    h = login(client, "priya", "patient123")
    today = client.get("/patients/IND-0215/reminders", headers=h).json()["today"]
    before = client.get("/patients/IND-0215/reminders", headers=h).json()["adherence_7d"]
    past = [d for d in today if d["status"] in ("pending", "missed")
            and datetime.fromisoformat(d["scheduled_time"]) <= datetime.now(timezone.utc)]
    if not past:  # early in the day: answer any dose; adherence counts it once its time has come
        past = today
    r = client.post(f"/doses/{past[0]['id']}", headers=h, json={"status": "taken"})
    assert r.status_code == 200
    assert client.post(f"/doses/{past[0]['id']}", headers=h, json={"status": "maybe"}).status_code == 422
    other = login(client, "ramesh", "patient123")
    assert client.post(f"/doses/{past[0]['id']}", headers=other, json={"status": "taken"}).status_code == 403
    after = r.json()["adherence_7d"]
    assert after["taken"] >= before["taken"]


def test_adherence_formula():
    with Session(engine) as s:
        a = adherence(s, "IND-0042", 30)
    assert a["pct"] == round(100 * a["taken"] / (a["taken"] + a["skipped"] + a["missed"]), 1)


def test_pending_dose_becomes_missed_after_two_hours():
    from src.db.models import DoseEvent, Medication
    with Session(engine) as s:
        med = s.exec(Medication.__table__.select().where(Medication.patient_id == "IND-0950")).first()
        e = DoseEvent(medication_id=med.id, scheduled_time=datetime.now(timezone.utc) - timedelta(hours=3))
        s.add(e)
        s.commit()
        s.refresh(e)
        assert mark_missed(s) >= 1
        s.refresh(e)
        assert e.status == "missed"


def test_prescribing_creates_reminders_and_reruns_twin(client):
    doc = login(client, "dr.mehta", "doctor123")
    r = client.post("/patients/IND-0042/medications", headers=doc,
                    json={"drug": "Dapagliflozin", "dose": "10 mg", "times": ["09:00"]}).json()
    med = r["medication"]
    assert med["drug_class"] == "sglt2i" and "sglt2i" in med["classes"] and r["dkd_risk_3y"] is not None
    today = client.get("/patients/IND-0042/reminders", headers=doc).json()["today"]
    assert any(d["drug"] == "Dapagliflozin" and d["local_time"] == "09:00" for d in today)
    twin = client.get("/patients/IND-0042/twin", headers=doc).json()["state"]
    assert twin["med_flags"]["on_sglt2i"] == 1
    # the advisor no longer offers SGLT2i
    opts = client.get("/patients/IND-0042/treatments", headers=doc).json()
    assert not any(o["option"] == "sglt2i" for o in opts["options"])
    # change time, then stop
    assert client.put(f"/medications/{med['id']}", headers=doc, json={"times": ["21:00"]}).json()["times"] == ["21:00"]
    assert client.put(f"/medications/{med['id']}", headers=doc, json={"times": ["9pm"]}).status_code == 422
    client.delete(f"/medications/{med['id']}", headers=doc)
    twin = client.get("/patients/IND-0042/twin", headers=doc).json()["state"]
    assert twin["med_flags"]["on_sglt2i"] == 0
    assert client.post("/patients/IND-0042/medications", headers=login(client, "ramesh", "patient123"),
                       json={"drug": "x"}).status_code == 403


# ---------------- meals and spikes ----------------

def test_seeded_meals_have_spikes_and_top_foods(client):
    h = login(client, "ramesh", "patient123")
    meals = client.get("/patients/IND-0042/meals", headers=h).json()
    spikes = [m["spike"] for m in meals if m["spike"] is not None]
    assert len(spikes) > 20 and 20 < sorted(spikes)[len(spikes) // 2] < 150
    top = client.get("/patients/IND-0042/meals/top-foods", headers=h).json()
    assert len(top) == 3 and top[0]["avg_spike"] >= top[-1]["avg_spike"]


def test_spike_is_peak_in_next_24_readings_minus_before():
    t0 = datetime.now(timezone.utc) - timedelta(days=40)
    with Session(engine) as s:
        for k in range(30):  # 100 before, then rises to 190 at reading 10, then falls
            v = 100 if k == 0 else 100 + 9 * min(k, 10) - 3 * max(0, k - 10)
            s.add(Observation(patient_id="IND-0724", loinc_code="2339-0", name="Glucose", value=v, unit="mg/dL",
                              effective_time=t0 + timedelta(minutes=5 * k), source="simulator", device="cgm"))
        meal = Meal(patient_id="IND-0724", time=t0 + timedelta(minutes=1),
                    items=[{"food": "Steamed white rice", "servings": 2}], total_carbs_g=84)
        s.add(meal)
        s.commit()
        compute_spikes(s, "IND-0724")
        s.refresh(meal)
        assert meal.glucose_before == 100 and meal.glucose_peak == 190 and meal.spike == 90


def test_top_foods_ignore_low_carb_side_dishes():
    now = datetime.now(timezone.utc)
    with Session(engine) as s:
        for k in range(3):
            s.add(Meal(patient_id="IND-0950", time=now - timedelta(days=1, hours=k), spike=120,
                       items=[{"food": "Steamed white rice", "servings": 2}, {"food": "Chicken curry", "servings": 1}]))
            s.add(Meal(patient_id="IND-0950", time=now - timedelta(days=2, hours=k), spike=30,
                       items=[{"food": "Moong dal chilla", "servings": 2}]))
        s.commit()
        foods = [f["food"] for f in top_spiking_foods(s, "IND-0950")]
    assert foods[0] == "Steamed white rice" and "Chicken curry" not in foods


def test_log_meal_validates_foods(client):
    h = login(client, "ramesh", "patient123")
    assert client.post("/patients/IND-0042/meals", headers=h, json={"items": [{"food": "Pizza"}]}).status_code == 422
    r = client.post("/patients/IND-0042/meals", headers=h,
                    json={"items": [{"food": "Idli", "servings": 3}, {"food": "Sambar", "servings": 1}]}).json()
    assert r["total_carbs_g"] == 36.0
    assert len(client.get("/foods", headers=h).json()) >= 50


# ---------------- simulator, Libre, vitals ----------------

def test_simulator_replays_and_scenarios_raise_alerts(client):
    h = login(client, "dr.mehta", "doctor123")
    assert client.post("/patients/IND-0839/devices/simulator/scenario", headers=h,
                       json={"scenario": "hypo"}).status_code == 409
    st = client.post("/patients/IND-0839/devices/simulator/start", headers=h, json={}).json()
    assert st["running"]
    with Session(engine) as s:
        sent = simulator.tick(s)
        assert any(x["patient_id"] == "IND-0839" for x in sent)
        client.post("/patients/IND-0839/devices/simulator/scenario", headers=h, json={"scenario": "hypo"})
        alerts = [a for _ in range(12) for x in simulator.tick(s) if x["patient_id"] == "IND-0839"
                  for a in x["new_alerts"]]
    assert any("severe hypoglycaemia" in a for a in alerts)
    assert any("Low glucose likely" in a for a in alerts)  # predicted before it happened
    client.post("/patients/IND-0839/devices/simulator/stop", headers=h)
    assert client.get("/patients/IND-0839/devices", headers=h).json()["simulator"]["running"] is False


def test_libre_csv_upload(client):
    h = login(client, "kavita", "patient123")
    csv = (ROOT / "data" / "fhir_samples" / "sample_libre.csv").read_bytes()
    r = client.post("/patients/IND-0724/devices/libre", headers=h,
                    files={"file": ("libre.csv", csv, "text/csv")}).json()
    assert r["readings"] > 250 and r["saved"] == r["readings"] and r["unit"] == "mg/dL"
    mmol = ("Glucose Data,Generated on,x\nDevice,Serial Number,Device Timestamp,Record Type,"
            "Historic Glucose mmol/L,Scan Glucose mmol/L\nLibre,1,01-10-2026 08:00,0,7.0,\n")
    r2 = client.post("/patients/IND-0724/devices/libre", headers=h, files={"file": ("m.csv", mmol, "text/csv")}).json()
    assert r2["unit"] == "mmol/L" and r2["saved"] == 1
    bad = client.post("/patients/IND-0724/devices/libre", headers=h, files={"file": ("x.csv", "a,b\n1,2\n", "text/csv")})
    assert bad.status_code == 422


def test_vitals_entry_and_dexcom_stub(client):
    h = login(client, "anita", "patient123")
    r = client.post("/patients/IND-0950/vitals", headers=h,
                    json={"systolic": 168, "diastolic": 96, "weight_kg": 59.5, "glucose_mg_dl": 145}).json()
    assert r["saved"] == 5  # sbp, dbp, weight, glucose, bmi
    assert any("Systolic BP 168" in a for a in r["new_alerts"])
    assert client.post("/patients/IND-0950/vitals", headers=h, json={"systolic": 120}).status_code == 422
    dev = client.get("/patients/IND-0950/devices", headers=h).json()
    assert dev["dexcom"]["available"] is False and "coming soon" in dev["dexcom"]["message"]
