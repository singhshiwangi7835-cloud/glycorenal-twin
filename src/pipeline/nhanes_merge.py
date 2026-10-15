"""Merge NHANES 2017-March 2020 pre-pandemic files into one adult-diabetes table.

Run `python scripts/download_data.py` first. Files expected in data/raw/nhanes/.
Output: data/processed/nhanes_t2dm.csv

Key variables:
  DIQ010  doctor told you have diabetes (1 = yes)     P_DIQ
  LBXGH   HbA1c (%)                                   P_GHB
  LBXSCR  serum creatinine (mg/dL)                    P_BIOPRO
  LBXSKSI potassium (mmol/L)                          P_BIOPRO
  URDACT  albumin/creatinine ratio (mg/g)             P_ALB_CR
  BPXOSY1-3 / BPXODI1-3 systolic / diastolic BP       P_BPXO
  BMXBMI, BMXWAIST                                    P_BMX
  RIDAGEYR, RIAGENDR (1 = male)                       P_DEMO
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.clinical.egfr import egfr_ckd_epi_2021
from src.clinical.kdigo import kdigo_stage

RAW = Path("data/raw/nhanes")
OUT = Path("data/processed/nhanes_t2dm.csv")


def _read(name: str, cols: list[str]) -> pd.DataFrame:
    df = pd.read_sas(RAW / f"{name}.xpt", format="xport")
    return df[["SEQN"] + [c for c in cols if c in df.columns]]


def build() -> pd.DataFrame:
    demo = _read("P_DEMO", ["RIDAGEYR", "RIAGENDR"])
    diq = _read("P_DIQ", ["DIQ010", "DID040"])
    ghb = _read("P_GHB", ["LBXGH"])
    bio = _read("P_BIOPRO", ["LBXSCR", "LBXSKSI"])
    alb = _read("P_ALB_CR", ["URDACT"])
    bp = _read("P_BPXO", ["BPXOSY1", "BPXOSY2", "BPXOSY3", "BPXODI1", "BPXODI2", "BPXODI3"])
    bmx = _read("P_BMX", ["BMXBMI", "BMXWAIST"])

    df = demo
    for part in (diq, ghb, bio, alb, bp, bmx):
        df = df.merge(part, on="SEQN", how="left")

    df["sbp"] = df[["BPXOSY1", "BPXOSY2", "BPXOSY3"]].mean(axis=1)
    df["dbp"] = df[["BPXODI1", "BPXODI2", "BPXODI3"]].mean(axis=1)
    df = df.rename(columns={
        "RIDAGEYR": "age", "LBXGH": "hba1c", "LBXSCR": "creatinine",
        "LBXSKSI": "potassium", "URDACT": "uacr", "BMXBMI": "bmi", "BMXWAIST": "waist",
    })
    df["sex"] = df["RIAGENDR"].map({1: "M", 2: "F"})
    df["dm_duration_yrs"] = (df["age"] - df["DID040"]).where(df["DID040"] < 120)

    # adults with diagnosed diabetes or HbA1c >= 6.5
    df = df[(df["age"] >= 18) & ((df["DIQ010"] == 1) | (df["hba1c"] >= 6.5))]
    df = df.dropna(subset=["creatinine", "uacr", "hba1c"])

    df["egfr"] = [egfr_ckd_epi_2021(c, a, s) for c, a, s in zip(df["creatinine"], df["age"], df["sex"])]
    stages = [kdigo_stage(e, u) for e, u in zip(df["egfr"], df["uacr"])]
    df["kdigo"] = [s["stage"] for s in stages]
    df["has_ckd"] = [int(s["has_ckd"]) for s in stages]

    keep = ["SEQN", "age", "sex", "dm_duration_yrs", "hba1c", "creatinine", "potassium",
            "uacr", "egfr", "kdigo", "has_ckd", "sbp", "dbp", "bmi", "waist"]
    return df[keep]


if __name__ == "__main__":
    OUT.parent.mkdir(parents=True, exist_ok=True)
    out = build()
    out.to_csv(OUT, index=False)
    print(f"Saved {len(out)} adults with diabetes to {OUT}")
    print(out["kdigo"].value_counts().head(10))
