"""NHANES 2017-March 2020 pre-pandemic: adults with diabetes, with a "has DKD now" label.

Run `python scripts/download_data.py nhanes` first (files in data/raw/nhanes/).
Output: data/processed/nhanes_diabetes.csv  (one row per adult with diabetes)

Diabetes = told by a doctor (DIQ010 = 1) or HbA1c >= 6.5%.
DKD now  = eGFR (CKD-EPI 2021, our egfr.py) < 60 or UACR >= 30 mg/g. Single measurement, so this
           is "CKD in diabetes" by lab values, not a confirmed 3-month diagnosis.

Key variables:
  RIDAGEYR age, RIAGENDR sex (1 = male), RIDRETH3 ethnicity (6 = non-Hispanic Asian)   P_DEMO
  DIQ010 diabetes, DID040 age at diagnosis, DIQ050 insulin, DIQ070 pills             P_DIQ
  LBXGH HbA1c                                                                         P_GHB
  LBXGLU fasting glucose (fasting subsample only)                                     P_GLU
  LBXSCR creatinine, LBXSKSI potassium                                                P_BIOPRO
  URDACT urine albumin/creatinine ratio (mg/g)                                        P_ALB_CR
  BPXOSY1-3 / BPXODI1-3 BP (oscillometric)                                            P_BPXO
  BPQ020 told high BP, BPQ050A taking BP medicine                                     P_BPQ
  BMXBMI, BMXWAIST                                                                    P_BMX
  SMQ020 smoked 100 cigarettes, SMQ040 smokes now (1 every day, 2 some days)          P_SMQ
  RXDDRUG prescription drug names (classified by data/reference/drug_classes.csv)     P_RXQ_RX
Survey weights are not applied: this is a modelling dataset, not a prevalence estimate.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from src.clinical.drugs import class_flags
from src.clinical.egfr import egfr_ckd_epi_2021
from src.clinical.kdigo import kdigo_stage

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw" / "nhanes"
OUT = ROOT / "data" / "processed" / "nhanes_diabetes.csv"


def _read(name: str, cols: list[str]) -> pd.DataFrame:
    df = pd.read_sas(RAW / f"{name}.xpt", format="xport", encoding="latin1")
    return df[["SEQN"] + [c for c in cols if c in df.columns]]


def _drug_flags() -> pd.DataFrame:
    rx = _read("P_RXQ_RX", ["RXDDRUG"]).dropna()
    rx = rx[rx["RXDDRUG"].str.len() > 3]
    per_person = rx.groupby("SEQN")["RXDDRUG"].apply(list)
    flags = pd.DataFrame([class_flags(d) for d in per_person], index=per_person.index)
    return flags.reset_index()


def build() -> pd.DataFrame:
    df = _read("P_DEMO", ["RIDAGEYR", "RIAGENDR", "RIDRETH3"])
    parts = [
        _read("P_DIQ", ["DIQ010", "DID040", "DIQ050", "DIQ070"]),
        _read("P_GHB", ["LBXGH"]),
        _read("P_GLU", ["LBXGLU"]),
        _read("P_BIOPRO", ["LBXSCR", "LBXSKSI"]),
        _read("P_ALB_CR", ["URDACT"]),
        _read("P_BPXO", ["BPXOSY1", "BPXOSY2", "BPXOSY3", "BPXODI1", "BPXODI2", "BPXODI3"]),
        _read("P_BPQ", ["BPQ020", "BPQ050A"]),
        _read("P_BMX", ["BMXBMI", "BMXWAIST"]),
        _read("P_SMQ", ["SMQ020", "SMQ040"]),
        _drug_flags(),
    ]
    for part in parts:
        df = df.merge(part, on="SEQN", how="left")

    df = df.rename(columns={
        "RIDAGEYR": "age", "LBXGH": "hba1c", "LBXGLU": "fasting_glucose", "LBXSCR": "creatinine",
        "LBXSKSI": "potassium", "URDACT": "uacr", "BMXBMI": "bmi", "BMXWAIST": "waist",
    })
    df["sbp"] = df[["BPXOSY1", "BPXOSY2", "BPXOSY3"]].mean(axis=1)
    df["dbp"] = df[["BPXODI1", "BPXODI2", "BPXODI3"]].mean(axis=1)
    df["sex"] = df["RIAGENDR"].map({1: "M", 2: "F"})
    df["male"] = (df["sex"] == "M").astype(int)
    df["asian"] = (df["RIDRETH3"] == 6).astype(int)
    df["dm_duration_yrs"] = (df["age"] - df["DID040"]).where(df["DID040"] < 120).clip(lower=0)
    df["smoker"] = ((df["SMQ020"] == 1) & df["SMQ040"].isin([1, 2])).astype(int)
    df["hypertension"] = ((df["BPQ020"] == 1) | (df["BPQ050A"] == 1) | (df["sbp"] >= 140)).astype(int)

    flag_cols = [c for c in df.columns if c.startswith("on_")]
    df[flag_cols] = df[flag_cols].fillna(0).astype(int)
    df["on_insulin"] = ((df["on_insulin"] == 1) | (df["DIQ050"] == 1)).astype(int)

    # adults with diabetes, with the labs needed for the label
    df = df[(df["age"] >= 18) & ((df["DIQ010"] == 1) | (df["hba1c"] >= 6.5))]
    df = df.dropna(subset=["creatinine", "uacr", "hba1c", "sex"]).copy()

    df["egfr"] = [egfr_ckd_epi_2021(c, a, s) for c, a, s in zip(df["creatinine"], df["age"], df["sex"])]
    df["log_uacr"] = np.log(df["uacr"].clip(lower=1))
    stages = [kdigo_stage(e, u) for e, u in zip(df["egfr"], df["uacr"])]
    df["kdigo"] = [s["stage"] for s in stages]
    df["has_dkd"] = [int(s["has_ckd"]) for s in stages]

    keep = ["SEQN", "age", "sex", "male", "asian", "dm_duration_yrs", "hba1c", "fasting_glucose",
            "creatinine", "potassium", "uacr", "log_uacr", "egfr", "kdigo", "has_dkd", "sbp", "dbp",
            "bmi", "waist", "smoker", "hypertension"] + flag_cols
    return df[keep].reset_index(drop=True)


def main() -> pd.DataFrame:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    out = build()
    out.to_csv(OUT, index=False)
    print(f"Saved {len(out)} adults with diabetes to {OUT.relative_to(ROOT)}")
    print(f"  DKD now (eGFR < 60 or UACR >= 30): {out['has_dkd'].mean():.1%}")
    print(f"  non-Hispanic Asian: {out['asian'].sum()}")
    return out


if __name__ == "__main__":
    main()
