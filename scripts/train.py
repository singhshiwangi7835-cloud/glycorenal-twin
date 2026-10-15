"""Train Model 1 and save it to models/model1.joblib.

Usage: python scripts/train.py [n_patients]
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.model1_risk.model import train  # noqa: E402
from src.pipeline.synthetic import generate_cohort  # noqa: E402

n = int(sys.argv[1]) if len(sys.argv) > 1 else 5000
cohort = generate_cohort(n)
Path("data/processed").mkdir(parents=True, exist_ok=True)
cohort.to_csv("data/processed/synthetic_cohort.csv", index=False)
bundle = train(cohort)
print(f"Model 1 = {bundle['dkd_model_name']}  {bundle['metrics']}")
