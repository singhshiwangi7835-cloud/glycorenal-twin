# GlycoRenal Twin

A proof-of-concept **digital twin** for people with **type 2 diabetes** that predicts short-term
glucose and 3-month HbA1c (**Track A**) and the risk of **diabetic kidney disease** onset and
progression over 3 years (**Track B**), then **simulates treatments on the twin** and ranks them by
predicted kidney-risk reduction. It joins **hospital EHR data (FHIR R4)**, **live wearable data**
(CGM, heart rate, steps) and the patient's own entries (meals, medicines, BP), with role-based
logins, medicine reminders, an Indian meal log, an AI assistant in English and Hindi, and PDF reports.

Built for the **Digital Twin Challenge 2026** (Happiest Health Summit, Bengaluru).

> **Decision support only.** Not a medical device and not for clinical use. The twin suggests and
> explains; the clinician decides. Patients only ever see lifestyle suggestions, never medicine changes.

![Architecture](docs/architecture.png)

## What it does

| | |
|---|---|
| **Twin state** | Latest labs with age and stale-data flags; eGFR by the race-free **CKD-EPI 2021** equation; **KDIGO** G/A stage and heat-map colour; eGFR slope; 14-day CGM metrics (TIR, TBR, TAR, GMI, CV, data sufficiency); BP target by albuminuria; 7/30-day medicine adherence |
| **Track A** | Glucose forecast +30 / +60 min with a rule-based hypo safety net; HbA1c in 3 months; 2-hour meal spikes and "top 3 spiking foods" |
| **Track B** | 3-year DKD **onset** (kidneys healthy now) or **progression** (DKD now) risk with the factors driving it; glycaemic features feed the kidney model |
| **Treatment advisor** | Eligibility from KDIGO 2022 / ADA 2026 rules (eGFR, UACR, potassium, current drugs), simulate each option on the twin (HbA1c, BP, weight change -> re-run the model -> trial hazard ratio), rank: *"Add SGLT2 inhibitor: DKD 3-yr risk 62% -> 38% (DAPA-CKD)"* |
| **Living twin** | Every reading: save -> instant alerts -> CGM metrics -> short-term forecast. Kidney risk re-runs on new labs, medicine changes and daily |
| **Data in** | FHIR R4 import (Synthea samples, public HAPI server) and export; lab CSV; live CGM simulator; Libre CSV upload; Dexcom (coming soon); patient app entries |
| **Alerts, reminders, meals** | Low/high glucose, predicted hypo, UACR rise, eGFR fall, potassium, BP, low adherence, sensor disconnected (no repeats within 60 min); daily doses with Taken/Skip, missed after 2 h; Indian food list with carbs and GI |
| **AI assistant** | Kimi (Moonshot) -> Gemini -> built-in templates; explains, never predicts; patient guardrails in English and Hindi; cites 8 guideline notes |
| **Screens and reports** | Doctor portal, patient app (English / हिंदी), admin panel; doctor PDF and one-page bilingual patient PDF |

## Quick start

### Option A: Docker (any computer)

```bash
docker compose up --build
```

App: http://localhost:8501 · API docs: http://localhost:8000/docs. The database creates and seeds
itself on first start (about a minute). Optional: copy `.env.example` to `.env` first and add LLM keys.

### Option B: Windows, no Docker (two PowerShell windows in this folder)

One-time setup:

```bash
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
copy .env.example .env
```

> **Windows on ARM** (e.g. Snapdragon laptops): Streamlit (pyarrow) and XGBoost have no ARM wheels,
> so use the **x64 build of Python 3.11** (runs under emulation): `python -m pip install uv`, then
> `python -m uv python install cpython-3.11.17-windows-x86_64-none`,
> `python -m uv venv --python cpython-3.11.17-windows-x86_64-none .venv`, then
> `python -m uv pip install --python .venv\Scripts\python.exe -r requirements-dev.txt`.

