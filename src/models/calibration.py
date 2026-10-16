"""Probability calibration for the DKD classifiers.

Platt scaling: a logistic regression on the logit of the raw XGBoost probability. We use it
instead of isotonic regression because, with a few hundred calibration patients, isotonic makes
wide flat steps: different patients (or a patient before and after a simulated treatment) then
get exactly the same risk, which hides real treatment effects. Platt scaling is smooth and
monotonic. Interface matches sklearn's IsotonicRegression: `.predict(raw_probabilities)`.
"""

from __future__ import annotations

import numpy as np
from sklearn.linear_model import LogisticRegression


def _logit(p) -> np.ndarray:
    p = np.clip(np.asarray(p, dtype=float), 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p)).reshape(-1, 1)


class PlattCalibrator:
    def fit(self, raw, y) -> "PlattCalibrator":
        self.lr = LogisticRegression(C=1e6, max_iter=1000).fit(_logit(raw), np.asarray(y))
        return self

    def predict(self, raw) -> np.ndarray:
        return self.lr.predict_proba(_logit(raw))[:, 1]
