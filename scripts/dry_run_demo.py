"""Dry run of the demo story (docs/demo_script.md) through the API, on a throwaway database.

Usage:  .\\.venv\\Scripts\\python.exe scripts/dry_run_demo.py
Prints each step and its result, saves sample PDFs to docs/samples/, and exits with an error
if any step fails. Your real database (data/twin.db) is not touched.
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["DATABASE_URL"] = f"sqlite:///{(Path(tempfile.mkdtemp()) / 'dry_run.db').as_posix()}"
os.environ["SCHEDULER_ENABLED"] = "false"   # no background threads; we drive the sensor by hand
os.environ["AUTO_SEED"] = "false"

from fastapi.testclient import TestClient  # noqa: E402
from sqlmodel import Session  # noqa: E402

from api.main import app  # noqa: E402
from src.db.session import engine  # noqa: E402
from src.ingestion import simulator  # noqa: E402

SAMPLES = ROOT / "docs" / "samples"
problems: list[str] = []


def step(n: int, title: str):
    print(f"\n[{n}] {title}")


def check(ok: bool, msg: str):
    print(("    OK  " if ok else "    !!  ") + msg)
    if not ok:
        problems.append(msg)


def login(c: TestClient, u: str, p: str) -> dict:
    return {"Authorization": f"Bearer {c.post('/auth/login', data={'username': u, 'password': p}).json()['access_token']}"}


def ticks(n: int, pid: str = "IND-0042") -> list[dict]:
    with Session(engine) as s:
        out = []
        for _ in range(n):
            out += [x for x in simulator.tick(s) if x["patient_id"] == pid]
        return out


def main() -> int:
    t0 = time.time()
    with TestClient(app) as c:
        from src.db.seed import seed_demo
        seed_demo(reset=True)
        adm = login(c, "admin", "admin123")

        step(1, "Admin: Demo mode (reset + story)")
        r = c.post("/admin/demo-mode", headers=adm)
        check(r.status_code == 200, f"demo mode: {r.json().get('status')}")
        doc, pat = login(c, "dr.mehta", "doctor123"), login(c, "ramesh", "patient123")

        step(2, "Admin: import a hospital EHR patient (FHIR R4, Synthea)")
        name = c.get("/ehr/samples", headers=adm).json()[0]
        r = c.post("/ehr/import/sample", headers=adm, json={"name": name}).json()
        check(r["created"] and r["observations_saved"] > 10,
              f"{name} -> {r['patient_id']}: {r['observations_saved']} observations, {r['medications_added']} medicines, "
              f"DKD risk {r['dkd_risk_3y']:.0%}")

        step(3, "Doctor: patient list and Ramesh before new labs")
        rows = c.get("/patients", headers=doc).json()
        ram = next(x for x in rows if x["patient_id"] == "IND-0042")
        before = ram["dkd_risk_3y"]
        check(ram["kdigo"] == "G2-A1", f"Ramesh {ram['kdigo']}, HbA1c {ram['hba1c']}%, UACR {ram['uacr']}, "
                                       f"risk {before:.0%} ({ram['risk_band']}), {len(rows)} patients listed")

        step(4, "Live CGM: sensor running")
        st = c.post("/patients/IND-0042/devices/simulator/start", headers=doc, json={}).json()
        sent = ticks(6)
        check(st["running"] and len(sent) == 6, f"6 readings: {[x['glucose'] for x in sent]}")

        step(5, "Patient: logs a rice meal -> spike + alert")
        r = c.post("/patients/IND-0042/meals", headers=pat,
                   json={"items": [{"food": "Steamed white rice", "servings": 2}, {"food": "Toor dal", "servings": 1}]}).json()
        sent = ticks(14)
        peak = max(x["glucose"] for x in sent)
        alerts = [a for x in sent for a in x["new_alerts"]]
        check(r["simulated_rise_added"] and peak > 250, f"meal {r['total_carbs_g']} g carbs; glucose peak {peak} mg/dL")
        check(any("above 250" in a for a in alerts), f"alerts: {alerts}")

        step(6, "Patient: medicines and a missed dose")
        rem = c.get("/patients/IND-0042/reminders", headers=pat).json()
        check(rem["adherence_7d"]["pct"] is not None, f"adherence 7 d {rem['adherence_7d']['pct']}% "
                                                      f"({rem['adherence_7d']['missed']} missed); today: "
                                                      f"{[(d['local_time'], d['drug'], d['status']) for d in rem['today']]}")

        step(7, "Doctor: new lab results arrive (lab CSV) -> twin re-runs, prediction confirmed")
        csv = (ROOT / "docs" / "demo" / "ramesh_labs_today.csv").read_bytes()
        r = c.post("/patients/IND-0042/labs/upload", headers=doc, files={"file": ("labs.csv", csv, "text/csv")}).json()
        tw = c.get("/patients/IND-0042/twin", headers=doc).json()
        after = tw["predictions"]["dkd_3y"]["risk_3y"]
        check(r["saved"] == 5 and r["reruns"].get("IND-0042") == "full", f"saved {r['saved']} labs, alerts {r['new_alerts']}")
        kind = tw["predictions"]["dkd_3y"]["kind"]
        check(kind == "progression" and tw["state"]["kidney"]["a_stage"] == "A2",
              f"prediction confirmed: onset risk was {before:.0%}; now KDIGO {tw['state']['kidney']['stage']} -> "
              f"{kind} risk {after:.0%}")

        step(8, "Doctor: ranked treatments")
        tr = c.get("/patients/IND-0042/treatments", headers=doc).json()
        top = tr["options"][0]
        check(top["option"] == "sglt2i", f"top: {top['summary']}")
        sim = c.post("/patients/IND-0042/treatments/simulate", headers=doc,
                     json={"options": ["sglt2i", "bp_control"]}).json()
        check(sim["risk_after"] < sim["risk_before"], f"what-if SGLT2i + BP: {sim['risk_before']:.0%} -> {sim['risk_after']:.0%}")

        step(9, "Doctor: prescribes dapagliflozin -> reminders + risk drops")
        r = c.post("/patients/IND-0042/medications", headers=doc,
                   json={"drug": "Dapagliflozin", "dose": "10 mg", "times": ["08:00"]}).json()
        check(r["dkd_risk_3y"] < after, f"risk {after:.0%} -> {r['dkd_risk_3y']:.0%} after prescribing "
                                        f"(simulation said {top['risk_after']:.0%})")

        step(10, "AI assistant (template if no key)")
        a = c.post("/patients/IND-0042/assistant", headers=doc, json={"mode": "doctor_summary"}).json()
        check(bool(a["text"]), f"doctor summary via {a['provider']} ({len(a['text'])} chars)")
        a = c.post("/patients/IND-0042/assistant", headers=pat,
                   json={"mode": "chat_patient", "language": "hi", "question": "क्या मैं मेटफॉर्मिन बंद कर दूँ?"}).json()
        check(a["guardrail"] in ("medicine question", "hypoglycaemia"), f"patient medicine question -> {a['guardrail']}")

        step(11, "Hypo scenario: predicted before it happens")
        simulator._sims["IND-0042"].rows["glucose"] = 150.0
        ticks(6)  # settle; the jump to 150 itself looks like a fall, so clear alerts afterwards
        from sqlmodel import select
        from src.db.models import Alert
        with Session(engine) as s:
            for a in s.exec(select(Alert).where(Alert.patient_id == "IND-0042", Alert.type == "predicted_hypo")).all():
                s.delete(a)
            s.commit()
        c.post("/patients/IND-0042/devices/simulator/scenario", headers=doc, json={"scenario": "hypo"})
        alerts = [a for x in ticks(12) for a in x["new_alerts"]]
        check(any("Low glucose likely" in a for a in alerts), f"alerts: {alerts}")

        step(12, "Both PDF reports")
        SAMPLES.mkdir(parents=True, exist_ok=True)
        for kind, hdr in (("doctor", doc), ("patient", pat)):
            r = c.get(f"/patients/IND-0042/report/{kind}.pdf", headers=hdr)
            ok = r.status_code == 200 and r.content[:4] == b"%PDF"
            (SAMPLES / f"{kind}_report_IND-0042.pdf").write_bytes(r.content)
            check(ok, f"{kind} PDF {len(r.content) // 1024} KB -> docs/samples/{kind}_report_IND-0042.pdf")
        simulator.stop(Session(engine), "IND-0042")

    print(f"\nDone in {time.time() - t0:.0f} s. " + ("All steps OK." if not problems else f"{len(problems)} problem(s):"))
    for p in problems:
        print("  -", p)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
