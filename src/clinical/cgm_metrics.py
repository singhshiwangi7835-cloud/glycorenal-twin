"""Continuous glucose monitoring (CGM) metrics, per the international consensus on time in range.

- Time in range (TIR): 70-180 mg/dL, target > 70%
- Time below range (TBR): < 70 and < 54 mg/dL, target < 4% and < 1%
- Time above range (TAR): > 180 and > 250 mg/dL, target < 25% and < 5%
- GMI (%) = 3.31 + 0.02392 x mean glucose (mg/dL)
- CV (%) = SD / mean x 100, target <= 36%
- Data sufficiency (%) = readings received / readings expected over the window
Ranges come from config/clinical_rules.yaml -> cgm.
"""

from __future__ import annotations

import statistics

from src.clinical.rules import clinical_rules


def gmi(mean_glucose_mg_dl: float) -> float:
    return round(3.31 + 0.02392 * mean_glucose_mg_dl, 2)


def cgm_metrics(glucose_mg_dl: list[float], window_days: float | None = None) -> dict:
    """Metrics for a list of CGM readings (mg/dL).

    window_days: length of the period the readings cover; if given, data sufficiency is
    calculated against the expected number of 5-minute readings.
    """
    c = clinical_rules()["cgm"]
    values = [float(v) for v in glucose_mg_dl if v is not None]
    if len(values) < 2:
        raise ValueError("need at least 2 CGM readings")

    n = len(values)
    mean = statistics.fmean(values)
    sd = statistics.stdev(values)
    lo, hi, very_lo, very_hi = c["range_low"], c["range_high"], c["very_low"], c["very_high"]

    sufficiency = None
    if window_days:
        expected = window_days * 24 * 60 / c["reading_interval_min"]
        sufficiency = round(min(n / expected, 1.0) * 100, 1)

    return {
        "n_readings": n,
        "mean_glucose": round(mean, 1),
        "gmi_pct": gmi(mean),
        "cv_pct": round(sd / mean * 100, 1),
        "tir_pct": round(sum(lo <= v <= hi for v in values) / n * 100, 1),
        "tbr_pct": round(sum(v < lo for v in values) / n * 100, 1),
        "tbr_severe_pct": round(sum(v < very_lo for v in values) / n * 100, 1),
        "tar_pct": round(sum(v > hi for v in values) / n * 100, 1),
        "tar_severe_pct": round(sum(v > very_hi for v in values) / n * 100, 1),
        "min": round(min(values), 1),
        "max": round(max(values), 1),
        "sufficiency_pct": sufficiency,
        "sufficient": sufficiency is None or sufficiency >= c["min_sufficiency_pct"],
    }
