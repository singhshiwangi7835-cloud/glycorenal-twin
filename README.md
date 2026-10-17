# GlycoRenal Twin

A prototype digital twin for people with type 2 diabetes. It combines hospital records (FHIR R4),
wearable data (CGM, heart rate, steps, sleep) and what the patient logs (meals, medicines, BP) to:

- forecast glucose 30 and 60 minutes ahead, warn of a glucose spike up to 90 minutes ahead, and
  forecast HbA1c in 3 months;
- estimate the 3-year risk of diabetic kidney disease (DKD) starting or getting worse;
- test treatment options on the twin and rank them by how much they lower kidney risk.

It has separate logins for doctors, patients and admins, medicine reminders, an Indian meal log, an
assistant that explains results in English and Hindi, and PDF reports.

Made for the Digital Twin Challenge 2026 (Happiest Health Summit, Bengaluru).

![Architecture](docs/architecture.png)

## Features

| Area | Details |
|---|---|
| Twin state | Latest labs with dates and out-of-date flags; eGFR (CKD-EPI 2021, race-free); KDIGO G/A stage; eGFR slope; 14-day CGM metrics (TIR, TBR, TAR, GMI, CV, data coverage); BP target by albuminuria; 7- and 30-day adherence |
| Glucose (Track A) | Forecast at +30 / +60 min with a rule-based low-glucose check; spike warning (glucose above 250 within 90 min, using recent readings and the patient's usual pattern at that time of day); HbA1c in 3 months; post-meal rise per food and the patient's top 3 spiking foods |
| Kidney (Track B) | 3-year risk of DKD onset (kidneys normal now) or progression (DKD now), with the main factors; glucose control feeds the kidney model |
| EHR and genetics | Demographics, diagnoses, labs and medicines from FHIR. Simulated genetic results: a kidney polygenic score adjusts DKD risk; TCF7L2, CYP2C9 and SLC22A1 add cautions for sulfonylureas and metformin |
| Treatment options | Eligibility from KDIGO 2022 and ADA rules (eGFR, UACR, potassium, current drugs). Each option is applied to the twin and the risk recalculated, e.g. "Add SGLT2 inhibitor: DKD 3-yr risk 62% to 38% (DAPA-CKD)" |
| Live updates | Each new reading is saved and checked for alerts, then CGM metrics and short-term forecasts update. Kidney risk is recalculated on new labs, medicine changes and once a day |
| Hospital EHR link | Admin panel, EHR import tab: connect to a FHIR R4 server, search patients (optionally only those with type 2 diabetes), import them, and they stay linked; new labs and prescriptions are pulled again every hour (`EHR_SYNC_MINUTES`) or with "Sync now", without duplicates. Also bulk upload of FHIR files. A hospital server's access token goes in `FHIR_AUTH_TOKEN` |
| Data input | FHIR R4 import (Synthea samples, HAPI test server) and export; lab CSV; CGM simulator (synthetic or a real ShanghaiT2DM patient); Libre CSV; patient app entries. Dexcom is not connected yet |
| Alerts, reminders, meals | Low/high glucose, predicted low or spike, UACR rise, eGFR fall, potassium, BP, low adherence, sensor disconnected (each at most once an hour); daily doses with Taken/Skip, marked missed after 2 h; Indian food list with carbs and GI |
| Assistant | Kimi, then Gemini, then fixed templates; explains results but does not make predictions; patient safety rules in English and Hindi; uses 8 short guideline notes |
| Screens and reports | Doctor portal, patient app (English / Hindi), admin panel; doctor PDF and a one-page bilingual patient PDF |

## Personal twin

Besides the population models, each patient has a model fitted to their own data.

- Glucose (`src/twin/personal_glucose.py`): baseline, morning rise, meal responses and walking effect,
  fitted to the patient's CGM, meals and heart rate. For the demo patient it finds about +12.9 mg/dL per
  10 g of carbs, a peak 50 minutes after eating, and about 14 mg/dL lower after a 15-minute walk. It is
  checked by replaying the last 3 days, which are not used for fitting (error about 8 mg/dL). It can also
  answer "what if I eat this now" or "what if I walk afterwards".
- Kidney (`src/twin/personal_kidney.py`): the patient's own eGFR and UACR trend, starting from the
  population slope and updated with each lab result (Bayesian). It shows an 80% range, years until eGFR
  60/45/30, and the same trend with treatment.
- A new patient starts close to population values and the model becomes more individual as data comes
  in. A 0-100% score shows how much it has learned. It is refitted every night and on request.

Settings: `config/clinical_rules.yaml`, section `personal_twin`.

## Running it

### Docker

```bash
docker compose up --build
```

App: http://localhost:8501. API docs: http://localhost:8000/docs. The database is created and filled
with demo data on first start (about a minute). To use the assistant with an LLM, copy `.env.example`
to `.env` and add the keys first.

### Windows without Docker

One-time setup:

```bash
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
copy .env.example .env
```

On Windows on ARM (e.g. Snapdragon laptops), Streamlit (pyarrow) and XGBoost have no ARM builds, so use
the x64 build of Python 3.11: `python -m pip install uv`, then
`python -m uv python install cpython-3.11.17-windows-x86_64-none`,
`python -m uv venv --python cpython-3.11.17-windows-x86_64-none .venv`, and
`python -m uv pip install --python .venv\Scripts\python.exe -r requirements-dev.txt`.

Then, in two PowerShell windows opened in the project folder:

```bash
.\.venv\Scripts\python.exe -m uvicorn api.main:app --reload
.\.venv\Scripts\python.exe -m streamlit run app/Home.py
```

Open http://localhost:8501.

### Demo accounts

| Role | Username | Password |
|---|---|---|
| Doctor | `dr.mehta` | `doctor123` |
| Patient | `ramesh`, `sunita` (also priya, mohan, arjun, lakshmi, imran, kavita, suresh, anita) | `patient123` |
| Admin | `admin` | `admin123` |

### Demo

- Admin panel, Demo data tab, Start demo mode: resets the data and sets up the demo story.
- [docs/demo_script.md](docs/demo_script.md): the 15-18 minute walkthrough.
- `.\.venv\Scripts\python.exe scripts/dry_run_demo.py` runs the whole story through the API in about
  two minutes and reports each step.
- Example reports: [docs/samples/](docs/samples/).

### Deployment

Hugging Face Spaces (one Docker container), including where to put the API keys:
[docs/deploy.md](docs/deploy.md).

## Data sources

| Dataset | Used for | Licence |
|---|---|---|
| NHANES 2017-Mar 2020 (CDC), 1,455 adults with diabetes | `dkd_current` model; adjusting risk weights in the synthetic cohort | Public domain |
| UCI Chronic Kidney Disease (Apollo Hospitals, India), 400 patients | Checking the eGFR/KDIGO logic and risk direction on Indian data | CC BY 4.0 |
| ShanghaiT2DM (Zhao et al., Sci Data 2023; figshare 10.6084/m9.figshare.20444397) | Real CGM from 100 people with T2DM: training and testing the glucose and spike models, and the "Real patient CGM" replay. The original zip (3.4 MB) is in `data/raw/shanghai_t2dm/` | CC BY 4.0 |
| Synthetic Indian T2DM cohort, 2,000 patients, 5 years of quarterly visits | DKD onset/progression and HbA1c models; settings based on ICMR-INDIAB in `config/clinical_rules.yaml` | Generated |
| Synthea (MITRE) | FHIR R4 sample patients in `data/fhir_samples/` | Apache 2.0 |
| CGMacros (PhysioNet) | Optional: used by the simulator and glucose training if downloaded | ODC-BY |
| Indian foods | `data/reference/indian_foods.csv`, carbs and GI category (to be checked against IFCT 2017) | Project |

The trained models are in `models/` (about 3 MB), so nothing has to be downloaded to run the app. To
rebuild them: `scripts/download_data.py`, then `python -m src.pipeline.nhanes_merge`, then
`scripts/build_synthetic_cohort.py`, then `scripts/train_models.py`. Apart from the ShanghaiT2DM zip,
raw data is not stored in the repository.

## Models

| Model | Trained on | Result |
|---|---|---|
| `dkd_current`: DKD now, from non-kidney data | NHANES (real) | AUROC 0.72 (5-fold CV); Asian subgroup 0.68 |
| `dkd_onset`: DKD within 3 years | Synthetic cohort | AUROC 0.90, Brier 0.11 |
| `dkd_progression`: worse KDIGO stage or eGFR down 30% within 3 years | Synthetic cohort; UCI check | AUROC 0.87; on UCI data AUROC 0.93 for CKD, and KDIGO staging matches the hospital diagnosis in 94% |
| `hba1c_forecast`: HbA1c in 3 months | Synthetic cohort | MAE 0.26% when a drug is added (0.39% for "no change") |
| `glucose_forecast`: +30 / +60 min | Synthetic + real CGM (ShanghaiT2DM) | On held-out real patients: MAE 9.8 / 17.1 mg/dL (11.8 / 19.4 for "no change") |
| `glucose_spike_90m`: glucose above 250 within 90 min | Synthetic + real CGM (ShanghaiT2DM) | On held-out real patients: AUROC 0.93; 72% of spikes flagged at least 30 min ahead (median 55 min) |

Details, plots and limitations: [models/model_card.md](models/model_card.md) and `docs/models/`.

## Clinical settings

These files can be edited without touching Python. Restart the API afterwards.

| File | Contents |
|---|---|
| `config/clinical_rules.yaml` | Targets, KDIGO cut-offs, drug eligibility, trial effect sizes, risk bands, genetics, synthetic cohort settings; each block has a `source` and a `verified` flag |
| `config/alerts.yaml` | Alert thresholds, repeat window, spike warning settings |
| `data/reference/indian_foods.csv` | Foods (English and Hindi), serving size, carbs, GI category |
| `data/reference/loinc_map.csv`, `loinc_aliases.csv` | Variable names, LOINC codes, units |
| `data/reference/drug_classes.csv` | Drug name to class |
| `data/guidelines/*.md` | The 8 guideline notes the assistant refers to |

## Assistant

- Uses any OpenAI-compatible API. Kimi is tried first (`LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL` in
  `.env`), then Gemini (`LLM_FALLBACK_*`), then templates labelled "offline summary". Test the
  connection with `.\.venv\Scripts\python.exe scripts/test_llm.py`.
- Only the patient ID and clinical values are sent, never names. It is called only when someone presses
  a button or asks a question, and answers are cached for 30 minutes.
- Kimi K2.6 is a reasoning model, so each call allows up to 5,000 tokens and 40 s (`LLM_TIMEOUT_S`); an
  empty answer is retried once, and after 60 s the template is used. Chat answers take about 5-10 s,
  summaries 10-60 s.
- Patient safety rules: no advice to change medicines (English and Hindi keyword check, with template
  fallback); medicine questions get "please discuss this with your doctor"; low glucose gets a fixed
  15-15 rule message.

## Project layout

```
config/              settings.py (.env), clinical_rules.yaml, alerts.yaml
data/reference/      LOINC map and aliases, drug classes, Indian foods
data/guidelines/     guideline notes for the assistant
data/fhir_samples/   Synthea FHIR R4 bundles, sample Libre CSV
data/raw/            ShanghaiT2DM zip (other raw downloads are not committed)
src/clinical/        eGFR, KDIGO, CGM metrics, units, LOINC, drug classes, genetics
src/db/              tables, session, demo data
src/auth/            password hashing, JWT, role checks
src/ingestion/       translator, FHIR, simulator, Libre, Dexcom stub, manual entry
src/twin/            twin state, engine, personal twin
src/models/          DKD and glucose models, features, calibration
src/treatment/       eligibility, simulation, ranking
src/alerts/ src/reminders/ src/meals/   alerts, doses and adherence, meal spikes
src/llm/             assistant, client, prompts, safety rules, retrieval, templates
src/reports/         doctor and patient PDFs
src/pipeline/        NHANES merge, synthetic cohort, synthetic CGM, CGMacros and ShanghaiT2DM readers
api/                 FastAPI app and routers
app/                 Streamlit: Home.py (login), pages per role, i18n.py
scripts/             data download, training, seeding, dry run, LLM test, secret check, diagram
tests/               pytest (102 tests)
docs/                architecture, model card, demo script, deployment guide, samples
deploy/start.sh      container entry point (MODE=api | ui | all)
```

## Checks

```bash
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts/check_secrets.py
.\.venv\Scripts\python.exe scripts/dry_run_demo.py
```

GitHub Actions runs these on every push, then builds and tests the Docker image.

## Limitations

- Real patient data is used for `dkd_current` (NHANES, US) and the glucose models (ShanghaiT2DM, China).
  The DKD onset/progression and HbA1c models are trained on a synthetic Indian cohort because there is no
  open Indian longitudinal dataset; their high AUROC reflects the simulation, not validation on Indian
  patients.
- No real Indian CGM data yet. The ShanghaiT2DM readings are every 15 minutes and have no carb counts.
  Low-glucose warnings rely on a rule-based check as well as the model.
- Treatment effects are average hazard ratios from trials (DAPA-CKD, CREDENCE, FLOW, FIDELIO-DKD,
  RENAAL) and are marked `verified: false` until checked; effects in individual patients vary.
- Genetic results are simulated, and their effect sizes are starting values from the literature
  (`verified: false`).
- DKD risk uses Platt scaling rather than isotonic calibration, which behaved better with a small
  calibration set.
- Demo patients are fictional; Synthea samples are synthetic and shifted to the current date.
- In the Hindi view, alert messages and medicine names are still in English.
- On Windows on ARM laptops (x64 emulation) a page can take 10-25 s to load.

## Next steps

- Dexcom connection (sandbox OAuth) and other wearables (Fitbit, Withings)
- Validation on Indian hospital records via FHIR, and recalibration to Indian incidence (ICMR-INDIAB)
- CDSCO Software as a Medical Device pathway
- Hosting in India in line with the DPDP Act 2023 (consent, audit logs, PostgreSQL, encrypted tokens)
- WhatsApp/SMS reminders, Hindi alerts, AI-READI CGM and lab data

## Team

- Shiwangi Singh: clinical logic, KDIGO staging, drug eligibility rules, data, pitch
- Teammate: DevOps, Docker, CI/CD, deployment

## Licence

MIT (see [LICENSE](LICENSE)). Fonts: Noto Sans and Noto Sans Devanagari, SIL Open Font License
(`assets/fonts/OFL.txt`). Swagger UI (`api/static/swagger`): Apache 2.0.