Start (note the `.\` at the start in PowerShell):

```bash
.\.venv\Scripts\python.exe -m uvicorn api.main:app --reload
.\.venv\Scripts\python.exe -m streamlit run app/Home.py
```

Open http://localhost:8501.

### Demo accounts

| Role | Username | Password |
|---|---|---|
| Doctor | `dr.mehta` | `doctor123` |
| Patient | `ramesh`, `sunita` (+ priya, mohan, arjun, lakshmi, imran, kavita, suresh, anita) | `patient123` |
| Admin | `admin` | `admin123` |

### Demo

- **One click:** Admin panel -> Demo data -> **Start demo mode** (resets the data and sets up the story).
- **Script:** [docs/demo_script.md](docs/demo_script.md), 15-18 minutes with what to click and say.
- **Rehearsal:** `.\.venv\Scripts\python.exe scripts/dry_run_demo.py` plays the whole story through
  the API in about 35 s (EHR import, live CGM, rice-meal spike, missed dose, new labs, ranked
  treatments, prescribing, predicted hypo, both PDFs).
- **Sample reports:** [docs/samples/](docs/samples/).

### Deploy (free)

Hugging Face Spaces (Docker, one container) step by step, including where to enter the API keys:
[docs/deploy.md](docs/deploy.md).

## Data sources

| Dataset | Use | Licence |
|---|---|---|
| NHANES 2017-Mar 2020 (CDC), 1,455 adults with diabetes | `dkd_current` model (real data); re-scales the synthetic cohort's risk weights | Public domain |
| UCI Chronic Kidney Disease (Apollo Hospitals, India), 400 patients | Sanity check of eGFR/KDIGO logic and risk direction on Indian data | CC BY 4.0 |
| Synthetic Indian T2DM cohort, 2,000 patients x 5 years quarterly | DKD onset/progression and HbA1c models; ICMR-INDIAB-informed settings in `config/clinical_rules.yaml` | generated |
| Synthea (MITRE) sample patients | FHIR R4 sample bundles in `data/fhir_samples/` | Apache 2.0 |
| CGMacros (PhysioNet) | Glucose forecast and simulator when downloaded (synthetic CGM until then) | ODC-BY |
| Indian foods | `data/reference/indian_foods.csv`, carbs and GI category (to verify vs IFCT 2017) | project |

Trained models are committed in `models/` (about 3 MB), so nothing needs downloading to run.
Rebuild from public data: `scripts/download_data.py` -> `python -m src.pipeline.nhanes_merge` ->
`scripts/build_synthetic_cohort.py` -> `scripts/train_models.py` (about 2 minutes plus downloads).
Raw data is never pushed to GitHub.

## Models (summary)

| Model | Trained on | Result |
|---|---|---|
| `dkd_current`: has DKD now, from non-kidney data | **Real:** NHANES | AUROC **0.72** (5-fold CV); Asian subgroup 0.68 |
| `dkd_onset`: DKD within 3 years | Synthetic cohort | AUROC 0.90, Brier 0.11 |
| `dkd_progression`: KDIGO stage worse or eGFR -30% in 3 years | Synthetic cohort; UCI check | AUROC 0.87; on UCI (Indian) risk separates CKD with AUROC 0.93; KDIGO rule agrees with the hospital diagnosis in **94%** |
| `hba1c_forecast`: HbA1c in 3 months | Synthetic cohort | MAE 0.26% when a drug is added (vs 0.39% "no change") |
| `glucose_forecast`: +30 / +60 min | Synthetic CGM | MAE 6 / 9 mg/dL (vs 13 / 21 "stays the same") |

Full details, plots and honest limitations: [models/model_card.md](models/model_card.md) and `docs/models/`.

## Clinical settings (no Python needed)

| File | What it holds |
|---|---|
| `config/clinical_rules.yaml` | Targets, KDIGO cut-offs, drug eligibility, trial effect sizes, risk bands, synthetic cohort; every block has `source` and `verified` |
| `config/alerts.yaml` | Alert thresholds and de-duplication window |
| `data/reference/indian_foods.csv` | Foods (English + Hindi), serving, carbs, GI category |
| `data/reference/loinc_map.csv`, `loinc_aliases.csv` | Variable <-> LOINC code <-> unit |
| `data/reference/drug_classes.csv` | Drug name -> class |
| `data/guidelines/*.md` | 8 short guideline notes the AI assistant cites |

Restart the API after editing them.

## AI assistant

- OpenAI-compatible client: **Kimi** first (`LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL` in `.env`),
  then **Gemini** (`LLM_FALLBACK_*`), then templates marked "offline summary". Check the connection with
  `.\.venv\Scripts\python.exe scripts/test_llm.py`.
- Sends only the patient id and numbers, never names; called only on a button press or question;
  answers cached 30 minutes; 20 s timeout.
- Guardrails: no medicine-change advice to patients (English + Hindi keyword check, template fallback);
  medicine questions -> "please discuss this with your doctor"; low glucose -> fixed 15-15 message;
  every answer ends with "Decision support only".

## Project structure

```
config/              settings.py (.env), clinical_rules.yaml, alerts.yaml
data/reference/      LOINC map + aliases, drug classes, Indian foods
data/guidelines/     guideline notes for the assistant
data/fhir_samples/   Synthea FHIR R4 bundles, sample Libre CSV
src/clinical/        eGFR, KDIGO, CGM metrics, units, LOINC, drug classes
src/db/              tables, session, demo seed
src/auth/            bcrypt passwords, JWT, role checks
src/ingestion/       translator, FHIR, simulator, Libre, Dexcom stub, manual entry
src/twin/            state builder, engine
src/models/          DKD and T2DM predictors, features, calibration
src/treatment/       eligibility, simulate, rank
src/alerts/ src/reminders/ src/meals/   alert engine, doses and adherence, meal spikes
src/llm/             assistant, client, prompts, guardrails, retrieval, templates
src/reports/         doctor and patient PDFs
src/pipeline/        NHANES merge, synthetic cohort, synthetic CGM, CGMacros reader
api/                 FastAPI app and routers
app/                 Streamlit: Home.py (login), pages per role, i18n.py
scripts/             data, training, seed, FHIR samples, dry run, LLM test, secret check, diagram
tests/               pytest (89 tests)
docs/                architecture, model card, demo script, deploy guide, samples
deploy/start.sh      container entry point (MODE=api | ui | all)
```

## Quality checks

```bash
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts/check_secrets.py
.\.venv\Scripts\python.exe scripts/dry_run_demo.py
```

GitHub Actions runs all three on every push, then builds the Docker image and smoke-tests it.

## Limitations

- Only `dkd_current` is trained on real patients; onset, progression and HbA1c models learn from a
  **simulated** Indian cohort (no open Indian longitudinal dataset exists). High AUROC there means the
  models learned the simulator's rules, not that they are validated on Indian patients.
- Treatment effects are average trial hazard ratios (DAPA-CKD, CREDENCE, FLOW, FIDELIO-DKD, RENAAL),
  all `verified: false` until checked; real effects vary by patient.
- DKD risk uses Platt calibration rather than isotonic (smoother with small calibration sets).
- Glucose forecast trained on synthetic CGM until CGMacros is added; hypo warnings rely on a
  rule-based safety net as well as the model.
- Demo patients are fictional; Synthea samples are synthetic and time-shifted to today.
- Hindi view: alert messages and medicine names still appear in English.
- Slow on Windows-on-ARM laptops (x64 emulation): a full page load can take 10-25 s.

## Next steps

Dexcom live OAuth (sandbox) · real-world validation on Indian hospital EHR data via FHIR ·
recalibration to Indian incidence (ICMR-INDIAB follow-up) · CDSCO Software-as-a-Medical-Device
pathway · DPDP Act 2023-compliant hosting in India (consent, audit logs, PostgreSQL, encrypted
tokens) · WhatsApp/SMS reminders · full Hindi alerts · AI-READI CGM + labs data.

## Team

- **Shiwangi Singh**: clinical logic, KDIGO staging, drug eligibility rules, data, pitch
- **Teammate**: DevOps, Docker, CI/CD, deployment

## Licence

MIT (see [LICENSE](LICENSE)). Fonts: Noto Sans / Noto Sans Devanagari, SIL Open Font License
(`assets/fonts/OFL.txt`). Swagger UI (`api/static/swagger`): Apache 2.0.
