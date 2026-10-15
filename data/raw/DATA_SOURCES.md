# GlycoRenal Twin: raw data sources (downloaded 15 Oct 2026)

Do not push this folder to GitHub (keep `data/raw/` in .gitignore).

| Folder | Dataset | Source | Notes |
|---|---|---|---|
| nhanes/ | NHANES 2017-Mar 2020 pre-pandemic (P_ files) | https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/2017/DataFiles/ | Read with `pd.read_sas(path, format="xport")`. Join on `SEQN`. |
| uci_ckd/ | UCI Chronic Kidney Disease (400 patients, Apollo Hospitals) | https://archive.ics.uci.edu/dataset/336/chronic+kidney+disease | `uci_ckd.csv` = cleaned version of `chronic_kidney_disease_full.arff` (blank = missing). CC BY 4.0 |
| shanghai_t2dm/ | ShanghaiT1DM + ShanghaiT2DM | https://doi.org/10.6084/m9.figshare.20444397 | Use the `Shanghai_T2DM/` folder + `Shanghai_T2DM_Summary.xlsx` inside the zip. CC BY 4.0 |
| synthea/ | Synthea 1K synthetic patients, CSV (Apr 2020) | https://synthea.mitre.org/downloads | |
| cgmacros/ | CGMacros v1.0.0 (PhysioNet) | https://physionet.org/content/cgmacros/1.0.0/ | Zip: https://physionet.org/static/published-projects/cgmacros/cgmacros-1.0.0.zip |
| (pending) | AI-READI | https://fairhub.io/datasets/2 | Needs access request |

## NHANES files
| File | Contents |
|---|---|
| P_DEMO | Demographics: age, sex, ethnicity, survey weights |
| P_DIQ | Diabetes questionnaire: diagnosis, duration, insulin/pills |
| P_GHB | HbA1c |
| P_GLU | Fasting plasma glucose (fasting subsample) |
| P_BIOPRO | Biochemistry: serum creatinine, potassium, lipids etc. |
| P_ALB_CR | Urine albumin, creatinine, UACR |
| P_BPXO | Blood pressure (oscillometric; this cycle has no BPX) |
| P_BPQ | BP and cholesterol questionnaire: hypertension dx, meds |
| P_BMX | Body measures: weight, BMI, waist |
| P_RXQ_RX | Prescription medications |
| P_MCQ | Medical conditions (CVD, kidney etc.) |
| P_SMQ | Smoking |
