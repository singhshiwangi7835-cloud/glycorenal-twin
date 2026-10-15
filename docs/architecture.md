# GlycoRenal Twin: architecture

```mermaid
flowchart TD
    A[Wearables / CGM<br/>glucose, steps, sleep] --> D
    B[Hospital EHR<br/>FHIR: labs, meds, BP] --> D
    C[Public datasets<br/>NHANES, CGMacros, UCI CKD] --> D
    D[Data pipeline<br/>cleaning, eGFR, KDIGO, synthetic Indian cohort] --> E
    E[Patient state<br/>labs, vitals, meds, CGM, eGFR, KDIGO] --> CORE

    subgraph CORE[Digital twin core]
        M1[Model 1: Risk prediction<br/>DKD onset / progression,<br/>HbA1c forecast, hypo/hyper risk]
        M2[Model 2: Treatment advisor<br/>eligibility, simulate, re-run Model 1, rank]
        M1 <--> M2
    end

    CORE --> F[Alert engine<br/>hypo, hyper, rising UACR, falling eGFR]
    CORE --> G[LLM assistant<br/>doctor notes, patient tips]
    F --> H[Hospital dashboard<br/>risk, ranked treatments]
    G --> H
    F --> I[Patient app<br/>readings, lifestyle tips, Hindi/English]
    G --> I
```

## Code map

| Box in the diagram | Code |
|---|---|
| Data pipeline | `src/pipeline/` (`egfr.py`, `kdigo.py`, `cgm.py`, `synthetic.py`, `nhanes_merge.py`) |
| Patient state | `src/patient_state/builder.py` |
| Model 1 | `src/model1_risk/model.py` |
| Model 2 | `src/model2_treatment/advisor.py` |
| Alert engine | `src/alerts/engine.py` |
| LLM assistant | `src/llm/assistant.py` |
| Living twin loop | `src/twin.py` |
| API | `api/main.py` (FastAPI) |
| Dashboards | `dashboards/hospital.py`, `dashboards/patient.py` (Streamlit) |
| Deployment | `Dockerfile`, `docker-compose.yml`, `.github/workflows/ci.yml` |

## Living twin loop

Every new lab report, CGM upload or prescription change is sent to `POST /patients`.
The twin rebuilds the patient state, re-runs Model 1, re-runs Model 2 (which itself calls
Model 1 for every simulated option), refreshes alerts and regenerates both explanations.
