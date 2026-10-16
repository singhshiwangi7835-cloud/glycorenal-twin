"""Make small FHIR R4 sample bundles from real Synthea patients (no Java needed).

Reads data/raw/synthea/synthea_sample_data_csv_apr2020.zip (Synthea 1K synthetic patients),
picks living patients with type 2 diabetes (SNOMED 44054006) and recent kidney labs, and writes
one FHIR R4 Bundle per patient to data/fhir_samples/ with Patient, Condition, Observation
(last 3 years, codes we use) and MedicationRequest resources.

Synthea's data ends in 2020, so every date is shifted forward (same shift for the whole patient,
birth date included) so the latest visit is 7 days ago. The bundle meta tag says so.

Usage:  python scripts/make_fhir_samples.py
"""

from __future__ import annotations

import json
import sys
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.clinical import loinc  # noqa: E402

ZIP = ROOT / "data" / "raw" / "synthea" / "synthea_sample_data_csv_apr2020.zip"
OUT = ROOT / "data" / "fhir_samples"
T2DM, DIABETIC_KIDNEY = 44054006, 127013003
SMOKING_LOINC = "72166-2"


def _read(z: zipfile.ZipFile, name: str) -> pd.DataFrame:
    return pd.read_csv(z.open(f"csv/{name}.csv"), low_memory=False)


def _keep_code(code: str) -> bool:
    return code == SMOKING_LOINC or loinc.variable_for(code) is not None


def build_bundle(pid: str, pats, conds, obs, meds) -> dict:
    p = pats[pats.Id == pid].iloc[0]
    o = obs[obs.PATIENT == pid].copy()
    keep = {c for c in o.CODE.astype(str).unique() if _keep_code(c)}
    o = o[o.CODE.astype(str).isin(keep)]
    o["DATE"] = pd.to_datetime(o.DATE, utc=True)
    last = o.DATE.max()
    shift = (datetime.now(timezone.utc) - timedelta(days=7)) - last.to_pydatetime()
    o = o[o.DATE >= last - pd.Timedelta(days=3 * 365)]

    def d(x) -> str:
        return (pd.to_datetime(x, utc=True) + shift).strftime("%Y-%m-%dT%H:%M:%SZ")

    def day(x) -> str:
        return (pd.to_datetime(x, utc=True) + shift).strftime("%Y-%m-%d")

    ref = f"Patient/{pid}"
    entries = [{"resource": {
        "resourceType": "Patient", "id": pid,
        "name": [{"given": [str(p.FIRST)], "family": str(p.LAST)}],
        "gender": "male" if p.GENDER == "M" else "female",
        "birthDate": day(p.BIRTHDATE),
    }}]
    for _, c in conds[conds.PATIENT == pid].drop_duplicates("CODE").iterrows():
        entries.append({"resource": {
            "resourceType": "Condition", "id": f"cond-{pid[:8]}-{c.CODE}",
            "subject": {"reference": ref},
            "code": {"coding": [{"system": "http://snomed.info/sct", "code": str(c.CODE),
                                 "display": c.DESCRIPTION}], "text": c.DESCRIPTION},
            "clinicalStatus": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/condition-clinical",
                                           "code": "active" if pd.isna(c.STOP) else "resolved"}]},
            "onsetDateTime": d(c.START),
        }})
    for i, r in o.reset_index(drop=True).iterrows():
        res = {"resourceType": "Observation", "id": f"obs-{pid[:8]}-{i}", "status": "final",
               "subject": {"reference": ref}, "effectiveDateTime": d(r.DATE),
               "code": {"coding": [{"system": "http://loinc.org", "code": str(r.CODE),
                                    "display": r.DESCRIPTION}], "text": r.DESCRIPTION}}
        if r.TYPE == "numeric":
            res["valueQuantity"] = {"value": float(r.VALUE), "unit": str(r.UNITS),
                                    "system": "http://unitsofmeasure.org"}
        else:
            res["valueCodeableConcept"] = {"text": str(r.VALUE)}
        entries.append({"resource": res})
    m = meds[(meds.PATIENT == pid) & meds.STOP.isna()].drop_duplicates("CODE")
    for _, r in m.iterrows():
        entries.append({"resource": {
            "resourceType": "MedicationRequest", "id": f"med-{pid[:8]}-{r.CODE}", "status": "active",
            "intent": "order", "subject": {"reference": ref}, "authoredOn": d(r.START),
            "medicationCodeableConcept": {"coding": [{"system": "http://www.nlm.nih.gov/research/umls/rxnorm",
                                                      "code": str(r.CODE), "display": r.DESCRIPTION}],
                                          "text": r.DESCRIPTION},
        }})
    return {"resourceType": "Bundle", "type": "collection",
            "meta": {"tag": [{"code": "synthea-time-shifted",
                              "display": f"Synthea Apr 2020 sample; dates shifted by {shift.days} days"}]},
            "entry": entries}


def main(n: int = 3) -> None:
    with zipfile.ZipFile(ZIP) as z:
        pats, conds = _read(z, "patients"), _read(z, "conditions")
        obs, meds = _read(z, "observations"), _read(z, "medications")
    dm = set(conds[conds.CODE == T2DM].PATIENT)
    alive = set(pats[pats.DEATHDATE.isna()].Id)
    kidney_labs = obs[obs.CODE.isin(["38483-4", "14959-1", "4548-4"])].groupby("PATIENT").CODE.nunique()
    has_labs = set(kidney_labs[kidney_labs == 3].index)
    dkd = set(conds[conds.CODE == DIABETIC_KIDNEY].PATIENT)
    pool = sorted(dm & alive & has_labs)
    chosen = [p for p in pool if p in dkd][:2] + [p for p in pool if p not in dkd][:1]
    OUT.mkdir(parents=True, exist_ok=True)
    for pid in chosen[:n]:
        b = build_bundle(pid, pats, conds, obs, meds)
        p = pats[pats.Id == pid].iloc[0]
        name = f"synthea_{str(p.FIRST).rstrip('0123456789').lower()}_{pid[:8]}.json"
        (OUT / name).write_text(json.dumps(b, indent=1))
        kinds = pd.Series([e["resource"]["resourceType"] for e in b["entry"]]).value_counts().to_dict()
        print(f"{name}: {kinds}, diabetic kidney disease: {pid in dkd}")


if __name__ == "__main__":
    main()
