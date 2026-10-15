"""Continuous glucose monitoring (CGM) metrics, per the international consensus on TIR.

- Time in range (TIR): 70-180 mg/dL, target > 70%
- Time below range (TBR): < 70 mg/dL, target < 4%
- Time above range (TAR): > 180 mg/dL, target < 25%
- GMI (%) = 3.31 + 0.02392 x mean glucose (mg/dL)
- CV (%) = SD / mean x 100, target <= 36%
"""

from __future__ import annotations

import statistics


def cgm_metrics(glucose_mg_dl: list[float]) -> dict:
    values = [float(v) for v in glucose_mg_dl if v is not None]
    if len(values) < 2:
        raise ValueError("need at least 2 CGM readings")

    n = len(values)
    mean = statistics.fmean(values)
    sd = statistics.stdev(values)
    return {
        "n_readings": n,
        "mean_glucose": round(mean, 1),
        "gmi_pct": round(3.31 + 0.02392 * mean, 2),
        "cv_pct": round(sd / mean * 100, 1),
        "tir_pct": round(sum(70 <= v <= 180 for v in values) / n * 100, 1),
        "tbr_pct": round(sum(v < 70 for v in values) / n * 100, 1),
        "tbr_severe_pct": round(sum(v < 54 for v in values) / n * 100, 1),
        "tar_pct": round(sum(v > 180 for v in values) / n * 100, 1),
        "tar_severe_pct": round(sum(v > 250 for v in values) / n * 100, 1),
        "min": round(min(values), 1),
        "max": round(max(values), 1),
    }
