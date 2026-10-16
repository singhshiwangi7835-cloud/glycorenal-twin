"""FT6 demo mode (runs last: it re-seeds the shared test database, then restores it)."""

from pathlib import Path

from tests.conftest import login

ROOT = Path(__file__).resolve().parents[1]


def test_demo_mode_story(client):
    adm = login(client, "admin", "admin123")
    assert client.post("/admin/demo-mode", headers=login(client, "dr.mehta", "doctor123")).status_code == 403
    r = client.post("/admin/demo-mode", headers=adm).json()
    assert r["status"] == "demo story ready" and "today,UACR,85" in r["lab_csv"]
    doc = login(client, "dr.mehta", "doctor123")
    before = client.get("/patients/IND-0042/twin", headers=doc).json()
    assert before["state"]["kidney"]["a_stage"] == "A1"            # this week's labs not there yet
    assert before["predictions"]["dkd_3y"]["kind"] == "onset"
    csv = (ROOT / "docs" / "demo" / "ramesh_labs_today.csv").read_bytes()
    up = client.post("/patients/IND-0042/labs/upload", headers=doc, files={"file": ("l.csv", csv, "text/csv")}).json()
    assert up["saved"] == 5 and any("A1 to A2" in a for a in up["new_alerts"])
    after = client.get("/patients/IND-0042/twin", headers=doc).json()
    assert after["state"]["kidney"]["stage"] == "G2-A2" and after["predictions"]["dkd_3y"]["kind"] == "progression"
    assert after["state"]["labs"]["uacr"]["days_old"] == 0
    client.post("/admin/reset-demo", headers=adm)  # leave the normal demo data behind
