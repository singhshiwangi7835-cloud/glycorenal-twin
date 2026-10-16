# GlycoRenal Twin

A proof-of-concept **digital twin** for people with **type 2 diabetes (T2DM)** that predicts
short-term glucose control and long-term **diabetic kidney disease (DKD)** risk, then
simulates which treatments would lower that risk.

Built for the **Digital Twin Challenge 2026** (Happiest Health, "Reimagining and Reforming
Healthcare in India" Summit, Bengaluru).

> Decision support only. The twin ranks options; the clinician decides. Patients only see
> lifestyle suggestions, never medicine changes.

## What it does

| Module | What it does |
|---|---|
| **Patient state** | One time-stamped record per patient: profile, labs, vitals, meds, CGM, plus derived eGFR (CKD-EPI 2021), KDIGO stage, CGM metrics (TIR, GMI, CV), eGFR slope and stale-data flags |
| **Model 1: risk** | 3-year DKD onset/progression risk, HbA1c forecast at 3 months, hypo/hyper risk from CGM, and the factors driving the risk |
| **Model 2: treatment advisor** | Eligibility rules (eGFR, UACR, potassium, current meds), simulates each eligible option on the twin, re-runs Model 1, ranks by risk reduction, e.g. *"Add SGLT2i: 39% → 21%"* |
| **Alert engine** | Severe hypo/hyper, low time in range, rising UACR, rapid eGFR decline, hyperkalaemia, stale data |
| **LLM assistant** | Doctor summary + "ask the twin" chat; patient explanations in English or Hindi. Uses Kimi (backup: Gemini) if keys are set, otherwise built-in templates |
| **App** | One Streamlit app with role-based login: doctor portal, patient app (Hindi/English), admin panel |

See [docs/architecture.md](docs/architecture.md) for the diagram.

## Run it locally (Windows)

One-time setup:

```bash
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
copy .env.example .env
```

> **Windows on ARM (e.g. Snapdragon laptops):** Streamlit (pyarrow) and XGBoost have no ARM
> wheels, so `.venv` uses the **x64 build of Python 3.11**, which runs under Windows emulation:
> `pip install uv`, then `uv venv --python cpython-3.11-windows-x86_64-none .venv`, then
> `uv pip install --python .venv\Scripts\python.exe -r requirements-dev.txt`.

Start the app (two PowerShell windows, both in this folder; note the `.\` at the start):

```bash
.\.venv\Scripts\python.exe -m uvicorn api.main:app --reload     # terminal 1: API on :8000
.\.venv\Scripts\python.exe -m streamlit run app/Home.py         # terminal 2: app on :8501
```

Open http://localhost:8501 and log in. The database (`data/twin.db`) creates and seeds itself on
first start. Reset it with `.\.venv\Scripts\python.exe scripts/seed_demo.py --reset`.

| Role | Username | Password |
|---|---|---|
| Doctor | `dr.mehta` | `doctor123` |
| Patient | `ramesh`, `sunita` (+ priya, mohan, arjun, lakshmi, imran, kavita, suresh, anita) | `patient123` |
| Admin | `admin` | `admin123` |

Tests: `.\.venv\Scripts\python.exe -m pytest -q`

## Clinical settings (no Python needed)

| File | What it holds |
|---|---|
| `config/clinical_rules.yaml` | targets, KDIGO cut-offs, drug eligibility, effect sizes, synthetic cohort (each with `source` + `verified`) |
| `config/alerts.yaml` | alert thresholds |
| `data/reference/indian_foods.csv` | foods, serving, carbs, GI category (verify vs IFCT 2017) |
| `data/reference/loinc_map.csv` | variable, LOINC code, unit (`verify` flag) |

Restart the API after editing them.

## Docker

```bash
docker compose up --build
```

API docs at http://localhost:8000/docs, app at http://localhost:8501.

## Data

Trained models are committed in `models/` (about 3 MB), so the app runs without any download.
To rebuild everything from the public data (about 2 minutes plus downloads):

```bash
.\.venv\Scripts\python.exe scripts/download_data.py              # NHANES, UCI CKD, CGMacros -> data/raw/
.\.venv\Scripts\python.exe -m src.pipeline.nhanes_merge          # -> data/processed/nhanes_diabetes.csv
.\.venv\Scripts\python.exe scripts/build_synthetic_cohort.py     # -> data/synthetic/ (cohort + demo CGM)
.\.venv\Scripts\python.exe scripts/train_models.py               # -> models/, docs/models/*.png
```

| Dataset | Use |
|---|---|
| NHANES 2017–Mar 2020 (CDC) | `dkd_current` model (real data); re-scales the synthetic cohort's risk weights |
| UCI Chronic Kidney Disease | ~400 Indian patients (Apollo Hospitals): sanity check of eGFR/KDIGO and risk direction |
| Synthetic Indian T2DM cohort | 2,000 patients x 5 years, from `config/clinical_rules.yaml -> cohort` (ICMR-INDIAB-informed) |
| CGMacros (PhysioNet) | glucose forecast (CGM + meals + Fitbit); synthetic CGM is used until it is downloaded |
| AI-READI | CGM + wearables + labs (access request at fairhub.io; not used yet) |

Models and honest limitations: [models/model_card.md](models/model_card.md).
Raw data is never pushed to GitHub (see `.gitignore`).

## Project structure

```
config/              settings.py (.env), clinical_rules.yaml, alerts.yaml   <- clinical numbers
data/reference/      loinc_map.csv, loinc_aliases.csv, drug_classes.csv, indian_foods.csv
data/fhir_samples/   FHIR R4 sample bundles made from Synthea patients
src/
  clinical/          eGFR (CKD-EPI 2021), KDIGO, CGM metrics, units, LOINC, drug classes
  db/                SQLModel tables, session, demo seed
  auth/              bcrypt passwords, JWT, role checks
  ingestion/         translator (living-twin loop), FHIR import/export, manual + lab CSV
  twin/              state.py (TwinState from the database), engine.py (runs the models)
  models/            dkd.py, t2dm.py (predict), features, calibration
  treatment/         eligibility, simulate, rank
  alerts/            alert engine with de-duplication
  pipeline/          NHANES merge, synthetic cohort, synthetic CGM, CGMacros reader
api/                 FastAPI: auth, patients, twin, treatments, alerts, ehr
app/                 Streamlit: Home.py (login) + pages per role
scripts/             download, cohort, training, FHIR samples, seed
tests/               pytest suite
docs/                architecture, model card, model plots
```

## How the twin updates (living-twin loop)

Every reading (EHR import, lab CSV, manual entry, sensor) goes through
`src/ingestion/translator.py`: map LOINC, convert units, skip duplicates, then
1. instant alerts on that reading (e.g. glucose < 54 = critical; repeats within 60 min are merged),
2. CGM readings -> glucose +30/+60 min forecast and predicted-hypo alert,
3. new labs -> full re-run: DKD 3-year risk, HbA1c in 3 months, kidney alerts.
DKD risk is never re-run on every CGM point; it also re-runs once a day (02:00).

## Live data, medicines and meals

- **Live sensor simulator** (`src/ingestion/simulator.py`): replays a patient's CGM + heart rate +
  steps as if arriving now; one 5-minute reading every `SIM_SPEED_SECONDS` (3 s = 100x real
  time). Ramesh's starts automatically (`SIM_AUTOSTART`). Demo scenarios: `meal_spike`, `hypo`
  (`POST /patients/{id}/devices/simulator/scenario`). Uses CGMacros when downloaded.
- **Libre:** upload a LibreView CSV export (sample: `data/fhir_samples/sample_libre.csv`).
  **Dexcom:** "coming soon" stub.
- **Home readings:** `POST /patients/{id}/vitals` (BP, weight, fingerstick glucose, sleep, steps).
- **Medicines and reminders:** doctor prescribes (`POST /patients/{id}/medications`) -> daily
  doses at the chosen times; patient taps Taken / Skip; pending > 2 h becomes missed;
  adherence % over 7 and 30 days feeds the twin. A prescription change re-runs kidney risk.
- **Indian meal log:** foods from `indian_foods.csv`, carbs summed; 2-hour glucose spike
  (peak of the next 24 CGM readings minus the reading before); "top 3 spiking foods".
  Logging a meal while the simulator runs adds a matching rise to the live sensor.

## Hospital EHR (FHIR R4)

- **Import a sample:** `POST /ehr/import/sample` with one of the files in `data/fhir_samples/`
  (real Synthea patients with type 2 diabetes, dates shifted to today; rebuild them with
  `scripts/make_fhir_samples.py`).
- **Fetch from a FHIR server:** `POST /ehr/fetch {"fhir_patient_id": "56196"}` pulls
  `Patient/56196/$everything` from `FHIR_BASE_URL` (default: the public HAPI R4 test server; its
  test data changes over time, so example ids may disappear).
- **Export:** `GET /patients/{id}/fhir` returns the twin's labs, vitals, diagnosis and medicines as
  a valid FHIR R4 Bundle (5-minute CGM and heart-rate streams stay in the twin).

API docs with every endpoint: http://localhost:8000/docs (click **Authorize**, log in as `dr.mehta`).

## Limitations

- Only `dkd_current` is trained on real patients (NHANES). The onset, progression and HbA1c
  models are trained on a **simulated** Indian cohort; see [models/model_card.md](models/model_card.md).
- Treatment effects (`config/clinical_rules.yaml -> effects`) are average trial hazard ratios
  (DAPA-CKD, CREDENCE, FLOW, FIDELIO-DKD, RENAAL) and are all `verified: false` until checked.
- DKD risk uses Platt calibration instead of isotonic (smoother with small calibration sets).
- The glucose forecast is trained on synthetic CGM until CGMacros is downloaded; hypo warnings
  rely on a rule-based safety net.
- Demo patients are fictional; Synthea FHIR samples are synthetic and time-shifted.
- Not a medical device. Not for clinical use.

## Team

- **Shiwangi Singh**: clinical logic, KDIGO staging, drug eligibility rules, data, pitch
- **Teammate**: DevOps, Docker, CI/CD, deployment

## License

MIT
