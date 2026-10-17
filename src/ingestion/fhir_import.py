"""Hospital EHR via FHIR R4: import a bundle, fetch from a FHIR server, export a twin.

import_bundle()   Bundle (Synthea sample or hospital) -> Patient, Observations, Medications
fetch_patient()   GET {FHIR_BASE_URL}/Patient/{id}/$everything (default: public HAPI R4 test server);
                  the patient stays LINKED to that server and is re-synced automatically
server_status()   GET {base}/metadata: is the hospital server reachable, which FHIR version
search_patients() find patients on the server by name, optionally only those with type 2 diabetes
sync_all()        re-pull every linked patient (background job, every EHR_SYNC_MINUTES)
export_bundle()   our patient -> FHIR R4 Bundle (GET /patients/{id}/fhir)

Mapping: Patient (name, gender, birthDate); Condition (SNOMED 44054006 T2DM -> diabetes onset
year, hypertension, diabetic kidney disease); Observation by LOINC via loinc_map.csv +
loinc_aliases.csv (BP panels read from components; smoking status 72166-2); MedicationRequest
-> Medication with a default reminder schedule. Each resource is validated with fhir.resources
(R4B models, compatible with R4); invalid resources are counted and still mapped where possible.
Imported patients get de-identified ids (EHR-0001...); the FHIR id is kept in Patient.fhir_id.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

import httpx
from fhir.resources.R4B import get_fhir_model_class
from sqlmodel import Session, select

from config.settings import get_settings
from src.clinical import loinc
from src.clinical.drugs import classify
from src.db.models import DeviceConnection, Medication, Observation, Patient
from src.ingestion.translator import ObservationIn, save

SAMPLES = Path(__file__).resolve().parents[2] / "data" / "fhir_samples"
SNOMED_T2DM = "44054006"
SNOMED_HYPERTENSION = {"38341003", "59621000"}
SNOMED_DIABETIC_KIDNEY = {"127013003", "431855005", "431856006", "433144002", "431857002",
                          "46177005", "90708001"}
BP_PANELS = {"85354-9", "55284-4"}

# default reminder times by drug class (doctor can edit in the Medications tab)
DEFAULT_TIMES = {"metformin": ["08:00", "20:00"], "insulin": ["08:00", "20:00"]}


def list_samples() -> list[str]:
    return sorted(p.name for p in SAMPLES.glob("*.json"))


def _validate(resource: dict) -> bool:
    try:
        get_fhir_model_class(resource["resourceType"]).model_validate(resource)
        return True
    except Exception:  # noqa: BLE001  (any validation problem: count it, keep going)
        return False


def _codes(concept: dict | None) -> list[str]:
    return [c.get("code", "") for c in (concept or {}).get("coding", [])]


def _when(r: dict) -> datetime | None:
    raw = r.get("effectiveDateTime") or (r.get("effectivePeriod") or {}).get("start") or r.get("issued")
    if not raw:
        return None
    t = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def _next_id(session: Session) -> str:
    ids = session.exec(select(Patient.id).where(Patient.id.like("EHR-%"))).all()
    n = max([int(i.split("-")[1]) for i in ids] or [0]) + 1
    return f"EHR-{n:04d}"


def import_bundle(session: Session, bundle: dict, doctor_id: int | None = None) -> dict:
    resources = [e.get("resource", {}) for e in bundle.get("entry", [])]
    by_type: dict[str, list[dict]] = {}
    for r in resources:
        by_type.setdefault(r.get("resourceType"), []).append(r)
    if not by_type.get("Patient"):
        raise ValueError("Bundle has no Patient resource")
    invalid = sum(not _validate(r) for r in resources)

    fp = by_type["Patient"][0]
    fhir_id = fp.get("id")
    patient = session.exec(select(Patient).where(Patient.fhir_id == fhir_id)).first() if fhir_id else None
    created = patient is None
    if created:
        name = (fp.get("name") or [{}])[0]
        display = " ".join(name.get("given", []) + [name.get("family", "")]).strip() or "EHR patient"
        birth = fp.get("birthDate", "1970-01-01")
        patient = Patient(id=_next_id(session), display_name=display,
                          sex="F" if fp.get("gender") == "female" else "M",
                          birth_year=int(birth[:4]), fhir_id=fhir_id, assigned_doctor_id=doctor_id)
        session.add(patient)

    # conditions
    for c in by_type.get("Condition", []):
        codes = set(_codes(c.get("code")))
        onset = c.get("onsetDateTime") or c.get("recordedDate")
        if SNOMED_T2DM in codes and onset:
            year = int(onset[:4])
            patient.dm_diagnosis_year = min(patient.dm_diagnosis_year or year, year)
        if codes & SNOMED_HYPERTENSION:
            patient.hypertension = True
    session.commit()

    # observations
    items, ignored = [], 0
    for o in by_type.get("Observation", []):
        t = _when(o)
        codes = _codes(o.get("code"))
        if t is None:
            ignored += 1
            continue
        if "72166-2" in codes:  # smoking status
            text = json.dumps(o.get("valueCodeableConcept", {})).lower()
            if t.year >= datetime.now().year - 2 and ("every day" in text or "current" in text):
                patient.smoker = True
            continue
        pairs = []
        if set(codes) & BP_PANELS:
            for comp in o.get("component", []):
                pairs.append((_codes(comp.get("code")), comp.get("valueQuantity")))
        else:
            pairs.append((codes, o.get("valueQuantity")))
        for cds, q in pairs:
            var = next((loinc.variable_for(c) for c in cds if loinc.variable_for(c)), None)
            if var is None or not q or q.get("value") is None:
                ignored += 1
                continue
            unit = (q.get("unit") or q.get("code") or "").replace("mm[Hg]", "mmHg").replace("{", "").replace("}", "")
            if var in ("sbp", "dbp", "heart_rate", "steps", "bmi"):
                unit = ""  # these come in the standard unit with UCUM spellings
            items.append(ObservationIn(patient_id=patient.id, variable=var, value=float(q["value"]),
                                       unit=unit, time=t, source="ehr", device="lab"))
    result = save(session, items, run_loop=False)

    # medications
    meds_added = 0
    existing = {m.drug for m in session.exec(select(Medication).where(Medication.patient_id == patient.id))}
    for mr in by_type.get("MedicationRequest", []):
        if mr.get("status") not in (None, "active"):
            continue
        concept = mr.get("medicationCodeableConcept") or {}
        drug = concept.get("text") or next((c.get("display") for c in concept.get("coding", [])), None)
        if not drug or drug in existing:
            continue
        classes = classify(drug) - {"acei_arb"}
        cls = sorted(classes)[0] if classes else ""
        authored = mr.get("authoredOn")
        session.add(Medication(patient_id=patient.id, drug=drug, drug_class=cls,
                               frequency="twice daily" if cls in DEFAULT_TIMES else "once daily",
                               times=DEFAULT_TIMES.get(cls, ["08:00"]),
                               start_date=date.fromisoformat(authored[:10]) if authored else None,
                               source="ehr"))
        existing.add(drug)
        meds_added += 1
    session.commit()

    from src.twin.engine import run_full
    twin = run_full(session, patient.id)
    return {"patient_id": patient.id, "created": created, "display_name": patient.display_name,
            "observations_saved": result["saved"], "observations_skipped": result["skipped"] + ignored,
            "medications_added": meds_added, "invalid_resources": invalid,
            "dkd_risk_3y": (twin.get("dkd") or {}).get("risk_3y")}


def import_sample(session: Session, name: str, doctor_id: int | None = None) -> dict:
    path = SAMPLES / Path(name).name
    if not path.exists():
        raise FileNotFoundError(f"No sample {name!r}. Available: {list_samples()}")
    return import_bundle(session, json.loads(path.read_text(encoding="utf-8")), doctor_id)


EHR_PROVIDER = "ehr_fhir"   # DeviceConnection.provider for a patient linked to a hospital FHIR server


def _base(base_url: str | None) -> str:
    return (base_url or get_settings().fhir_base_url).rstrip("/")


def _client(timeout: float = 30) -> httpx.Client:
    headers = {"Accept": "application/fhir+json"}
    token = get_settings().fhir_auth_token
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return httpx.Client(timeout=timeout, headers=headers, follow_redirects=True)


def server_status(base_url: str | None = None) -> dict:
    base = _base(base_url)
    try:
        with _client(15) as c:
            r = c.get(f"{base}/metadata", params={"_summary": "true"})
            r.raise_for_status()
            m = r.json()
        return {"ok": True, "base_url": base, "fhir_version": m.get("fhirVersion"),
                "software": (m.get("software") or {}).get("name"), "auth": bool(get_settings().fhir_auth_token)}
    except (httpx.HTTPError, ValueError) as e:
        return {"ok": False, "base_url": base, "error": str(e)[:200]}


def search_patients(session: Session, name: str = "", diabetes_only: bool = True,
                    base_url: str | None = None, count: int = 20) -> list[dict]:
    """Patients on the FHIR server. diabetes_only: has a Condition coded SNOMED 44054006 (T2DM)."""
    params: dict = {"_count": count}
    if name.strip():
        params["name"] = name.strip()
    if diabetes_only:
        params["_has:Condition:patient:code"] = f"http://snomed.info/sct|{SNOMED_T2DM}"
    with _client() as c:
        r = c.get(f"{_base(base_url)}/Patient", params=params)
        r.raise_for_status()
        bundle = r.json()
    local = {p.fhir_id: p.id for p in session.exec(select(Patient).where(Patient.fhir_id.is_not(None)))}
    out = []
    for e in bundle.get("entry", []):
        p = e.get("resource", {})
        if p.get("resourceType") != "Patient":
            continue
        n = (p.get("name") or [{}])[0]
        out.append({"fhir_id": p.get("id"),
                    "name": " ".join(n.get("given", []) + [n.get("family", "")]).strip() or "(no name)",
                    "gender": p.get("gender"), "birth_date": p.get("birthDate"),
                    "imported_as": local.get(p.get("id"))})
    return out


def _link(session: Session, patient_id: str, base: str, fhir_id: str, status: str = "linked") -> None:
    conn = session.exec(select(DeviceConnection).where(DeviceConnection.patient_id == patient_id,
                                                       DeviceConnection.provider == EHR_PROVIDER)).first()
    if conn is None:
        conn = DeviceConnection(patient_id=patient_id, provider=EHR_PROVIDER)
    conn.status = status  # "linked", not "connected": no CGM is expected from a hospital record
    conn.tokens = {"base_url": base, "fhir_id": fhir_id}
    conn.last_sync = datetime.now(timezone.utc)
    session.add(conn)
    session.commit()


def linked_patients(session: Session) -> list[dict]:
    rows = session.exec(select(DeviceConnection).where(DeviceConnection.provider == EHR_PROVIDER)).all()
    return [{"patient_id": c.patient_id, "fhir_id": c.tokens.get("fhir_id"), "server": c.tokens.get("base_url"),
             "status": c.status, "last_sync": c.last_sync.isoformat() if c.last_sync else None} for c in rows]


def sync_all(session: Session) -> dict:
    """Re-pull every linked patient, so new labs and medicines arrive without typing anything again."""
    done, failed, new_obs = 0, 0, 0
    conns = session.exec(select(DeviceConnection).where(DeviceConnection.provider == EHR_PROVIDER)).all()
    for pid, tokens in [(c.patient_id, dict(c.tokens)) for c in conns]:
        base, fid = tokens.get("base_url"), tokens.get("fhir_id")
        try:
            r = fetch_patient(session, fid, base_url=base)
            done += 1
            new_obs += r["observations_saved"]
        except (httpx.HTTPError, ValueError) as e:
            failed += 1
            _link(session, pid, base, fid, status=f"error: {str(e)[:80]}")
    return {"synced": done, "failed": failed, "new_observations": new_obs}


def fetch_patient(session: Session, fhir_patient_id: str, doctor_id: int | None = None,
                  base_url: str | None = None, max_pages: int = 5) -> dict:
    """Pull one patient's record from a FHIR R4 server ($everything, following 'next' pages).
    Importing again updates the same patient (no duplicates), so this is also the re-sync."""
    base = _base(base_url)
    url = f"{base}/Patient/{fhir_patient_id}/$everything?_count=200"
    entries = []
    with _client() as client:
        for _ in range(max_pages):
            r = client.get(url)
            r.raise_for_status()
            page = r.json()
            entries += page.get("entry", [])
            nxt = next((link["url"] for link in page.get("link", []) if link.get("relation") == "next"), None)
            if not nxt:
                break
            url = nxt
    result = import_bundle(session, {"resourceType": "Bundle", "type": "collection", "entry": entries},
                           doctor_id)
    _link(session, result["patient_id"], base, fhir_patient_id)
    result["linked_to"] = base
    return result


def export_bundle(session: Session, patient_id: str) -> dict:
    """Our twin's data as a FHIR R4 collection Bundle."""
    p = session.get(Patient, patient_id)
    if p is None:
        raise LookupError(patient_id)
    ref = {"reference": f"Patient/{p.id}"}
    entries = [{"resource": {"resourceType": "Patient", "id": p.id,
                             "identifier": [{"system": "urn:glycorenal-twin:patient", "value": p.id}],
                             "gender": "female" if p.sex == "F" else "male",
                             "birthDate": f"{p.birth_year}-01-01"}}]
    if p.dm_diagnosis_year:
        entries.append({"resource": {
            "resourceType": "Condition", "id": f"{p.id}-t2dm", "subject": ref,
            "code": {"coding": [{"system": "http://snomed.info/sct", "code": SNOMED_T2DM,
                                 "display": "Diabetes mellitus type 2"}]},
            "onsetDateTime": f"{p.dm_diagnosis_year}-01-01"}})
    # labs and vitals only: 5-minute CGM and wearable heart-rate streams stay in the twin
    obs = session.exec(select(Observation).where(
        Observation.patient_id == p.id,
        ~(Observation.device.in_(["cgm", "fitbit"]) & Observation.loinc_code.in_(
            [loinc.code("glucose"), loinc.code("heart_rate")])))
        .order_by(Observation.effective_time)).all()
    for o in obs:
        entries.append({"resource": {
            "resourceType": "Observation", "id": f"obs-{o.id}", "status": "final", "subject": ref,
            "code": {"coding": [{"system": "http://loinc.org", "code": o.loinc_code, "display": o.name}]},
            "effectiveDateTime": o.effective_time.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "valueQuantity": {"value": round(o.value, 3), "unit": o.unit, "system": "http://unitsofmeasure.org"},
        }})
    for m in session.exec(select(Medication).where(Medication.patient_id == p.id)).all():
        entries.append({"resource": {
            "resourceType": "MedicationRequest", "id": f"med-{m.id}", "status": "active", "intent": "order",
            "subject": ref, "medicationCodeableConcept": {"text": f"{m.drug} {m.dose}".strip()},
            "dosageInstruction": [{"text": f"{m.frequency} at {', '.join(m.times)}".strip()}]}})
    bundle = {"resourceType": "Bundle", "type": "collection",
              "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "entry": entries}
    get_fhir_model_class("Bundle").model_validate(bundle)  # raises if we produced invalid FHIR
    return bundle
