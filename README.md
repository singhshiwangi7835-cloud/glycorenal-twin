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
.venv\Scripts\python -m pip install -r requirements-dev.txt
copy .env.example .env
```

> **Windows on ARM (e.g. Snapdragon laptops):** Streamlit (pyarrow) and XGBoost have no ARM
> wheels, so `.venv` uses the **x64 build of Python 3.11**, which runs under Windows emulation:
> `pip install uv`, then `uv venv --python cpython-3.11-windows-x86_64-none .venv`, then
> `uv pip install --python .venv\Scripts\python.exe -r requirements-dev.txt`.

Start the app (two terminals, from this folder):

```bash
.venv\Scripts\python -m uvicorn api.main:app --reload     # terminal 1: API on :8000
.venv\Scripts\python -m streamlit run app/Home.py         # terminal 2: app on :8501
```

Open http://localhost:8501 and log in. The database (`data/twin.db`) creates and seeds itself on
first start. Reset it with `.venv\Scripts\python scripts/seed_demo.py --reset`.

| Role | Username | Password |
|---|---|---|
| Doctor | `dr.mehta` | `doctor123` |
| Patient | `ramesh`, `sunita` (+ priya, mohan, arjun, lakshmi, imran, kavita, suresh, anita) | `patient123` |
| Admin | `admin` | `admin123` |

Tests: `.venv\Scripts\python -m pytest -q`

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

The prototype runs on a **synthetic Indian T2DM cohort** (`src/pipeline/synthetic.py`) and five
demo patients, so no download is needed to try it. To use real public data:

```bash
python scripts/download_data.py          # NHANES 2017-2020, UCI CKD, CGMacros
python -m src.pipeline.nhanes_merge      # -> data/processed/nhanes_t2dm.csv
```

| Dataset | Use |
|---|---|
| NHANES 2017–Mar 2020 (CDC) | HbA1c, creatinine, UACR, BP, BMI, meds |
| UCI Chronic Kidney Disease | ~400 Indian patients (Apollo Hospitals, Tamil Nadu) |
| CGMacros (PhysioNet) | CGM + meals + Fitbit, incl. T2D participants |
| AI-READI | CGM + wearables + labs (access request at fairhub.io) |

Raw data is never pushed to GitHub (see `.gitignore`).

## Project structure

```
src/
  pipeline/          eGFR, KDIGO, CGM metrics, synthetic cohort, NHANES merge
  patient_state/     patient record builder
  model1_risk/       risk prediction
  model2_treatment/  eligibility, simulation, ranking
  alerts/            alert engine
  llm/               doctor + patient assistant
  twin.py            the living twin loop
api/                 FastAPI backend
dashboards/          Streamlit hospital + patient views
scripts/             data download, training
tests/               pytest suite
docs/                architecture
```

## Status and caveats

- Model 1 is trained on **synthetic data** with a known risk function. Calibrate against
  ICMR-INDIAB and validate on NHANES / UCI CKD before quoting performance.
- Treatment effect sizes in `src/model2_treatment/advisor.py` are approximate, summarised from
  DAPA-CKD, CREDENCE, FLOW, FIDELIO/FIGARO and RENAAL. They are being finalised in the
  clinical rules sheet.
- Not a medical device. Not for clinical use.

## Team

- **Shiwangi Singh**: clinical logic, KDIGO staging, drug eligibility rules, data, pitch
- **Teammate**: DevOps, Docker, CI/CD, deployment

## License

MIT
