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
| **LLM assistant** | Doctor summary + "ask the twin" chat; patient explanations in English or Hindi. Uses Claude or Gemini if a key is set, otherwise built-in templates |
| **Dashboards** | Hospital view (patient list, risk, ranked options, alerts) and patient app (bilingual) |

See [docs/architecture.md](docs/architecture.md) for the diagram.

## Quick start with Docker (recommended)

1. Install and open **Docker Desktop** (wait for "Engine running").
2. In this folder run:

   ```bash
   docker compose up --build
   ```

3. Open:
   - Hospital dashboard: http://localhost:8501
   - Patient app: http://localhost:8502
   - API docs: http://localhost:8000/docs

Stop with `Ctrl+C`, or `docker compose down`.

**Optional LLM:** copy `.env.example` to `.env` and add `ANTHROPIC_API_KEY` or `GEMINI_API_KEY`.

## Run without Docker

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate     Mac/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
python scripts/train.py
uvicorn api.main:app --reload                     # terminal 1
streamlit run dashboards/hospital.py              # terminal 2
streamlit run dashboards/patient.py --server.port 8502   # terminal 3
pytest                                            # tests
```

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
