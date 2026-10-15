"""Tests for the legacy v0.1 twin (in-memory demo patients), kept until FAST TRACK step 3."""

from src.demo_patients import DEMO_BY_ID
from src.model2_treatment.advisor import eligibility
from src.patient_state.builder import build_state
from src.twin.loop import run_twin

def test_twin_runs_for_all_demo_patients():
    for p in DEMO_BY_ID.values():
        t = run_twin(p)
        assert 0 <= t["prediction"]["dkd_risk_3y"] <= 1
        assert t["doctor_summary"] and t["patient_message"]


def test_options_reduce_risk_and_are_ranked():
    rec = run_twin(DEMO_BY_ID["IND-0107"], with_text=False)["recommendation"]
    reductions = [o["absolute_reduction"] for o in rec["ranked_options"]]
    assert reductions == sorted(reductions, reverse=True)
    assert all(o["risk_after"] <= o["risk_before"] for o in rec["ranked_options"])


def test_eligibility_rules():
    # IND-0333: eGFR ~30, on metformin + sulfonylurea, K 5.1
    elig, warnings = eligibility(build_state(DEMO_BY_ID["IND-0333"]))
    assert elig["sglt2i"] == "eligible"          # eGFR >= 20
    assert elig["finerenone"] != "eligible"      # potassium > 5.0
    assert any("Metformin" in w for w in warnings)
    assert any("Sulfonylurea" in w for w in warnings)


def test_patient_never_sees_drug_options(client):
    v = client.get("/legacy/patients/IND-0107/patient-view").json()
    assert all(o["kind"] == "lifestyle" for o in v["lifestyle_options"])
    assert "recommendation" not in v


def test_legacy_api_endpoints(client):
    assert client.get("/health").json()["status"] == "ok"
    rows = client.get("/legacy/patients").json()
    assert len(rows) == 5
    assert rows[0]["dkd_risk_3y"] >= rows[-1]["dkd_risk_3y"]
    assert client.get("/legacy/patients/NOPE/twin").status_code == 404
    r = client.post("/legacy/patients/IND-0042/ask", json={"question": "why?", "mode": "doctor"})
    assert r.status_code == 200 and r.json()["answer"]
