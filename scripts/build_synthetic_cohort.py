"""Build the synthetic data the twin needs (re-creatable; written to data/synthetic/, git-ignored).

1. Synthetic Indian T2DM cohort: 2,000 patients x 5 years of quarterly visits
   -> data/synthetic/cohort_visits.csv (+ calibration.json: NHANES re-scaling of weights)
2. 14 days of 5-minute CGM + heart rate + steps for every demo patient, so the live simulator
   works even without CGMacros -> data/synthetic/cgm/<patient_id>.csv and <patient_id>_meals.json

Usage:  python scripts/build_synthetic_cohort.py
Settings: config/clinical_rules.yaml -> cohort
"""

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.pipeline import cgm_synth, cohort  # noqa: E402

OUT = ROOT / "data" / "synthetic"

# glycaemic profile of each demo patient (matches the demo story; labs are seeded in step 3)
DEMO_GLYCAEMIA = {
    #            HbA1c  CV    steps/day
    "IND-0042": (8.4, 0.34, 3500),   # Ramesh: poor control, low activity
    "IND-0107": (7.9, 0.30, 4500),   # Sunita
    "IND-0215": (6.8, 0.24, 8200),   # Priya: well controlled
    "IND-0333": (8.9, 0.42, 2500),   # Mohan: very variable, on sulfonylurea
    "IND-0481": (9.6, 0.33, 3000),   # Arjun
    "IND-0512": (7.6, 0.28, 5000),
    "IND-0618": (8.1, 0.31, 4000),
    "IND-0724": (7.2, 0.27, 6500),
    "IND-0839": (8.0, 0.36, 3800),
    "IND-0950": (6.9, 0.25, 7500),
}


def main() -> None:
    t0 = time.time()
    visits, report = cohort.generate()
    cohort.save(visits, report, OUT)
    n = visits["patient_id"].nunique()
    print(f"Cohort: {n} patients, {len(visits)} visits -> data/synthetic/cohort_visits.csv")
    if report.get("used"):
        print(f"  eGFR-decline weights re-scaled to NHANES odds ratios (n={report['n']}): "
              f"{report['odds_ratio_per_sd']}")
    else:
        print(f"  NHANES re-scaling not used: {report.get('reason')}")

    cgm_dir = OUT / "cgm"
    cgm_dir.mkdir(parents=True, exist_ok=True)
    for i, (pid, (hba1c, cv, steps)) in enumerate(DEMO_GLYCAEMIA.items()):
        readings, meals = cgm_synth.generate(days=14, hba1c=hba1c, cv_target=cv,
                                             steps_per_day=steps, seed=100 + i)
        readings.to_csv(cgm_dir / f"{pid}.csv", index=False)
        meals_out = meals.assign(time=meals["time"].astype(str)).to_dict(orient="records")
        (cgm_dir / f"{pid}_meals.json").write_text(json.dumps(meals_out, indent=1))
    print(f"Demo CGM: {len(DEMO_GLYCAEMIA)} patients x 14 days -> data/synthetic/cgm/")
    print(f"Done in {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
